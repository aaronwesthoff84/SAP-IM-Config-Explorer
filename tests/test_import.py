from __future__ import annotations

import json
from typing import Any
import pytest
from fastapi.testclient import TestClient

from sap_im_config_graph_explorer.app import app
from sap_im_config_graph_explorer.portable_exports import (
    PortableGraphExportError,
    import_and_migrate_graph_document,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_import_and_migrate_valid_1_2() -> None:
    # A complete valid 1.2 payload
    payload: dict[str, Any] = {
        "schemaVersion": "1.2",
        "topologyMode": "core",
        "snapshots": [
            {
                "id": "configuration",
                "role": "configuration",
                "sourceFiles": ["export.xml"],
                "sourceProfiles": []
            }
        ],
        "nodes": [
            {
                "id": "n1",
                "canonicalKey": "rule:r1",
                "snapshotId": "configuration",
                "label": "R1",
                "type": "Rule",
                "sourceFile": "export.xml",
                "xmlPath": "/path",
                "rawXml": "<RULE name='R1'/>",
                "metadata": {}
            }
        ],
        "links": [],
        "findings": []
    }

    doc = import_and_migrate_graph_document(payload)
    assert doc.schemaVersion == "1.2"
    assert doc.topologyMode == "core"
    assert len(doc.nodes) == 1
    assert doc.nodes[0].id == "n1"


def test_import_and_migrate_version_1_1_defaults_topology() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": "1.1",
        "snapshots": [
            {
                "id": "configuration",
                "role": "configuration",
                "sourceFiles": ["export.xml"],
                "sourceProfiles": []
            }
        ],
        "nodes": [
            {
                "id": "n1",
                "canonicalKey": "rule:r1",
                "snapshotId": "configuration",
                "label": "R1",
                "type": "Rule",
                "sourceFile": "export.xml",
                "xmlPath": "/path",
                "rawXml": "<RULE name='R1'/>"
            }
        ],
        "links": [],
        "findings": []
    }

    doc = import_and_migrate_graph_document(payload)
    # Checks that older 1.1 migrates to 1.2 and topologyMode defaults to "core"
    assert doc.schemaVersion == "1.2"
    assert doc.topologyMode == "core"
    assert doc.nodes[0].snapshotId == "configuration"


def test_import_and_migrate_version_1_0_defaults_source_profiles() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": "1.0",
        "snapshots": [
            {
                "id": "configuration",
                "role": "configuration",
                "sourceFiles": ["export.xml"]
            }
        ],
        "nodes": [
            {
                "id": "n1",
                "label": "R1",
                "type": "Rule",
                "sourceFile": "export.xml",
                "xmlPath": "/path",
                "rawXml": "<RULE name='R1'/>"
            }
        ],
        "links": [],
        "findings": []
    }

    doc = import_and_migrate_graph_document(payload)
    assert doc.schemaVersion == "1.2"
    assert doc.topologyMode == "core"
    assert len(doc.snapshots) == 1
    assert doc.snapshots[0].sourceProfiles == []


def test_reject_future_schema_version() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": "1.3",
        "topologyMode": "core",
        "snapshots": [],
        "nodes": [],
        "links": [],
        "findings": []
    }
    with pytest.raises(PortableGraphExportError, match="Unsupported future schema version"):
        import_and_migrate_graph_document(payload)


def test_reject_invalid_schema_version_type() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": 1.2,  # Not a string
        "topologyMode": "core",
        "snapshots": [],
        "nodes": [],
        "links": [],
        "findings": []
    }
    with pytest.raises(PortableGraphExportError, match="Invalid schema version"):
        import_and_migrate_graph_document(payload)


def test_reject_invalid_node_type() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": "1.2",
        "topologyMode": "core",
        "snapshots": [
            {"id": "configuration", "role": "configuration", "sourceFiles": [], "sourceProfiles": []}
        ],
        "nodes": [
            {
                "id": "n1",
                "label": "R1",
                "type": "InvalidType",  # Invalid type
                "sourceFile": "export.xml",
                "xmlPath": "/path",
                "rawXml": "<XML/>"
            }
        ],
        "links": [],
        "findings": []
    }
    with pytest.raises(PortableGraphExportError, match="Unsupported graph node type"):
        import_and_migrate_graph_document(payload)


