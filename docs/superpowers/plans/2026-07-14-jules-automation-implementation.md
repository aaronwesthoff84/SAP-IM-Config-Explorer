# Jules Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded GitHub automation system that dispatches well-specified SAP IM Config Explorer Issues to Google Jules, independently validates the resulting pull requests, auto-merges eligible low- and medium-risk work sequentially, and asks Aaron only when a decision is required.

**Architecture:** GitHub Issues remain the work contracts, a GitHub Project provides ordered queue visibility, repository labels provide machine-readable state, and GitHub Actions coordinate validation, dispatch, risk review, merge control, notifications, and post-merge progression. Google Jules is triggered only by the native `jules` Issue label and never receives direct write access to `master`.

**Tech Stack:** GitHub Actions, GitHub REST and GraphQL APIs, Python 3.12, pytest, FastAPI/Uvicorn, Node.js 20, Playwright, GitHub CodeQL, GitHub Dependency Review, Google Jules.

## Global Constraints

- Default branch is `master`.
- Maximum active Jules Issues is `2`.
- Only one Jules pull request may merge at a time.
- GitHub Issues are the authoritative backlog.
- The GitHub Project is the ordered operational view.
- The native `jules` label is the final Jules dispatch trigger.
- Issues missing required sections move to `Needs Details` and are not dispatched.
- Low- and medium-risk changes may auto-merge after every required gate passes.
- High-risk changes always require approval from `aaronwesthoff84`.
- High risk includes external XML/configuration transmission, authentication or credentials, persisted file-format or graph-schema changes, destructive behavior, major architecture changes, and changes to privacy or local-first guarantees.
- Jules receives at most two automated repair requests after CI failure.
- Every behavior change requires targeted regression coverage.
- UI changes require Playwright coverage where the behavior can be exercised in a browser.
- The strict graph allowlist, snapshot-scoped resolution, and prohibition on inferred graph nodes must remain intact.
- Dependency changes must be justified in the pull-request description.
- No workflow may silently suppress a test failure, warning, browser error, or validation finding.

---

## Delivery Stages

1. **Safe Jules Foundation:** agent instructions, Issue/PR contracts, CI, browser tests, deterministic policy review, and documented owner setup. After this stage, Aaron can safely add the `jules` label manually and receive guarded Jules pull requests.
2. **Automated Queue Dispatch:** Project-backed readiness validation, two-slot concurrency, area conflict serialization, pause/resume, and automatic application of the `jules` label.
3. **Merge, Repair, and Notification Control:** sequential auto-merge, two-attempt repair workflow, owner commands, action-required notifications, post-merge cleanup, and next-Issue dispatch.

---

### Task 1: Add repository-level Jules instructions and work contracts

**Files:**
- Create: `AGENTS.md`
- Create: `.github/ISSUE_TEMPLATE/feature.yml`
- Create: `.github/ISSUE_TEMPLATE/bug.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`
- Create: `docs/JULES_AUTOMATION.md`
- Modify: `README.md`
- Test: `tests/test_project_hygiene.py`

**Interfaces:**
- Consumes: Existing setup and validation commands from `README.md`.
- Produces: A stable Issue contract, PR contract, agent operating instructions, and owner-facing automation guide used by every later task.

- [ ] **Step 1: Extend the project-hygiene test with required automation files**

Add a test that asserts the required files exist and contain the key safety statements:

```python
def test_jules_automation_contract_files_exist():
    required = [
        "AGENTS.md",
        ".github/ISSUE_TEMPLATE/feature.yml",
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/pull_request_template.md",
        "docs/JULES_AUTOMATION.md",
    ]
    assert not [path for path in required if not (ROOT / path).is_file()]

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for required_text in (
        "local-first",
        "strict graph node allowlist",
        "snapshot-scoped",
        "one primary GitHub Issue per pull request",
        "Do not hide or suppress failures",
    ):
        assert required_text in agents
```

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

