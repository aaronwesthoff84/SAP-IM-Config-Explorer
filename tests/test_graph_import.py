import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sap_im_config_graph_explorer import graph_import
from sap_im_config_graph_explorer.app import app
from sap_im_config_graph_explorer.graph_import import (
    GraphDocumentImportError,
    import_graph_document_bytes,
    migrate_graph_payload,
)
from sap_im_config_graph_explorer.portable_exports import (
    PortableGraphExportError,
    graph_document_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "portable_export_graph.json"


def _fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _encoded(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _minimal_payload(
    *, node_count: int = 1, link_count: int = 0, finding_count: int = 0
) -> dict[str, object]:
    nodes = [
        {
            "id": f"node-{index}",
            "canonicalKey": f"plan:{index}",
            "snapshotId": "configuration",
            "label": f"Plan {index}",
            "type": "Plan",
            "sourceFile": "source.xml",
            "xmlPath": f"/DATA_IMPORT/PLAN[{index + 1}]",
            "rawXml": f'<PLAN NAME="Plan {index}" />',
            "metadata": {},
        }
        for index in range(node_count)
    ]
    links = [
        {
            "id": f"link-{index}",
            "source": "node-0",
            "target": "node-1",
            "relationship": "belongs_to_plan",
            "confidence": "high",
            "metadata": {},
        }
        for index in range(link_count)
    ]
    findings = [
        {
            "id": f"finding-{index}",
            "code": "unused_object",
            "severity": "warning",
            "snapshotId": "configuration",
            "nodeIds": ["node-0"],
            "message": "Unused object",
            "details": {},
        }
        for index in range(finding_count)
    ]
    return {
        "schemaVersion": "1.3",
        "topologyMode": "core",
        "provenance": {"origin": "xml", "fileName": None},
        "snapshots": [
            {
                "id": "configuration",
                "role": "configuration",
                "sourceFiles": ["source.xml"],
                "sourceProfiles": [],
            }
        ],
        "nodes": nodes,
        "links": links,
        "findings": findings,
    }


def test_current_export_import_export_preserves_the_complete_graph_contract():
    original = _fixture_payload()
    exported = _encoded(graph_document_from_payload(original).to_dict())
    before = bytes(exported)

    imported = import_graph_document_bytes(exported, "saved-graph.json").to_dict()

    assert exported == before
    assert imported["schemaVersion"] == "1.3"
    assert imported["provenance"] == {
        "origin": "imported",
        "fileName": "saved-graph.json",
    }
    for field in (
        "topologyMode",
        "snapshots",
        "nodes",
        "links",
        "findings",
        "migrationRisk",
    ):
        assert imported[field] == original[field]
    assert graph_document_from_payload(imported).to_dict() == imported


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2"])
def test_supported_schema_migrations_are_deterministic_and_preserve_identity(
    version: str,
):
    historical = _fixture_payload()
    historical["schemaVersion"] = version
    historical.pop("provenance")
    if version in {"1.0", "1.1"}:
        historical.pop("topologyMode")
    if version == "1.0":
        for snapshot in historical["snapshots"]:
            snapshot.pop("sourceProfiles")
    original = copy.deepcopy(historical)
    node_ids = [node["id"] for node in historical["nodes"]]
    link_ids = [link["id"] for link in historical["links"]]

    first = import_graph_document_bytes(_encoded(historical), "historical.json")
    second = import_graph_document_bytes(_encoded(historical), "historical.json")

    assert historical == original
    assert first.to_dict() == second.to_dict()
    assert first.schemaVersion == "1.3"
    assert first.topologyMode == "core"
    assert [node.id for node in first.nodes] == node_ids
    assert [link.id for link in first.links] == link_ids
    assert first.provenance.to_dict() == {
        "origin": "imported",
        "fileName": "historical.json",
    }
    if version == "1.0":
        assert all(snapshot.sourceProfiles == [] for snapshot in first.snapshots)


def test_migration_rejects_fields_that_do_not_belong_to_the_declared_schema():
    payload = _fixture_payload()
    payload["schemaVersion"] = "1.0"
    payload.pop("provenance")
    payload.pop("topologyMode")

    with pytest.raises(PortableGraphExportError) as exc_info:
        migrate_graph_payload(payload)

    assert str(exc_info.value) == (
        "schemaVersion 1.0 snapshot contains unsupported field: sourceProfiles."
    )


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda payload: payload["nodes"][0].update(type="FUNCTION"),
            "Unsupported graph node type: FUNCTION",
        ),
        (
            lambda payload: payload["links"][0].update(relationship="invented"),
            "Unsupported graph relationship: invented",
        ),
        (
            lambda payload: payload["links"][0].update(target="missing-node"),
            "must reference existing node IDs",
        ),
        (
            lambda payload: payload["nodes"][0].update(snapshotId="missing"),
            "references unknown snapshot: missing",
        ),
        (
            lambda payload: payload["findings"][0].update(nodeIds=["missing-node"]),
            "references unknown node IDs",
        ),
        (
            lambda payload: payload["snapshots"].append(
                copy.deepcopy(payload["snapshots"][0])
            ),
            "Duplicate snapshot ID: production",
        ),
        (
            lambda payload: payload["nodes"].append(
                copy.deepcopy(payload["nodes"][0])
            ),
            "Duplicate graph node ID: rule-production",
        ),
        (
            lambda payload: payload["links"].append(
                copy.deepcopy(payload["links"][0])
            ),
            "Duplicate graph link ID: edge-production-component-plan",
        ),
        (
            lambda payload: payload["findings"].append(
                copy.deepcopy(payload["findings"][0])
            ),
            "Duplicate validation finding ID: finding-production",
        ),
        (
            lambda payload: payload["provenance"].update(origin="remote"),
            "Unsupported graph provenance origin: remote",
        ),
        (
            lambda payload: payload["migrationRisk"]["factors"][0].update(
                severity="critical"
            ),
            "Unsupported migration risk severity: critical",
        ),
    ],
)
def test_import_rejects_invalid_contract_values_without_repair(mutate, error: str):
    payload = _fixture_payload()
    mutate(payload)

    with pytest.raises(GraphDocumentImportError) as exc_info:
        import_graph_document_bytes(_encoded(payload), "invalid.json")

    assert str(exc_info.value).startswith("Invalid Graph JSON file invalid.json: ")
    assert error in str(exc_info.value)


