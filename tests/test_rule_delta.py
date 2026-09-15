from __future__ import annotations

import pytest
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import (
    GraphDocument,
    GraphLink,
    GraphNode,
    Snapshot,
)
from sap_im_config_graph_explorer.rule_delta import (
    FormulaExprNode,
    FormulaAstParser,
    FormulaAstComparator,
    DownstreamImpactAnalyzer,
    format_ast,
)
from sap_im_config_graph_explorer.comparator import ConfigComparator


SAMPLE_FORMULA_BASELINE = """<FORMULA NAME="Commission_Calc" RETURN_TYPE="DECIMAL">
    <EXPRESSION>
        <MATH_OPERATION TYPE="MULTIPLY">
            <LOOKUP_TABLE_REF NAME="Attainment_Rates" FIELD="RATE"/>
            <VARIABLE_REF NAME="Eligible_Sales"/>
        </MATH_OPERATION>
    </EXPRESSION>
</FORMULA>"""

SAMPLE_FORMULA_CANDIDATE_OP_CHANGE = """<FORMULA NAME="Commission_Calc" RETURN_TYPE="DECIMAL">
    <EXPRESSION>
        <MATH_OPERATION TYPE="ADD">
            <LOOKUP_TABLE_REF NAME="Attainment_Rates" FIELD="RATE"/>
            <VARIABLE_REF NAME="Eligible_Sales"/>
        </MATH_OPERATION>
    </EXPRESSION>
</FORMULA>"""

SAMPLE_FORMULA_CANDIDATE_REF_CHANGE = """<FORMULA NAME="Commission_Calc" RETURN_TYPE="DECIMAL">
    <EXPRESSION>
        <MATH_OPERATION TYPE="MULTIPLY">
            <LOOKUP_TABLE_REF NAME="Accelerated_Rates" FIELD="RATE"/>
            <VARIABLE_REF NAME="Eligible_Sales"/>
        </MATH_OPERATION>
    </EXPRESSION>
</FORMULA>"""

SAMPLE_FORMULA_CANDIDATE_CONST_CHANGE = """<FORMULA NAME="Commission_Calc" RETURN_TYPE="DECIMAL">
    <EXPRESSION>
        <MATH_OPERATION TYPE="MULTIPLY">
            <LITERAL VALUE="0.08" TYPE="DECIMAL"/>
            <VARIABLE_REF NAME="Eligible_Sales"/>
        </MATH_OPERATION>
    </EXPRESSION>
</FORMULA>"""

SAMPLE_RULE_WITH_CONDITION_BASELINE = """<RULE NAME="Direct_Sales_Rule" TYPE="COMMISSION">
    <CONDITION>
        <EXPRESSION>
            <MATH_OPERATION TYPE="GREATER_THAN">
                <VARIABLE_REF NAME="Attainment_Pct"/>
                <LITERAL VALUE="1.0" TYPE="DECIMAL"/>
            </MATH_OPERATION>
        </EXPRESSION>
    </CONDITION>
    <ACTION>
        <CALCULATION>
            <MATH_OPERATION TYPE="MULTIPLY">
                <VARIABLE_REF NAME="Eligible_Sales"/>
                <LITERAL VALUE="0.05" TYPE="DECIMAL"/>
            </MATH_OPERATION>
        </CALCULATION>
    </ACTION>
</RULE>"""

SAMPLE_RULE_WITH_CONDITION_CANDIDATE = """<RULE NAME="Direct_Sales_Rule" TYPE="COMMISSION">
    <CONDITION>
        <EXPRESSION>
            <MATH_OPERATION TYPE="GREATER_THAN_OR_EQUAL">
                <VARIABLE_REF NAME="Attainment_Pct"/>
                <LITERAL VALUE="0.9" TYPE="DECIMAL"/>
            </MATH_OPERATION>
        </EXPRESSION>
    </CONDITION>
    <ACTION>
        <CALCULATION>
            <MATH_OPERATION TYPE="MULTIPLY">
                <VARIABLE_REF NAME="Eligible_Sales"/>
                <LITERAL VALUE="0.08" TYPE="DECIMAL"/>
            </MATH_OPERATION>
        </CALCULATION>
    </ACTION>
</RULE>"""


def test_formula_ast_parser_parses_math_operations():
    parser = FormulaAstParser()
    ast = parser.parse(SAMPLE_FORMULA_BASELINE)
    assert ast is not None
    assert ast.node_type == "FORMULA"
    assert len(ast.children) == 1
    expr = ast.children[0]
    assert expr.node_type == "EXPRESSION"
    math_op = expr.children[0]
    assert math_op.node_type == "MATH_OPERATION"
    assert math_op.operator == "MULTIPLY"
    assert len(math_op.children) == 2
    assert math_op.children[0].node_type == "LOOKUP_TABLE_REF"
    assert math_op.children[0].name == "Attainment_Rates"
    assert math_op.children[0].field == "RATE"
    assert math_op.children[1].node_type == "VARIABLE_REF"
    assert math_op.children[1].name == "Eligible_Sales"