```powershell
python -m pytest tests/test_project_hygiene.py::test_jules_automation_contract_files_exist -q
```

Expected: failure because the automation contract files do not yet exist.

- [ ] **Step 3: Create `AGENTS.md` with exact Jules operating rules**

The file must include:

```markdown
# SAP IM Config Explorer Agent Instructions

## Required setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

## Required validation

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python -m pytest -q -p no:cacheprovider
node --check sap_im_config_graph_explorer/static/app.js
.\.venv\Scripts\python sap_im_transformer.py tests\fixtures\minimal_plan.xml "$env:TEMP\minimal-plan-acceptance.html" --variant=A
```

## Product invariants

- The application is local-first. XML and configuration content must not leave the workstation unless an approved Issue explicitly requires an external provider and the pull request is marked high risk.
- Preserve the strict graph node allowlist documented in `README.md`.
- Preserve snapshot-scoped reference resolution.
- Never create inferred or placeholder graph nodes for unresolved references.
- Keep Formula and Rule internals as metadata or reference evidence unless a separately approved schema change says otherwise.

## Change contract

- Implement one primary GitHub Issue per pull request.
- Treat the Issue acceptance criteria and non-goals as binding.
- Add targeted regression tests for every behavior change.
- Add or update Playwright coverage for browser-visible behavior where practical.
- Explain every dependency addition or upgrade in the pull-request description.
- Stop and request clarification when product behavior, privacy, schema, destructive behavior, or architecture is unresolved.
- Do not hide or suppress failures, warnings, browser console errors, or validation findings instead of fixing their cause.
```

- [ ] **Step 4: Create Issue Forms with required fields**

Both `feature.yml` and `bug.yml` must require Goal/Problem, User-visible behavior, Scope, Non-goals, Acceptance criteria, Tests, Dependencies, Security/privacy, and Definition of done. They must apply `state:needs-details` by default rather than `jules`.

- [ ] **Step 5: Create the pull-request template**

Require these sections:

```markdown
## Primary Issue

Closes #

## Summary

## Acceptance-criteria coverage

## Validation performed

## Browser validation

## Dependency changes

## Risk and privacy review

## Documentation changes
```

- [ ] **Step 6: Create the owner guide and link it from the README**

`docs/JULES_AUTOMATION.md` must explain the labels, Project statuses, queue controls, owner commands, high-risk policy, manual fallback, and the one-time repository settings required later in this plan.

- [ ] **Step 7: Run project-hygiene tests**

Run:

```powershell
python -m pytest tests/test_project_hygiene.py -q
```

Expected: all project-hygiene tests pass.

- [ ] **Step 8: Commit**

```bash
git add AGENTS.md .github README.md docs/JULES_AUTOMATION.md tests/test_project_hygiene.py
git commit -m "docs: define Jules automation contracts"
```

---

### Task 2: Add a single reproducible validation entry point

**Files:**
- Create: `scripts/validate.py`
- Create: `tests/test_validation_script.py`
- Modify: `README.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: `requirements-dev.txt`, pytest suite, `sap_im_transformer.py`, `tests/fixtures/minimal_plan.xml`, and `sap_im_config_graph_explorer/static/app.js`.
- Produces: `python scripts/validate.py --mode ci`, the canonical local and CI validation command.

- [ ] **Step 1: Write tests for validation command construction and failure propagation**

```python
from scripts.validate import build_commands


def test_ci_mode_contains_required_checks():
    commands = build_commands("ci")
    rendered = [" ".join(command) for command in commands]
    assert any("pytest" in command for command in rendered)
    assert any("node --check sap_im_config_graph_explorer/static/app.js" in command for command in rendered)
    assert any("sap_im_transformer.py" in command for command in rendered)
```

Also test that the runner returns the first non-zero exit status and never skips later-required reporting.

- [ ] **Step 2: Verify the new tests fail**

```powershell
python -m pytest tests/test_validation_script.py -q
```

Expected: import failure because `scripts/validate.py` does not exist.

