from __future__ import annotations

from collections import defaultdict
from typing import Any

from sap_im_config_graph_explorer.models import (
    GraphDocument,
    GraphNode,
    PipelineFlowResult,
    PipelineStageGroupRecord,
    PipelineStepRecord,
    PipelineTransitionRecord,
)

STAGE_ALLOCATE = "allocate"
STAGE_CREDIT = "credit"
STAGE_PRIMARY_MEASUREMENT = "primary_measurement"
STAGE_SECONDARY_MEASUREMENT = "secondary_measurement"
STAGE_INCENTIVE = "incentive"
STAGE_DEPOSIT = "deposit"
STAGE_PAYMENT = "payment"
STAGE_UNKNOWN = "unknown"

STAGE_RANKS: dict[str, int] = {
    STAGE_ALLOCATE: 1,
    STAGE_CREDIT: 2,
    STAGE_PRIMARY_MEASUREMENT: 3,
    STAGE_SECONDARY_MEASUREMENT: 4,
    STAGE_INCENTIVE: 5,
    STAGE_DEPOSIT: 6,
    STAGE_PAYMENT: 7,
    STAGE_UNKNOWN: 99,
}

STAGE_LABELS: dict[str, str] = {
    STAGE_ALLOCATE: "Allocation",
    STAGE_CREDIT: "Crediting",
    STAGE_PRIMARY_MEASUREMENT: "Primary Measurement",
    STAGE_SECONDARY_MEASUREMENT: "Secondary Measurement",
    STAGE_INCENTIVE: "Incentive / Calculation",
    STAGE_DEPOSIT: "Deposit",
    STAGE_PAYMENT: "Payment",
    STAGE_UNKNOWN: "Unmapped / Custom Stage",
}

STAGE_DESCRIPTIONS: dict[str, str] = {
    STAGE_ALLOCATE: "Transaction allocation, territory assignment, and credit eligibility filtering.",
    STAGE_CREDIT: "Direct and rollup credit rules calculate credited amounts for participants.",
    STAGE_PRIMARY_MEASUREMENT: "Primary measurement rules aggregate credits and performance metrics.",
    STAGE_SECONDARY_MEASUREMENT: "Secondary measurement rules evaluate composite or multi-period measurement tiers.",
    STAGE_INCENTIVE: "Commission and bonus rules calculate incentive earnings from measurements or credits.",
    STAGE_DEPOSIT: "Deposit and detail deposit rules apply holding, draws, caps, and release policies.",
    STAGE_PAYMENT: "Payment rules finalize disbursements and payroll export allocations.",
    STAGE_UNKNOWN: "Rules without standard pipeline classification; execution sequence is unverified.",
}


def classify_rule_stage(node: GraphNode) -> tuple[str, str]:
    """Classify a rule node into a standard SAP Incentive Management calculation pipeline stage.
    
    Returns (stage_id, explanation_evidence).
    """
    metadata = node.metadata or {}
    subtype = (metadata.get("ruleSubtype") or metadata.get("type") or "").strip().upper()
    family = (metadata.get("ruleFamily") or "").strip().lower()

    if subtype in {"DIRECT_TRANSACTION_CREDIT", "ROLLUP_TRANSACTION_CREDIT"} or "CREDIT" in subtype:
        return (
            STAGE_CREDIT,
            f"Rule TYPE '{subtype or 'CREDIT'}' maps to the SAP IM Crediting phase.",
        )
    if subtype == "PRIMARY_MEASUREMENT":
        return (
            STAGE_PRIMARY_MEASUREMENT,
            "Rule TYPE 'PRIMARY_MEASUREMENT' maps to the SAP IM Primary Measurement phase.",
        )
    if subtype == "SECONDARY_MEASUREMENT":
        return (
            STAGE_SECONDARY_MEASUREMENT,
            "Rule TYPE 'SECONDARY_MEASUREMENT' maps to the SAP IM Secondary Measurement phase.",
        )
    if subtype in {"COMMISSION", "BULK_COMMISSION", "INCENTIVE", "BONUS"} or "COMMISSION" in subtype:
        return (
            STAGE_INCENTIVE,
            f"Rule TYPE '{subtype}' maps to the SAP IM Incentive / Calculation phase.",
        )
    if subtype in {"DEPOSIT", "DETAIL_DEPOSIT"} or "DEPOSIT" in subtype:
        return (
            STAGE_DEPOSIT,
            f"Rule TYPE '{subtype}' maps to the SAP IM Deposit phase.",
        )
    if subtype == "PAYMENT" or "PAYMENT" in subtype:
        return (
            STAGE_PAYMENT,
            f"Rule TYPE '{subtype}' maps to the SAP IM Payment phase.",
        )

    # Fallback to ruleFamily if subtype was not specific
    if family == "credit":
        return STAGE_CREDIT, "Rule family 'credit' maps to the SAP IM Crediting phase."
    if family == "measurement":
        return STAGE_PRIMARY_MEASUREMENT, "Rule family 'measurement' maps to the SAP IM Measurement phase."
    if family == "incentive":
        return STAGE_INCENTIVE, "Rule family 'incentive' maps to the SAP IM Incentive phase."
    if family == "deposit":
        return STAGE_DEPOSIT, "Rule family 'deposit' maps to the SAP IM Deposit phase."
    if family == "payment":
        return STAGE_PAYMENT, "Rule family 'payment' maps to the SAP IM Payment phase."

    return (
        STAGE_UNKNOWN,
        f"Rule TYPE '{subtype or 'Unspecified'}' does not map to a standard SAP IM pipeline stage.",
    )


