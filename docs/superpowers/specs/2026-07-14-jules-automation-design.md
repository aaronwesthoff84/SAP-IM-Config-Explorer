# Jules Automation Design

**Repository:** `aaronwesthoff84/SAP-IM-Config-Explorer`  
**Date:** 2026-07-14  
**Status:** Approved design pending implementation-plan review

## 1. Purpose

Create a bounded, mostly autonomous software-delivery loop in which Google Jules implements well-specified GitHub Issues, validates changes through independent GitHub Actions, repairs failed checks within defined limits, and auto-merges eligible low- and medium-risk changes.

Aaron remains involved only when product details are missing, automation cannot recover, or a high-risk change requires explicit approval.

## 2. Goals

- Use GitHub Issues as the authoritative backlog.
- Use a GitHub Project as the ordered queue and operational dashboard.
- Allow Aaron to add, refine, prioritize, pause, approve, and block work through GitHub or an AI chat connected to GitHub.
- Keep up to two non-conflicting Issues active with Jules.
- Merge Jules pull requests sequentially.
- Require independent validation and review before auto-merge.
- Preserve the application's local-first, privacy-preserving design.
- Notify Aaron only when action is required.

## 3. Non-goals

- Allowing Jules to choose arbitrary open Issues.
- Allowing direct writes to `master`.
- Allowing unlimited repair loops or unlimited concurrent tasks.
- Treating repeated execution of the same test as sufficient verification.
- Auto-merging high-risk changes without Aaron's approval.
- Making GitHub Project fields the only machine-readable source of workflow state.
- Replacing GitHub Issues with `README.md`, planning documents, or chat history.

## 4. Operating model

GitHub Issues are the durable work contracts. The GitHub Project provides ordering and visibility. Labels provide repository-local machine-readable state. GitHub Actions coordinate dispatch, validation, escalation, and post-merge progression. Jules remains the implementation agent.

Normal flow:

```text
Idea or request
  -> Issue refinement
  -> Ready for Jules
  -> Dispatcher adds `jules`
  -> Jules creates branch and pull request
  -> CI, browser tests, security checks, and independent review
  -> Repair loop when needed
  -> Sequential merge gate
  -> Auto-merge or Aaron approval
  -> Issue closed, Project moved to Done, branch deleted
  -> Next eligible Issue dispatched
```

## 5. Human interaction

Aaron can manage the system in three ways:

1. Chat with an AI that has GitHub access.
2. Respond to a GitHub Issue or pull-request notification.
3. Manually use the GitHub Project board.

Examples of supported chat requests:

- Create an Issue from a rough feature idea.
- Refine an Issue and add acceptance criteria.
- Move an Issue to the top of the Jules queue.
- Pause or resume new dispatches.
- Approve or reject a high-risk pull request.
- Show all items waiting for Aaron.
- Block, retry, cancel, or reprioritize work.

GitHub remains the source of truth after every chat-driven update.

## 6. Notifications

Aaron's primary notification channel is a GitHub mention to `@aaronwesthoff84`, using GitHub's normal web and email notifications.

Aaron is notified only when:

- Required Issue details are missing.
- A high-risk change requires approval.
- CI still fails after two Jules repair attempts.
- An independent review reports a blocking concern.
- A pull request cannot be rebased or has an unresolved merge conflict.
- Jules identifies a product, privacy, schema, or architecture decision that the Issue does not resolve.

Action-required comments must contain:

- A concise reason.
- What Jules or automation already attempted.
- The exact decision needed.
- A recommended response.
- Supported commands.

Supported owner-only commands should include:

```text
/approve
/request-changes <instructions>
/retry
/block <reason>
/cancel
/needs-details
/ready
/pause
/resume
```

Only commands issued by the repository owner are trusted for privileged workflow transitions.

## 7. Project statuses

The Project should use these statuses:

| Status | Meaning |
|---|---|
| Idea | Captured but not refined |
| Needs Details | Not safe or clear enough to implement |
| Ready for Jules | Validated and ordered queue |
| Jules Working | Dispatched to Jules |
| PR Validation | Pull request open and gates running |
| Waiting for Aaron | Requires an owner decision |
| Blocked | Automation cannot proceed |
| Ready to Merge | All automated gates passed |
| Done | Merged and closed |

Project built-in workflows should handle simple transitions such as adding repository Issues and moving closed items to Done. Repository workflows handle validation, Jules dispatch, concurrency, risk, and escalation.

## 8. Labels

Recommended labels:

### State

- `state:idea`
- `state:needs-details`
- `state:ready`
- `state:in-progress`
- `state:waiting-owner`
- `state:blocked`
- `state:ready-to-merge`