- [ ] **Step 3: Implement `scripts/validate.py`**

Implement:

```python
def build_commands(mode: str) -> list[list[str]]: ...
def run_commands(commands: list[list[str]]) -> int: ...
def main() -> int: ...
```

`ci` mode must execute the full pytest suite, JavaScript syntax validation, and XML-to-HTML acceptance conversion. It must print each command before execution and return a non-zero exit code on any failure.

- [ ] **Step 4: Run targeted and full tests**

```powershell
python -m pytest tests/test_validation_script.py -q
python scripts/validate.py --mode ci
```

Expected: validation succeeds with no new warnings beyond issues explicitly tracked in GitHub.

- [ ] **Step 5: Update documentation to use the canonical command**

Add:

```powershell
.\.venv\Scripts\python scripts\validate.py --mode ci
```

Keep the component commands documented for troubleshooting.

- [ ] **Step 6: Commit**

```bash
git add scripts/validate.py tests/test_validation_script.py README.md AGENTS.md
git commit -m "test: add reproducible validation entry point"
```

---

### Task 3: Add independent GitHub Actions CI and security gates

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/codeql.yml`
- Create: `.github/workflows/dependency-review.yml`
- Modify: `tests/test_project_hygiene.py`

**Interfaces:**
- Consumes: `python scripts/validate.py --mode ci` from Task 2.
- Produces required checks named `validation`, `codeql`, and `dependency-review` for branch protection and merge control.

- [ ] **Step 1: Add hygiene assertions for workflow permissions and triggers**

The test must parse the workflow text and assert:

- Pull-request validation runs on `master`.
- Default permissions are read-only.
- No workflow uses `pull_request_target` for untrusted code execution.
- CI calls `python scripts/validate.py --mode ci`.

- [ ] **Step 2: Verify the hygiene tests fail**

```powershell
python -m pytest tests/test_project_hygiene.py -q
```

Expected: failure because workflows are absent.

- [ ] **Step 3: Create `ci.yml`**

Use Ubuntu, Python 3.12, dependency caching, `pip install -r requirements-dev.txt`, and the canonical validation command. Upload generated acceptance artifacts and test output on failure.

- [ ] **Step 4: Create CodeQL and dependency-review workflows**

`codeql.yml` must analyze Python and JavaScript on pull requests and a weekly schedule. `dependency-review.yml` must run on pull requests and fail for newly introduced high-severity vulnerabilities.

- [ ] **Step 5: Run local tests and inspect workflow syntax**

```powershell
python -m pytest tests/test_project_hygiene.py -q
```

Expected: pass. Validate YAML with a parser in the test rather than relying on visual inspection.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows tests/test_project_hygiene.py
git commit -m "ci: add validation and security gates"
```

---

### Task 4: Add Playwright critical-path browser validation

**Files:**
- Create: `package.json`
- Create: `package-lock.json`
- Create: `playwright.config.ts`
- Create: `tests/e2e/app-smoke.spec.ts`
- Create: `tests/e2e/fixtures/minimal_plan.xml`
- Modify: `.gitignore`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/validate.py`
- Modify: `tests/test_validation_script.py`

**Interfaces:**
- Consumes: Local FastAPI app at `http://127.0.0.1:8000`, representative XML fixture, and existing browser UI controls.
- Produces: `npm run test:e2e`, Playwright traces/screenshots on failure, and an `e2e` required check.

- [ ] **Step 1: Add failing validation-script expectations for browser mode**

Assert that `build_commands("full")` includes `npm ci` and `npm run test:e2e`, while `ci` mode remains suitable for Python-only debugging when requested.

- [ ] **Step 2: Create the Playwright package and configuration**

Use Node 20-compatible Playwright, Chromium only initially, one worker in CI, trace on first retry, screenshot on failure, and a `webServer` command that starts:

```powershell
python -m uvicorn sap_im_config_graph_explorer.app:app --host 127.0.0.1 --port 8000
```

