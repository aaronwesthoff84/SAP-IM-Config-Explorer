from __future__ import annotations

from pathlib import Path
import pytest

from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import (
    GraphLink,
    GraphNode,
    SimulationEvent,
    SimulationStep,
    SimulationTrace,
)
from sap_im_config_graph_explorer.rule_delta import FormulaExprNode
from sap_im_config_graph_explorer.simulator import (
    CompensationRuleSimulator,
    SafeAstEvaluator,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_safe_ast_evaluator_basic_math():
    evaluator = SafeAstEvaluator()

    # Addition: 10 + 20 = 30
    add_ast = FormulaExprNode(
        node_type="MATH_OPERATION",
        operator="ADD",
        children=(
            FormulaExprNode(node_type="LITERAL", value="10"),
            FormulaExprNode(node_type="LITERAL", value="20"),
        ),
    )
    assert evaluator.evaluate(add_ast, {}) == 30.0

    # Multiplication: 5 * 4 = 20
    mult_ast = FormulaExprNode(
        node_type="MATH_OPERATION",
        operator="MULTIPLY",
        children=(
            FormulaExprNode(node_type="LITERAL", value="5"),
            FormulaExprNode(node_type="LITERAL", value="4"),
        ),
    )
    assert evaluator.evaluate(mult_ast, {}) == 20.0

    # Safe division by zero
    div_zero_ast = FormulaExprNode(
        node_type="MATH_OPERATION",
        operator="DIVIDE",
        children=(
            FormulaExprNode(node_type="LITERAL", value="100"),
            FormulaExprNode(node_type="LITERAL", value="0"),
        ),
    )
    assert evaluator.evaluate(div_zero_ast, {}) == 0.0


def test_safe_ast_evaluator_functions_and_variables():
    evaluator = SafeAstEvaluator()
    ctx = {"amount": 100000.0, "quota": 100000.0, "credit": 100000.0, "attainment": 1.0}

    # Variable lookup
    var_ast = FormulaExprNode(node_type="VARIABLE_REF", name="credit")
    assert evaluator.evaluate(var_ast, ctx) == 100000.0

    # Min function: MIN(credit, quota)
    min_ast = FormulaExprNode(
        node_type="FUNCTION",
        name="MIN",
        children=(
            FormulaExprNode(node_type="VARIABLE_REF", name="credit"),
            FormulaExprNode(node_type="VARIABLE_REF", name="quota"),
        ),
    )
    assert evaluator.evaluate(min_ast, ctx) == 100000.0

    # Ternary / IF function
    if_ast = FormulaExprNode(
        node_type="FUNCTION",
        name="IF",
        children=(
            FormulaExprNode(node_type="LITERAL", value="1"),  # condition true
            FormulaExprNode(node_type="LITERAL", value="500"),
            FormulaExprNode(node_type="LITERAL", value="100"),
        ),
    )
    assert evaluator.evaluate(if_ast, ctx) == 500.0


def test_simulator_full_pipeline_known_order():
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_known_order.xml"])

    simulator = CompensationRuleSimulator.from_graph_document(graph)

    # Standard sale: $100,000, 100% quota, 1.0 split
    event = SimulationEvent(
        eventType="DirectSale",
        amount=100000.0,
        participant="REP_001",
        period="2026-01",
        quota=100000.0,
        creditSplit=1.0,
    )

    trace = simulator.simulate(event)

    assert trace.ok is True
    assert trace.status == "completed"
    assert trace.totalCredited == 100000.0
    assert trace.totalIncentive > 0.0
    assert trace.finalDeposit > 0.0
    assert len(trace.steps) == 6

    stages = [s.stage for s in trace.steps]
    assert stages == [
        "Crediting",
        "Primary Measurement",
        "Secondary Measurement",
        "Incentive / Calculation",
        "Incentive / Calculation",
        "Deposit",
    ]


def test_simulator_over_quota_accelerator():
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_known_order.xml"])

    simulator = CompensationRuleSimulator.from_graph_document(graph)

    # Over-quota sale: $150,000 on $100,000 quota
    event = SimulationEvent(
        eventType="DirectSale",
        amount=150000.0,
        participant="TOP_PERFORMER",
        period="2026-01",
        quota=100000.0,
        creditSplit=1.0,
    )

    trace = simulator.simulate(event)

    assert trace.ok is True
    assert trace.totalCredited == 150000.0
    # Secondary measurement should reflect tier 3 (1.25x)
    sec_step = next(s for s in trace.steps if s.stage == "Secondary Measurement")
    assert sec_step.output == 1.25

    # Total incentive should include both standard ($100k * 0.10 * 1.25 = $12,500) and accelerator ($50k * 0.15 * 1.25 = $9,375)
    assert trace.totalIncentive == 21875.0
    assert trace.finalDeposit == 21875.0


def test_simulator_split_commission():
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_known_order.xml"])

    simulator = CompensationRuleSimulator.from_graph_document(graph)

    # Split commission: $50,000 sale, 50% split (0.5)
    event = SimulationEvent(
        eventType="DirectSale",
        amount=50000.0,
        participant="TEAM_REP_A",
        period="2026-01",
        quota=100000.0,
        creditSplit=0.5,
    )

    trace = simulator.simulate(event)

    assert trace.ok is True
    assert trace.totalCredited == 25000.0
    credit_step = next(s for s in trace.steps if s.stage == "Crediting")
    assert credit_step.output == 25000.0


def test_simulator_step_limit_safety():
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_known_order.xml"])

    simulator = CompensationRuleSimulator.from_graph_document(graph)

    # Restrict max steps to 2
    event = SimulationEvent(amount=100000.0, quota=100000.0)
    trace = simulator.simulate(event, max_steps=2)

    assert trace.ok is False
    assert trace.status == "max_steps_exceeded"
    assert len(trace.steps) == 2
    assert "maximum step limit" in trace.error


def test_simulator_empty_rules():
    simulator = CompensationRuleSimulator(nodes=[], links=[])
    trace = simulator.simulate()

    assert trace.ok is True
    assert trace.status == "no_rules_found"
    assert len(trace.steps) == 0


def test_simulator_api_endpoint():
    from fastapi.testclient import TestClient
    from sap_im_config_graph_explorer.app import app

    client = TestClient(app)
    builder = GraphBuilder(topology_mode="full")
    graph = builder.build_from_paths([FIXTURES / "pipeline_known_order.xml"])

    response = client.post(
        "/api/simulator/run",
        json={
            "event": {
                "eventType": "DirectSale",
                "amount": 120000.0,
                "quota": 100000.0,
                "participant": "SIM_USER",
            },
            "graph": graph.to_dict(),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "completed"
    assert len(data["steps"]) == 6
    assert data["totalCredited"] == 120000.0
    assert data["finalDeposit"] > 0.0

