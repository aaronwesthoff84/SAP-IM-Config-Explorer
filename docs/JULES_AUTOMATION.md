# Jules Automation

This repository uses GitHub Issues as work contracts and Google Jules as the implementation agent. The native `jules` label is the final dispatch trigger.

## Issue readiness

A ready Issue includes a `## Goal`, `## Scope`, and `## Acceptance criteria` section, plus required tests, dependencies, security/privacy considerations, and definition of done. It must carry `state:ready`, `agent:jules`, exactly one `risk:*` label, and exactly one `area:*` label.

## Automated queue

`Jules Dispatch` runs on Issue changes, merged pull requests, manual dispatch, and every 15 minutes. It permits at most two active Issues and will not dispatch two Issues with the same area. When a Project token and number are configured, Project item order determines queue order. Without them, the dispatcher falls back to Issue order.

The dispatcher is controlled by the repository variable `JULES_AUTOMATION_ENABLED`. Use `/pause` and `/resume` from an owner-authored Issue or PR comment to change it.

## Risk and merge policy

Low- and medium-risk Jules pull requests become auto-merge eligible only after `validation`, `e2e`, `codeql`, and `dependency-review` succeed. High-risk work requires `/approve` from `@aaronwesthoff84`.

High risk includes external XML/configuration transmission, authentication or credentials, persisted file-format or graph-schema changes, destructive behavior, major architecture changes, and changes to privacy or local-first guarantees.

Pull requests merge sequentially through the `jules-sequential-merge` concurrency group and use squash merge.

## Repair policy

A failed CI run produces a scoped `@jules` repair request. Jules receives no more than two automated repair attempts. A failure after the second attempt moves the linked Issue to `state:blocked` and mentions the owner.

## Owner commands

Only commands authored by `aaronwesthoff84` are trusted:

- `/approve`
- `/request-changes <instructions>`
- `/retry`
- `/block <reason>`
- `/cancel`
- `/needs-details`
- `/ready`
- `/pause`
- `/resume`

## Post-merge behavior

After a Jules pull request merges, automation closes the linked Issue, marks it `state:done`, removes temporary workflow labels, safely deletes the feature branch, and dispatches the next eligible Issue.

## Bootstrap and one-time configuration

Run the `Jules Bootstrap` workflow once after the orchestration pull request merges. It creates the labels and default repository variables, with automation initially paused.

Then configure:

1. A user-owned GitHub Project with statuses: Idea, Needs Details, Ready for Jules, Jules Working, PR Validation, Waiting for Aaron, Blocked, Ready to Merge, and Done.
2. Repository variable `JULES_PROJECT_NUMBER` with that Project number.
3. Repository secret `JULES_PROJECT_TOKEN` using a fine-grained token that can read and update the Project.
4. A `master` ruleset requiring pull requests, current branches, resolved conversations, and checks `validation`, `e2e`, `codeql`, and `dependency-review`.
5. Squash merge, auto-merge, and automatic source-branch deletion.
6. Set `JULES_AUTOMATION_ENABLED=true` or comment `/resume` after the pilot is ready.

GitHub Issues and labels remain the durable fallback if Project synchronization is temporarily unavailable.
