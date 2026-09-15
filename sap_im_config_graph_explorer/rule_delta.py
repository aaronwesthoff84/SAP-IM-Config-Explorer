from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import (
    BlastRadiusImpactedNode,
    BlastRadiusReport,
    FormulaDifferenceDetail,
    GraphDocument,
    GraphNode,
)
from sap_im_config_graph_explorer.pipeline import classify_rule_stage, STAGE_DEPOSIT
import defusedxml.ElementTree as DefusedET


@dataclass(frozen=True)
class FormulaExprNode:
    """Normalized Abstract Syntax Tree node for formula and rule calculation expressions."""
    node_type: str
    value: str | None = None
    operator: str | None = None
    name: str | None = None
    field: str | None = None
    children: tuple[FormulaExprNode, ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()


def _clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    s = text.strip()
    return s if s else None


class FormulaAstParser:
    """Parses XML formula and rule logic into normalized FormulaExprNode ASTs."""

    def parse(self, xml_input: str | ET.Element) -> FormulaExprNode | None:
        if isinstance(xml_input, str):
            if not xml_input.strip():
                return None
            try:
                elem = DefusedET.fromstring(xml_input.strip())
            except Exception:
                try:
                    elem = ET.fromstring(xml_input.strip())
                except Exception:
                    return None
        elif isinstance(xml_input, ET.Element):
            elem = xml_input
        else:
            return None

        return self._parse_element(elem)

    def _parse_element(self, elem: ET.Element) -> FormulaExprNode:
        tag = elem.tag.upper()
        attribs = {k.upper(): v.strip() for k, v in elem.attrib.items() if v}
        
        name = attribs.get("NAME") or attribs.get("ID")
        val = attribs.get("VALUE") or _clean_text(elem.text)
        op = attribs.get("TYPE") or attribs.get("OPERATOR") or attribs.get("OP")
        fld = attribs.get("FIELD") or attribs.get("COLUMN")

        children = tuple(
            self._parse_element(child)
            for child in elem
            if isinstance(child.tag, str) and child.tag.strip()
        )

        sorted_attrs = tuple(sorted((k, v) for k, v in attribs.items()))

        return FormulaExprNode(
            node_type=tag,
            value=val,
            operator=op,
            name=name,
            field=fld,
            children=children,
            attributes=sorted_attrs,
        )


def format_ast(node: FormulaExprNode | None) -> str:
    """Renders a human-readable mathematical or logical expression from a FormulaExprNode."""
    if node is None:
        return ""

    nt = node.node_type

    if nt == "MATH_OPERATION":
        op = node.operator or "OP"
        child_strs = [format_ast(c) for c in node.children]
        if len(child_strs) == 2:
            op_syms = {
                "ADD": "+",
                "PLUS": "+",
                "SUBTRACT": "-",
                "MINUS": "-",
                "MULTIPLY": "*",
                "DIVIDE": "/",
                "GREATER_THAN": ">",
                "GREATER_THAN_OR_EQUAL": ">=",
                "LESS_THAN": "<",
                "LESS_THAN_OR_EQUAL": "<=",
                "EQUALS": "==",
                "NOT_EQUALS": "!=",
            }
            if op in op_syms:
                return f"({child_strs[0]} {op_syms[op]} {child_strs[1]})"
        return f"{op}({', '.join(child_strs)})"

    if nt in ("LOOKUP_TABLE_REF", "LOOKUP_TABLE"):
        target = node.name or "Table"
        if node.field:
            return f"Lookup({target}.{node.field})"
        return f"Lookup({target})"

    if nt in ("VARIABLE_REF", "VARIABLE"):
        return f"Variable({node.name or node.value or ''})"

    if nt in ("LITERAL", "CONSTANT"):
        return node.value or node.name or "0"

    if nt in ("FUNCTION", "FUNC"):
        fn_name = node.name or node.operator or "FUNC"
        child_strs = [format_ast(c) for c in node.children]
        return f"{fn_name}({', '.join(child_strs)})"

    if nt == "CONDITION":
        child_strs = [format_ast(c) for c in node.children]
        return f"IF ({' AND '.join(child_strs)})"

    if nt in ("ACTION", "CALCULATION"):
        child_strs = [format_ast(c) for c in node.children]
        return f"{', '.join(child_strs)}"

    if nt == "EXPRESSION":
        if len(node.children) == 1:
            return format_ast(node.children[0])
        return f"EXPR({', '.join(format_ast(c) for c in node.children)})"

    if nt in ("FORMULA", "RULE"):
        if node.children:
            return "; ".join(format_ast(c) for c in node.children if format_ast(c))
        return f"{nt}({node.name or ''})"

    # Fallback generic
    if node.children:
        child_strs = [format_ast(c) for c in node.children]
        label = node.name or node.operator or nt
        return f"{label}({', '.join(child_strs)})"

    return node.value or node.name or nt


class FormulaAstComparator:
    """Compares two formula or rule ASTs and reports structural and semantic differences."""

    def __init__(self) -> None:
        self.parser = FormulaAstParser()

    def diff_xml(
        self,
        baseline_xml: str,
        candidate_xml: str,
        formula_name: str = "",
    ) -> list[FormulaDifferenceDetail]:
        b_ast = self.parser.parse(baseline_xml)
        c_ast = self.parser.parse(candidate_xml)
        return self.diff_ast(b_ast, c_ast, formula_name=formula_name)

    def diff_nodes(
        self,
        b_node: GraphNode,
        c_node: GraphNode,
    ) -> list[FormulaDifferenceDetail]:
        b_xml = b_node.rawXml or ""
        c_xml = c_node.rawXml or ""
        if not b_xml and not c_xml:
            return []
        return self.diff_xml(b_xml, c_xml, formula_name=c_node.label or b_node.label)

    def diff_ast(
        self,
        b_ast: FormulaExprNode | None,
        c_ast: FormulaExprNode | None,
        formula_name: str = "",
    ) -> list[FormulaDifferenceDetail]:
        if b_ast is None and c_ast is None:
            return []

        fname = formula_name or (c_ast.name if c_ast else "") or (b_ast.name if b_ast else "") or "Formula"
        b_expr = format_ast(b_ast)
        c_expr = format_ast(c_ast)

        if b_ast is None and c_ast is not None:
            return [
                FormulaDifferenceDetail(
                    formulaName=fname,
                    changeType="structure_modified",
                    baselineExpression="",
                    candidateExpression=c_expr,
                    detail=f"Formula expression added: '{c_expr}'",
                )
            ]
        if b_ast is not None and c_ast is None:
            return [
                FormulaDifferenceDetail(
                    formulaName=fname,
                    changeType="structure_modified",
                    baselineExpression=b_expr,
                    candidateExpression="",
                    detail=f"Formula expression removed: '{b_expr}'",
                )
            ]

        assert b_ast is not None and c_ast is not None

        diffs: list[FormulaDifferenceDetail] = []
        self._compare_nodes(b_ast, c_ast, fname, b_expr, c_expr, diffs)
        return diffs

    def _compare_nodes(
        self,
        b: FormulaExprNode,
        c: FormulaExprNode,
        fname: str,
        b_expr: str,
        c_expr: str,
        diffs: list[FormulaDifferenceDetail],
    ) -> None:
        # Operator change
        if (b.operator or "").upper() != (c.operator or "").upper():
            diffs.append(
                FormulaDifferenceDetail(
                    formulaName=fname,
                    changeType="operator_modified",
                    baselineExpression=b_expr,
                    candidateExpression=c_expr,
                    detail=f"Operator changed from '{b.operator}' to '{c.operator}' in expression",
                )
            )

        # Reference change (name or field)
        if b.node_type in ("LOOKUP_TABLE_REF", "VARIABLE_REF", "RULE_REF") or c.node_type in (
            "LOOKUP_TABLE_REF",
            "VARIABLE_REF",
            "RULE_REF",
        ):
            if (b.name or "") != (c.name or "") or (b.field or "") != (c.field or ""):
                b_ref = f"{b.name or ''}{'.' + b.field if b.field else ''}"
                c_ref = f"{c.name or ''}{'.' + c.field if c.field else ''}"
                ref_kind = "Lookup table" if "LOOKUP" in b.node_type or "LOOKUP" in c.node_type else "Variable"
                diffs.append(
                    FormulaDifferenceDetail(
                        formulaName=fname,
                        changeType="reference_modified",
                        baselineExpression=b_expr,
                        candidateExpression=c_expr,
                        detail=f"{ref_kind} reference changed from '{b_ref}' to '{c_ref}'",
                    )
                )

        # Constant change
        if b.node_type in ("LITERAL", "CONSTANT") and c.node_type in ("LITERAL", "CONSTANT"):
            if (b.value or "") != (c.value or ""):
                diffs.append(
                    FormulaDifferenceDetail(
                        formulaName=fname,
                        changeType="constant_modified",
                        baselineExpression=b_expr,
                        candidateExpression=c_expr,
                        detail=f"Constant value changed from '{b.value}' to '{c.value}'",
                    )
                )

        # Node type change (e.g. constant replaced with lookup or variable)
        if b.node_type != c.node_type:
            diffs.append(
                FormulaDifferenceDetail(
                    formulaName=fname,
                    changeType="structure_modified",
                    baselineExpression=b_expr,
                    candidateExpression=c_expr,
                    detail=f"Expression structure changed: '{b.node_type}' replaced by '{c.node_type}'",
                )
            )
            return

        # Condition logic change
        if b.node_type == "CONDITION":
            b_cond_str = format_ast(b)
            c_cond_str = format_ast(c)
            if b_cond_str != c_cond_str:
                diffs.append(
                    FormulaDifferenceDetail(
                        formulaName=fname,
                        changeType="condition_modified",
                        baselineExpression=b_expr,
                        candidateExpression=c_expr,
                        detail=f"Condition predicate changed from '{b_cond_str}' to '{c_cond_str}'",
                    )
                )

        # Recurse children
        min_len = min(len(b.children), len(c.children))
        for i in range(min_len):
            self._compare_nodes(b.children[i], c.children[i], fname, b_expr, c_expr, diffs)

        if len(b.children) != len(c.children):
            diffs.append(
                FormulaDifferenceDetail(
                    formulaName=fname,
                    changeType="structure_modified",
                    baselineExpression=b_expr,
                    candidateExpression=c_expr,
                    detail=f"Operand count changed from {len(b.children)} to {len(c.children)}",
                )
            )


class DownstreamImpactAnalyzer:
    """Computes transitive downstream blast radius and organizational impact of configuration alterations."""

    def analyze_blast_radius(
        self,
        altered_node: GraphNode,
        graph: GraphDocument,
        baseline_graph: GraphDocument | None = None,
    ) -> BlastRadiusReport:
        node_by_id = {node.id: node for node in graph.nodes}
        if altered_node.id not in node_by_id:
            # Check baseline graph if present
            if baseline_graph:
                b_map = {n.id: n for n in baseline_graph.nodes}
                if altered_node.id in b_map:
                    node_by_id = b_map

        # Build forward downstream adjacency index:
        # A node U impacts node V if:
        # 1. V references/uses U: link.target == U and relationship starts with 'uses_'
        # 2. U belongs to V: link.source == U and relationship in ('belongs_to_plan_component', 'belongs_to_plan', 'parent_child')
        # 3. U feeds V: link.source == U and relationship == 'feeds_deposit'
        # 4. Pipeline flow: V is a rule in a later pipeline stage connected via pipeline link
        downstream_adj: dict[str, set[str]] = defaultdict(set)

        for link in graph.links:
            s_id = link.source
            t_id = link.target
            rel = link.relationship

            # If V uses U, link.source=V, link.target=U. So U impacts V!
            if rel.startswith("uses_"):
                downstream_adj[t_id].add(s_id)
            # If U belongs to container V (Rule belongs_to_plan_component PC, PC belongs_to_plan Plan)
            elif rel in ("belongs_to_plan", "belongs_to_plan_component", "parent_child"):
                downstream_adj[s_id].add(t_id)
            # If U feeds deposit V
            elif rel in ("feeds_deposit", "runs_in_pipeline"):
                downstream_adj[s_id].add(t_id)
            else:
                # Default generic dependency
                downstream_adj[t_id].add(s_id)

        # BFS forward downstream traversal
        visited: set[str] = set()
        queue: deque[str] = deque([altered_node.id])
        visited.add(altered_node.id)

        impacted_nodes: list[BlastRadiusImpactedNode] = []
        plans_count = 0
        components_count = 0
        rules_count = 0
        deposit_rules_count = 0

        while queue:
            curr_id = queue.popleft()
            for next_id in downstream_adj.get(curr_id, set()):
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append(next_id)
                    next_node = node_by_id.get(next_id)
                    if not next_node:
                        continue

                    # Classify impacted node
                    stage_label = None
                    if next_node.type == "Rule":
                        rules_count += 1
                        stage, _ = classify_rule_stage(next_node)
                        stage_label = stage
                        if stage == STAGE_DEPOSIT or "DEPOSIT" in (next_node.metadata.get("ruleSubtype") or "").upper():
                            deposit_rules_count += 1
                    elif next_node.type == "Plan":
                        plans_count += 1
                    elif next_node.type == "PlanComponent":
                        components_count += 1

                    impacted_nodes.append(
                        BlastRadiusImpactedNode(
                            id=next_node.id,
                            type=next_node.type,
                            label=next_node.label,
                            canonicalKey=next_node.canonicalKey,
                            pipelineStage=stage_label,
                        )
                    )

        # Sort impacted nodes deterministically
        impacted_nodes.sort(key=lambda n: (n.type, n.label.casefold()))

        # Score calculation: 10 per plan, 5 per deposit rule, 2 per plan component, 1 per other rule
        other_rules = max(0, rules_count - deposit_rules_count)
        score = round(
            10.0 * plans_count + 5.0 * deposit_rules_count + 2.0 * components_count + 1.0 * other_rules,
            2,
        )

        # Severity classification
        if score >= 40.0 or plans_count >= 5 or deposit_rules_count >= 3:
            severity = "critical"
        elif score >= 20.0 or plans_count >= 2 or deposit_rules_count >= 1:
            severity = "high"
        elif score >= 5.0 or plans_count >= 1 or (rules_count + components_count) >= 2:
            severity = "medium"
        else:
            severity = "low"

        return BlastRadiusReport(
            severity=severity,
            score=score,
            impactedNodes=impacted_nodes,
            impactedPlansCount=plans_count,
            impactedComponentsCount=components_count,
            impactedRulesCount=rules_count,
            impactedDepositRulesCount=deposit_rules_count,
        )
