from pathlib import Path

from fastapi.testclient import TestClient

from sap_im_config_graph_explorer.app import app


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "minimal_plan.xml"
EXTRACTOR_FIXTURE = ROOT / "tests" / "fixtures" / "extractor_families.xml"
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
    assert 'data-view="html-output-view"' in response.text
    assert 'id="html-output-preview"' in response.text
    assert 'id="theme-toggle"' in response.text
    assert "Generate HTML" in response.text


def test_html_client_uses_the_selected_xml_file():
    script = (ROOT / "sap_im_config_graph_explorer" / "static" / "app.js").read_text(encoding="utf-8")

    assert "const file = npFileInput.files[0] || pFileInput.files[0];" in script
    assert "html-output-preview" in script
    assert "enableHtmlPreviewAnchors" in script
    assert 'href?.startsWith("#")' in script
    assert "event.preventDefault();" in script
    assert 'formData.append("theme", currentTheme());' in script
    assert "renderFindings(state.html.findings || []);" in script
    assert "function applyThemeToHtml" in script
    assert "before-html-file" not in script
    assert "after-html-file" not in script


def test_html_output_preview_uses_the_available_workspace_height():
    styles = (ROOT / "sap_im_config_graph_explorer" / "static" / "styles.css").read_text(encoding="utf-8")

    assert "#html-output-view.active" in styles
    assert "grid-template-rows: 42px minmax(0, 1fr);" in styles
    assert "#html-output-preview" in styles


def test_spectrumtek_light_and_dark_theme_variables_are_defined():
    styles = (ROOT / "sap_im_config_graph_explorer" / "static" / "styles.css").read_text(encoding="utf-8")

    for color in ("#2e7d32", "#81c784", "#333333", "#ffffff", "#d32f2f", "#ffa000"):
        assert color in styles
    assert ':root[data-theme="dark"]' in styles
    assert "font-size: 36px;" in styles
    assert "font-size: 24px;" in styles
    assert "font-size: 18px;" in styles
    assert "rgba(129, 199, 132" in styles


