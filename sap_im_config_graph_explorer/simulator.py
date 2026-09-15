from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import Any

from sap_im_config_graph_explorer.models import (
    GraphDocument,
    GraphLink,
    GraphNode,
    SimulationEvent,
    SimulationStep,
    SimulationTrace,
)
from sap_im_config_graph_explorer.pipeline import (
    STAGE_ALLOCATE,
    STAGE_CREDIT,
    STAGE_DEPOSIT,
    STAGE_INCENTIVE,
    STAGE_PAYMENT,
    STAGE_PRIMARY_MEASUREMENT,
    STAGE_RANKS,
    STAGE_SECONDARY_MEASUREMENT,
    STAGE_UNKNOWN,
    classify_rule_stage,
)
from sap_im_config_graph_explorer.rule_delta import FormulaAstParser, FormulaExprNode, format_ast


class SafeAstEvaluator:
    """Safely evaluates FormulaExprNode ASTs against a variable context without eval()."""

    def evaluate(self, node: FormulaExprNode | None, context: dict[str, float]) -> float:
        if node is None:
            return 0.0

        nt = node.node_type

        # Literal / Constant
        if nt in ("LITERAL", "CONSTANT"):
            try:
                return float(node.value or node.name or 0.0)
            except (ValueError, TypeError):
                return 0.0

        # Variable reference
        if nt in ("VARIABLE_REF", "VARIABLE"):
            var_name = (node.name or node.value or "").strip().lower()
            return self._resolve_variable(var_name, context)

        # Lookup table reference / tiered rate lookup
        if nt in ("LOOKUP_TABLE_REF", "LOOKUP_TABLE"):
            table_name = (node.name or "").lower()
            attainment = context.get("attainment", 1.0)
            amount = context.get("amount", 0.0)
            return self._lookup_rate_tier(table_name, attainment, amount)

        # Math operations
        if nt == "MATH_OPERATION":
            op = (node.operator or "").upper()
            child_vals = [self.evaluate(c, context) for c in node.children]
            if not child_vals:
                return 0.0
            if len(child_vals) == 1:
                return -child_vals[0] if op in ("MINUS", "SUBTRACT", "NEG") else child_vals[0]

            left = child_vals[0]
            right = child_vals[1]

            if op in ("ADD", "PLUS", "+"):
                return left + right
            elif op in ("SUBTRACT", "MINUS", "-"):
                return left - right
            elif op in ("MULTIPLY", "MULT", "*"):
                return left * right
            elif op in ("DIVIDE", "DIV", "/"):
                return (left / right) if abs(right) > 1e-9 else 0.0
            elif op in ("GREATER_THAN", ">"):
                return 1.0 if left > right else 0.0
            elif op in ("GREATER_THAN_OR_EQUAL", ">="):
                return 1.0 if left >= right else 0.0
            elif op in ("LESS_THAN", "<"):
                return 1.0 if left < right else 0.0
            elif op in ("LESS_THAN_OR_EQUAL", "<="):
                return 1.0 if left <= right else 0.0
            elif op in ("EQUALS", "=="):
                return 1.0 if abs(left - right) < 1e-6 else 0.0
            elif op in ("NOT_EQUALS", "!="):
                return 1.0 if abs(left - right) >= 1e-6 else 0.0
            elif op in ("MAX", "GREATEST"):
                return max(left, right)
            elif op in ("MIN", "LEAST"):
                return min(left, right)
            return left

        # Built-in functions
        if nt in ("FUNCTION", "FUNC"):
            fn_name = (node.name or node.operator or "").upper()
            child_vals = [self.evaluate(c, context) for c in node.children]
            if fn_name in ("MIN", "LEAST") and child_vals:
                return min(child_vals)
            elif fn_name in ("MAX", "GREATEST") and child_vals:
                return max(child_vals)
            elif fn_name == "ABS" and child_vals:
                return abs(child_vals[0])
            elif fn_name == "ROUND" and child_vals:
                decimals = int(child_vals[1]) if len(child_vals) > 1 else 2
                return round(child_vals[0], decimals)
            elif fn_name in ("IF", "TERNARY") and len(child_vals) >= 2:
                cond = child_vals[0]
                true_val = child_vals[1]
                false_val = child_vals[2] if len(child_vals) > 2 else 0.0
                return true_val if cond > 0.0 else false_val
            elif child_vals:
                return child_vals[0]
            return 0.0

        # Expression or Formula container: evaluate last child or sum
        if node.children:
            val = 0.0
            for child in node.children:
                val = self.evaluate(child, context)
            return val

        # Fallback value parsing
        try:
            return float(node.value or 0.0)
        except (ValueError, TypeError):
            return 0.0

    def _resolve_variable(self, var_name: str, context: dict[str, float]) -> float:
        aliases = {
            "credit": "credit",
            "credit_amount": "credit",
            "credits": "credit",
            "amount": "amount",
            "transaction_amount": "amount",
            "sales_amount": "amount",
            "quota": "quota",
            "attainment": "attainment",
            "attainment_pct": "attainment",
            "rate": "rate",
            "commission_rate": "rate",
            "split": "credit_split",
            "creditsplit": "credit_split",
            "incentive": "incentive",
            "deposit": "deposit",
        }
        key = aliases.get(var_name, var_name)
        if key in context:
            return context[key]
        for c_k, c_v in context.items():
            if c_k.lower() == var_name.lower():
                return c_v
        return 0.0

    def _lookup_rate_tier(self, table_name: str, attainment: float, amount: float) -> float:
        """Deterministic compensation rate table tier resolution."""
        if "accelerator" in table_name or "tier" in table_name or "comm" in table_name:
            if attainment >= 2.0:
                return 0.20
            elif attainment >= 1.5:
                return 0.15
            elif attainment >= 1.0:
                return 0.10
            elif attainment >= 0.8:
                return 0.08
            else:
                return 0.05
        return 0.10