- [ ] **Step 3: Write the critical-path smoke test**

The test must:

1. Open the app.
2. Confirm the page title identifies SAP IM Config Explorer.
3. Upload `minimal_plan.xml`.
4. Generate a graph.
5. Confirm Plans, Plan Components, and Rules are visible.
6. Select a node and confirm the details panel changes.
7. Generate HTML and confirm the preview is populated.
8. Switch theme and confirm the selection persists after reload.
9. Fail on uncaught page errors or unexpected console errors.

- [ ] **Step 4: Run Playwright locally**

```powershell
npm ci
npx playwright install chromium
npm run test:e2e
```

Expected: all browser tests pass without uncaught browser errors.

- [ ] **Step 5: Add the `e2e` CI job**

Install Node 20, run `npm ci`, install Chromium with dependencies, execute Playwright, and upload the HTML report, traces, and screenshots when the job fails.

- [ ] **Step 6: Run complete validation**

```powershell
python scripts/validate.py --mode full
```

Expected: Python tests, JavaScript check, converter acceptance test, and Playwright all pass.

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json playwright.config.ts tests/e2e .gitignore .github/workflows/ci.yml scripts/validate.py tests/test_validation_script.py
git commit -m "test: add Playwright critical-path validation"
```

---

### Task 5: Implement deterministic Issue readiness and risk policy

**Files:**
- Create: `scripts/automation/__init__.py`
- Create: `scripts/automation/issue_policy.py`
- Create: `scripts/automation/pr_policy.py`
- Create: `tests/automation/test_issue_policy.py`
- Create: `tests/automation/test_pr_policy.py`
- Create: `.github/automation-policy.json`

**Interfaces:**
- Consumes: Issue title/body/labels, PR changed paths, dependency diff metadata, and the policy JSON.
- Produces:
  - `evaluate_issue(issue: dict) -> IssueDecision`
  - `evaluate_pull_request(pr: dict, changed_paths: list[str]) -> PullRequestDecision`
  - JSON-serializable reasons, missing sections, risk, and required owner approval.

- [ ] **Step 1: Write Issue-policy tests**

Cover:

- Complete Issue is eligible.
- Missing required section returns `needs-details` and lists the exact missing sections.
- Missing/duplicate risk labels are rejected.
- Missing area label is rejected.
- `risk:high` remains dispatchable only when explicitly approved for implementation but can never auto-merge.
- Blocked, paused, or unresolved-dependency Issues are not eligible.

- [ ] **Step 2: Write PR-policy tests**

High-risk detection must include changes to:

```text
requirements.txt
sap_im_config_graph_explorer/graph_schema.py
sap_im_config_graph_explorer/models.py
```

when the diff indicates schema/runtime dependency impact, plus any external network-client introduction, credential handling, upload-to-provider code, or destructive file operations. Documentation-only and test-only changes should normally classify as low risk.

- [ ] **Step 3: Verify tests fail**

```powershell
python -m pytest tests/automation -q
```

Expected: import failures because policy modules are absent.

- [ ] **Step 4: Implement typed decisions**

Use frozen dataclasses or typed dictionaries with explicit fields:

```python
@dataclass(frozen=True)
class IssueDecision:
    eligible: bool
    target_state: str
    missing_sections: tuple[str, ...]
    reasons: tuple[str, ...]

@dataclass(frozen=True)
class PullRequestDecision:
    risk: Literal["low", "medium", "high"]
    owner_approval_required: bool
    blocking_reasons: tuple[str, ...]
