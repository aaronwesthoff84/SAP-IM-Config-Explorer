# Triage Labels

The engineering skills use five canonical triage-state roles. This file maps those roles to the GitHub label strings used in this repository.

| Label in mattpocock/skills | Label in this repository | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Maintainer needs to evaluate the issue |
| `needs-info` | `needs-info` | Waiting for information or a decision |
| `ready-for-agent` | `ready-for-agent` | Fully specified and ready for an AFK agent |
| `ready-for-human` | `ready-for-human` | Requires human implementation or judgment |
| `wontfix` | `wontfix` | Will not be actioned |

When a skill mentions a canonical role, apply the corresponding repository label from this table.

## Classification rules

Every triaged implementation issue should have:

- Exactly one category: `bug` or `enhancement`.
- Exactly one canonical triage-state label from the table above.

Other labels—including `backlog`, `area:*`, `risk:*`, `type:*`, `automation:*`, and ownership labels—are supplemental. They do not replace the category or triage-state label.

An issue without a triage-state label should initially receive `needs-triage`.

When an issue moves to `ready-for-agent`, add a durable `## Agent Brief` comment describing:

- Category and summary
- Current behavior
- Desired behavior
- Key interfaces
- Testable acceptance criteria
- Explicit out-of-scope boundaries

Improve existing issues in place. Do not recreate them solely to change their labels or add an Agent Brief.
