from pathlib import Path

import pytest

from sap_im_config_graph_explorer.graph_builder import GraphBuilder, SnapshotInput
from sap_im_config_graph_explorer.object_extractors import default_registry


FIXTURES = Path(__file__).parent / "fixtures"


def test_default_registry_uses_domain_extractors_in_integration_order():
    assert [
        type(extractor).__name__ for extractor in default_registry().extractors
    ] == [
        "PlanExtractor",
        "PlanComponentExtractor",
        "CreditRuleExtractor",
        "MeasurementRuleExtractor",
        "IncentiveRuleExtractor",
        "DepositRuleExtractor",
        "FallbackRuleExtractor",
        "FormulaExtractor",
        "PrimaryObjectExtractor",
        "AuxiliaryObjectExtractor",
    ]


def test_resolver_emits_real_stable_links_for_explicit_candidates():
    graph = GraphBuilder().build_from_paths([FIXTURES / "minimal_plan.xml"])
    node_ids = {node.id for node in graph.nodes}

    assert all(link.source in node_ids and link.target in node_ids for link in graph.links)
    assert all(link.id.startswith("link-") for link in graph.links)
    assert len({link.id for link in graph.links}) == len(graph.links)
    assert sum(link.relationship == "uses_formula" for link in graph.links) == 1
    assert sum(link.relationship == "belongs_to_plan" for link in graph.links) == 1
    assert (
        sum(link.relationship == "belongs_to_plan_component" for link in graph.links)
        == 1
    )
    assert not {
        finding.code
        for finding in graph.findings
        if finding.code in {"missing_reference", "ambiguous_reference"}
    }


def test_missing_and_ambiguous_references_become_findings_not_links():
    graph = GraphBuilder().build_from_paths(
        [FIXTURES / "reference_resolution.xml"]
    )

    assert {"missing_reference", "ambiguous_reference"} <= {
        finding.code for finding in graph.findings
    }
    assert all(finding.id.startswith("finding-") for finding in graph.findings)
    assert graph.links == []


def test_reference_resolution_is_scoped_to_each_snapshot():
    xml = b"""<DATA_IMPORT>
    <FORMULA NAME="Uses Gate"><VARIABLE_REF NAME="Gate" /></FORMULA>
    <VARIABLE NAME="Gate" />
    </DATA_IMPORT>"""
    graph = GraphBuilder().build_snapshots(
        [
            SnapshotInput("non-prod", "non_production", [("np.xml", xml)]),
            SnapshotInput("prod", "production", [("prod.xml", xml)]),
        ]
    )
    node_by_id = {node.id: node for node in graph.nodes}

    assert [snapshot.id for snapshot in graph.snapshots] == ["non-prod", "prod"]
    assert len(graph.links) == 2
    assert not {
        finding.code
        for finding in graph.findings
        if finding.code in {"missing_reference", "ambiguous_reference"}
    }
    assert all(
        node_by_id[link.source].snapshotId == node_by_id[link.target].snapshotId
        for link in graph.links
    )


def test_snapshot_ids_must_be_unique():
    with pytest.raises(ValueError, match="Snapshot IDs must be unique"):
        GraphBuilder().build_snapshots(
            [
                SnapshotInput("same", "non_production", []),
                SnapshotInput("same", "production", []),
            ]
        )