```

- [ ] **Step 5: Add the repository policy JSON**

Store required sections, labels, area conflict groups, high-risk path patterns, trusted owner, maximum concurrency `2`, repair limit `2`, and default branch `master`.

- [ ] **Step 6: Run tests**

```powershell
python -m pytest tests/automation -q
python scripts/validate.py --mode ci
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/automation tests/automation .github/automation-policy.json
git commit -m "feat: add deterministic Jules readiness and risk policy"
```

---

### Task 6: Add Project queue synchronization and Jules dispatcher

**Files:**
- Create: `scripts/automation/github_graphql.py`
- Create: `scripts/automation/project_queue.py`
- Create: `tests/automation/test_project_queue.py`
- Create: `.github/workflows/jules-dispatch.yml`
- Modify: `docs/JULES_AUTOMATION.md`

**Interfaces:**
- Consumes: GitHub Project GraphQL data, repository variables, Issue-policy decisions, and active Jules Issue/PR state.
- Produces:
  - `select_dispatch_candidates(items, active_work, limit=2) -> list[Candidate]`
  - Project status synchronization.
  - Native `jules` label application for eligible Issues.

- [ ] **Step 1: Write queue-selection tests**

Cover:

- Top-to-bottom Project order.
- Maximum two active Issues.
- No dispatch when `JULES_AUTOMATION_ENABLED=false`.
- Shared primary area serializes work.
- Unknown area overlap serializes work.
- Closed dependencies allow dispatch; open dependencies block it.
- Already labeled `jules` Issues are not dispatched twice.

- [ ] **Step 2: Implement GraphQL query and mutation helpers**

Use GitHub's GraphQL API to read Project items and status/order and to update Project status. Keep API transport isolated in `github_graphql.py`; queue selection must remain pure and unit-testable.

Required repository variables:

```text
JULES_AUTOMATION_ENABLED=true
JULES_PROJECT_OWNER=aaronwesthoff84
JULES_PROJECT_NUMBER=<the created Project number>
JULES_RECONCILE_MINUTES=15
```

The Project field and option IDs must be discovered at runtime by name and cached only for the workflow run; they must not be hard-coded.

- [ ] **Step 3: Create `jules-dispatch.yml`**

Trigger on:

- `issues` changes relevant to labels/state.
- `pull_request` close/merge events.
- `workflow_dispatch`.
- A 15-minute reconciliation schedule.

Permissions must be minimal: Issues write, pull requests read, contents read. Project access uses a fine-grained owner token stored as `JULES_PROJECT_TOKEN` because repository `GITHUB_TOKEN` Project permissions are insufficient for user-owned Projects.

- [ ] **Step 4: Implement readiness failure handling**

When a candidate is incomplete:

- Remove `jules` if present.
- Apply `state:needs-details`.
- Update Project status to Needs Details.
- Add one idempotent comment mentioning `@aaronwesthoff84` and listing missing sections.

- [ ] **Step 5: Implement dispatch**

For each selected candidate:

- Apply `state:in-progress`.
- Update Project status to Jules Working.
- Add the native `jules` label last, after all state mutations succeed.
- Record a machine-readable dispatch marker comment to prevent duplicate dispatch.

- [ ] **Step 6: Run tests and dry-run the workflow**

```powershell
python -m pytest tests/automation/test_project_queue.py -q
```

Run the script against checked-in JSON fixtures before enabling write mode. Expected: the top two non-conflicting eligible Issues are selected in Project order.

- [ ] **Step 7: Commit**

```bash
git add scripts/automation/github_graphql.py scripts/automation/project_queue.py tests/automation/test_project_queue.py .github/workflows/jules-dispatch.yml docs/JULES_AUTOMATION.md
git commit -m "feat: dispatch Project queue Issues to Jules"
```

---

### Task 7: Add PR lifecycle, independent policy review, and sequential merge control

**Files:**
- Create: `scripts/automation/pr_controller.py`
- Create: `tests/automation/test_pr_controller.py`
- Create: `.github/workflows/jules-pr-control.yml`
- Modify: `.github/automation-policy.json`
- Modify: `docs/JULES_AUTOMATION.md`

**Interfaces:**
- Consumes: PR metadata, linked Issue, required-check conclusions, PR policy decision, active merge lock, and owner approval marker.
- Produces: PR state labels, Project status changes, merge eligibility decision, and sequential auto-merge enablement.

- [ ] **Step 1: Write controller tests**

Cover:

- Low/medium risk plus all green checks is merge-eligible.
- High risk always requires owner approval.
- Missing primary Issue blocks merge.
- Multiple primary Issues block merge.
- Failed or pending checks block merge.
- A second Jules PR waits while another merge lock exists.
- After the first merge, the second must be current with `master` and all checks must rerun.
- Blocking policy findings prevent merge.

- [ ] **Step 2: Implement a pure merge decision function**

```python
def decide_merge(
    *,
    risk: str,
    owner_approved: bool,
    required_checks: dict[str, str],
    linked_issue_count: int,
    branch_current: bool,
    merge_lock_available: bool,
    blocking_findings: tuple[str, ...],
) -> MergeDecision:
    ...
