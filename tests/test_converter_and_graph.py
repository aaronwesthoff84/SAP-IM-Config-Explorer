import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from sap_im_config_graph_explorer.graph_builder import (
    CORE_GRAPH_NODE_TYPES,
    GraphBuilder,
)
from sap_im_config_graph_explorer.models import NODE_TYPES, RELATIONSHIP_TYPES
from sap_im_config_graph_explorer.xml_loader import XmlLoadError, load_xml_file
from sap_im_config_graph_explorer.xml_to_html_converter import Transformer, render_action


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
HTML_SORTING_FIXTURE = FIXTURES / "html_sorting_comparison.xml"


def full_graph_builder() -> GraphBuilder:
    return GraphBuilder(
        node_types=NODE_TYPES,
        relationship_types=RELATIONSHIP_TYPES,
    )


def test_xml_to_html_conversion_still_emits_plan_summary():
    transformer = Transformer()

    transformer.parse(str(FIXTURES / "minimal_plan.xml"))
    html = transformer.html()

    assert "<!DOCTYPE HTML>" in html
    assert "SAP Incentive Management Plan Summary" in html
    assert "Enterprise Plan" in html
    assert html.index("Plans (1)") < html.index("Plan Components (1)")
    assert html.index("Plan Components (1)") < html.index("Rules (1)")
    assert html.index("Rules (1)") < html.index("Formulas (1)")
    assert html.index("Formulas (1)") < html.index("Variables (0)")
    assert html.index("Variables (0)") < html.index("Lookup Tables (1)")
    assert html.index("Lookup Tables (1)") < html.index("Quotas (0)")
    assert html.index("Quotas (0)") < html.index("Territories (0)")
    assert html.index("Territories (0)") < html.index("Fixed Values (0)")
    assert html.count('class="SummaryCell"') == 27
    assert ">Copyright<" not in html


def test_html_sorts_objects_by_name_and_rules_by_category_then_name():
    transformer = Transformer()
    transformer.parse(str(HTML_SORTING_FIXTURE))
    html = transformer.html()

    assert html.index('name="Alpha Plan-plan"') < html.index('name="Zulu Plan-plan"')
    assert html.index('name="Alpha Component-plan-Alpha Plan"') < html.index(
        'name="Zeta Component-plan-Alpha Plan"'
    )

    ordered_rule_anchors = [
        'name="Alpha Credit-rule-Alpha Component-Alpha Plan"',
        'name="Zulu Credit-rule-Zeta Component-Alpha Plan"',
        'name="Beta Measurement-rule-Zeta Component-Alpha Plan"',
        'name="Alpha Incentive-rule-Zeta Component-Alpha Plan"',
        'name="Zulu Deposit-rule-Alpha Component-Alpha Plan"',
        'name="Alpha Detailed Deposit-rule-Alpha Component-Alpha Plan"',
    ]
    assert [html.index(anchor) for anchor in ordered_rule_anchors] == sorted(
        html.index(anchor) for anchor in ordered_rule_anchors
    )

    for first_anchor, second_anchor in [
        ('name="Alpha Lookup-mdlt"', 'name="Zulu Lookup-mdlt"'),
        ('name="Alpha Fixed-fv"', 'name="Zulu Fixed-fv"'),
        ('name="Alpha Quota-quota"', 'name="Zulu Quota-quota"'),
        ('name="Alpha Formula-formula"', 'name="Zulu Formula-formula"'),
        ('name="Alpha Territory-terr"', 'name="Zulu Territory-terr"'),
        ('name="Alpha Variable-var"', 'name="Zulu Variable-var"'),
    ]:
        assert html.index(first_anchor) < html.index(second_anchor)

    summary_rules = html[html.index("Rules (6)"):html.index("Formulas (2)")]
    for first_name, second_name in zip(
        ["Alpha Credit", "Zulu Credit", "Beta Measurement", "Alpha Incentive", "Zulu Deposit"],
        ["Zulu Credit", "Beta Measurement", "Alpha Incentive", "Zulu Deposit", "Alpha Detailed Deposit"],
    ):
        assert summary_rules.index(f">{first_name}</a>") < summary_rules.index(f">{second_name}</a>")


def test_rule_actions_omit_null_generic_values():
    action = ET.fromstring(
        """<FUNCTION ID="DIRECT_TRANSACTION_CREDIT_ALLGAs">
  <STRING_LITERAL>NULL</STRING_LITERAL>
  <VALUE DECIMAL_VALUE="NULL" />
  <DATE_LITERAL>NULL</DATE_LITERAL>
  <BOOLEAN VALUE="NULL" />
  <STRING_LITERAL>Keep attribute</STRING_LITERAL>
  <VALUE DECIMAL_VALUE="5" UNIT_TYPE="USD" />
  <DATE_LITERAL>2026-01-01</DATE_LITERAL>
  <BOOLEAN VALUE="true" />
</FUNCTION>"""
    )

    html = render_action(action)

    assert "NULL" not in html
    assert "Keep attribute" in html
    assert "5 USD" in html
    assert "2026-01-01" in html
    assert "true" in html


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
    type_by_label = {node["label"]: node["type"] for node in graph["nodes"]}
    relationships = {link["relationship"] for link in graph["links"]}

    assert labels == {
        "Enterprise Plan",
        "Core Component",
        "Credit Rule",
    }
    assert type_by_label["Core Component"] == "PlanComponent"
    assert relationships == {"belongs_to_plan", "belongs_to_plan_component"}
    assert not graph["findings"]
    assert {node["type"] for node in graph["nodes"]} == CORE_GRAPH_NODE_TYPES
    assert all(node["type"] in NODE_TYPES for node in graph["nodes"])
    assert all(link["relationship"] in RELATIONSHIP_TYPES for link in graph["links"])


