from __future__ import annotations


def next_repair_attempt(labels: set[str]) -> int | None:
    if "automation:repair-2" in labels:
        return None
    if "automation:repair-1" in labels:
        return 2
    return 1


def build_repair_comment(checks: list[str], attempt: int) -> str:
    if attempt not in {1, 2}:
        raise ValueError("repair attempt must be 1 or 2")
    return (
        "@jules Repair the failing required checks for this pull request.\n\n"
        "Do not change the Issue scope. Diagnose the root cause, add or update "
        "regression coverage, run the complete validation commands from AGENTS.md, "
        "and push the repair to this branch.\n\n"
        "Failing checks:\n- "
        + "\n- ".join(checks)
        + f"\n\nRepair attempt: {attempt} of 2"
    )
