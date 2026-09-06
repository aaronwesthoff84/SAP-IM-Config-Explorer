"""Strict, local-only Graph JSON import and schema migration."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from sap_im_config_graph_explorer.models import (
    GRAPH_SCHEMA_VERSION,
    GraphDocument,
    GraphProvenance,
)
from sap_im_config_graph_explorer.portable_exports import (
    PortableGraphExportError,
    graph_document_from_payload,
    validate_graph_document,
)


MAX_GRAPH_JSON_BYTES = 25 * 1024 * 1024
MAX_GRAPH_JSON_NODES = 50_000
MAX_GRAPH_JSON_LINKS = 100_000
MAX_GRAPH_JSON_FINDINGS = 50_000

SUPPORTED_GRAPH_SCHEMA_VERSIONS = ("1.0", "1.1", "1.2", GRAPH_SCHEMA_VERSION)


class GraphDocumentImportError(ValueError):
    """Raised when a local Graph JSON file cannot be imported safely."""


def import_graph_document_bytes(content: bytes, filename: str) -> GraphDocument:
    """Parse, migrate, and validate one local Graph JSON file without mutating it."""

    safe_filename = validate_graph_json_filename(filename)
    if len(content) > MAX_GRAPH_JSON_BYTES:
        raise GraphDocumentImportError(
            f"Graph JSON file {safe_filename} exceeds the 25 MiB file-size limit."
        )

    payload = _strict_json_object(content, safe_filename)
    validate_graph_import_counts(payload, safe_filename)
    try:
        migrated = migrate_graph_payload(payload)
        document = graph_document_from_payload(migrated)
        document.provenance = GraphProvenance(
            origin="imported", fileName=safe_filename
        )
        validate_graph_document(document)
    except (PortableGraphExportError, ValueError) as exc:
        raise GraphDocumentImportError(
            f"Invalid Graph JSON file {safe_filename}: {exc}"
        ) from exc
    return document


def migrate_graph_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a migrated copy of a supported repository Graph JSON schema.

    Migrations only add fields introduced by repository schemas 1.1, 1.2, and
    1.3. Node, link, finding, and snapshot identity values are never changed.
    """

    if not isinstance(payload, Mapping):
        raise PortableGraphExportError("Graph import payload must be an object.")
    version = payload.get("schemaVersion")
    if not isinstance(version, str):
        raise PortableGraphExportError("schemaVersion must be a string.")
    if version not in SUPPORTED_GRAPH_SCHEMA_VERSIONS:
        label = "future graph schema version" if _is_future_version(version) else "graph schema version"
        raise PortableGraphExportError(f"Unsupported {label}: {version}")

    try:
        migrated = copy.deepcopy(dict(payload))
    except RecursionError as exc:
        raise PortableGraphExportError("Graph import payload is too deeply nested.") from exc

    _validate_historical_shape(migrated, version)
    if version == "1.0":
        snapshots = migrated.get("snapshots")
        if isinstance(snapshots, list):
            for snapshot in snapshots:
                if isinstance(snapshot, dict):
                    snapshot["sourceProfiles"] = []
        migrated["schemaVersion"] = "1.1"
        version = "1.1"
    if version == "1.1":
        migrated["topologyMode"] = "core"
        migrated["schemaVersion"] = "1.2"
        version = "1.2"
    if version == "1.2":
        migrated["provenance"] = {"origin": "xml", "fileName": None}
        migrated["schemaVersion"] = GRAPH_SCHEMA_VERSION
    return migrated


def validate_graph_import_counts(
    payload: Mapping[str, Any], filename: str
) -> None:
    """Reject declared graph collections above the named import limits."""

    for field, limit, label in (
        ("nodes", MAX_GRAPH_JSON_NODES, "node"),
        ("links", MAX_GRAPH_JSON_LINKS, "link"),
        ("findings", MAX_GRAPH_JSON_FINDINGS, "finding"),
    ):
        values = payload.get(field)
        if isinstance(values, list) and len(values) > limit:
            raise GraphDocumentImportError(
                f"Graph JSON file {filename} exceeds the {limit:,} {label} limit."
            )


def validate_graph_json_filename(filename: str) -> str:
    """Return a bounded local basename or reject a non-JSON upload name."""

    normalized = str(filename or "upload.json").replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    safe_filename = "".join(
        character if 32 <= ord(character) < 127 else "_"
        for character in basename
    )[:255] or "upload.json"
    if not safe_filename.lower().endswith(".json"):
        raise GraphDocumentImportError(
            f"Unsupported Graph JSON file: {safe_filename}. Only .json files are supported."
        )
    return safe_filename


def _strict_json_object(content: bytes, filename: str) -> dict[str, Any]:
    try:
        text = content.decode("utf-8-sig")
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonstandard_number,
        )
    except (RecursionError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise GraphDocumentImportError(
            f"Malformed Graph JSON file {filename}."
        ) from exc
    if not isinstance(payload, dict):
        raise GraphDocumentImportError(
            f"Graph JSON file {filename} must contain a JSON object."
        )
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object field: {key}")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> None:
    raise ValueError(f"Non-standard JSON number: {value}")


def _validate_historical_shape(payload: dict[str, Any], version: str) -> None:
    allowed = {
        "schemaVersion",
        "snapshots",
        "nodes",
        "links",
        "findings",
        "migrationRisk",
    }
    if version in {"1.2", GRAPH_SCHEMA_VERSION}:
        allowed.add("topologyMode")
    if version == GRAPH_SCHEMA_VERSION:
        allowed.add("provenance")
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        raise PortableGraphExportError(
            f"Graph import payload contains unsupported field: {unexpected[0]}."
        )

    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        return
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        if version == "1.0" and "sourceProfiles" in snapshot:
            raise PortableGraphExportError(
                "schemaVersion 1.0 snapshot contains unsupported field: sourceProfiles."
            )


def _is_future_version(version: str) -> bool:
    try:
        requested = tuple(int(part) for part in version.split("."))
        current = tuple(int(part) for part in GRAPH_SCHEMA_VERSION.split("."))
    except ValueError:
        return False
    return requested > current
