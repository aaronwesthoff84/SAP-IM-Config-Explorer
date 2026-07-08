import json
import subprocess
import sys
from pathlib import Path

import pytest

from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import NODE_TYPES, RELATIONSHIP_TYPES
from sap_im_config_graph_explorer.xml_loader import XmlLoadError, load_xml_file
from sap_im_config_graph_explorer.xml_to_html_converter import Transformer


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def test_xml_to_html_conversion_still_emits_plan_summary():
    transformer = Transformer()

    transformer.parse(str(FIXTURES / "minimal_plan.xml"))
    html = transformer.html()

    assert "<!DOCTYPE HTML>" in html
    assert "SAP Incentive Management Plan Summary" in html
    assert "Enterprise Plan" in html


def test_legacy_cli_still_accepts_old_argument_shape(tmp_path):
    output = tmp_path / "minimal_plan.html"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "sap_im_transformer.py"),
            str(FIXTURES / "minimal_plan.xml"),
            str(output),
            "--variant=A",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert "SAP Incentive Management Plan Summary" in output.read_text(encoding="utf-8")


def test_graph_builder_returns_valid_nodes_and_links():
    graph = GraphBuilder().build_from_paths([FIXTURES / "minimal_plan.xml"]).to_dict()

    labels = {node["label"] for node in graph["nodes"]}
    relationships = {link["relationship"] for link in graph["links"]}

    assert {"Enterprise Plan", "Credit Rule", "Eligibility Formula", "Rate Table"} <= labels
    assert "belongs_to_plan" in relationships
    assert "uses_formula" in relationships
    assert "uses_lookup" in relationships
    assert all(node["type"] in NODE_TYPES for node in graph["nodes"])
    assert all(link["relationship"] in RELATIONSHIP_TYPES for link in graph["links"])


def test_multiple_xml_files_merge_and_preserve_source_file():
    graph = GraphBuilder().build_from_paths(
        [FIXTURES / "minimal_plan.xml", FIXTURES / "unknown_object.xml"]
    )

    source_files = {node.sourceFile for node in graph.nodes}

    assert {"minimal_plan.xml", "unknown_object.xml"} <= source_files
    assert any(node.label == "Partner Mapping" for node in graph.nodes)


def test_malformed_empty_and_unsupported_files_raise_useful_errors(tmp_path):
    malformed = tmp_path / "broken.xml"
    malformed.write_text("<DATA_IMPORT><PLAN_SET>", encoding="utf-8")
    empty = tmp_path / "empty.xml"
    empty.write_text("", encoding="utf-8")
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("<DATA_IMPORT />", encoding="utf-8")

    with pytest.raises(XmlLoadError, match="Malformed XML"):
        load_xml_file(malformed)
    with pytest.raises(XmlLoadError, match="Empty XML file"):
        load_xml_file(empty)
    with pytest.raises(XmlLoadError, match="Unsupported file type"):
        load_xml_file(unsupported)


def test_unknown_object_types_become_other_nodes():
    graph = GraphBuilder().build_from_paths([FIXTURES / "unknown_object.xml"])

    partner = next(node for node in graph.nodes if node.label == "Partner Mapping")

    assert partner.type == "Other"


def test_exported_graph_json_matches_expected_schema():
    graph = GraphBuilder().build_from_paths([FIXTURES / "minimal_plan.xml"]).to_dict()
    reloaded = json.loads(json.dumps(graph))

    assert set(reloaded) == {"nodes", "links"}
    assert all(
        set(node) == {"id", "label", "type", "sourceFile", "xmlPath", "rawXml", "metadata"}
        for node in reloaded["nodes"]
    )
    assert all(
        set(link) == {"source", "target", "relationship", "confidence", "metadata"}
        for link in reloaded["links"]
    )


def test_duplicate_object_ids_are_stable_non_colliding_and_recorded():
    graph = GraphBuilder().build_from_paths([FIXTURES / "duplicate_ids.xml"])
    duplicate_nodes = [node for node in graph.nodes if node.metadata.get("sourceId") == "DUP-1"]

    assert len(duplicate_nodes) == 2
    assert len({node.id for node in duplicate_nodes}) == 2
    assert any(node.metadata.get("duplicateKey") for node in duplicate_nodes)