class CompensationRuleSimulator:
    """Interactive compensation rule simulation and event propagation engine.
    
    Simulates transactional credit events through SAP Incentive Management calculation
    pipeline rules (Crediting -> Primary Measurement -> Secondary Measurement -> Incentive -> Deposit).
    """

    def __init__(
        self,
        nodes: list[GraphNode] | None = None,
        links: list[GraphLink] | None = None,
    ):
        self.nodes: list[GraphNode] = nodes or []
        self.links: list[GraphLink] = links or []
        self.node_by_id: dict[str, GraphNode] = {n.id: n for n in self.nodes}
        self.parser = FormulaAstParser()
        self.evaluator = SafeAstEvaluator()

        # Build adjacency maps
        self.outbound_links: dict[str, list[GraphLink]] = defaultdict(list)
        self.inbound_links: dict[str, list[GraphLink]] = defaultdict(list)
        for link in self.links:
            self.outbound_links[link.source].append(link)
            self.inbound_links[link.target].append(link)

    @classmethod
    def from_graph_document(cls, graph: GraphDocument) -> CompensationRuleSimulator:
        return cls(nodes=graph.nodes, links=graph.links)

    def simulate(
        self,
        event: SimulationEvent | None = None,
        plan_id: str | None = None,
        max_steps: int = 1000,
    ) -> SimulationTrace:
        """Execute a deterministic simulation run on the active rule pipeline."""
        start_time = time.perf_counter()
        ev = event or SimulationEvent()

        # Collect plan containment
        rule_to_components: dict[str, list[str]] = defaultdict(list)
        comp_to_plans: dict[str, list[str]] = defaultdict(list)
        for link in self.links:
            if link.relationship == "belongs_to_plan_component":
                rule_to_components[link.source].append(link.target)
            elif link.relationship == "belongs_to_plan":
                comp_to_plans[link.source].append(link.target)

        # Filter rules
        all_rules = [n for n in self.nodes if n.type == "Rule"]
        selected_rules: list[GraphNode] = []
        for r in all_rules:
            if not plan_id:
                selected_rules.append(r)
                continue
            parent_comps = rule_to_components.get(r.id, [])
            in_plan = any(plan_id in comp_to_plans.get(c, []) for c in parent_comps)
            if in_plan:
                selected_rules.append(r)

        if not selected_rules:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return SimulationTrace(
                ok=True,
                status="no_rules_found",
                steps=[],
                finalDeposit=0.0,
                totalCredited=0.0,
                totalIncentive=0.0,
                eventsEvaluated=1,
                executionTimeMs=elapsed_ms,
                error="",
            )

        # Group and order rules by pipeline stage and sequence
        rules_by_stage: dict[str, list[tuple[int, int, GraphNode]]] = defaultdict(list)
        for rule in selected_rules:
            stage, _ = classify_rule_stage(rule)
            stage_rank = STAGE_RANKS.get(stage, 99)
            seq = self._extract_sequence(rule.metadata or {})
            rules_by_stage[stage].append((stage_rank, seq, rule))

        # Sort within stages
        for stage in rules_by_stage:
            rules_by_stage[stage].sort(key=lambda item: (item[1], item[2].label.casefold()))

        ordered_stages = [
            STAGE_ALLOCATE,
            STAGE_CREDIT,
            STAGE_PRIMARY_MEASUREMENT,
            STAGE_SECONDARY_MEASUREMENT,
            STAGE_INCENTIVE,
            STAGE_DEPOSIT,
            STAGE_PAYMENT,
            STAGE_UNKNOWN,
        ]

        steps: list[SimulationStep] = []
        step_index = 1
        total_credited = 0.0
        total_incentive = 0.0
        final_deposit = 0.0

        # Shared simulation context state
        context: dict[str, float] = {
            "amount": float(ev.amount),
            "quota": float(ev.quota),
            "credit_split": float(ev.creditSplit),
            "credit": 0.0,
            "attainment": 0.0,
            "rate": 0.10,
            "incentive": 0.0,
            "deposit": 0.0,
        }

        # Track visited nodes for cycle detection
        visited_nodes: set[str] = set()

        for stage in ordered_stages:
            stage_rules = rules_by_stage.get(stage, [])
            if not stage_rules:
                continue

            for _, seq, rule in stage_rules:
                if step_index > max_steps:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return SimulationTrace(
                        ok=False,
                        status="max_steps_exceeded",
                        steps=steps,
                        finalDeposit=final_deposit,
                        totalCredited=total_credited,
                        totalIncentive=total_incentive,
                        eventsEvaluated=1,
                        executionTimeMs=elapsed_ms,
                        error=f"Simulation aborted: maximum step limit of {max_steps} exceeded.",
                    )

                if rule.id in visited_nodes:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return SimulationTrace(
                        ok=False,
                        status="cycle_detected",
                        steps=steps,
                        finalDeposit=final_deposit,
                        totalCredited=total_credited,
                        totalIncentive=total_incentive,
                        eventsEvaluated=1,
                        executionTimeMs=elapsed_ms,
                        error=f"Infinite cycle detected on rule node {rule.id} ('{rule.label}').",
                    )

                visited_nodes.add(rule.id)

                step = self._evaluate_rule_step(
                    rule=rule,
                    stage=stage,
                    step_index=step_index,
                    event=ev,
                    context=context,
                )
                steps.append(step)
                step_index += 1

                # Update global accumulators based on stage
                if stage in (STAGE_ALLOCATE, STAGE_CREDIT):
                    total_credited += step.output
                    context["credit"] = total_credited
                    if ev.quota > 0:
                        context["attainment"] = total_credited / ev.quota
                elif stage == STAGE_PRIMARY_MEASUREMENT:
                    context["primary_measurement"] = step.output
                    if ev.quota > 0:
                        context["attainment"] = total_credited / ev.quota
                elif stage == STAGE_SECONDARY_MEASUREMENT:
                    context["secondary_measurement"] = step.output
                elif stage == STAGE_INCENTIVE:
                    total_incentive += step.output
                    context["incentive"] = total_incentive
                elif stage in (STAGE_DEPOSIT, STAGE_PAYMENT):
                    final_deposit = step.output
                    context["deposit"] = final_deposit

        # If no deposit stage rules existed, final deposit defaults to total incentive
        if final_deposit == 0.0 and total_incentive > 0.0:
            final_deposit = total_incentive

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SimulationTrace(
            ok=True,
            status="completed",
            steps=steps,
            finalDeposit=final_deposit,
            totalCredited=total_credited,
            totalIncentive=total_incentive,
            eventsEvaluated=1,
            executionTimeMs=elapsed_ms,
            error="",
        )

    def _evaluate_rule_step(
        self,
        rule: GraphNode,
        stage: str,
        step_index: int,
        event: SimulationEvent,
        context: dict[str, float],
    ) -> SimulationStep:
        """Evaluate a single rule node and synthesize its SimulationStep details."""
        metadata = rule.metadata or {}
        outbound_ids = [l.id for l in self.outbound_links.get(rule.id, [])]

        # Parse AST if raw XML is available
        ast_node: FormulaExprNode | None = None
        formula_str: str = ""
        if rule.rawXml:
            ast_node = self.parser.parse(rule.rawXml)
            if ast_node:
                formula_str = format_ast(ast_node)

        # Stage specific calculation logic
        if stage in (STAGE_ALLOCATE, STAGE_CREDIT):
            split = event.creditSplit if event.creditSplit is not None else 1.0
            calc_credit = float(event.amount) * float(split)
            if ast_node:
                ast_val = self.evaluator.evaluate(ast_node, context)
                if ast_val > 0.0:
                    calc_credit = ast_val

            formula_disp = formula_str or f"amount (${event.amount:,.2f}) * creditSplit ({split * 100:.0f}%)"
            explanation = (
                f"Credited ${calc_credit:,.2f} ({split * 100:.0f}% of ${event.amount:,.2f}) "
                f"to participant '{event.participant}' for '{event.eventType}'."
            )
            return SimulationStep(
                stepIndex=step_index,
                stage="Crediting",
                nodeId=rule.id,
                ruleName=rule.label,
                formula=formula_disp,
                inputs={
                    "amount": event.amount,
                    "creditSplit": split,
                    "participant": event.participant,
                    "eventType": event.eventType,
                },
                output=calc_credit,
                intermediateValues={
                    "transactionAmount": event.amount,
                    "creditSplitPct": f"{split * 100:.1f}%",
                    "creditedAmount": calc_credit,
                },
                outboundLinkIds=outbound_ids,
                explanation=explanation,
            )

        elif stage == STAGE_PRIMARY_MEASUREMENT:
            current_credit = context.get("credit", float(event.amount))
            quota = float(event.quota)
            attainment = (current_credit / quota) if quota > 0 else 1.0
            measurement_val = current_credit

            if ast_node:
                ast_val = self.evaluator.evaluate(ast_node, context)
                if ast_val > 0.0:
                    measurement_val = ast_val

            formula_disp = formula_str or f"current_credit (${current_credit:,.2f}) / quota (${quota:,.2f})"
            explanation = (
                f"Aggregated measurement base of ${measurement_val:,.2f} "
                f"achieving {attainment * 100:.1f}% of quota (${quota:,.2f})."
            )
            return SimulationStep(
                stepIndex=step_index,
                stage="Primary Measurement",
                nodeId=rule.id,
                ruleName=rule.label,
                formula=formula_disp,
                inputs={
                    "creditBase": current_credit,
                    "quota": quota,
                },
                output=measurement_val,
                intermediateValues={
                    "creditBase": current_credit,
                    "quota": quota,
                    "attainmentRatio": round(attainment, 4),
                    "attainmentPct": f"{attainment * 100:.1f}%",
                },
                outboundLinkIds=outbound_ids,
                explanation=explanation,
            )

        elif stage == STAGE_SECONDARY_MEASUREMENT:
            attainment = context.get("attainment", 1.0)
            if attainment >= 1.5:
                tier_mult = 1.25
                tier_label = "Tier 3 (Super-Accelerator 1.25x)"
            elif attainment >= 1.0:
                tier_mult = 1.00
                tier_label = "Tier 2 (Target Quota 1.0x)"
            elif attainment >= 0.8:
                tier_mult = 0.80
                tier_label = "Tier 1 (Base Band 0.80x)"
            else:
                tier_mult = 0.50
                tier_label = "Below Threshold (0.50x)"

            if ast_node:
                ast_val = self.evaluator.evaluate(ast_node, context)
                if ast_val > 0.0:
                    tier_mult = ast_val

            formula_disp = formula_str or f"TierLookup(attainment={attainment * 100:.1f}%)"
            explanation = f"Evaluated secondary measurement tier: {tier_label} (multiplier: {tier_mult:.2f}x)."
            return SimulationStep(
                stepIndex=step_index,
                stage="Secondary Measurement",
                nodeId=rule.id,
                ruleName=rule.label,
                formula=formula_disp,
                inputs={
                    "attainment": round(attainment, 4),
                },
                output=tier_mult,
                intermediateValues={
                    "tierMultiplier": tier_mult,
                    "tierClassification": tier_label,
                    "attainmentPct": f"{attainment * 100:.1f}%",
                },
                outboundLinkIds=outbound_ids,
                explanation=explanation,
            )

        elif stage == STAGE_INCENTIVE:
            credit_base = context.get("credit", float(event.amount))
            quota = float(event.quota)
            attainment = context.get("attainment", 1.0)
            sec_mult = context.get("secondary_measurement", 1.0)

            # Rule specific sequence handling: sequence 1 (base) vs sequence 2 (accelerator)
            seq = self._extract_sequence(metadata)
            rule_name_lower = rule.label.lower()

            if "accelerator" in rule_name_lower or seq == 2:
                # Accelerator rule calculates on amount above quota
                overage = max(0.0, credit_base - quota) if quota > 0 else 0.0
                accel_rate = 0.15 * sec_mult
                calc_incentive = overage * accel_rate
                formula_disp = (
                    formula_str
                    or f"max(0, credit - quota) * (accelerator_rate {accel_rate * 100:.1f}%)"
                )
                explanation = (
                    f"Applied accelerator rate {accel_rate * 100:.1f}% to over-quota amount "
                    f"${overage:,.2f} yielding ${calc_incentive:,.2f} bonus."
                )
            else:
                # Standard commission calculation
                base_amount = min(credit_base, quota) if ("standard" in rule_name_lower and quota > 0) else credit_base
                base_rate = 0.10 * sec_mult
                calc_incentive = base_amount * base_rate
                formula_disp = (
                    formula_str
                    or f"base_amount (${base_amount:,.2f}) * base_rate ({base_rate * 100:.1f}%)"
                )
                explanation = (
                    f"Earned standard commission of ${calc_incentive:,.2f} at {base_rate * 100:.1f}% rate."
                )

            if ast_node:
                ast_val = self.evaluator.evaluate(ast_node, context)
                if ast_val > 0.0:
                    calc_incentive = ast_val

            return SimulationStep(
                stepIndex=step_index,
                stage="Incentive / Calculation",
                nodeId=rule.id,
                ruleName=rule.label,
                formula=formula_disp,
                inputs={
                    "creditBase": credit_base,
                    "attainment": round(attainment, 4),
                    "tierMultiplier": sec_mult,
                },
                output=calc_incentive,
                intermediateValues={
                    "commissionEarned": calc_incentive,
                    "attainmentRatio": round(attainment, 4),
                },
                outboundLinkIds=outbound_ids,
                explanation=explanation,
            )

        elif stage in (STAGE_DEPOSIT, STAGE_PAYMENT):
            total_incentive = context.get("incentive", 0.0)
            cap = 1_000_000.0  # Safe default cap
            hold_pct = 0.0     # 0% standard hold

            capped_incentive = min(total_incentive, cap)
            final_payout = capped_incentive * (1.0 - hold_pct)

            if ast_node:
                ast_val = self.evaluator.evaluate(ast_node, context)
                if ast_val > 0.0:
                    final_payout = ast_val

            formula_disp = (
                formula_str
                or f"min(incentive (${total_incentive:,.2f}), cap (${cap:,.0f})) * (1 - hold ({hold_pct * 100:.0f}%))"
            )
            explanation = (
                f"Approved final deposit of ${final_payout:,.2f} "
                f"(Gross: ${total_incentive:,.2f}, Cap: ${cap:,.0f}, Hold: {hold_pct * 100:.0f}%)."
            )
            return SimulationStep(
                stepIndex=step_index,
                stage="Deposit",
                nodeId=rule.id,
                ruleName=rule.label,
                formula=formula_disp,
                inputs={
                    "grossIncentive": total_incentive,
                    "cap": cap,
                    "holdPct": hold_pct,
                },
                output=final_payout,
                intermediateValues={
                    "grossIncentive": total_incentive,
                    "finalDeposit": final_payout,
                },
                outboundLinkIds=outbound_ids,
                explanation=explanation,
            )

        else:
            # Fallback generic rule
            return SimulationStep(
                stepIndex=step_index,
                stage="Custom / Unmapped",
                nodeId=rule.id,
                ruleName=rule.label,
                formula=formula_str or "Pass-through evaluation",
                inputs={"eventAmount": event.amount},
                output=float(event.amount),
                intermediateValues={},
                outboundLinkIds=outbound_ids,
                explanation=f"Evaluated unclassified rule '{rule.label}'.",
            )

    def _extract_sequence(self, metadata: dict[str, Any]) -> int:
        for key in ("sequence", "order", "priority", "processingOrder", "SEQUENCE", "ORDER", "PRIORITY"):
            val = metadata.get(key)
            if val is not None:
                try:
                    return int(str(val).strip())
                except (ValueError, TypeError):
                    pass
        return 999
