import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from sap_im_config_graph_explorer.app import app
from sap_im_config_graph_explorer.portable_exports import (
    CSV_FINDING_COLUMNS,
    CSV_LINK_COLUMNS,
    CSV_NODE_COLUMNS,
    graph_document_from_payload,
    serialize_csv_bundle,
    serialize_graphml,
    serialize_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "portable_export_graph.json"
EXPECTED_HASHES = ROOT / "tests" / "fixtures" / "portable_export_expected_hashes.json"
GRAPHML_NAMESPACE = {"graphml": "http://graphml.graphdrawing.org/xmlns"}


def _fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _document():
    return graph_document_from_payload(_fixture_payload())


def _expected_hashes() -> dict[str, object]:
    return json.loads(EXPECTED_HASHES.read_text(encoding="utf-8"))


def test_csv_bundle_is_deterministic_and_uses_the_documented_members_and_columns():
    document = _document()
    first = serialize_csv_bundle(document)
    second = serialize_csv_bundle(document)
    expected = _expected_hashes()

    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == ["nodes.csv", "links.csv", "findings.csv", "manifest.json"]
        assert {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
        } == expected["csvMembers"]
        assert archive.read("nodes.csv").decode("utf-8").splitlines()[0].split(",") == list(CSV_NODE_COLUMNS)
        assert archive.read("links.csv").decode("utf-8").splitlines()[0].split(",") == list(CSV_LINK_COLUMNS)
        assert archive.read("findings.csv").decode("utf-8").splitlines()[0].split(",") == list(CSV_FINDING_COLUMNS)
        portable_content = b"\n".join(archive.read(name) for name in archive.namelist())
        assert b"rawXml" not in portable_content
        assert b"EXCLUDED_RAW_XML" not in portable_content
        manifest = json.loads(archive.read("manifest.json"))

    assert manifest["counts"] == {"nodes": 6, "links": 4, "findings": 2}
    assert [snapshot["id"] for snapshot in manifest["snapshots"]] == ["configuration", "production"]


def test_markdown_is_stable_readable_and_escapes_table_cells():
    markdown = serialize_markdown(_document()).decode("utf-8")

    assert hashlib.sha256(markdown.encode("utf-8")).hexdigest() == _expected_hashes()["markdownSha256"]
    assert markdown.startswith("# SAP IM Config Explorer Graph Export\n")
    assert all(section in markdown for section in (
        "## Schema and topology",
        "## Provenance",
        "## Snapshots",
        "## Counts",
        "## Nodes",
        "## Links",
        "## Findings",
    ))
    assert "North \\| Plan<br>One" in markdown
    assert "Pipe \\| newline<br>message" in markdown
    assert "### Migration risk" in markdown
    assert "| 3.5 | 1 |" in markdown
    assert "missing_relationship" in markdown
    assert "Review north plan" in markdown
    assert "rawXml" not in markdown
    assert "EXCLUDED_RAW_XML" not in markdown


def test_graphml_is_parseable_and_preserves_node_edge_and_graph_properties():
    graphml = serialize_graphml(_document())
    assert hashlib.sha256(graphml).hexdigest() == _expected_hashes()["graphmlSha256"]
    root = ET.fromstring(graphml)
    graph = root.find("graphml:graph", GRAPHML_NAMESPACE)
    assert graph is not None

    node_ids = [node.attrib["id"] for node in graph.findall("graphml:node", GRAPHML_NAMESPACE)]
    edge_ids = [edge.attrib["id"] for edge in graph.findall("graphml:edge", GRAPHML_NAMESPACE)]
    assert node_ids == [
        "plan-configuration",
        "component-configuration",
        "rule-configuration",
        "plan-production",
        "component-production",
        "rule-production",
    ]
    assert edge_ids == [
        "edge-configuration-component-plan",
        "edge-production-component-plan",
        "edge-configuration-rule-component",
        "edge-production-rule-component",
    ]
    keys = {
        key.attrib["id"]: key.attrib["attr.name"]
        for key in root.findall("graphml:key", GRAPHML_NAMESPACE)
    }
    assert keys["nodeType"] == "type"
    assert keys["nodeLabel"] == "label"
    assert keys["nodeSourceFile"] == "sourceFile"
    assert keys["edgeRelationship"] == "relationship"
    assert keys["edgeConfidence"] == "confidence"
    graph_data = {
        data.attrib["key"]: data.text
        for data in graph.findall("graphml:data", GRAPHML_NAMESPACE)
    }
    assert json.loads(graph_data["graphSnapshotsJson"])[0]["id"] == "configuration"
    assert json.loads(graph_data["graphFindingsJson"])[0]["id"] == "finding-configuration"
    assert "rawXml" not in graphml.decode("utf-8")
    assert "EXCLUDED_RAW_XML" not in graphml.decode("utf-8")

    payload = _fixture_payload()
    expected_nodes = {
        node["id"]: {
            "nodeId": node["id"],
            "nodeCanonicalKey": node["canonicalKey"],
            "nodeSnapshotId": node["snapshotId"],
            "nodeType": node["type"],
            "nodeLabel": node["label"],
            "nodeSourceFile": node["sourceFile"],
            "nodeXmlPath": node["xmlPath"],
            "nodeMetadataJson": json.dumps(
                node["metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        }
        for node in payload["nodes"]
    }
    actual_nodes = {
        node.attrib["id"]: {
            data.attrib["key"]: data.text or ""
            for data in node.findall("graphml:data", GRAPHML_NAMESPACE)
        }
        for node in graph.findall("graphml:node", GRAPHML_NAMESPACE)
    }
    assert actual_nodes == expected_nodes

    expected_links = {
        link["id"]: {
            "edgeId": link["id"],
            "edgeSource": link["source"],
            "edgeTarget": link["target"],
            "edgeRelationship": link["relationship"],
            "edgeConfidence": link["confidence"],
            "edgeMetadataJson": json.dumps(
                link["metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        }
        for link in payload["links"]
    }
    actual_links = {
        edge.attrib["id"]: {
            data.attrib["key"]: data.text or ""
            for data in edge.findall("graphml:data", GRAPHML_NAMESPACE)
        }
        for edge in graph.findall("graphml:edge", GRAPHML_NAMESPACE)
    }
    assert actual_links == expected_links


def test_duplicate_labels_and_snapshot_identities_remain_distinct_in_every_format():
    document = _document()
    markdown = serialize_markdown(document).decode("utf-8")
    graphml = serialize_graphml(document).decode("utf-8")
    with zipfile.ZipFile(io.BytesIO(serialize_csv_bundle(document))) as archive:
        nodes = archive.read("nodes.csv").decode("utf-8")

    assert nodes.count("Duplicate Label") == 2
    assert nodes.count("rule:duplicate-label") == 2
    assert markdown.count("Duplicate Label") == 3
    assert "rule-configuration" in graphml
    assert "rule-production" in graphml


def test_portable_routes_return_local_downloads_and_reject_non_allowlisted_nodes():
    client = TestClient(app)
    payload = _fixture_payload()

    responses = {
        "csv": client.post("/api/export/graph-csv", json=payload),
        "markdown": client.post("/api/export/graph-markdown", json=payload),
        "graphml": client.post("/api/export/graph-graphml", json=payload),
    }

    assert responses["csv"].headers["content-type"].startswith("application/zip")
    assert "sap-im-config-graph-csv.zip" in responses["csv"].headers["content-disposition"]
    assert responses["markdown"].headers["content-type"].startswith("text/markdown")
    assert "sap-im-config-graph.md" in responses["markdown"].headers["content-disposition"]
    assert responses["graphml"].headers["content-type"].startswith("application/graphml+xml")
    assert "sap-im-config-graph.graphml" in responses["graphml"].headers["content-disposition"]
    assert all(b"rawXml" not in response.content for response in responses.values())
    assert all(b"EXCLUDED_RAW_XML" not in response.content for response in responses.values())

    payload["nodes"][0]["type"] = "FUNCTION"  # type: ignore[index]
    rejected = client.post("/api/export/graph-csv", json=payload)
    assert rejected.status_code == 422
    assert rejected.json() == {"error": "Unsupported graph node type: FUNCTION"}


def test_portable_routes_reject_payloads_outside_the_declared_graph_contract():
    client = TestClient(app)

    wrong_schema = _fixture_payload()
    wrong_schema["schemaVersion"] = "0.0"
    response = client.post("/api/export/graph-markdown", json=wrong_schema)
    assert response.status_code == 422
    assert response.json() == {"error": "Unsupported graph schema version: 0.0"}

    wrong_topology = _fixture_payload()
    wrong_topology["nodes"][0]["type"] = "Formula"  # type: ignore[index]
    response = client.post("/api/export/graph-graphml", json=wrong_topology)
    assert response.status_code == 422
    assert response.json() == {
        "error": "Node type Formula is not allowed in core topology."
    }

    missing_endpoint = _fixture_payload()
    missing_endpoint["links"][0]["target"] = "missing-node"  # type: ignore[index]
    response = client.post("/api/export/graph-csv", json=missing_endpoint)
    assert response.status_code == 422
    assert response.json() == {
        "error": "Graph link edge-production-component-plan must reference existing node IDs."
    }

    cross_snapshot_link = _fixture_payload()
    cross_snapshot_link["links"][0]["target"] = "plan-configuration"  # type: ignore[index]
    response = client.post("/api/export/graph-csv", json=cross_snapshot_link)
    assert response.status_code == 422
    assert response.json() == {
        "error": "Graph link edge-production-component-plan crosses snapshot boundaries."
    }

    cross_snapshot_finding = _fixture_payload()
    cross_snapshot_finding["findings"][0]["nodeIds"] = ["rule-configuration"]  # type: ignore[index]
    response = client.post("/api/export/graph-csv", json=cross_snapshot_finding)
    assert response.status_code == 422
    assert response.json() == {
        "error": "Validation finding finding-production crosses snapshot boundaries."
    }

    invalid_profile = _fixture_payload()
    invalid_profile["snapshots"][0]["sourceProfiles"][0]["encoding"] = "latin-1"  # type: ignore[index]
    response = client.post("/api/export/graph-csv", json=invalid_profile)
    assert response.status_code == 422
    assert response.json() == {
        "error": "Unsupported source profile encoding: latin-1"
    }


def test_csv_neutralizes_spreadsheet_formula_prefixes_from_graph_content():
    payload = _fixture_payload()
    dangerous_labels = {
        "plan-configuration": '=WEBSERVICE("https://example.invalid")',
        "component-configuration": "+SUM(1,1)",
        "rule-configuration": "-2+3",
        "plan-production": "@SUM(1,1)",
        "component-production": "\t=1+1",
        "rule-production": "\r=1+1",
    }
    for node in payload["nodes"]:
        node["label"] = dangerous_labels[node["id"]]

    with zipfile.ZipFile(io.BytesIO(serialize_csv_bundle(graph_document_from_payload(payload)))) as archive:
        rows = {
            row["id"]: row
            for row in csv.DictReader(io.StringIO(archive.read("nodes.csv").decode("utf-8")))
        }

    assert {
        node_id: rows[node_id]["label"]
        for node_id in dangerous_labels
    } == {
        node_id: f"'{label}"
        for node_id, label in dangerous_labels.items()
    }
