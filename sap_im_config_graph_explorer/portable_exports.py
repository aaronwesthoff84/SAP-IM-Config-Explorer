"""Deterministic, local-only portable serializers for ``GraphDocument`` values."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import (
    CONFIDENCE_LEVELS,
    FINDING_SEVERITIES,
    GRAPH_SCHEMA_VERSION,
    GRAPH_TOPOLOGIES,
    NODE_TYPES,
    RELATIONSHIP_TYPES,
    SNAPSHOT_ROLES,
    TOPOLOGY_MODES,
    GraphDocument,
    GraphLink,
    GraphNode,
    MigrationRiskFactor,
    MigrationRiskReport,
    Snapshot,
    SourceProfile,
    ValidationFinding,
)


CSV_NODE_COLUMNS = (
    "id",
    "canonicalKey",
    "snapshotId",
    "type",
    "label",
    "sourceFile",
    "xmlPath",
    "metadataJson",
)
CSV_LINK_COLUMNS = (
    "id",
    "source",
    "target",
    "relationship",
    "confidence",
    "metadataJson",
)
CSV_FINDING_COLUMNS = (
    "id",
    "code",
    "severity",
    "snapshotId",
    "nodeIds",
    "message",
    "detailsJson",
)

CSV_BUNDLE_FILENAME = "sap-im-config-graph-csv.zip"
MARKDOWN_FILENAME = "sap-im-config-graph.md"
GRAPHML_FILENAME = "sap-im-config-graph.graphml"

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_GRAPHML_NAMESPACE = "http://graphml.graphdrawing.org/xmlns"
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


class PortableGraphExportError(ValueError):
    """Raised when an API payload is not a complete, valid graph document."""


def graph_document_from_payload(payload: Mapping[str, Any]) -> GraphDocument:
    """Deserialize the browser's complete graph payload into the graph contract.

    The application only posts its current in-memory graph to portable export routes.
    Reconstructing the model here prevents a caller from serializing unknown graph
    types, malformed findings, or arbitrary payload fields as portable exports.
    """

    data = _mapping(payload, "Graph export payload")
    snapshots = [_snapshot_from_payload(item) for item in _list(data, "snapshots")]
    nodes = [_node_from_payload(item) for item in _list(data, "nodes")]
    links = [_link_from_payload(item) for item in _list(data, "links")]
    findings = [_finding_from_payload(item) for item in _list(data, "findings")]
    migration_risk = _migration_risk_from_payload(data.get("migrationRisk"))

    try:
        document = GraphDocument(
            schemaVersion=_string(data, "schemaVersion"),
            topologyMode=_string(data, "topologyMode"),
            snapshots=snapshots,
            nodes=nodes,
            links=links,
            findings=findings,
            migrationRisk=migration_risk,
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc

    validate_graph_document(document)
    return document


def validate_graph_document(document: GraphDocument) -> None:
    """Validate the mutable dataclass contract before a portable serialization."""

    if not isinstance(document, GraphDocument):
        raise PortableGraphExportError("Portable exports require a GraphDocument.")
    if document.schemaVersion != GRAPH_SCHEMA_VERSION:
        raise PortableGraphExportError(
            f"Unsupported graph schema version: {document.schemaVersion}"
        )
    if document.topologyMode not in TOPOLOGY_MODES:
        raise PortableGraphExportError(
            f"Unsupported topology mode: {document.topologyMode}"
        )
    topology = GRAPH_TOPOLOGIES[document.topologyMode]

    snapshot_ids: set[str] = set()
    for snapshot in document.snapshots:
        if snapshot.id in snapshot_ids:
            raise PortableGraphExportError(f"Duplicate snapshot ID: {snapshot.id}")
        snapshot_ids.add(snapshot.id)
        if snapshot.role not in SNAPSHOT_ROLES:
            raise PortableGraphExportError(
                f"Unsupported snapshot role: {snapshot.role}"
            )
        _json_value(snapshot.to_dict(), "snapshot")

    node_ids: set[str] = set()
    node_snapshot_ids: dict[str, str] = {}
    for node in document.nodes:
        if node.type not in NODE_TYPES:
            raise PortableGraphExportError(f"Unsupported graph node type: {node.type}")
        if node.type not in topology.node_types:
            raise PortableGraphExportError(
                f"Node type {node.type} is not allowed in {document.topologyMode} topology."
            )
        if node.id in node_ids:
            raise PortableGraphExportError(f"Duplicate graph node ID: {node.id}")
        node_ids.add(node.id)
        node_snapshot_ids[node.id] = node.snapshotId
        if node.snapshotId not in snapshot_ids:
            raise PortableGraphExportError(
                f"Graph node {node.id} references unknown snapshot: {node.snapshotId}"
            )
        _json_value(node.metadata, f"node metadata for {node.id}")

    link_ids: set[str] = set()
    for link in document.links:
        if link.relationship not in RELATIONSHIP_TYPES:
            raise PortableGraphExportError(
                f"Unsupported graph relationship: {link.relationship}"
            )
        if link.relationship not in topology.relationship_types:
            raise PortableGraphExportError(
                f"Relationship {link.relationship} is not allowed in "
                f"{document.topologyMode} topology."
            )
        if link.confidence not in CONFIDENCE_LEVELS:
            raise PortableGraphExportError(
                f"Unsupported confidence level: {link.confidence}"
            )
        if link.id in link_ids:
            raise PortableGraphExportError(f"Duplicate graph link ID: {link.id}")
        link_ids.add(link.id)
        if link.source not in node_ids or link.target not in node_ids:
            raise PortableGraphExportError(
                f"Graph link {link.id} must reference existing node IDs."
            )
        if node_snapshot_ids[link.source] != node_snapshot_ids[link.target]:
            raise PortableGraphExportError(
                f"Graph link {link.id} crosses snapshot boundaries."
            )
        _json_value(link.metadata, f"link metadata for {link.id}")

    finding_ids: set[str] = set()
    for finding in document.findings:
        if finding.severity not in FINDING_SEVERITIES:
            raise PortableGraphExportError(
                f"Unsupported finding severity: {finding.severity}"
            )
        if finding.id in finding_ids:
            raise PortableGraphExportError(
                f"Duplicate validation finding ID: {finding.id}"
            )
        finding_ids.add(finding.id)
        if finding.snapshotId not in snapshot_ids:
            raise PortableGraphExportError(
                f"Validation finding {finding.id} references unknown snapshot: "
                f"{finding.snapshotId}"
            )
        for node_id in finding.nodeIds:
            if node_id not in node_ids:
                raise PortableGraphExportError(
                    f"Validation finding {finding.id} references unknown node IDs."
                )
            if node_snapshot_ids[node_id] != finding.snapshotId:
                raise PortableGraphExportError(
                    f"Validation finding {finding.id} crosses snapshot boundaries."
                )
        _json_value(finding.details, f"finding details for {finding.id}")
    if document.migrationRisk is not None:
        _json_value(document.migrationRisk.to_dict(), "migration risk report")


def serialize_csv_bundle(document: GraphDocument) -> bytes:
    """Return a byte-stable CSV ZIP bundle without raw XML content."""

    validate_graph_document(document)
    members = (
        ("nodes.csv", _nodes_csv(document)),
        ("links.csv", _links_csv(document)),
        ("findings.csv", _findings_csv(document)),
        ("manifest.json", _pretty_json(_manifest(document))),
    )
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, content in members:
            entry = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content.encode("utf-8"), compresslevel=9)
    return output.getvalue()


def serialize_markdown(document: GraphDocument) -> bytes:
    """Return a readable, stable Markdown report without raw XML content."""

    validate_graph_document(document)
    lines = [
        "# SAP IM Config Explorer Graph Export",
        "",
        "## Schema and topology",
        "",
        *_markdown_table(
            ("Field", "Value"),
            (
                ("Schema version", document.schemaVersion),
                ("Topology mode", document.topologyMode),
            ),
        ),
        "",
        "## Provenance",
        "",
        "Portable exports contain only the current in-memory graph. JSON remains the lossless local graph export.",
        "",
        *_markdown_migration_risk(document),
        "",
        "## Snapshots",
        "",
        *_markdown_table(
            ("ID", "Role", "Source files", "Source profiles"),
            (
                (
                    snapshot.id,
                    snapshot.role,
                    ", ".join(sorted(snapshot.sourceFiles)),
                    _canonical_json(_source_profiles(snapshot)),
                )
                for snapshot in _sorted_snapshots(document)
            ),
        ),
        "",
        "## Counts",
        "",
        *_markdown_table(
            ("Object", "Count"),
            (
                ("Nodes", str(len(document.nodes))),
                ("Links", str(len(document.links))),
                ("Findings", str(len(document.findings))),
            ),
        ),
        "",
        "## Nodes",
        "",
        *_markdown_table(
            ("ID", "Canonical key", "Snapshot", "Type", "Label", "Source file", "XML path", "Metadata JSON"),
            (
                (
                    node.id,
                    node.canonicalKey,
                    node.snapshotId,
                    node.type,
                    node.label,
                    node.sourceFile,
                    node.xmlPath,
                    _canonical_json(node.metadata),
                )
                for node in _sorted_nodes(document)
            ),
        ),
        "",
        "## Links",
        "",
        *_markdown_table(
            ("ID", "Source", "Target", "Relationship", "Confidence", "Metadata JSON"),
            (
                (
                    link.id,
                    link.source,
                    link.target,
                    link.relationship,
                    link.confidence,
                    _canonical_json(link.metadata),
                )
                for link in _sorted_links(document)
            ),
        ),
        "",
        "## Findings",
        "",
        *_markdown_table(
            ("ID", "Code", "Severity", "Snapshot", "Node IDs", "Message", "Details JSON"),
            (
                (
                    finding.id,
                    finding.code,
                    finding.severity,
                    finding.snapshotId,
                    _canonical_json(list(finding.nodeIds)),
                    finding.message,
                    _canonical_json(finding.details),
                )
                for finding in _sorted_findings(document)
            ),
        ),
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def serialize_graphml(document: GraphDocument) -> bytes:
    """Return a deterministic GraphML document without raw XML content."""

    validate_graph_document(document)
    ET.register_namespace("", _GRAPHML_NAMESPACE)
    qualified = lambda name: f"{{{_GRAPHML_NAMESPACE}}}{name}"
    root = ET.Element(qualified("graphml"))
    for key_id, scope, name in (
        ("graphSchemaVersion", "graph", "schemaVersion"),
        ("graphTopologyMode", "graph", "topologyMode"),
        ("graphSnapshotsJson", "graph", "snapshotsJson"),
        ("graphFindingsJson", "graph", "findingsJson"),
        ("graphProvenanceJson", "graph", "provenanceJson"),
        ("nodeId", "node", "id"),
        ("nodeCanonicalKey", "node", "canonicalKey"),
        ("nodeSnapshotId", "node", "snapshotId"),
        ("nodeType", "node", "type"),
        ("nodeLabel", "node", "label"),
        ("nodeSourceFile", "node", "sourceFile"),
        ("nodeXmlPath", "node", "xmlPath"),
        ("nodeMetadataJson", "node", "metadataJson"),
        ("edgeId", "edge", "id"),
        ("edgeSource", "edge", "source"),
        ("edgeTarget", "edge", "target"),
        ("edgeRelationship", "edge", "relationship"),
        ("edgeConfidence", "edge", "confidence"),
        ("edgeMetadataJson", "edge", "metadataJson"),
    ):
        ET.SubElement(
            root,
            qualified("key"),
            {"id": key_id, "for": scope, "attr.name": name, "attr.type": "string"},
        )

    graph = ET.SubElement(
        root,
        qualified("graph"),
        {"id": "sap-im-config-graph", "edgedefault": "directed"},
    )
    _graphml_data(graph, qualified, "graphSchemaVersion", document.schemaVersion)
    _graphml_data(graph, qualified, "graphTopologyMode", document.topologyMode)
    _graphml_data(graph, qualified, "graphSnapshotsJson", _canonical_json(_snapshots_payload(document)))
    _graphml_data(graph, qualified, "graphFindingsJson", _canonical_json(_findings_payload(document)))
    _graphml_data(graph, qualified, "graphProvenanceJson", _canonical_json(_provenance(document)))

    for node in _sorted_nodes(document):
        element = ET.SubElement(graph, qualified("node"), {"id": node.id})
        for key, value in (
            ("nodeId", node.id),
            ("nodeCanonicalKey", node.canonicalKey),
            ("nodeSnapshotId", node.snapshotId),
            ("nodeType", node.type),
            ("nodeLabel", node.label),
            ("nodeSourceFile", node.sourceFile),
            ("nodeXmlPath", node.xmlPath),
            ("nodeMetadataJson", _canonical_json(node.metadata)),
        ):
            _graphml_data(element, qualified, key, value)

    for link in _sorted_links(document):
        element = ET.SubElement(
            graph,
            qualified("edge"),
            {"id": link.id, "source": link.source, "target": link.target},
        )
        for key, value in (
            ("edgeId", link.id),
            ("edgeSource", link.source),
            ("edgeTarget", link.target),
            ("edgeRelationship", link.relationship),
            ("edgeConfidence", link.confidence),
            ("edgeMetadataJson", _canonical_json(link.metadata)),
        ):
            _graphml_data(element, qualified, key, value)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def _nodes_csv(document: GraphDocument) -> str:
    return _csv_text(
        CSV_NODE_COLUMNS,
        (
            (
                node.id,
                node.canonicalKey,
                node.snapshotId,
                node.type,
                node.label,
                node.sourceFile,
                node.xmlPath,
                _canonical_json(node.metadata),
            )
            for node in _sorted_nodes(document)
        ),
    )


def _links_csv(document: GraphDocument) -> str:
    return _csv_text(
        CSV_LINK_COLUMNS,
        (
            (
                link.id,
                link.source,
                link.target,
                link.relationship,
                link.confidence,
                _canonical_json(link.metadata),
            )
            for link in _sorted_links(document)
        ),
    )


def _findings_csv(document: GraphDocument) -> str:
    return _csv_text(
        CSV_FINDING_COLUMNS,
        (
            (
                finding.id,
                finding.code,
                finding.severity,
                finding.snapshotId,
                _canonical_json(list(finding.nodeIds)),
                finding.message,
                _canonical_json(finding.details),
            )
            for finding in _sorted_findings(document)
        ),
    )


def _manifest(document: GraphDocument) -> dict[str, Any]:
    return {
        "format": "sap-im-config-graph-csv",
        "schemaVersion": document.schemaVersion,
        "topologyMode": document.topologyMode,
        "counts": {
            "nodes": len(document.nodes),
            "links": len(document.links),
            "findings": len(document.findings),
        },
        "snapshots": _snapshots_payload(document),
        "provenance": _provenance(document),
    }


def _snapshots_payload(document: GraphDocument) -> list[dict[str, Any]]:
    return [
        {
            "id": snapshot.id,
            "role": snapshot.role,
            "sourceFiles": sorted(snapshot.sourceFiles),
            "sourceProfiles": _source_profiles(snapshot),
        }
        for snapshot in _sorted_snapshots(document)
    ]


def _source_profiles(snapshot: Snapshot) -> list[dict[str, Any]]:
    return [
        profile.to_dict()
        for profile in sorted(
            snapshot.sourceProfiles,
            key=lambda profile: (
                profile.sourceFile,
                profile.encoding,
                profile.namespaceUri or "",
                profile.exportVersion or "",
            ),
        )
    ]


def _findings_payload(document: GraphDocument) -> list[dict[str, Any]]:
    return [finding.to_dict() for finding in _sorted_findings(document)]


def _provenance(document: GraphDocument) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "sourceProfiles": [
            {"snapshotId": snapshot.id, "profiles": _source_profiles(snapshot)}
            for snapshot in _sorted_snapshots(document)
        ]
    }
    if document.migrationRisk is not None:
        provenance["migrationRisk"] = {
            "score": document.migrationRisk.score,
            "factors": [
                factor.to_dict() for factor in _sorted_migration_risk_factors(document)
            ],
        }
    return provenance


def _markdown_migration_risk(document: GraphDocument) -> list[str]:
    lines = ["### Migration risk", ""]
    if document.migrationRisk is None:
        return [*lines, "No migration-risk report is available."]
    lines.extend(
        _markdown_table(
            ("Score", "Factor count"),
            (
                (
                    str(document.migrationRisk.score),
                    str(len(document.migrationRisk.factors)),
                ),
            ),
        )
    )
    lines.extend(
        [
            "",
            "#### Migration-risk factors",
            "",
            *_markdown_table(
                ("Code", "Severity", "Weight", "Node IDs", "Message"),
                (
                    (
                        factor.code,
                        factor.severity,
                        str(factor.weight),
                        _canonical_json(list(factor.nodeIds)),
                        factor.message,
                    )
                    for factor in _sorted_migration_risk_factors(document)
                ),
            ),
        ]
    )
    return lines


def _sorted_migration_risk_factors(
    document: GraphDocument,
) -> list[MigrationRiskFactor]:
    if document.migrationRisk is None:
        return []
    return sorted(
        document.migrationRisk.factors,
        key=lambda factor: (
            factor.severity,
            factor.code,
            factor.message,
            factor.weight,
            factor.nodeIds,
        ),
    )


def _sorted_nodes(document: GraphDocument) -> list[GraphNode]:
    return sorted(
        document.nodes,
        key=lambda node: (node.snapshotId, node.type, node.canonicalKey, node.id),
    )


def _sorted_links(document: GraphDocument) -> list[GraphLink]:
    return sorted(
        document.links,
        key=lambda link: (link.source, link.target, link.relationship, link.id),
    )


def _sorted_findings(document: GraphDocument) -> list[ValidationFinding]:
    return sorted(
        document.findings,
        key=lambda finding: (
            finding.snapshotId,
            finding.severity,
            finding.code,
            finding.id,
        ),
    )


def _sorted_snapshots(document: GraphDocument) -> list[Snapshot]:
    return sorted(document.snapshots, key=lambda snapshot: (snapshot.id, snapshot.role))


def _csv_text(columns: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_safe_csv_cell(column) for column in columns)
    for row in rows:
        writer.writerow(_safe_csv_cell(value) for value in row)
    return output.getvalue()


def _safe_csv_cell(value: object) -> str:
    text = str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _markdown_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    escaped_headers = [_escape_markdown_cell(value) for value in headers]
    lines = [
        f"| {' | '.join(escaped_headers)} |",
        f"| {' | '.join('---' for _ in headers)} |",
    ]
    lines.extend(
        f"| {' | '.join(_escape_markdown_cell(value) for value in row)} |"
        for row in rows
    )
    return lines


def _escape_markdown_cell(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )


def _graphml_data(element: ET.Element, qualified: Any, key: str, value: str) -> None:
    child = ET.SubElement(element, qualified("data"), {"key": key})
    child.text = value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PortableGraphExportError(f"Value is not portable JSON: {exc}") from exc


def _pretty_json(value: object) -> str:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise PortableGraphExportError(f"Value is not portable JSON: {exc}") from exc


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PortableGraphExportError(f"{name} must be an object.")
    return value


def _list(data: Mapping[str, Any], name: str) -> list[Any]:
    value = data.get(name)
    if not isinstance(value, list):
        raise PortableGraphExportError(f"{name} must be an array.")
    return value


def _string(data: Mapping[str, Any], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str):
        raise PortableGraphExportError(f"{name} must be a string.")
    return value


def _string_list(data: Mapping[str, Any], name: str) -> list[str]:
    values = _list(data, name)
    if not all(isinstance(value, str) for value in values):
        raise PortableGraphExportError(f"{name} must contain only strings.")
    return values


def _object(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise PortableGraphExportError(f"{name} must be an object.")
    return value


def _snapshot_from_payload(value: object) -> Snapshot:
    data = _mapping(value, "snapshot")
    try:
        profiles = []
        for profile_value in _list(data, "sourceProfiles"):
            profile = _mapping(profile_value, "source profile")
            profiles.append(
                SourceProfile(
                    sourceFile=_string(profile, "sourceFile"),
                    encoding=_string(profile, "encoding"),
                    namespaceUri=_optional_string(profile, "namespaceUri"),
                    exportVersion=_optional_string(profile, "exportVersion"),
                )
            )
        return Snapshot(
            id=_string(data, "id"),
            role=_string(data, "role"),
            sourceFiles=_string_list(data, "sourceFiles"),
            sourceProfiles=profiles,
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _node_from_payload(value: object) -> GraphNode:
    data = _mapping(value, "node")
    try:
        return GraphNode(
            id=_string(data, "id"),
            canonicalKey=_string(data, "canonicalKey"),
            snapshotId=_string(data, "snapshotId"),
            label=_string(data, "label"),
            type=_string(data, "type"),
            sourceFile=_string(data, "sourceFile"),
            xmlPath=_string(data, "xmlPath"),
            rawXml=_string(data, "rawXml"),
            metadata=_object(data, "metadata"),
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _link_from_payload(value: object) -> GraphLink:
    data = _mapping(value, "link")
    try:
        return GraphLink(
            id=_string(data, "id"),
            source=_string(data, "source"),
            target=_string(data, "target"),
            relationship=_string(data, "relationship"),
            confidence=_string(data, "confidence"),
            metadata=_object(data, "metadata"),
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _finding_from_payload(value: object) -> ValidationFinding:
    data = _mapping(value, "finding")
    try:
        return ValidationFinding(
            id=_string(data, "id"),
            code=_string(data, "code"),
            severity=_string(data, "severity"),
            snapshotId=_string(data, "snapshotId"),
            nodeIds=tuple(_string_list(data, "nodeIds")),
            message=_string(data, "message"),
            details=_object(data, "details"),
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _migration_risk_from_payload(value: object) -> MigrationRiskReport | None:
    if value is None:
        return None
    data = _mapping(value, "migrationRisk")
    score = data.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise PortableGraphExportError("migrationRisk.score must be a number.")
    factors = []
    for item in _list(data, "factors"):
        factor = _mapping(item, "migration risk factor")
        weight = factor.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise PortableGraphExportError("migration risk factor weight must be a number.")
        factors.append(
            MigrationRiskFactor(
                code=_string(factor, "code"),
                severity=_string(factor, "severity"),
                message=_string(factor, "message"),
                weight=weight,
                nodeIds=tuple(_string_list(factor, "nodeIds")),
            )
        )
    return MigrationRiskReport(score=score, factors=factors)


def _optional_string(data: Mapping[str, Any], name: str) -> str | None:
    value = data.get(name)
    if value is None or isinstance(value, str):
        return value
    raise PortableGraphExportError(f"{name} must be a string or null.")


def _json_value(value: object, name: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PortableGraphExportError(f"{name} is not portable JSON: {exc}") from exc