def test_theme_toggle_persists_and_redraws_the_graph():
    script = (ROOT / "sap_im_config_graph_explorer" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'localStorage.getItem("sap-im-config-explorer-theme")' in script
    assert 'localStorage.setItem("sap-im-config-explorer-theme", theme)' in script
    assert 'document.documentElement.dataset.theme = theme;' in script
    assert "if (state.graph.nodes.length) renderGraph();" in script
    assert "function graphThemeColors()" in script


def test_html_endpoint_applies_selected_theme_and_returns_findings():
    client = TestClient(app)

    response = client.post(
        "/api/convert/html",
        data={"variant": "A", "theme": "dark"},
        files={"file": ("validation_findings.xml", VALIDATION_FIXTURE.read_bytes(), "application/xml")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert '<html data-theme="dark">' in payload["html"]
    assert {finding["code"] for finding in payload["findings"]} >= {
        "duplicate_object",
        "unused_object",
        "orphaned_object",
    }


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
    assert payload["schemaVersion"] == "1.2"
    assert payload["topologyMode"] == "core"
    assert payload["snapshots"] == [
        {
            "id": "configuration",
            "role": "configuration",
            "sourceFiles": ["first.xml", "second.xml"],
            "sourceProfiles": [
                {
                    "sourceFile": "first.xml",
                    "encoding": "utf-8",
                    "namespaceUri": None,
                    "exportVersion": "16.0",
                },
                {
                    "sourceFile": "second.xml",
                    "encoding": "utf-8",
                    "namespaceUri": None,
                    "exportVersion": "16.0",
                },
            ],
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


def test_graph_endpoint_selects_core_or_full_topology_from_multipart_form():
    client = TestClient(app)
    xml = EXTRACTOR_FIXTURE.read_bytes()

    omitted = client.post(
        "/api/graph",
        files={"files": ("extractor_families.xml", xml, "application/xml")},
    )
    explicit_core = client.post(
        "/api/graph",
        data={"topology_mode": "core"},
        files={"files": ("extractor_families.xml", xml, "application/xml")},
    )
    full = client.post(
        "/api/graph",
        data={"topology_mode": "full"},
        files={"files": ("extractor_families.xml", xml, "application/xml")},
    )

    assert omitted.status_code == explicit_core.status_code == full.status_code == 200
    assert omitted.json()["topologyMode"] == explicit_core.json()["topologyMode"] == "core"
    assert {node["type"] for node in omitted.json()["nodes"]} == {
        "Plan",
        "PlanComponent",
        "Rule",
    }
    assert full.json()["topologyMode"] == "full"
    assert {node["type"] for node in full.json()["nodes"]} == {
        "FixedValue",
        "Formula",
        "LookupTable",
        "Quota",
        "RateTable",
        "Territory",
        "Variable",
        "Rule",
        "Plan",
        "PlanComponent",
        "EventType",
        "CreditType",
        "EarningCode",
        "EarningGroup",
        "BusinessUnit",
        "ProcessingUnit",
        "Calendar",
    }


def test_graph_endpoint_rejects_unsupported_topology_mode_with_stable_error():
    client = TestClient(app)

    response = client.post(
        "/api/graph",
        data={"topology_mode": "expanded"},
        files={
            "files": (
                "minimal_plan.xml",
                FIXTURE.read_bytes(),
                "application/xml",
            )
        },
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Unsupported topology mode: expanded"}


def test_graph_endpoint_runs_migration_analysis_on_the_selected_topology():
    client = TestClient(app)
    non_production = b"""<DATA_IMPORT>
      <FORMULA NAME="Eligibility" />
      <VARIABLE NAME="Gate" />
    </DATA_IMPORT>"""
    production = b"""<DATA_IMPORT>
      <FORMULA NAME="Eligibility"><VARIABLE_REF NAME="Gate" /></FORMULA>
      <VARIABLE NAME="Gate" />
    </DATA_IMPORT>"""
    uploads = [
        ("np_files", ("np.xml", non_production, "application/xml")),
        ("p_files", ("p.xml", production, "application/xml")),
    ]

    core = client.post(
        "/api/graph",
        data={"topology_mode": "core"},
        files=uploads,
    )
    full = client.post(
        "/api/graph",
        data={"topology_mode": "full"},
        files=uploads,
    )

    assert core.status_code == full.status_code == 200
    assert core.json()["topologyMode"] == "core"
    assert core.json()["migrationRisk"] == {"score": 0, "factors": []}
    assert full.json()["topologyMode"] == "full"
    assert {factor["code"] for factor in full.json()["migrationRisk"]["factors"]} >= {
        "missing_relationship"
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


def test_session_export_and_import_cycle():
    client = TestClient(app)
    import base64
    import io
    import json
    import zipfile

    # 1. Export session
    session_data = json.dumps({
        "schemaVersion": "1.2",
        "graph": {"nodes": [], "links": []},
        "activeView": "graph-view",
    })
    dummy_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    export_response = client.post(
        "/api/session/export",
        data={"session_data": session_data, "graph_image": dummy_image},
    )

    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/zip"

    zip_bytes = export_response.content
    zip_buffer = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_buffer, "r") as zip_file:
        assert set(zip_file.namelist()) == {"session.json", "graph.png"}
        assert zip_file.read("session.json").decode("utf-8") == session_data
        assert zip_file.read("graph.png") == base64.b64decode(dummy_image.split(",", 1)[1])

    # 2. Import back
    import_response = client.post(
        "/api/session/import",
        files={"file": ("sap-im-config-graph-session.zip", zip_bytes, "application/zip")},
    )
    assert import_response.status_code == 200
    assert import_response.json()["schemaVersion"] == "1.2"
    assert import_response.json()["activeView"] == "graph-view"


def test_session_import_rejections_and_security_safeguards():
    client = TestClient(app)
    import io
    import json
    import zipfile

    # Helper to create memory ZIP bytes
    def make_zip(members: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, content in members.items():
                z.writestr(name, content)
        return buf.getvalue()

    # Rejection: wrong file extension
    r_ext = client.post(
        "/api/session/import",
        files={"file": ("session.txt", b"not-a-zip", "text/plain")},
    )
    assert r_ext.status_code == 400
    assert "Only .zip session files are supported" in r_ext.json()["error"]

    # Rejection: wrong member count (1 file)
    z1 = make_zip({"session.json": b"{}"})
    r_count = client.post(
        "/api/session/import",
        files={"file": ("session.zip", z1, "application/zip")},
    )
    assert r_count.status_code == 400
    assert "expected exactly 2 members" in r_count.json()["error"]

    # Rejection: wrong names / directory traversal path
    z_paths = make_zip({
        "../../session.json": b"{}",
        "graph.png": b"image-data",
    })
    r_paths = client.post(
        "/api/session/import",
        files={"file": ("session.zip", z_paths, "application/zip")},
    )
    assert r_paths.status_code == 400
    assert "members must be exactly 'session.json' and 'graph.png'" in r_paths.json()["error"]

    # Rejection: oversized session.json (simulate by writing 51MB dummy string)
    z_size = make_zip({
        "session.json": b" " * 53_000_000,
        "graph.png": b"image-data",
    })
    r_size = client.post(
        "/api/session/import",
        files={"file": ("session.zip", z_size, "application/zip")},
    )
    assert r_size.status_code == 400
    assert "exceeds the maximum allowed size" in r_size.json()["error"]

    # Rejection: malformed JSON
    z_malformed = make_zip({
        "session.json": b"not json!",
        "graph.png": b"image-data",
    })
    r_malformed = client.post(
        "/api/session/import",
        files={"file": ("session.zip", z_malformed, "application/zip")},
    )
    assert r_malformed.status_code == 400
    assert "Malformed session.json" in r_malformed.json()["error"]

    # Rejection: unsupported schema version
    z_version = make_zip({
        "session.json": json.dumps({"schemaVersion": "1.3"}).encode("utf-8"),
        "graph.png": b"image-data",
    })
    r_version = client.post(
        "/api/session/import",
        files={"file": ("session.zip", z_version, "application/zip")},
    )
    assert r_version.status_code == 400
    assert "Unsupported session schema version: 1.3" in r_version.json()["error"]

    # Rejection: missing structure
    z_structure = make_zip({
        "session.json": json.dumps({"schemaVersion": "1.2"}).encode("utf-8"),
        "graph.png": b"image-data",
    })
    r_structure = client.post(
        "/api/session/import",
        files={"file": ("session.zip", z_structure, "application/zip")},
    )
    assert r_structure.status_code == 400
    assert "missing required structure" in r_structure.json()["error"]