def test_formula_ast_formatter_produces_readable_expression():
    parser = FormulaAstParser()
    ast = parser.parse(SAMPLE_FORMULA_BASELINE)
    expr_str = format_ast(ast)
    assert "MULTIPLY" in expr_str or "*" in expr_str
    assert "Attainment_Rates" in expr_str
    assert "Eligible_Sales" in expr_str


def test_formula_ast_comparator_detects_operator_change():
    comparator = FormulaAstComparator()
    diffs = comparator.diff_xml(SAMPLE_FORMULA_BASELINE, SAMPLE_FORMULA_CANDIDATE_OP_CHANGE, formula_name="Commission_Calc")
    assert len(diffs) >= 1
    op_diff = next((d for d in diffs if d.changeType == "operator_modified"), None)
    assert op_diff is not None
    assert "MULTIPLY" in op_diff.baselineExpression or "MULTIPLY" in op_diff.detail
    assert "ADD" in op_diff.candidateExpression or "ADD" in op_diff.detail


def test_formula_ast_comparator_detects_reference_change():
    comparator = FormulaAstComparator()
    diffs = comparator.diff_xml(SAMPLE_FORMULA_BASELINE, SAMPLE_FORMULA_CANDIDATE_REF_CHANGE, formula_name="Commission_Calc")
    assert len(diffs) >= 1
    ref_diff = next((d for d in diffs if d.changeType == "reference_modified"), None)
    assert ref_diff is not None
    assert "Attainment_Rates" in ref_diff.detail
    assert "Accelerated_Rates" in ref_diff.detail


def test_formula_ast_comparator_detects_constant_shift():
    comparator = FormulaAstComparator()
    diffs = comparator.diff_xml(SAMPLE_FORMULA_BASELINE, SAMPLE_FORMULA_CANDIDATE_CONST_CHANGE, formula_name="Commission_Calc")
    assert len(diffs) >= 1
    assert any(d.changeType in ("constant_modified", "structure_modified") for d in diffs)


def test_formula_ast_comparator_detects_rule_condition_and_action_changes():
    comparator = FormulaAstComparator()
    diffs = comparator.diff_xml(SAMPLE_RULE_WITH_CONDITION_BASELINE, SAMPLE_RULE_WITH_CONDITION_CANDIDATE, formula_name="Direct_Sales_Rule")
    assert len(diffs) >= 1
    types = {d.changeType for d in diffs}
    assert any(t in types for t in ("operator_modified", "constant_modified", "condition_modified"))


def test_downstream_impact_analyzer_traces_rule_to_component_and_plan():
    # Build graph: Rule -> PlanComponent -> Plan
    rule = GraphNode(id="r1", type="Rule", label="Direct Commission", sourceFile="test.xml", xmlPath="/RULE", rawXml="", metadata={"ruleSubtype": "COMMISSION"})
    comp = GraphNode(id="pc1", type="PlanComponent", label="Sales Comp", sourceFile="test.xml", xmlPath="/PC", rawXml="", metadata={})
    plan = GraphNode(id="p1", type="Plan", label="Enterprise Sales 2026", sourceFile="test.xml", xmlPath="/PLAN", rawXml="", metadata={})
    
    link1 = GraphLink(id="l1", source="r1", target="pc1", relationship="belongs_to_plan_component", confidence="high")
    link2 = GraphLink(id="l2", source="pc1", target="p1", relationship="belongs_to_plan", confidence="high")
    
    graph = GraphDocument(
        schemaVersion="1.0.0",
        snapshots=[Snapshot(id="candidate", role="non_production")],
        nodes=[rule, comp, plan],
        links=[link1, link2],
    )
    
    analyzer = DownstreamImpactAnalyzer()
    report = analyzer.analyze_blast_radius(rule, graph)
    
    assert report.impactedPlansCount == 1
    assert report.impactedComponentsCount == 1
    impacted_ids = {n.id for n in report.impactedNodes}
    assert "pc1" in impacted_ids
    assert "p1" in impacted_ids
    assert report.severity in ("medium", "high")


