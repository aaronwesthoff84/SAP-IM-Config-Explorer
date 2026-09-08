from __future__ import annotations

from pathlib import Path
import pytest

from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import GraphNode
from sap_im_config_graph_explorer.pipeline import (
    STAGE_CREDIT,
    STAGE_DEPOSIT,
    STAGE_INCENTIVE,
    STAGE_PAYMENT,
    STAGE_PRIMARY_MEASUREMENT,
    STAGE_SECONDARY_MEASUREMENT,
    STAGE_UNKNOWN,
    classify_rule_stage,
    derive_pipeline_flow,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_classify_rule_stage_maps_standard_and_custom_types():
    # Direct credit
    node_credit = GraphNode(id="n1", type="Rule", label="Credit Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="<RULE/>", metadata={"ruleSubtype": "DIRECT_TRANSACTION_CREDIT"})
    stage, evidence = classify_rule_stage(node_credit)
    assert stage == STAGE_CREDIT
    assert "Crediting" in evidence

    # Primary measurement
    node_pm = GraphNode(id="n2", type="Rule", label="PM Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="<RULE/>", metadata={"ruleSubtype": "PRIMARY_MEASUREMENT"})
    stage, evidence = classify_rule_stage(node_pm)
    assert stage == STAGE_PRIMARY_MEASUREMENT
    assert "Primary Measurement" in evidence

    # Secondary measurement
    node_sm = GraphNode(id="n3", type="Rule", label="SM Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="<RULE/>", metadata={"ruleSubtype": "SECONDARY_MEASUREMENT"})
    stage, evidence = classify_rule_stage(node_sm)
    assert stage == STAGE_SECONDARY_MEASUREMENT

    # Incentive / Commission
    node_comm = GraphNode(id="n4", type="Rule", label="Comm Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="<RULE/>", metadata={"ruleSubtype": "COMMISSION"})
    stage, evidence = classify_rule_stage(node_comm)
    assert stage == STAGE_INCENTIVE
    assert "Incentive" in evidence

    # Deposit
    node_dep = GraphNode(id="n5", type="Rule", label="Dep Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="<RULE/>", metadata={"ruleSubtype": "DEPOSIT"})
    stage, evidence = classify_rule_stage(node_dep)
    assert stage == STAGE_DEPOSIT

    # Payment
    node_pay = GraphNode(id="n6", type="Rule", label="Pay Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="<RULE/>", metadata={"ruleSubtype": "PAYMENT"})
    stage, evidence = classify_rule_stage(node_pay)
    assert stage == STAGE_PAYMENT

    # Unmapped custom rule
    node_custom = GraphNode(id="n7", type="Rule", label="Custom Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="<RULE/>", metadata={"ruleSubtype": "CUSTOM_PLUGIN_X"})
    stage, evidence = classify_rule_stage(node_custom)
    assert stage == STAGE_UNKNOWN
    assert "does not map" in evidence


def test_derive_pipeline_flow_known_order_fixture():
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_known_order.xml"])

    flow = derive_pipeline_flow(graph)

    assert flow.ok is True
    assert flow.summary["totalSteps"] == 6
    assert flow.summary["unknownCount"] == 0
    assert flow.summary["knownCount"] > 0
    assert len(flow.availablePlans) == 1
    assert flow.availablePlans[0]["label"] == "Sales Commission Plan"

    # Verify stage groups
    stage_names = [g.stage for g in flow.stages]
    assert STAGE_CREDIT in stage_names
    assert STAGE_PRIMARY_MEASUREMENT in stage_names
    assert STAGE_SECONDARY_MEASUREMENT in stage_names
    assert STAGE_INCENTIVE in stage_names
    assert STAGE_DEPOSIT in stage_names

    # Check explicit sequence in incentive stage
    seq_transitions = [t for t in flow.transitions if t.transitionType == "explicit_sequence"]
    assert len(seq_transitions) == 1
    seq_t = seq_transitions[0]
    assert seq_t.orderStatus == "known"
    assert seq_t.sourceRuleLabel == "Standard Commission Rule"
    assert seq_t.targetRuleLabel == "Accelerator Commission Rule"
    assert "Sequence 1 precedes Sequence 2" in seq_t.sourceEvidence

    # Check stage transitions between consecutive stages
    stage_transitions = [t for t in flow.transitions if t.transitionType == "stage_transition"]
    assert len(stage_transitions) == 4
    for st in stage_transitions:
        assert st.orderStatus == "known"
        assert "calculation pipeline" in st.sourceEvidence


def test_derive_pipeline_flow_unknown_order_fixture():
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_unknown_order.xml"])

    flow = derive_pipeline_flow(graph)

    assert flow.ok is True
    assert flow.summary["totalSteps"] == 3
    assert flow.summary["unknownCount"] > 0

    # Sibling commission rules without sequence must be flagged unknown
    unknown_transitions = [t for t in flow.transitions if t.transitionType == "unknown_order"]
    assert len(unknown_transitions) >= 1

    unseq_t = next(t for t in unknown_transitions if "Commission Plan A" in t.sourceRuleLabel)
    assert unseq_t.orderStatus == "unknown"
    assert "without explicit sequence attributes" in unseq_t.sourceEvidence

    # Sibling steps marked unknown
    comm_a_step = next(s for s in flow.steps if s.label == "Commission Plan A")
    assert comm_a_step.orderStatus == "unknown"
    assert "cannot be determined" in comm_a_step.sourceEvidence


def test_derive_pipeline_flow_scoped_to_plan():
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_known_order.xml"])

    plan_node = next(n for n in graph.nodes if n.type == "Plan")
    flow = derive_pipeline_flow(graph, plan_id=plan_node.id)

    assert flow.ok is True
    assert flow.scopedPlanId == plan_node.id
    assert flow.scopedPlanLabel == "Sales Commission Plan"
    assert flow.summary["totalSteps"] == 6

    # If scoped to a nonexistent plan, 0 rules match
    empty_flow = derive_pipeline_flow(graph, plan_id="nonexistent-plan-id")
    assert empty_flow.ok is True
    assert empty_flow.summary["totalSteps"] == 0
    assert len(empty_flow.steps) == 0


def test_pipeline_flow_result_serialization():
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_known_order.xml"])

    flow = derive_pipeline_flow(graph)
    data = flow.to_dict()

    assert data["ok"] is True
    assert isinstance(data["availablePlans"], list)
    assert isinstance(data["stages"], list)
    assert isinstance(data["steps"], list)
    assert isinstance(data["transitions"], list)
    assert isinstance(data["summary"], dict)

    first_step = data["steps"][0]
    assert "id" in first_step
    assert "ruleId" in first_step
    assert "stage" in first_step
    assert "orderStatus" in first_step
    assert "sourceEvidence" in first_step