@pytest.mark.parametrize(
    ("content", "error"),
    [
        (b"{", "Malformed Graph JSON file broken.json."),
        (
            b'{"schemaVersion":"1.3","schemaVersion":"1.3"}',
            "Malformed Graph JSON file broken.json.",
        ),
        (b'{"value":NaN}', "Malformed Graph JSON file broken.json."),
        (b"[]", "Graph JSON file broken.json must contain a JSON object."),
    ],
)
def test_malformed_and_ambiguous_json_is_rejected_safely(content: bytes, error: str):
    with pytest.raises(GraphDocumentImportError) as exc_info:
        import_graph_document_bytes(content, "broken.json")

    assert str(exc_info.value) == error


@pytest.mark.parametrize(
    ("version", "error"),
    [
        ("9.0", "Unsupported future graph schema version: 9.0"),
        ("0.9", "Unsupported graph schema version: 0.9"),
    ],
)
def test_unsupported_schema_versions_are_rejected(version: str, error: str):
    payload = _fixture_payload()
    payload["schemaVersion"] = version

    with pytest.raises(GraphDocumentImportError) as exc_info:
        import_graph_document_bytes(_encoded(payload), "version.json")

    assert str(exc_info.value) == f"Invalid Graph JSON file version.json: {error}"


def test_named_import_limits_and_exact_boundaries(monkeypatch):
    assert graph_import.MAX_GRAPH_JSON_BYTES == 25 * 1024 * 1024
    assert graph_import.MAX_GRAPH_JSON_NODES == 50_000
    assert graph_import.MAX_GRAPH_JSON_LINKS == 100_000
    assert graph_import.MAX_GRAPH_JSON_FINDINGS == 50_000

    cases = [
        ("MAX_GRAPH_JSON_NODES", {"node_count": 1}, {"node_count": 2}, "node"),
        (
            "MAX_GRAPH_JSON_LINKS",
            {"node_count": 2, "link_count": 1},
            {"node_count": 2, "link_count": 2},
            "link",
        ),
        (
            "MAX_GRAPH_JSON_FINDINGS",
            {"finding_count": 1},
            {"finding_count": 2},
            "finding",
        ),
    ]
    for constant, boundary_args, over_args, label in cases:
        with monkeypatch.context() as context:
            context.setattr(graph_import, constant, 1)
            import_graph_document_bytes(
                _encoded(_minimal_payload(**boundary_args)), "boundary.json"
            )
            with pytest.raises(GraphDocumentImportError) as exc_info:
                import_graph_document_bytes(
                    _encoded(_minimal_payload(**over_args)), "over.json"
                )
            assert str(exc_info.value) == (
                f"Graph JSON file over.json exceeds the 1 {label} limit."
            )

    boundary_bytes = _encoded(_minimal_payload())
    monkeypatch.setattr(graph_import, "MAX_GRAPH_JSON_BYTES", len(boundary_bytes))
    import_graph_document_bytes(boundary_bytes, "boundary.json")
    with pytest.raises(GraphDocumentImportError) as exc_info:
        import_graph_document_bytes(boundary_bytes + b" ", "over.json")
    assert str(exc_info.value) == (
        "Graph JSON file over.json exceeds the 25 MiB file-size limit."
    )


def test_import_api_round_trips_without_modifying_the_selected_file(tmp_path: Path):
    source = tmp_path / "selected-graph.json"
    source.write_bytes(_encoded(_fixture_payload()))
    before = source.read_bytes()
    client = TestClient(app)

    with source.open("rb") as handle:
        response = client.post(
            "/api/import/graph-json",
            files={"file": (source.name, handle, "application/json")},
        )

    assert response.status_code == 200
    assert source.read_bytes() == before
    payload = response.json()
    assert payload["provenance"] == {
        "origin": "imported",
        "fileName": "selected-graph.json",
    }
    assert [node["id"] for node in payload["nodes"]] == [
        node["id"] for node in _fixture_payload()["nodes"]
    ]


def test_import_api_returns_stable_safe_400_errors(monkeypatch):
    client = TestClient(app)

    malformed = client.post(
        "/api/import/graph-json",
        files={"file": ("broken.json", b"{", "application/json")},
    )
    assert malformed.status_code == 400
    assert malformed.json() == {"error": "Malformed Graph JSON file broken.json."}

    wrong_type = client.post(
        "/api/import/graph-json",
        files={"file": ("graph.xml", b"<DATA_IMPORT />", "application/xml")},
    )
    assert wrong_type.status_code == 400
    assert wrong_type.json() == {
        "error": (
            "Unsupported Graph JSON file: graph.xml. Only .json files are supported."
        )
    }

    monkeypatch.setattr(graph_import, "MAX_GRAPH_JSON_NODES", 0)
    over_limit = client.post(
        "/api/import/graph-json",
        files={
            "file": (
                "count.json",
                _encoded(_minimal_payload()),
                "application/json",
            )
        },
    )
    assert over_limit.status_code == 400
    assert over_limit.json() == {
        "error": "Graph JSON file count.json exceeds the 0 node limit."
    }
