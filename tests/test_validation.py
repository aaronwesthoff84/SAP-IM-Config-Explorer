from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import GraphLink, GraphNode, ValidationFinding
from sap_im_config_graph_explorer.validation import ValidationEngine


def _node(
    node_id: str,
    canonical_key: str,
    node_type: str,
    snapshot_id: str = "configuration",
) -> GraphNode:
    return GraphNode(
        id=node_id,
        canonicalKey=canonical_key,
        snapshotId=snapshot_id,
        label=node_id,
        type=node_type,
        sourceFile=f"{snapshot_id}.xml",
        xmlPath=f"/DATA_IMPORT[1]/{node_id}[1]",
        rawXml=f'<{node_type} />',
    )


def _link(source: str, target: str, relationship: str) -> GraphLink:
    return GraphLink(
        id=f"link-{source}-{target}",
        source=source,
        target=target,
        relationship=relationship,
        confidence="high",
    )


def test_duplicate_detector_is_snapshot_scoped_and_reports_every_duplicate_instance():
    nodes = [
        _node("formula-a", "formula:duplicate", "Formula"),
        _node("formula-b", "formula:duplicate", "Formula"),
        _node("formula-prod", "formula:duplicate", "Formula", "production"),
    ]

    findings = ValidationEngine().validate(nodes, [], [])
    duplicates = [finding for finding in findings if finding.code == "duplicate_object"]

    assert len(duplicates) == 1
    assert duplicates[0].severity == "warning"
    assert duplicates[0].snapshotId == "configuration"
    assert duplicates[0].nodeIds == ("formula-a", "formula-b")
    assert duplicates[0].details == {
        "canonicalKey": "formula:duplicate",
        "nodeCount": 2,
        "sourceFiles": ["configuration.xml"],
    }


def test_unused_and_orphaned_detectors_share_indexes_but_keep_distinct_meaning():
    nodes = [
        _node("plan", "plan:enterprise", "Plan"),
        _node("component", "plancomponent:core", "PlanComponent"),
        _node("rule", "rule:credit", "Rule"),
        _node("formula", "formula:eligibility", "Formula"),
        _node("orphan", "variable:orphan", "Variable"),
    ]
    links = [
        _link("component", "plan", "belongs_to_plan"),
        _link("rule", "component", "belongs_to_plan_component"),
        _link("rule", "formula", "uses_formula"),
    ]

    findings = ValidationEngine().validate(nodes, links, [])
    unused = {finding.nodeIds[0] for finding in findings if finding.code == "unused_object"}
    orphaned = {
        finding.nodeIds[0] for finding in findings if finding.code == "orphaned_object"
    }

    assert unused == {"component", "rule", "orphan"}
    assert orphaned == {"orphan"}
    assert "plan" not in unused
    assert "formula" not in unused


def test_reference_resolution_findings_remain_the_canonical_broken_reference_signal():
    existing = ValidationFinding(
        id="finding-missing",
        code="missing_reference",
        severity="error",
        snapshotId="configuration",
        nodeIds=("formula",),
        message="Missing Variable reference: Gate",
    )

    findings = ValidationEngine().validate(
        [_node("formula", "formula:uses-gate", "Formula")],
        [],
        [existing],
    )

    assert findings[0] is existing
    assert {finding.code for finding in findings} >= {"missing_reference"}


def test_validation_findings_are_stable_and_graph_builder_runs_the_engine():
    nodes = [
        _node("formula-a", "formula:duplicate", "Formula"),
        _node("formula-b", "formula:duplicate", "Formula"),
    ]
    engine = ValidationEngine()

    first = engine.validate(nodes, [], [])
    second = engine.validate(nodes, [], [])
    assert [finding.to_dict() for finding in first] == [
        finding.to_dict() for finding in second
    ]

    graph = GraphBuilder().build_from_paths(["tests/fixtures/duplicate_ids.xml"])
    assert any(finding.code == "duplicate_object" for finding in graph.findings)