```

- [ ] **Step 3: Create `jules-pr-control.yml`**

Trigger on PR open/synchronize/reopen, check-suite completion, review submission, and manual dispatch. The workflow must:

1. Confirm the PR is Jules-originated through the linked Issue dispatch marker.
2. Run deterministic PR policy review.
3. Update the Project to PR Validation, Waiting for Aaron, Blocked, or Ready to Merge.
4. Apply state/risk labels idempotently.
5. Enable GitHub auto-merge only when the merge decision is eligible.

- [ ] **Step 4: Implement independent review gates**

Required gates are:

- `validation`
- `e2e`
- `codeql`
- `dependency-review`
- `automation-policy-review`

`automation-policy-review` must validate Issue acceptance-criteria mapping, changed-path risk, dependency justification, required tests, local-first constraints, and graph-contract-sensitive changes. It is independent of Jules because it runs deterministic repository-owned code in GitHub Actions.

- [ ] **Step 5: Implement high-risk notification**

Add one idempotent PR comment:

```markdown
## Action required from @aaronwesthoff84

**Reason:** High-risk change detected
**Approval required because:** <reasons>

Commands:
- `/approve`
- `/request-changes <instructions>`
- `/block <reason>`
- `/cancel`
```

- [ ] **Step 6: Run tests**

```powershell
python -m pytest tests/automation/test_pr_controller.py tests/automation/test_pr_policy.py -q
```

Expected: all lifecycle and risk cases pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/automation/pr_controller.py tests/automation/test_pr_controller.py .github/workflows/jules-pr-control.yml .github/automation-policy.json docs/JULES_AUTOMATION.md
git commit -m "feat: control Jules pull request validation and merging"
```

---

### Task 8: Add two-attempt repair and owner command handling

**Files:**
- Create: `scripts/automation/owner_commands.py`
- Create: `scripts/automation/repair_controller.py`
- Create: `tests/automation/test_owner_commands.py`
- Create: `tests/automation/test_repair_controller.py`
- Create: `.github/workflows/owner-command.yml`
- Create: `.github/workflows/jules-repair.yml`
- Modify: `docs/JULES_AUTOMATION.md`

**Interfaces:**
- Consumes: Owner Issue/PR comments, failing check summaries, repair-attempt labels, and Jules PR metadata.
- Produces: trusted command decisions, at most two repair requests, blocked escalation, pause/resume state, and owner notifications.

- [ ] **Step 1: Write command parser tests**

Recognize only comments authored by `aaronwesthoff84` and only these commands:

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

Reject commands from bots and other users and reject malformed privileged commands.

- [ ] **Step 2: Write repair-state tests**

Cover transitions:

```text
0 failures -> repair attempt 1
repair attempt 1 fails -> repair attempt 2
repair attempt 2 fails -> blocked and owner notification
successful rerun -> clear repair labels
```

- [ ] **Step 3: Implement owner commands**

Commands must mutate labels/Project status idempotently. `/pause` sets `JULES_AUTOMATION_ENABLED=false` through the repository Actions variable API; `/resume` restores true. `/approve` records an owner approval marker comment and label consumed by the PR controller.

- [ ] **Step 4: Implement repair requests**

