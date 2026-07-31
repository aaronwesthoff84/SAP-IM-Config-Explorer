# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues:

`aaronwesthoff84/SAP-IM-Config-Explorer`

Use the `gh` CLI for issue operations.

## Conventions

- **Create an issue:** `gh issue create --title "..." --body "..."`
- **Create an issue with a multiline body:** pipe a PowerShell here-string to `gh issue create --body-file -`.
- **Read an issue:** `gh issue view <number> --comments`
- **List issues:** `gh issue list --state open --json number,title,body,labels,comments`
- **Comment:** `gh issue comment <number> --body "..."`
- **Apply a label:** `gh issue edit <number> --add-label "..."`
- **Remove a label:** `gh issue edit <number> --remove-label "..."`
- **Close:** `gh issue close <number> --comment "..."`

Infer the repository from `git remote -v`; `gh` does this automatically when run inside the clone.

Preserve existing issues and their history. Improve their labels, descriptions, and Agent Brief comments in place rather than closing and recreating them unless an issue is genuinely a duplicate or superseded.

## Pull requests as a triage surface

**PRs as a request surface: no.**

Pull requests are implementation and review surfaces, not substitutes for feature requests. Each pull request should identify one primary GitHub Issue.

GitHub shares one number space across issues and pull requests. A bare reference such as `#42` may refer to either one. Resolve it with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run:

```powershell
gh issue view <number> --comments
```

## Wayfinding operations

The `/wayfinder` skill uses one map issue with child issues as tickets.

- **Map:** a single issue labelled `wayfinder:map`, containing Notes, Decisions-so-far, and Fog.
- **Child ticket:** link the issue as a GitHub sub-issue. If sub-issues are unavailable, add it to a task list in the map and put `Part of #<map>` at the beginning of the child body.
- **Child labels:** use `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`.
- **Blocking:** use GitHub's native issue dependencies. If those are unavailable, add `Blocked by: #<number>` to the child body.
- **Frontier:** the next ticket is the first open, unassigned child whose blockers are all closed.
- **Claim:** `gh issue edit <number> --add-assignee @me`
- **Resolve:** comment with the result, close the child issue, and add a durable context link to the map's Decisions-so-far section.
