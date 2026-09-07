from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import (
    FindingWaiver,
    GraphDocument,
    GraphLink,
    GraphNode,
    ValidationFinding,
)
from sap_im_config_graph_explorer.portable_exports import (
    PortableGraphExportError,
    graph_document_from_payload,
)
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
    assert duplicates[0].severity == "error"
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

    assert unused == {"orphan"}
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

    graph = GraphBuilder(topology_mode="full").build_from_paths(
        ["tests/fixtures/duplicate_ids.xml"]
    )
    assert any(finding.code == "duplicate_object" for finding in graph.findings)


def test_finding_waiver_model_and_graph_document_serialization():
    waiver = FindingWaiver(
        findingId="f-1",
        reason="Legacy accepted debt",
        reviewer="auditor@company.com",
        createdAt="2026-09-07T12:00:00Z",
        expiresAt="2026-12-31T00:00:00Z",
    )
    assert waiver.to_dict() == {
        "findingId": "f-1",
        "reason": "Legacy accepted debt",
        "reviewer": "auditor@company.com",
        "createdAt": "2026-09-07T12:00:00Z",
        "expiresAt": "2026-12-31T00:00:00Z",
    }

    doc_empty = GraphDocument()
    assert "waivers" not in doc_empty.to_dict()

    doc_with_waivers = GraphDocument(waivers=[waiver])
    assert doc_with_waivers.to_dict()["waivers"] == [waiver.to_dict()]


def test_graph_document_from_payload_waivers_roundtrip_and_validation():
    import json
    from pathlib import Path
    import pytest

    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "portable_export_graph.json"
        ).read_text(encoding="utf-8")
    )
    payload["waivers"] = [
        {
            "findingId": "finding-duplicate",
            "reason": "Accepted duplicate across snapshots",
            "reviewer": "alice",
            "createdAt": "2026-09-07T12:00:00Z",
            "expiresAt": None,
        }
    ]
    doc = graph_document_from_payload(payload)
    assert len(doc.waivers) == 1
    assert doc.waivers[0].findingId == "finding-duplicate"
    assert doc.waivers[0].reviewer == "alice"

    # Test duplicate waiver rejection
    payload["waivers"].append(
        {
            "findingId": "finding-duplicate",
            "reason": "Duplicate waiver id",
            "reviewer": "bob",
        }
    )
    with pytest.raises(PortableGraphExportError, match="Duplicate waiver"):
        graph_document_from_payload(payload)