### Agent and automation

- `jules`
- `agent:jules`
- `automation:paused`
- `automation:repair-1`
- `automation:repair-2`

### Risk

- `risk:low`
- `risk:medium`
- `risk:high`

### Type

- `type:bug`
- `type:feature`
- `type:refactor`
- `type:test`
- `type:documentation`
- `type:maintenance`

### Area

- `area:graph-model`
- `area:xml-parser`
- `area:html-output`
- `area:web-ui`
- `area:testing`
- `area:documentation`
- `area:dependencies`

The native `jules` label is the final dispatch trigger. `agent:jules` records intended ownership before dispatch.

## 9. Issue readiness contract

An Issue is eligible only when it contains:

- Problem or user need.
- Goal.
- User-visible behavior.
- Scope.
- Non-goals.
- Acceptance criteria.
- Required test coverage.
- Relevant examples, fixtures, or screenshots when applicable.
- Dependencies.
- Security and privacy considerations.
- Definition of done.

An Issue must also:

- Be in Ready for Jules.
- Carry `state:ready` and `agent:jules`.
- Have exactly one risk label.
- Have at least one area label.
- Have no unresolved dependency.
- Not carry `state:blocked`, `state:needs-details`, or `automation:paused`.

If required details are missing, automation removes Jules eligibility, moves the item to Needs Details, and mentions Aaron with the missing sections.

## 10. Dispatch and concurrency

Maximum active Jules Issues: **two**.

The dispatcher selects Issues from the top of the Ready for Jules queue. Before adding `jules`, it verifies readiness, dependencies, the global pause state, and active work count.

The second Issue may start only when its declared area does not overlap the first active Issue's primary area. When overlap cannot be determined confidently, work is serialized.

A repository variable controls dispatch:

```text
JULES_AUTOMATION_ENABLED=true
```

Setting it to false prevents new dispatches without interrupting active pull requests.

The dispatcher should run on relevant Issue and Project events and on a conservative scheduled reconciliation interval. Scheduled reconciliation makes the workflow self-healing when an external integration misses an event.

## 11. Jules instructions

A root `AGENTS.md` will define:

- Exact environment setup and validation commands.
- The local-first privacy guarantee.
- The strict graph node allowlist.
- Snapshot-scoped reference resolution.
- Prohibition on inferred graph nodes.
- Requirements for targeted regression tests.
- Browser-test expectations for UI changes.
- Dependency documentation requirements.
- One primary Issue per pull request.
- Required pull-request description sections.
- Prohibition on hiding errors instead of fixing root causes.
- Requirement to stop and request clarification for unresolved product, privacy, schema, or architectural decisions.

## 12. Validation pipeline

Every Jules pull request must pass independent GitHub Actions checks.

### Python tests

```powershell
python -m pytest -q
```

### JavaScript validation

```powershell
node --check sap_im_config_graph_explorer/static/app.js
```

### XML-to-HTML acceptance validation

- Convert representative XML fixtures.
- Verify expected HTML sections and behavior.
- Use deterministic output assertions where practical.

### Graph acceptance validation

- Verify the approved node allowlist.
- Verify containment and dependency direction.
- Verify snapshot isolation.
- Verify duplicate, missing-reference, ambiguous-reference, unused, and orphaned findings.

### Targeted regression coverage

Every behavior change or bug fix must add or update automated coverage tied to the Issue's acceptance criteria.

### Playwright browser validation

Initial critical-path tests must cover:

- Uploading XML.
- Generating the graph.
- Searching and filtering.
- Selecting nodes and inspecting details.
- Generating, previewing, and downloading HTML.
- Comparing two XML files.
- Switching themes.
- Detecting uncaught browser errors.

Relevant feature Issues must extend the browser suite when user-visible behavior changes.

### Security and dependency validation

- Dependency review for pull requests.
- Static analysis appropriate to Python and JavaScript.
- Secret scanning where repository capabilities permit it.
- No new unresolved high-severity findings.

## 13. Independent review

Jules cannot approve its own work.

An independent automated reviewer must assess:

- Acceptance-criteria coverage.
- Test adequacy.
- Security and privacy.
- Local-first compliance.
- Graph-contract compliance.
- Backward compatibility.
- Dependency necessity and risk.
- Maintainability.

A blocking finding prevents auto-merge. Review findings must be machine-readable or mapped to a required check so branch protection can enforce them.

The implementation plan must select the exact reviewer available to the repository. Preferred order:

1. GitHub Copilot automatic code review, if enabled for the repository and enforceable in the selected plan.
2. A separate review workflow using a non-Jules model and a required status check.
3. Static analysis plus mandatory owner approval until an independent AI reviewer is configured.