On failed required checks, comment on the Jules PR with:

```markdown
@jules Repair the failing required checks for this pull request.

Do not change the Issue scope. Diagnose the root cause, add or update regression coverage, run the complete validation commands from AGENTS.md, and push the repair to this branch.

Failing checks:
<check names and concise failure summaries>

Repair attempt: <1 or 2> of 2
```

The workflow must not start a third attempt. If Jules does not react to PR feedback in the connected mode, the same comment remains the actionable owner notification and the workflow blocks after the configured attempt limit rather than pretending a repair occurred.

- [ ] **Step 5: Create command and repair workflows**

Use `issue_comment` only after verifying the repository, item type, author, and command. Never check out or execute untrusted PR code in an `issue_comment` or `pull_request_target` context.

- [ ] **Step 6: Run tests**

```powershell
python -m pytest tests/automation/test_owner_commands.py tests/automation/test_repair_controller.py -q
```

Expected: all trust-boundary and attempt-limit tests pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/automation/owner_commands.py scripts/automation/repair_controller.py tests/automation/test_owner_commands.py tests/automation/test_repair_controller.py .github/workflows/owner-command.yml .github/workflows/jules-repair.yml docs/JULES_AUTOMATION.md
git commit -m "feat: add Jules repair and owner command workflows"
```

---

### Task 9: Add post-merge progression and operational reconciliation

**Files:**
- Create: `scripts/automation/post_merge.py`
- Create: `tests/automation/test_post_merge.py`
- Create: `.github/workflows/jules-post-merge.yml`
- Modify: `.github/workflows/jules-dispatch.yml`
- Modify: `docs/JULES_AUTOMATION.md`

**Interfaces:**
- Consumes: merged PR, linked Issue, source branch, Project item, and queue state.
- Produces: closed Issue, Done Project status, deleted branch, cleared merge lock, and next dispatch invocation.

- [ ] **Step 1: Write post-merge tests**

Cover:

- Exactly one linked Issue closes as completed.
- Project item moves to Done.
- Feature branch deletion excludes protected/default branches.
- Merge lock clears.
- Dispatcher is invoked once after cleanup.
- Duplicate merge events remain idempotent.

- [ ] **Step 2: Implement post-merge plan generation**

Keep decision generation pure:

```python
def build_post_merge_actions(event: dict, policy: dict) -> tuple[Action, ...]:
    ...
```

- [ ] **Step 3: Create `jules-post-merge.yml`**

On merged PR:

1. Verify Jules origin.
2. Close the primary Issue.
3. Move it to Done.
4. Delete the source branch when safe.
5. Clear merge and repair labels.
6. Dispatch the next eligible Issue through a reusable workflow or repository dispatch event.

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/automation/test_post_merge.py -q
python scripts/validate.py --mode full
```