def test_reject_invalid_relationship() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": "1.2",
        "topologyMode": "full",
        "snapshots": [
            {"id": "configuration", "role": "configuration", "sourceFiles": [], "sourceProfiles": []}
        ],
        "nodes": [
            {"id": "n1", "label": "R1", "type": "Rule", "sourceFile": "export.xml", "xmlPath": "/p", "rawXml": "<R/>"},
            {"id": "n2", "label": "R2", "type": "Rule", "sourceFile": "export.xml", "xmlPath": "/p", "rawXml": "<R/>"}
        ],
        "links": [
            {
                "id": "l1",
                "source": "n1",
                "target": "n2",
                "relationship": "invalid_relationship",  # Invalid relationship
                "confidence": "high"
            }
        ],
        "findings": []
    }
    with pytest.raises(PortableGraphExportError, match="Unsupported graph relationship"):
        import_and_migrate_graph_document(payload)


def test_reject_dangling_endpoints() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": "1.2",
        "topologyMode": "core",
        "snapshots": [
            {"id": "configuration", "role": "configuration", "sourceFiles": [], "sourceProfiles": []}
        ],
        "nodes": [
            {"id": "n1", "label": "R1", "type": "Rule", "sourceFile": "export.xml", "xmlPath": "/p", "rawXml": "<R/>"}
        ],
        "links": [
            {
                "id": "l1",
                "source": "n1",
                "target": "non_existent",  # Dangling endpoint
                "relationship": "belongs_to_plan_component",
                "confidence": "high"
            }
        ],
        "findings": []
    }
    with pytest.raises(PortableGraphExportError, match="must reference existing node IDs"):
        import_and_migrate_graph_document(payload)


def test_reject_duplicate_ids() -> None:
    payload: dict[str, Any] = {
        "schemaVersion": "1.2",
        "topologyMode": "core",
        "snapshots": [
            {"id": "configuration", "role": "configuration", "sourceFiles": [], "sourceProfiles": []}
        ],
        "nodes": [
            {"id": "n1", "label": "R1", "type": "Rule", "sourceFile": "export.xml", "xmlPath": "/p", "rawXml": "<R/>"},
            {"id": "n1", "label": "Duplicate ID", "type": "Rule", "sourceFile": "export.xml", "xmlPath": "/p", "rawXml": "<R/>"}
        ],
        "links": [],
        "findings": []
    }
    with pytest.raises(PortableGraphExportError, match="Duplicate graph node ID"):
        import_and_migrate_graph_document(payload)


def test_api_import_valid(client: TestClient) -> None:
    payload = {
        "schemaVersion": "1.2",
        "topologyMode": "core",
        "snapshots": [],
        "nodes": [],
        "links": [],
        "findings": []
    }
    files = {"file": ("graph.json", json.dumps(payload), "application/json")}
    response = client.post("/api/import/graph-json", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["imported"] is True
    assert data["schemaVersion"] == "1.2"


def test_api_import_invalid_file_type(client: TestClient) -> None:
    files = {"file": ("graph.txt", "{}", "text/plain")}
    response = client.post("/api/import/graph-json", files=files)
    assert response.status_code == 400
    assert "Only .json files are supported" in response.json()["error"]


def test_api_import_empty_file(client: TestClient) -> None:
    files = {"file": ("graph.json", "", "application/json")}
    response = client.post("/api/import/graph-json", files=files)
    assert response.status_code == 400
    assert "Empty JSON file" in response.json()["error"]


def test_api_import_oversized_file(client: TestClient) -> None:
    huge_data = " " * (20 * 1024 * 1024 + 10)
    files = {"file": ("graph.json", huge_data, "application/json")}
    response = client.post("/api/import/graph-json", files=files)
    assert response.status_code == 400
    assert "Oversized document" in response.json()["error"]


def test_api_import_oversized_elements(client: TestClient) -> None:
    # Too many nodes/links in a small JSON
    nodes = [{"id": f"n{i}", "label": "R", "type": "Rule", "sourceFile": "e.xml", "xmlPath": "/p", "rawXml": "<R/>"} for i in range(100001)]
    payload = {
        "schemaVersion": "1.2",
        "topologyMode": "core",
        "snapshots": [{"id": "configuration", "role": "configuration", "sourceFiles": [], "sourceProfiles": []}],
        "nodes": nodes,
        "links": [],
        "findings": []
    }
    files = {"file": ("graph.json", json.dumps(payload), "application/json")}
    response = client.post("/api/import/graph-json", files=files)
    assert response.status_code == 400
    assert "Oversized document" in response.json()["error"]