The system must not claim independent AI review is active until the selected reviewer is actually configured and verified.

## 14. Risk policy

Low- and medium-risk changes may auto-merge after all required gates pass.

The following are always high risk and require Aaron's explicit approval:

- Sending XML or configuration content to an external AI model or service.
- Authentication, authorization, secrets, credentials, or permissions.
- Persisted file-format or graph-schema changes.
- Destructive or irreversible behavior.
- Major architectural changes.
- Changes affecting privacy or the local-first guarantee.

Automation may raise risk but must not automatically downgrade `risk:high`.

## 15. Dependency policy

Jules may add or upgrade dependencies when needed for an Issue, provided the pull request documents:

- Why the dependency is required.
- Alternatives considered.
- Runtime or development-only impact.
- License and maintenance considerations.
- Security implications.

A dependency change becomes high risk when it materially affects architecture, security, privacy, external data transfer, persisted formats, or the local-first guarantee.

## 16. Repair policy

When a required check fails:

1. Failure evidence is posted to the pull request.
2. Jules receives repair attempt one.
3. Relevant and full required checks rerun.
4. Jules receives repair attempt two if needed.
5. If checks still fail, automation removes Jules eligibility, marks the Issue Blocked, disables auto-merge, and mentions Aaron with a concise diagnosis.

Passing only on retry does not erase evidence of a flaky test. Flakiness must remain visible and block auto-merge when reliability is uncertain.

## 17. Sequential merge policy

Two Issues may be under development, but only one Jules pull request may merge at a time.

Before the second pull request becomes merge-eligible after another merge:

- Its branch must be updated from `master`.
- All required checks must rerun.
- Independent review must rerun against the updated branch.
- Merge conflicts must be resolved.

Eligible pull requests use squash merge and must:

- Be current with `master`.
- Pass every required check.
- Have no unresolved blocking findings.
- Link exactly one primary Issue.
- Include test evidence and required documentation updates.

High-risk pull requests additionally require Aaron's approval.

## 18. Post-merge behavior

After successful merge:

- The linked Issue closes.
- The Project item moves to Done.
- The source branch is deleted.
- Completed automation labels are cleaned up.
- The next eligible Issue is dispatched automatically.

## 19. Branch and repository protection

The default branch must require:

- Pull requests for changes.
- Required CI and review checks.
- Up-to-date branches before merge.
- Resolution of blocking review conversations.
- No force pushes.
- No branch deletion.

Auto-merge remains disabled until all required workflows are installed, verified on a setup pull request, and selected as required checks.

## 20. Initial implementation scope

The first implementation effort will add:

- Root `AGENTS.md`.
- Structured GitHub Issue Forms.
- Pull-request template.
- Workflow and label documentation.
- CI workflow.
- Playwright installation and initial critical-path tests.
- Dependency and static-analysis checks.
- Independent review integration or an explicit temporary approval fallback.
- Jules dispatcher and concurrency controls.
- Owner-command processing.
- Repair and escalation workflows.
- Sequential merge control.
- Post-merge cleanup and next-work dispatch.
- Repository documentation for chat and GitHub management.
- A readiness migration for current open Issues.

GitHub Project creation, custom fields, status values, and organization/user-level permissions may require owner actions that repository files cannot perform safely with the default Actions token. The implementation must document and minimize those one-time steps rather than pretending they are repository-local automation.

## 21. Rollout

### Stage 1: Observe-only

- Install CI and review checks.
- Do not dispatch or auto-merge.
- Validate checks on the setup pull request.

### Stage 2: Controlled dispatch

- Enable one active Jules Issue.
- Require owner approval for all merges.
- Validate Project synchronization and repair handling.

### Stage 3: Two-slot automation

- Enable two non-conflicting active Issues.
- Permit low-risk auto-merge.
- Keep medium-risk owner-approved temporarily.

### Stage 4: Approved target state

- Permit low- and medium-risk sequential auto-merge.
- Retain mandatory owner approval for high-risk work.

Promotion between stages requires evidence that dispatch, checks, escalation, and merge controls behave correctly.

## 22. Success criteria

The system is ready when:

- Aaron can create or reprioritize work through GitHub or AI chat.
- Only validated Issues reach Jules.
- No more than two non-conflicting Issues are active.
- Every Jules pull request receives independent tests and review.
- Low- and medium-risk changes merge sequentially without routine intervention.
- High-risk changes cannot merge without Aaron.
- Failed work stops after two repair attempts and clearly requests action.
- A successful merge closes the Issue, updates the Project, deletes the branch, and starts the next eligible item.
- Pausing dispatch prevents new Jules tasks.
- Repository documentation accurately matches actual automation behavior.