def test_downstream_impact_analyzer_traces_pipeline_and_deposit_severity():
    # Build pipeline: Credit Rule -> Primary Measurement -> Commission -> Deposit
    r_cred = GraphNode(id="r_cred", type="Rule", label="Credit Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="", metadata={"ruleSubtype": "DIRECT_TRANSACTION_CREDIT"})
    r_pm = GraphNode(id="r_pm", type="Rule", label="PM Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="", metadata={"ruleSubtype": "PRIMARY_MEASUREMENT"})
    r_comm = GraphNode(id="r_comm", type="Rule", label="Comm Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="", metadata={"ruleSubtype": "COMMISSION"})
    r_dep = GraphNode(id="r_dep", type="Rule", label="Dep Rule", sourceFile="test.xml", xmlPath="/RULE", rawXml="", metadata={"ruleSubtype": "DEPOSIT"})
    
    # 5 plans for critical severity
    plans = [GraphNode(id=f"plan_{i}", type="Plan", label=f"Plan {i}", sourceFile="test.xml", xmlPath="/PLAN", rawXml="") for i in range(5)]
    pcs = [GraphNode(id=f"pc_{i}", type="PlanComponent", label=f"PC {i}", sourceFile="test.xml", xmlPath="/PC", rawXml="") for i in range(5)]
    
    links = [
        GraphLink(id="l_pipe1", source="r_pm", target="r_cred", relationship="uses_rule", confidence="high"),
        GraphLink(id="l_pipe2", source="r_comm", target="r_pm", relationship="uses_rule", confidence="high"),
        GraphLink(id="l_pipe3", source="r_comm", target="r_dep", relationship="feeds_deposit", confidence="high"),
    ]
    for i in range(5):
        links.append(GraphLink(id=f"l_pc_{i}", source="r_cred", target=f"pc_{i}", relationship="belongs_to_plan_component", confidence="high"))
        links.append(GraphLink(id=f"l_p_{i}", source=f"pc_{i}", target=f"plan_{i}", relationship="belongs_to_plan", confidence="high"))

    all_nodes = [r_cred, r_pm, r_comm, r_dep] + plans + pcs
    graph = GraphDocument(
        schemaVersion="1.0.0",
        snapshots=[Snapshot(id="candidate", role="non_production")],
        nodes=all_nodes,
        links=links,
    )
    
    analyzer = DownstreamImpactAnalyzer()
    report = analyzer.analyze_blast_radius(r_cred, graph)
    
    assert report.severity == "critical"
    assert report.impactedPlansCount >= 5
    assert report.impactedDepositRulesCount >= 1


def test_config_comparator_integrates_formula_differences_and_blast_radius():
    baseline_xml = """<DATA_IMPORT VERSION="16.0">
        <PLAN_SET><PLAN NAME="Sales Plan"><COMPONENT_REF NAME="Sales Comp"/></PLAN></PLAN_SET>
        <PLANCOMPONENT_SET><PLANCOMPONENT NAME="Sales Comp"><RULE_REF NAME="Sales Rule"/></PLANCOMPONENT></PLANCOMPONENT_SET>
        <RULE_SET><RULE NAME="Sales Rule" TYPE="COMMISSION"><FORMULA_REF NAME="Commission_Calc"/></RULE></RULE_SET>
        <FORMULA_SET>
            <FORMULA NAME="Commission_Calc">
                <EXPRESSION>
                    <MATH_OPERATION TYPE="MULTIPLY">
                        <LOOKUP_TABLE_REF NAME="Attainment_Rates" FIELD="RATE"/>
                        <VARIABLE_REF NAME="Eligible_Sales"/>
                    </MATH_OPERATION>
                </EXPRESSION>
            </FORMULA>
        </FORMULA_SET>
    </DATA_IMPORT>"""

    candidate_xml = """<DATA_IMPORT VERSION="16.0">
        <PLAN_SET><PLAN NAME="Sales Plan"><COMPONENT_REF NAME="Sales Comp"/></PLAN></PLAN_SET>
        <PLANCOMPONENT_SET><PLANCOMPONENT NAME="Sales Comp"><RULE_REF NAME="Sales Rule"/></PLANCOMPONENT></PLANCOMPONENT_SET>
        <RULE_SET><RULE NAME="Sales Rule" TYPE="COMMISSION"><FORMULA_REF NAME="Commission_Calc"/></RULE></RULE_SET>
        <FORMULA_SET>
            <FORMULA NAME="Commission_Calc">
                <EXPRESSION>
                    <MATH_OPERATION TYPE="ADD">
                        <LOOKUP_TABLE_REF NAME="Attainment_Rates" FIELD="RATE"/>
                        <VARIABLE_REF NAME="Eligible_Sales"/>
                    </MATH_OPERATION>
                </EXPRESSION>
            </FORMULA>
        </FORMULA_SET>
    </DATA_IMPORT>"""

    comparator = ConfigComparator(topology_mode="full")
    result = comparator.compare_xml_texts(baseline_xml, candidate_xml)
    
    assert result.ok is True
    assert len(result.changed) >= 1
    
    changed_formula = next((c for c in result.changed if c.type == "Formula"), None)
    assert changed_formula is not None
    assert len(changed_formula.formulaDifferences) >= 1
    assert changed_formula.formulaDifferences[0].changeType == "operator_modified"
    assert changed_formula.blastRadius is not None
    assert changed_formula.blastRadius.score > 0
    impacted_labels = {node.label for node in changed_formula.blastRadius.impactedNodes}
    assert "Sales Rule" in impacted_labels or "Sales Comp" in impacted_labels or "Sales Plan" in impacted_labels
