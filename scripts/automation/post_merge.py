from __future__ import annotations


def build_post_merge_actions(event: dict, default_branch: str = "master") -> tuple[str, ...]:
    actions = ["close-primary-issue", "move-project-item-to-done", "clear-merge-lock"]
    head_ref = event["pull_request"]["head"]["ref"]
    if head_ref != default_branch:
        actions.append("delete-source-branch")
    actions.append("dispatch-next-issue")
    return tuple(actions)
