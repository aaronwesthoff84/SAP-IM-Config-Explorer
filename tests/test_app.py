from pathlib import Path

from fastapi.testclient import TestClient

from sap_im_config_graph_explorer.app import app


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "minimal_plan.xml"
VALIDATION_FIXTURE = ROOT / "tests" / "fixtures" / "validation_findings.xml"


def test_health_endpoint():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_uses_project_name():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "<title>SAP IM Config Explorer</title>" in response.text
    assert "<h1>SAP IM Config Explorer</h1>" in response.text
    assert 'id="validation-findings"' in response.text
    assert 'id="before-html-file"' in response.text
    assert 'id="after-html-file"' in response.text
    assert "Generate HTML Comparison" in response.text
    assert 'data-view="before-html-view"' in response.text
    assert 'data-view="after-html-view"' in response.text
    assert 'data-view="development-baseline-html-view"' in response.text
    assert 'data-view="development-candidate-html-view"' in response.text


def test_html_comparison_client_uses_two_selected_files_not_matching_names():
    script = (ROOT / "sap_im_config_graph_explorer" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'document.getElementById("before-html-file")' in script
    assert 'document.getElementById("after-html-file")' in script
    assert "Promise.all([" in script
    assert "sameHtmlSource" not in script


def test_graph_endpoint_accepts_multiple_uploads():
    client = TestClient(app)
    xml = FIXTURE.read_bytes()

    response = client.post(
        "/api/graph",
        files=[
            ("files", ("first.xml", xml, "application/xml")),
            ("files", ("second.xml", xml, "application/xml")),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["nodes"]
    assert {node["sourceFile"] for node in payload["nodes"]} == {"first.xml", "second.xml"}
    assert payload["schemaVersion"] == "1.0"
    assert payload["snapshots"] == [
        {
            "id": "configuration",
            "role": "configuration",
            "sourceFiles": ["first.xml", "second.xml"],
        }
    ]
    assert payload["findings"]
    finding_codes = {finding["code"] for finding in payload["findings"]}
    assert "ambiguous_reference" in finding_codes
    assert finding_codes <= {
        "ambiguous_reference",
        "duplicate_object",
        "unused_object",
        "orphaned_object",
    }


def test_graph_endpoint_exposes_duplicate_unused_and_orphaned_findings():
    client = TestClient(app)

    response = client.post(
        "/api/graph",
        files={
            "files": (
                "validation_findings.xml",
                VALIDATION_FIXTURE.read_bytes(),
                "application/xml",
            )
        },
    )

    assert response.status_code == 200
    findings = response.json()["findings"]
    finding_by_code = {finding["code"]: finding for finding in findings}
    assert {"duplicate_object", "unused_object", "orphaned_object"} <= set(finding_by_code)
    assert finding_by_code["duplicate_object"]["severity"] == "error"
    assert finding_by_code["orphaned_object"]["message"] == "Orphaned Rule object: Unattached Rule"


def test_html_endpoint_returns_generated_html():
    client = TestClient(app)

    response = client.post(
        "/api/convert/html",
        data={"variant": "A"},
        files={"file": ("minimal_plan.xml", FIXTURE.read_bytes(), "application/xml")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "SAP Incentive Management Plan Summary" in payload["html"]
    assert payload["outputFile"] == "minimal_plan.html"


def test_html_endpoint_accepts_before_and_after_files_with_different_names():
    client = TestClient(app)

    before = client.post(
        "/api/convert/html",
        data={"variant": "A"},
        files={"file": ("before-export.xml", FIXTURE.read_bytes(), "application/xml")},
    )
    after = client.post(
        "/api/convert/html",
        data={"variant": "A"},
        files={"file": ("after-export.xml", FIXTURE.read_bytes(), "application/xml")},
    )

    assert before.status_code == 200
    assert after.status_code == 200
    assert before.json()["outputFile"] == "before-export.html"
    assert after.json()["outputFile"] == "after-export.html"


def test_development_html_endpoints_serve_converter_snapshots():
    client = TestClient(app)

    baseline = client.get("/api/development/html/baseline")
    candidate = client.get("/api/development/html/candidate")

    assert baseline.status_code == 200
    assert candidate.status_code == 200
    assert "SAP Incentive Management Plan Summary" in baseline.text
    assert "SAP Incentive Management Plan Summary" in candidate.text
    assert baseline.text != candidate.text


def test_export_graph_json_endpoint_returns_downloadable_json():
    client = TestClient(app)
    graph = {"nodes": [], "links": []}

    response = client.post("/api/export/graph-json", json=graph)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    assert response.json() == graph


def test_graph_endpoint_reports_malformed_xml():
    client = TestClient(app)

    response = client.post(
        "/api/graph",
        files=[("files", ("broken.xml", b"<DATA_IMPORT>", "application/xml"))],
    )

    assert response.status_code == 400
    assert "Malformed XML" in response.json()["error"]
