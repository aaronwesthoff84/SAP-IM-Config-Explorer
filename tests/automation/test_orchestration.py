from scripts.automation.owner_commands import OwnerCommand, parse_owner_command
from scripts.automation.policy import decide_merge, issue_is_ready, missing_headings
from scripts.automation.post_merge import build_post_merge_actions
from scripts.automation.project_queue import select_dispatch_candidates
from scripts.automation.repair_controller import build_repair_comment, next_repair_attempt


def test_issue_readiness_contract():
    body = "## Goal\nX\n## Scope\nY\n## Acceptance criteria\n- Works"
    labels = {"state:ready", "agent:jules", "risk:medium", "area:web-ui"}
    assert not missing_headings(body)
    assert issue_is_ready(body=body, labels=labels)
    assert not issue_is_ready(body="## Goal\nX", labels=labels)


def test_queue_limits_and_serializes_areas():
    ordered = [
        {"number": 1, "eligible": True, "primary_area": "area:web-ui"},
        {"number": 2, "eligible": True, "primary_area": "area:web-ui"},
        {"number": 3, "eligible": True, "primary_area": "area:html-output"},
    ]
    assert [item["number"] for item in select_dispatch_candidates(ordered, [], 2)] == [1, 3]
    assert select_dispatch_candidates(ordered, [{"primary_area": "area:web-ui"}, {"primary_area": "area:testing"}], 2) == []


def test_merge_policy():
    checks = {name: "success" for name in ("validation", "e2e", "codeql", "dependency-review", "automation-policy-review")}
    assert decide_merge(risk="medium", owner_approved=False, required_checks=checks, linked_issue_count=1, branch_current=True, merge_lock_available=True).eligible
    high = decide_merge(risk="high", owner_approved=False, required_checks=checks, linked_issue_count=1, branch_current=True, merge_lock_available=True)
    assert high.waiting_for_owner and not high.eligible


def test_owner_commands_are_trusted():
    assert parse_owner_command("someone", "/approve") is None
    assert parse_owner_command("aaronwesthoff84", "/approve") == OwnerCommand("approve")
    assert parse_owner_command("aaronwesthoff84", "/block") is None
    assert parse_owner_command("aaronwesthoff84", "/block unsafe") == OwnerCommand("block", "unsafe")


def test_repair_is_capped_at_two():
    assert next_repair_attempt(set()) == 1
    assert next_repair_attempt({"automation:repair-1"}) == 2
    assert next_repair_attempt({"automation:repair-2"}) is None
    assert "Repair attempt: 2 of 2" in build_repair_comment(["e2e"], 2)


def test_post_merge_actions_do_not_delete_default_branch():
    event = {"pull_request": {"head": {"ref": "jules/feature"}}}
    assert "delete-source-branch" in build_post_merge_actions(event)
    default = {"pull_request": {"head": {"ref": "master"}}}
    assert "delete-source-branch" not in build_post_merge_actions(default)