def test_phase_one_acceptance_covers_exact_allowlist_and_no_logic_nodes():
    graph = full_graph_builder().build_from_paths(
        [FIXTURES / "extractor_families.xml", FIXTURES / "minimal_plan.xml"]
    )
    node_ids = {node.id for node in graph.nodes}

    assert {node.type for node in graph.nodes} == NODE_TYPES
    assert all(link.source in node_ids and link.target in node_ids for link in graph.links)
    assert not any(
        node.metadata.get("tag") in {"FUNCTION", "PARAMETER_LIST"}
        for node in graph.nodes
    )
    assert [snapshot.to_dict() for snapshot in graph.snapshots] == [
        {
            "id": "configuration",
            "role": "configuration",
            "sourceFiles": ["extractor_families.xml", "minimal_plan.xml"],
        }
    ]


def test_multiple_xml_files_merge_and_preserve_source_file():
    graph = full_graph_builder().build_from_paths(
        [FIXTURES / "minimal_plan.xml", FIXTURES / "duplicate_ids.xml"]
    )

    source_files = {node.sourceFile for node in graph.nodes}

    assert {"minimal_plan.xml", "duplicate_ids.xml"} <= source_files
    assert any(node.label == "Duplicate Formula A" for node in graph.nodes)


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


def test_unknown_object_types_are_ignored():
    graph = GraphBuilder().build_from_paths([FIXTURES / "unknown_object.xml"])

    assert graph.nodes == []
    assert graph.links == []


def test_formula_logic_elements_do_not_become_graph_nodes(tmp_path):
    source = tmp_path / "formula_logic.xml"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT VERSION="16.0">
  <FORMULA_SET>
    <FORMULA NAME="Commission Gate" RETURN_TYPE="Boolean">
      <EXPRESSION>
        <FUNCTION ID="ifThenElse">
          <PARAMETER_LIST>
            <BOOLEAN VALUE="true" />
            <FUNCTION ID="isNull">
              <VARIABLE_REF NAME="Gate Variable" />
            </FUNCTION>
            <STRING VALUE="approved" />
          </PARAMETER_LIST>
        </FUNCTION>
      </EXPRESSION>
    </FORMULA>
  </FORMULA_SET>
  <VARIABLE_SET>
    <VARIABLE NAME="Gate Variable" VARIABLE_TYPE="String" />
  </VARIABLE_SET>
</DATA_IMPORT>
""",
        encoding="utf-8",
    )

    graph = full_graph_builder().build_from_paths([source])

    assert {node.label for node in graph.nodes} == {"Commission Gate", "Gate Variable"}
    assert {node.type for node in graph.nodes} == {"Formula", "Variable"}


def test_exported_graph_json_matches_expected_schema():
    graph = GraphBuilder().build_from_paths([FIXTURES / "minimal_plan.xml"]).to_dict()
    reloaded = json.loads(json.dumps(graph))

    assert set(reloaded) == {"schemaVersion", "snapshots", "nodes", "links", "findings"}
    assert all(
        set(node)
        == {
            "id",
            "canonicalKey",
            "snapshotId",
            "label",
            "type",
            "sourceFile",
            "xmlPath",
            "rawXml",
            "metadata",
        }
        for node in reloaded["nodes"]
    )
    assert all(
        set(link) == {"id", "source", "target", "relationship", "confidence", "metadata"}
        for link in reloaded["links"]
    )


def test_duplicate_object_ids_are_stable_non_colliding_and_recorded():
    graph = full_graph_builder().build_from_paths([FIXTURES / "duplicate_ids.xml"])
    duplicate_nodes = [node for node in graph.nodes if node.metadata.get("sourceId") == "DUP-1"]

    assert len(duplicate_nodes) == 2
    assert len({node.id for node in duplicate_nodes}) == 2
    assert any(node.metadata.get("duplicateKey") for node in duplicate_nodes)


def test_core_graph_only_resolves_plan_component_and_rule_containment(tmp_path):
    source = tmp_path / "core-topology.xml"
    source.write_text(
        """<DATA_IMPORT>
  <PLAN NAME="Plan A"><COMPONENT_REF NAME="Component A" /></PLAN>
  <PLAN_COMPONENT NAME="Component A"><RULE_REF NAME="Rule A" /></PLAN_COMPONENT>
  <RULE NAME="Rule A" TYPE="DIRECT_TRANSACTION_CREDIT">
    <RULE_ELEMENT_REF NAME="F Spiff Percentage to Pay" />
    <HOLD_REF RELEASE_TYPE="Release Immediately" />
    <CREDIT_TYPE>Compounding</CREDIT_TYPE>
  </RULE>
  <FORMULA NAME="F Spiff Percentage to Pay" />
  <CREDIT_TYPE NAME="Compounding" />
  <CREDIT_TYPE NAME="Compounding" />
</DATA_IMPORT>""",
        encoding="utf-8",
    )

    graph = GraphBuilder().build_from_paths([source])

    assert {(node.label, node.type) for node in graph.nodes} == {
        ("Plan A", "Plan"),
        ("Component A", "PlanComponent"),
        ("Rule A", "Rule"),
    }
    assert {link.relationship for link in graph.links} == {
        "belongs_to_plan",
        "belongs_to_plan_component",
    }
    assert not {
        finding.code
        for finding in graph.findings
        if finding.code in {"missing_reference", "ambiguous_reference"}
    }