Expected: all automation and application validations pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/automation/post_merge.py tests/automation/test_post_merge.py .github/workflows/jules-post-merge.yml .github/workflows/jules-dispatch.yml docs/JULES_AUTOMATION.md
git commit -m "feat: progress Jules queue after merge"
```

---

### Task 10: Configure GitHub settings, migrate the backlog, and perform a controlled pilot

**Files:**
- Modify: `docs/JULES_AUTOMATION.md`
- Modify: Existing open Issues and Project configuration through GitHub APIs/UI
- No application-code changes

**Interfaces:**
- Consumes: All workflows and contracts from Tasks 1–9.
- Produces: Enabled repository controls, an ordered Project queue, normalized Issues, and one completed pilot Issue.

- [ ] **Step 1: Create the GitHub Project and statuses**

Create statuses exactly as specified:

```text
Idea
Needs Details
Ready for Jules
Jules Working
PR Validation
Waiting for Aaron
Blocked
Ready to Merge
Done
```

Enable built-in workflows to add repository Issues and move closed items to Done.

- [ ] **Step 2: Create repository labels**

Create state, risk, type, area, `agent:jules`, native `jules`, pause, and repair labels from the approved design.

- [ ] **Step 3: Configure repository variables and secret**

Set:

```text
JULES_AUTOMATION_ENABLED=false
JULES_PROJECT_OWNER=aaronwesthoff84
JULES_PROJECT_NUMBER=<actual project number>
JULES_RECONCILE_MINUTES=15
```

Add `JULES_PROJECT_TOKEN` as a fine-grained token limited to the Project and this repository. Leave automation disabled until the pilot checks are complete.

- [ ] **Step 4: Configure merge and branch protections**

- Enable squash merge.
- Enable auto-merge.
- Enable automatic branch deletion after merge.
- Require pull requests for `master`.
- Require branches to be current before merge.
- Require `validation`, `e2e`, `codeql`, `dependency-review`, and `automation-policy-review`.
- Block force pushes and branch deletion.
- Require unresolved conversations to be resolved.

- [ ] **Step 5: Normalize existing open Issues**

For each Issue:

- Add missing contract sections without changing intended scope.
- Apply exactly one risk label.
- Apply at least one area label.
- Record dependencies explicitly.
- Move incomplete Issues to Needs Details.
- Move complete Issues into ordered Ready for Jules positions.
- Do not apply native `jules` manually during migration.

- [ ] **Step 6: Run a dry-run queue audit**

Execute dispatcher selection without writes and verify:

- Exactly the expected top two Issues are candidates.
- They do not share a conflicting primary area.
- High-risk status is visible.
- No incomplete Issue is selected.

- [ ] **Step 7: Run one controlled pilot**

Choose a low-risk, small Issue with clear automated-test coverage. Enable automation, allow one Jules slot for the pilot, and verify:

1. Project status changes to Jules Working.
2. Jules comments on the Issue.
3. Jules opens a linked PR.
4. All required checks run independently.
5. Policy review classifies the PR correctly.
6. The PR merges only after required gates pass.
7. The Issue closes and moves to Done.
8. The next Issue is not dispatched until the pilot is reviewed.

- [ ] **Step 8: Enable normal two-slot operation**

After the pilot passes, restore maximum concurrency `2`, set `JULES_AUTOMATION_ENABLED=true`, and confirm the dispatcher selects the first two non-conflicting Ready for Jules Issues.

- [ ] **Step 9: Record the operational baseline**

Document the Project URL/number, required check names, repository variables, current queue order, pilot Issue/PR, and pause/recovery procedure in `docs/JULES_AUTOMATION.md`.

- [ ] **Step 10: Commit documentation updates**

```bash
git add docs/JULES_AUTOMATION.md
git commit -m "docs: record Jules automation operational baseline"
```

---

## Final Verification

Run locally:

```powershell
python scripts/validate.py --mode full
```

Verify in GitHub:

- Every required check is visible and enforceable.
- A direct push to `master` is blocked.
- An incomplete Issue cannot receive the native `jules` label from the dispatcher.
- Two same-area Issues do not run concurrently.
- A high-risk PR cannot auto-merge without Aaron approval.
- A low-risk pilot PR can auto-merge after all gates pass.
- A third repair attempt cannot be created.
- Pause prevents new dispatches.
- Post-merge cleanup dispatches the next eligible Issue.

## Plan Self-Review Results

- **Spec coverage:** All approved design requirements map to Tasks 1–10.
- **Scope:** The plan is staged so Stage 1 provides a usable, safe Jules foundation before queue and merge orchestration are enabled.
- **Trust boundaries:** Workflows avoid executing untrusted code under `pull_request_target` or privileged `issue_comment` contexts.
- **Provider uncertainty:** Repair comments explicitly block rather than falsely advancing if the connected Jules mode does not respond to PR feedback.
- **Owner-only actions:** Privileged commands are accepted only from `aaronwesthoff84`.
- **No unresolved placeholders:** Runtime-discovered Project IDs are intentionally discovered by name; only actual owner setup values are entered during Task 10.