def _extract_sequence_number(metadata: dict[str, Any]) -> int | None:
    """Extract explicit sequence integer from metadata if documented."""
    for key in ("sequence", "order", "priority", "processingOrder", "SEQUENCE", "ORDER", "PRIORITY"):
        val = metadata.get(key)
        if val is not None:
            try:
                return int(str(val).strip())
            except (ValueError, TypeError):
                pass
    return None


def derive_pipeline_flow(
    graph: GraphDocument,
    plan_id: str | None = None,
) -> PipelineFlowResult:
    """Derive deterministic pipeline execution flow from allowlisted graph objects and metadata.
    
    Zero runtime invention:
    - Inter-stage transitions follow standard SAP IM calculation lifecycle.
    - Intra-stage rules with explicit sequence attributes are ordered and marked 'known'.
    - Intra-stage rules without documented sequence or data dependencies are marked 'unknown'.
    """
    node_by_id: dict[str, GraphNode] = {n.id: n for n in graph.nodes}
    plans = [n for n in graph.nodes if n.type == "Plan"]
    components = [n for n in graph.nodes if n.type == "PlanComponent"]
    all_rules = [n for n in graph.nodes if n.type == "Rule"]

    available_plans = [
        {"id": p.id, "label": p.label}
        for p in sorted(plans, key=lambda p: p.label.casefold())
    ]

    # Index containment links
    # rule -> component
    rule_to_components: dict[str, list[str]] = defaultdict(list)
    for link in graph.links:
        if link.relationship == "belongs_to_plan_component":
            rule_to_components[link.source].append(link.target)

    # component -> plan
    comp_to_plans: dict[str, list[str]] = defaultdict(list)
    for link in graph.links:
        if link.relationship == "belongs_to_plan":
            comp_to_plans[link.source].append(link.target)

    # Index rule-to-rule dependencies or direct references
    rule_data_dependencies: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for link in graph.links:
        if link.source in node_by_id and link.target in node_by_id:
            src_node = node_by_id[link.source]
            tgt_node = node_by_id[link.target]
            if src_node.type == "Rule" and tgt_node.type == "Rule" and link.source != link.target:
                rule_data_dependencies[link.source].append((link.target, link.relationship))

    scoped_plan_label: str | None = None
    if plan_id:
        scoped_plan = node_by_id.get(plan_id)
        if scoped_plan and scoped_plan.type == "Plan":
            scoped_plan_label = scoped_plan.label

    # Filter rules if plan_id is specified
    selected_rules: list[GraphNode] = []
    for rule in all_rules:
        if not plan_id:
            selected_rules.append(rule)
            continue
        # Check if rule belongs to plan_id
        parent_comps = rule_to_components.get(rule.id, [])
        in_plan = any(
            plan_id in comp_to_plans.get(comp_id, [])
            for comp_id in parent_comps
        )
        if in_plan:
            selected_rules.append(rule)

    # Build PipelineStepRecord for each rule
    steps_by_stage: dict[str, list[PipelineStepRecord]] = defaultdict(list)
    step_records: list[PipelineStepRecord] = []

    for rule in selected_rules:
        stage, stage_evidence = classify_rule_stage(rule)
        stage_label = STAGE_LABELS.get(stage, "Unmapped Stage")
        stage_rank = STAGE_RANKS.get(stage, 99)
        seq_num = _extract_sequence_number(rule.metadata or {})

        parent_comps = rule_to_components.get(rule.id, [])
        primary_comp_id = parent_comps[0] if parent_comps else None
        primary_comp_node = node_by_id.get(primary_comp_id) if primary_comp_id else None

        parent_plan_ids = comp_to_plans.get(primary_comp_id, []) if primary_comp_id else []
        primary_plan_id = parent_plan_ids[0] if parent_plan_ids else None
        primary_plan_node = node_by_id.get(primary_plan_id) if primary_plan_id else None

        rule_subtype = rule.metadata.get("ruleSubtype") or rule.metadata.get("type") or ""

        evidence_parts = [stage_evidence]
        if seq_num is not None:
            evidence_parts.append(f"Explicit sequence attribute: {seq_num}.")

        step = PipelineStepRecord(
            id=f"step-{rule.id}",
            ruleId=rule.id,
            label=rule.label,
            stage=stage,
            stageLabel=stage_label,
            stageRank=stage_rank,
            ruleSubtype=rule_subtype,
            sourceFile=rule.sourceFile,
            planId=primary_plan_node.id if primary_plan_node else None,
            planLabel=primary_plan_node.label if primary_plan_node else None,
            componentId=primary_comp_node.id if primary_comp_node else None,
            componentLabel=primary_comp_node.label if primary_comp_node else None,
            sequenceNumber=seq_num,
            orderStatus="known",
            sourceEvidence=" ".join(evidence_parts),
            metadata=rule.metadata or {},
        )
        step_records.append(step)
        steps_by_stage[stage].append(step)

    transitions: list[PipelineTransitionRecord] = []
    transition_counter = 0

    # Sort stages by rank
    active_stage_keys = sorted(
        steps_by_stage.keys(),
        key=lambda s: (STAGE_RANKS.get(s, 99), s)
    )

    stage_groups: list[PipelineStageGroupRecord] = []

    # Process each stage for intra-stage ordering
    for stage_key in active_stage_keys:
        stage_steps = steps_by_stage[stage_key]
        stage_label = STAGE_LABELS.get(stage_key, "Unmapped Stage")

        # Sort steps in this stage by explicit sequence if present, otherwise by label
        stage_steps.sort(
            key=lambda s: (
                0 if s.sequenceNumber is not None else 1,
                s.sequenceNumber if s.sequenceNumber is not None else 0,
                s.label.casefold(),
            )
        )

        has_explicit_sequence = all(s.sequenceNumber is not None for s in stage_steps) and len(stage_steps) > 1
        sequence_numbers_set = {s.sequenceNumber for s in stage_steps if s.sequenceNumber is not None}

        # Check for sequence-based transitions
        if len(stage_steps) > 1 and len(sequence_numbers_set) == len(stage_steps):
            for i in range(len(stage_steps) - 1):
                transition_counter += 1
                transitions.append(
                    PipelineTransitionRecord(
                        id=f"trans-{transition_counter}",
                        sourceStepId=stage_steps[i].id,
                        targetStepId=stage_steps[i + 1].id,
                        sourceRuleLabel=stage_steps[i].label,
                        targetRuleLabel=stage_steps[i + 1].label,
                        transitionType="explicit_sequence",
                        orderStatus="known",
                        sourceEvidence=(
                            f"Explicit sequence ordering in source XML: "
                            f"Sequence {stage_steps[i].sequenceNumber} precedes "
                            f"Sequence {stage_steps[i + 1].sequenceNumber}."
                        ),
                    )
                )
        elif len(stage_steps) > 1:
            # Check if any explicit data dependencies exist
            has_data_dep = False
            for s1 in stage_steps:
                for tgt_id, rel in rule_data_dependencies.get(s1.ruleId, []):
                    s2 = next((s for s in stage_steps if s.ruleId == tgt_id), None)
                    if s2:
                        has_data_dep = True
                        transition_counter += 1
                        transitions.append(
                            PipelineTransitionRecord(
                                id=f"trans-{transition_counter}",
                                sourceStepId=s1.id,
                                targetStepId=s2.id,
                                sourceRuleLabel=s1.label,
                                targetRuleLabel=s2.label,
                                transitionType="data_dependency",
                                orderStatus="known",
                                sourceEvidence=(
                                    f"Direct data relationship in configuration: "
                                    f"'{s1.label}' -> '{s2.label}' via '{rel}'."
                                ),
                            )
                        )

            # If rules lack both explicit sequence and data dependencies, execution order is unknown
            if not has_data_dep:
                for s in stage_steps:
                    s.orderStatus = "unknown"
                    s.sourceEvidence += (
                        f" Execution order within '{stage_label}' stage cannot be determined "
                        "from source XML (unsequenced sibling rules)."
                    )

                for i in range(len(stage_steps) - 1):
                    transition_counter += 1
                    transitions.append(
                        PipelineTransitionRecord(
                            id=f"trans-{transition_counter}",
                            sourceStepId=stage_steps[i].id,
                            targetStepId=stage_steps[i + 1].id,
                            sourceRuleLabel=stage_steps[i].label,
                            targetRuleLabel=stage_steps[i + 1].label,
                            transitionType="unknown_order",
                            orderStatus="unknown",
                            sourceEvidence=(
                                f"Rules '{stage_steps[i].label}' and '{stage_steps[i + 1].label}' execute "
                                f"in the same stage ('{stage_label}') without explicit sequence attributes "
                                "or directional dependencies in source XML; execution order cannot be determined from export."
                            ),
                        )
                    )

        stage_groups.append(
            PipelineStageGroupRecord(
                stage=stage_key,
                label=stage_label,
                rank=STAGE_RANKS.get(stage_key, 99),
                steps=stage_steps,
            )
        )

    # Inter-stage transitions between consecutive pipeline stages
    ordered_stages = [g for g in stage_groups if g.stage != STAGE_UNKNOWN and g.steps]
    for i in range(len(ordered_stages) - 1):
        prev_group = ordered_stages[i]
        next_group = ordered_stages[i + 1]

        # Terminal step of previous stage connects to initial step of next stage
        source_step = prev_group.steps[-1]
        target_step = next_group.steps[0]

        transition_counter += 1
        transitions.append(
            PipelineTransitionRecord(
                id=f"trans-{transition_counter}",
                sourceStepId=source_step.id,
                targetStepId=target_step.id,
                sourceRuleLabel=source_step.label,
                targetRuleLabel=target_step.label,
                transitionType="stage_transition",
                orderStatus="known",
                sourceEvidence=(
                    f"Standard SAP Incentive Management calculation pipeline: "
                    f"'{prev_group.label}' stage executes prior to '{next_group.label}' stage."
                ),
            )
        )

    # If unknown stage rules exist, connect terminal standard step to unknown stage with unknown status
    unknown_group = next((g for g in stage_groups if g.stage == STAGE_UNKNOWN and g.steps), None)
    if unknown_group and ordered_stages:
        last_standard_step = ordered_stages[-1].steps[-1]
        first_unknown_step = unknown_group.steps[0]
        transition_counter += 1
        transitions.append(
            PipelineTransitionRecord(
                id=f"trans-{transition_counter}",
                sourceStepId=last_standard_step.id,
                targetStepId=first_unknown_step.id,
                sourceRuleLabel=last_standard_step.label,
                targetRuleLabel=first_unknown_step.label,
                transitionType="unknown_order",
                orderStatus="unknown",
                sourceEvidence=(
                    f"Rule '{first_unknown_step.label}' is in unmapped stage; "
                    "execution order relative to pipeline cannot be verified from source XML."
                ),
            )
        )

    known_count = sum(1 for t in transitions if t.orderStatus == "known")
    unknown_count = sum(1 for t in transitions if t.orderStatus == "unknown")

    summary = {
        "totalSteps": len(step_records),
        "totalTransitions": len(transitions),
        "knownCount": known_count,
        "unknownCount": unknown_count,
        "stageCount": len(stage_groups),
    }

    return PipelineFlowResult(
        ok=True,
        scopedPlanId=plan_id,
        scopedPlanLabel=scoped_plan_label,
        availablePlans=available_plans,
        stages=stage_groups,
        steps=step_records,
        transitions=transitions,
        summary=summary,
    )
