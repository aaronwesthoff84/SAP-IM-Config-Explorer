from __future__ import annotations

from dataclasses import dataclass

REQUIRED_HEADINGS = (
    "Goal",
    "Scope",
    "Acceptance criteria",
)

HIGH_RISK_PATH_PREFIXES = (
    "sap_im_config_graph_explorer/models",
    "sap_im_config_graph_explorer/graph",
    "requirements.txt",
)


def missing_headings(body: str) -> tuple[str, ...]:
    lowered = body.lower()
    return tuple(h for h in REQUIRED_HEADINGS if f"## {h.lower()}" not in lowered)


def risk_from_labels(labels: set[str]) -> str:
    risks = sorted(label.removeprefix("risk:") for label in labels if label.startswith("risk:"))
    return risks[0] if len(risks) == 1 else "invalid"


def primary_area(labels: set[str]) -> str:
    areas = sorted(label for label in labels if label.startswith("area:"))
    return areas[0] if len(areas) == 1 else "unknown"


def issue_is_ready(*, body: str, labels: set[str], dependencies_open: bool = False) -> bool:
    return (
        not missing_headings(body)
        and "state:ready" in labels
        and "agent:jules" in labels
        and risk_from_labels(labels) in {"low", "medium", "high"}
        and primary_area(labels) != "unknown"
        and not dependencies_open
        and "state:blocked" not in labels
        and "state:needs-details" not in labels
    )


@dataclass(frozen=True)
class MergeDecision:
    eligible: bool
    waiting_for_owner: bool
    reasons: tuple[str, ...]


def decide_merge(
    *,
    risk: str,
    owner_approved: bool,
    required_checks: dict[str, str],
    linked_issue_count: int,
    branch_current: bool,
    merge_lock_available: bool,
    blocking_findings: tuple[str, ...] = (),
) -> MergeDecision:
    reasons: list[str] = []
    if linked_issue_count != 1:
        reasons.append("Exactly one primary Issue is required")
    failed = sorted(name for name, state in required_checks.items() if state != "success")
    if failed:
        reasons.append("Required checks not successful: " + ", ".join(failed))
    if not branch_current:
        reasons.append("Branch must be current with master")
    if not merge_lock_available:
        reasons.append("Another Jules pull request owns the merge lock")
    reasons.extend(blocking_findings)
    waiting = risk == "high" and not owner_approved
    if waiting:
        reasons.append("High-risk change requires owner approval")
    return MergeDecision(not reasons, waiting, tuple(reasons))
