# Jules Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded GitHub delivery loop that dispatches ready SAP IM Config Explorer Issues to Google Jules, independently validates the resulting pull requests, auto-merges eligible low- and medium-risk work sequentially, and notifies Aaron only when a decision is required.

**Architecture:** GitHub Issues are the work contracts, a user-owned GitHub Project is the ordered queue, repository labels are the machine-readable state, and GitHub Actions coordinate dispatch, validation, policy review, repair, merge control, notifications, and post-merge progression. The native `jules` label is applied only after repository-owned readiness checks pass.

**Tech Stack:** GitHub Actions, GitHub REST and GraphQL APIs, Python 3.12, pytest, FastAPI/Uvicorn, Node.js 20, Playwright, GitHub CodeQL, GitHub Dependency Review, Google Jules.

## Global Constraints

- The default branch is `master`.
- At most two Issues may be active with Jules.
- Only one Jules pull request may merge at a time.
- Issues without complete acceptance criteria are moved to Needs Details.
- Low- and medium-risk changes may auto-merge only after every required check passes.
- High-risk changes require approval from `aaronwesthoff84`.
- High risk includes external XML/configuration transmission, authentication or credentials, persisted file-format or graph-schema changes, destructive behavior, major architecture changes, and changes to privacy or local-first guarantees.
- Jules receives at most two repair requests after failed required checks.
- Every behavior change requires targeted regression coverage.
- Browser-visible behavior requires Playwright coverage when it can be exercised deterministically.
- Preserve the strict graph allowlist, snapshot-scoped resolution, and prohibition on inferred graph nodes.
- Dependency additions and upgrades must be justified in the pull-request body.
- Workflows may not hide failures, warnings, browser errors, or validation findings.
- Privileged Issue/PR commands are accepted only from `aaronwesthoff84`.

---

## Stage 1: Safe Jules Foundation

After Tasks 1-4, Aaron may safely add the native `jules` label manually. Jules pull requests will have repository instructions, independent CI, browser validation, and security analysis even before automatic dispatch is enabled.

### Task 1: Add Jules instructions, Issue Forms, and PR contract

**Files:**
- Create: `AGENTS.md`
- Create: `.github/ISSUE_TEMPLATE/feature.yml`
- Create: `.github/ISSUE_TEMPLATE/bug.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`
- Create: `docs/JULES_AUTOMATION.md`
- Modify: `README.md`
- Modify: `tests/test_project_hygiene.py`

**Interfaces:**
- Consumes: Existing commands and graph invariants documented in `README.md`.
- Produces: Stable instructions and work contracts used by Jules and later workflows.

- [ ] **Step 1: Write the failing hygiene test**

Add:

```python
def test_jules_contract_files_exist_and_define_invariants():
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
    required_text = {
        "local-first",
        "strict graph node allowlist",
        "snapshot-scoped",
        "one primary GitHub Issue per pull request",
        "Do not hide or suppress failures",
    }
    assert required_text <= set(agents.splitlines()) or all(
        text in agents for text in required_text
    )
```

- [ ] **Step 2: Confirm the test fails**

```powershell
python -m pytest tests/test_project_hygiene.py::test_jules_contract_files_exist_and_define_invariants -q
```

Expected: failure because the required files are absent.

- [ ] **Step 3: Create `AGENTS.md`**

Include exact setup and validation commands, the local-first guarantee, strict graph allowlist, snapshot-scoped resolution, no inferred graph nodes, one primary Issue per PR, targeted tests, browser tests for UI work, dependency justification, and mandatory clarification for unresolved privacy/schema/architecture decisions.

- [ ] **Step 4: Create required Issue Forms**

Both forms must require these sections:

```text
Problem or goal
User-visible behavior
Scope
Non-goals
Acceptance criteria
Required tests
Dependencies
Security and privacy considerations
Definition of done
```

Apply `state:needs-details` by default. Do not apply `jules` automatically from the form.

- [ ] **Step 5: Create the PR template**

Use these headings exactly:

```markdown
## Primary Issue
## Summary
## Acceptance-criteria coverage
## Validation performed
## Browser validation
## Dependency changes
## Risk and privacy review
## Documentation changes
```

- [ ] **Step 6: Create the owner guide and README link**

Document queue statuses, labels, risk policy, commands, pause/resume, manual fallback, required GitHub settings, and the pilot procedure.

- [ ] **Step 7: Run the hygiene tests**

```powershell
python -m pytest tests/test_project_hygiene.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add AGENTS.md .github README.md docs/JULES_AUTOMATION.md tests/test_project_hygiene.py
git commit -m "docs: define Jules automation contracts"
```

### Task 2: Add a canonical validation command

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/validate.py`
- Create: `tests/test_validation_script.py`
- Modify: `README.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Produces: `build_commands(mode: str) -> list[list[str]]`, `run_commands(commands: list[list[str]]) -> int`, and CLI command `python scripts/validate.py --mode ci`.

- [ ] **Step 1: Write failing tests**

```python
from scripts.validate import build_commands, run_commands


def test_ci_mode_contains_required_checks():
    rendered = [" ".join(command) for command in build_commands("ci")]
    assert any("pytest" in command for command in rendered)
    assert any("node --check sap_im_config_graph_explorer/static/app.js" in command for command in rendered)
    assert any("sap_im_transformer.py" in command for command in rendered)


def test_run_commands_returns_first_failure(monkeypatch):
    results = iter([0, 7])
    monkeypatch.setattr("scripts.validate.subprocess.call", lambda command: next(results))
    assert run_commands([["first"], ["second"]]) == 7
```

- [ ] **Step 2: Confirm failure**

```powershell
python -m pytest tests/test_validation_script.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement `scripts/validate.py`**

Use this command construction:

```python
def build_commands(mode: str) -> list[list[str]]:
    python = sys.executable
    commands = [
        [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        ["node", "--check", "sap_im_config_graph_explorer/static/app.js"],
        [
            python,
            "sap_im_transformer.py",
            "tests/fixtures/minimal_plan.xml",
            str(Path(tempfile.gettempdir()) / "minimal-plan-acceptance.html"),
            "--variant=A",
        ],
    ]
    if mode == "full":
        commands.extend([["npm", "ci"], ["npm", "run", "test:e2e"]])
    if mode not in {"ci", "full"}:
        raise ValueError(f"Unsupported validation mode: {mode}")
    return commands
```

`run_commands` must print every command and stop on the first non-zero exit code. `main` must parse `--mode` with choices `ci` and `full`.

- [ ] **Step 4: Run tests and validation**

```powershell
python -m pytest tests/test_validation_script.py -q
python scripts/validate.py --mode ci
```

Expected: both commands pass.

- [ ] **Step 5: Update docs and commit**

```bash
git add scripts tests/test_validation_script.py README.md AGENTS.md
git commit -m "test: add canonical validation command"
```

### Task 3: Add GitHub Actions CI and security checks

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/codeql.yml`
- Create: `.github/workflows/dependency-review.yml`
- Modify: `tests/test_project_hygiene.py`

**Interfaces:**
- Produces required check names `validation`, `codeql`, and `dependency-review`.

- [ ] **Step 1: Add failing workflow hygiene tests**

Assert that workflows target pull requests to `master`, set read-only default permissions, do not use `pull_request_target`, and run `python scripts/validate.py --mode ci`.

- [ ] **Step 2: Create `ci.yml`**

Use Ubuntu, Python 3.12, pip caching, `pip install -r requirements-dev.txt`, and the canonical validation command. Upload logs and the generated HTML artifact when validation fails.

- [ ] **Step 3: Create CodeQL and dependency review**

Analyze Python and JavaScript on PRs and weekly. Fail dependency review for newly introduced high-severity vulnerabilities.

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/test_project_hygiene.py -q
```

Expected: pass with YAML parsed by the test suite.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows tests/test_project_hygiene.py
git commit -m "ci: add validation and security gates"
```

### Task 4: Add Playwright browser validation

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
- Produces required check `e2e` and local command `npm run test:e2e`.

- [ ] **Step 1: Add failing `full` mode tests**

Assert that `build_commands("full")` appends `npm ci` and `npm run test:e2e`.

- [ ] **Step 2: Create Playwright configuration**

Use Chromium, one CI worker, one retry in CI, trace on first retry, screenshot on failure, and this web server command:

```text
python -m uvicorn sap_im_config_graph_explorer.app:app --host 127.0.0.1 --port 8000
```

- [ ] **Step 3: Implement the critical-path test**

The test must open the app, verify the title, upload the fixture, generate a graph, confirm Plans/Plan Components/Rules, select a node, verify details, generate HTML, verify preview content, switch theme, reload, confirm persistence, and fail on uncaught page errors or unexpected console errors.

- [ ] **Step 4: Run locally**

```powershell
npm ci
npx playwright install chromium
npm run test:e2e
python scripts/validate.py --mode full
```

Expected: all commands pass.

- [ ] **Step 5: Add the `e2e` CI job and commit**

```bash
git add package.json package-lock.json playwright.config.ts tests/e2e .gitignore .github/workflows/ci.yml scripts/validate.py tests/test_validation_script.py
git commit -m "test: add Playwright critical-path validation"
```

---

## Stage 2: Automated Queue Dispatch

### Task 5: Implement deterministic Issue and PR policy

**Files:**
- Create: `scripts/automation/__init__.py`
- Create: `scripts/automation/issue_policy.py`
- Create: `scripts/automation/pr_policy.py`
- Create: `.github/automation-policy.json`
- Create: `tests/automation/test_issue_policy.py`
- Create: `tests/automation/test_pr_policy.py`

**Interfaces:**

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

- [ ] **Step 1: Write Issue-policy tests**

Cover complete Issue, missing sections, missing/duplicate risk labels, missing area label, blocked/paused Issue, open dependencies, and high-risk dispatch eligibility without merge eligibility.

- [ ] **Step 2: Write PR-policy tests**

Classify documentation/test-only work as low by default; ordinary application changes as medium; and external network calls, credentials, destructive operations, runtime dependency changes with architectural impact, graph schema changes, persisted format changes, or local-first changes as high.

- [ ] **Step 3: Implement policy modules and JSON**

The JSON must contain owner `aaronwesthoff84`, default branch `master`, concurrency `2`, repair limit `2`, required Issue headings, state/risk/type/area labels, high-risk path patterns, and conflicting area groups.

- [ ] **Step 4: Run tests and commit**

```powershell
python -m pytest tests/automation -q
python scripts/validate.py --mode ci
git add scripts/automation tests/automation .github/automation-policy.json
git commit -m "feat: add deterministic Jules policy"
```

### Task 6: Implement Project queue and Jules dispatcher

**Files:**
- Create: `scripts/automation/github_graphql.py`
- Create: `scripts/automation/project_queue.py`
- Create: `tests/automation/test_project_queue.py`
- Create: `.github/workflows/jules-dispatch.yml`
- Modify: `docs/JULES_AUTOMATION.md`

**Interfaces:**

```python
def select_dispatch_candidates(
    ordered_items: list[dict],
    active_items: list[dict],
    maximum_active: int,
) -> list[dict]:
    available = max(0, maximum_active - len(active_items))
    selected: list[dict] = []
    active_areas = {item["primary_area"] for item in active_items}
    for item in ordered_items:
        if len(selected) >= available:
            break
        if not item["eligible"] or item["primary_area"] in active_areas:
            continue
        selected.append(item)
        active_areas.add(item["primary_area"])
    return selected
```

- [ ] **Step 1: Write queue tests**

Cover Project order, two-slot maximum, pause state, area conflicts, unknown area serialization, open dependencies, and duplicate-dispatch prevention.

- [ ] **Step 2: Implement GraphQL transport**

Read Project items in board order, resolve the Status field and options by name at runtime, and update Project status. Keep API calls outside the pure queue-selection function.

- [ ] **Step 3: Create dispatcher workflow**

Trigger on Issue label/state changes, PR close/merge, manual dispatch, and a 15-minute schedule. Use repository variables:

```text
JULES_AUTOMATION_ENABLED
JULES_PROJECT_OWNER
JULES_PROJECT_NUMBER
JULES_RECONCILE_MINUTES
```

Use `JULES_PROJECT_TOKEN` for the user-owned Project. Apply `state:in-progress`, update status to Jules Working, then add native `jules` last.

- [ ] **Step 4: Implement incomplete-Issue handling**

Remove native `jules`, add `state:needs-details`, move to Needs Details, and add one idempotent comment listing exact missing headings and mentioning `@aaronwesthoff84`.

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest tests/automation/test_project_queue.py -q
git add scripts/automation/github_graphql.py scripts/automation/project_queue.py tests/automation/test_project_queue.py .github/workflows/jules-dispatch.yml docs/JULES_AUTOMATION.md
git commit -m "feat: dispatch Project queue Issues to Jules"
```

---

## Stage 3: Validation, Repair, Merge, and Notifications

### Task 7: Implement PR control and sequential auto-merge

**Files:**
- Create: `scripts/automation/pr_controller.py`
- Create: `tests/automation/test_pr_controller.py`
- Create: `.github/workflows/jules-pr-control.yml`
- Modify: `.github/automation-policy.json`
- Modify: `docs/JULES_AUTOMATION.md`

**Interfaces:**

```python
@dataclass(frozen=True)
class MergeDecision:
    eligible: bool
    waiting_for_owner: bool
    reasons: tuple[str, ...]


def decide_merge(
    risk: str,
    owner_approved: bool,
    required_checks: dict[str, str],
    linked_issue_count: int,
    branch_current: bool,
    merge_lock_available: bool,
    blocking_findings: tuple[str, ...],
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
```

- [ ] **Step 1: Write controller tests**

Cover green low/medium PR, high-risk owner gate, missing/multiple Issues, pending/failed checks, merge lock, stale branch, and policy findings.

- [ ] **Step 2: Create PR-control workflow**

Confirm Jules origin from the linked Issue marker, run deterministic policy review, set Project status, apply labels idempotently, and enable auto-merge only when `MergeDecision.eligible` is true.

- [ ] **Step 3: Require independent checks**

Require `validation`, `e2e`, `codeql`, `dependency-review`, and `automation-policy-review`. The policy review must verify Issue mapping, changed-path risk, test changes, dependency justification, local-first constraints, and graph-contract-sensitive changes.

- [ ] **Step 4: Implement high-risk notification**

Construct the comment in code:

```python
comment = (
    "## Action required from @aaronwesthoff84\n\n"
    "**Reason:** High-risk change detected\n"
    f"**Approval required because:** {'; '.join(decision.blocking_reasons)}\n\n"
    "Commands:\n- `/approve`\n- `/request-changes <instructions>`\n"
    "- `/block <reason>`\n- `/cancel`\n"
)
```

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest tests/automation/test_pr_controller.py tests/automation/test_pr_policy.py -q
git add scripts/automation/pr_controller.py tests/automation/test_pr_controller.py .github/workflows/jules-pr-control.yml .github/automation-policy.json docs/JULES_AUTOMATION.md
git commit -m "feat: control Jules pull request merging"
```

### Task 8: Implement owner commands and two-attempt repair

**Files:**
- Create: `scripts/automation/owner_commands.py`
- Create: `scripts/automation/repair_controller.py`
- Create: `tests/automation/test_owner_commands.py`
- Create: `tests/automation/test_repair_controller.py`
- Create: `.github/workflows/owner-command.yml`
- Create: `.github/workflows/jules-repair.yml`
- Modify: `docs/JULES_AUTOMATION.md`

**Interfaces:**
- Recognized commands: `/approve`, `/request-changes`, `/retry`, `/block`, `/cancel`, `/needs-details`, `/ready`, `/pause`, `/resume`.
- Repair states: zero failures to attempt 1; attempt 1 failure to attempt 2; attempt 2 failure to Blocked.

- [ ] **Step 1: Write trust-boundary and repair-state tests**

Reject commands from bots or non-owner users. Reject malformed commands. Confirm no third repair attempt can be generated.

- [ ] **Step 2: Implement command parser and actions**

`/pause` sets `JULES_AUTOMATION_ENABLED=false`; `/resume` sets true; `/approve` records an owner-approval label and marker comment; state commands update labels and Project status idempotently.

- [ ] **Step 3: Implement repair comment generation**

```python
def build_repair_comment(checks: list[str], attempt: int) -> str:
    return (
        "@jules Repair the failing required checks for this pull request.\n\n"
        "Do not change the Issue scope. Diagnose the root cause, add or update "
        "regression coverage, run the complete validation commands from AGENTS.md, "
        "and push the repair to this branch.\n\n"
        "Failing checks:\n- "
        + "\n- ".join(checks)
        + f"\n\nRepair attempt: {attempt} of 2"
    )
```

If connected Jules mode does not respond to PR feedback, the workflow must move the PR to Blocked after the configured attempt state rather than claiming a repair occurred.

- [ ] **Step 4: Create safe workflows**

Never check out or execute untrusted PR code from `issue_comment` or `pull_request_target`. Validate repository, author, item type, and command before any write.

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest tests/automation/test_owner_commands.py tests/automation/test_repair_controller.py -q
git add scripts/automation/owner_commands.py scripts/automation/repair_controller.py tests/automation/test_owner_commands.py tests/automation/test_repair_controller.py .github/workflows/owner-command.yml .github/workflows/jules-repair.yml docs/JULES_AUTOMATION.md
git commit -m "feat: add Jules repair and owner commands"
```

### Task 9: Implement post-merge progression

**Files:**
- Create: `scripts/automation/post_merge.py`
- Create: `tests/automation/test_post_merge.py`
- Create: `.github/workflows/jules-post-merge.yml`
- Modify: `.github/workflows/jules-dispatch.yml`
- Modify: `docs/JULES_AUTOMATION.md`

**Interfaces:**

```python
def build_post_merge_actions(event: dict, default_branch: str) -> tuple[str, ...]:
    actions = ["close-primary-issue", "move-project-item-to-done", "clear-merge-lock"]
    head_ref = event["pull_request"]["head"]["ref"]
    if head_ref != default_branch:
        actions.append("delete-source-branch")
    actions.append("dispatch-next-issue")
    return tuple(actions)
```

- [ ] **Step 1: Write idempotency and safety tests**

Cover linked Issue closure, Done status, protected branch exclusion, lock clearing, single next-dispatch event, and duplicate merge event handling.

- [ ] **Step 2: Create post-merge workflow**

Verify Jules origin, close the primary Issue, update Project status, delete the safe source branch, clear merge/repair labels, and invoke the dispatcher once.

- [ ] **Step 3: Run full validation and commit**

```powershell
python -m pytest tests/automation/test_post_merge.py -q
python scripts/validate.py --mode full
git add scripts/automation/post_merge.py tests/automation/test_post_merge.py .github/workflows/jules-post-merge.yml .github/workflows/jules-dispatch.yml docs/JULES_AUTOMATION.md
git commit -m "feat: progress Jules queue after merge"
```

---

## Stage 4: GitHub Configuration and Pilot

### Task 10: Configure GitHub and run one controlled pilot

**Files and settings:**
- Update: `docs/JULES_AUTOMATION.md`
- Configure: GitHub Project, labels, repository variables, secret, branch rules, merge settings, and current Issues.

- [ ] **Step 1: Create Project statuses**

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

- [ ] **Step 2: Create all labels from the approved design**

Create state, risk, type, area, `agent:jules`, native `jules`, pause, repair, and owner-approval labels.

- [ ] **Step 3: Configure variables and secret**

Set `JULES_AUTOMATION_ENABLED=false`, `JULES_PROJECT_OWNER=aaronwesthoff84`, `JULES_PROJECT_NUMBER` to the numeric Project number returned by GitHub, and `JULES_RECONCILE_MINUTES=15`. Store a fine-grained Project token as `JULES_PROJECT_TOKEN`.

- [ ] **Step 4: Configure repository protections**

Enable squash merge, auto-merge, automatic branch deletion, PR-only changes to `master`, current-branch requirement, required conversations resolved, force-push/deletion protection, and required checks `validation`, `e2e`, `codeql`, `dependency-review`, and `automation-policy-review`.

- [ ] **Step 5: Normalize current open Issues**

Add missing headings without changing intended scope, apply exactly one risk label and at least one area label, record dependencies, move incomplete work to Needs Details, and order complete work in Ready for Jules. Do not apply native `jules` during migration.

- [ ] **Step 6: Dry-run the dispatcher**

Confirm it selects the expected first two non-conflicting Issues and no incomplete Issue.

- [ ] **Step 7: Run a one-Issue low-risk pilot**

Temporarily limit active work to one, enable automation, and verify Issue dispatch, Jules comment, linked PR, all checks, policy classification, sequential merge, Issue closure, Done status, and branch deletion.

- [ ] **Step 8: Enable normal operation**

Restore concurrency to two and set `JULES_AUTOMATION_ENABLED=true` after the pilot passes.

- [ ] **Step 9: Record the operational baseline**

Document the Project number, required checks, repository variables, pilot Issue/PR, current queue order, pause/recovery procedure, and owner notification behavior.

- [ ] **Step 10: Commit documentation**

```bash
git add docs/JULES_AUTOMATION.md
git commit -m "docs: record Jules automation baseline"
```

---

## Final Verification

Run:

```powershell
python scripts/validate.py --mode full
```

Verify in GitHub:

- Direct changes to `master` are blocked.
- Incomplete Issues cannot be dispatched.
- Two same-area Issues are serialized.
- High-risk PRs cannot auto-merge without Aaron approval.
- Low/medium pilot work can auto-merge after all required gates pass.
- A third repair attempt cannot be generated.
- Pause prevents new dispatches.
- A merge cleans up the branch and dispatches the next eligible Issue.

## Self-Review

- Every approved design requirement maps to a task.
- Stage 1 provides a safe manual Jules workflow before autonomous dispatch is enabled.
- Privileged workflows do not execute untrusted PR code.
- Project field option identifiers are discovered by name at runtime rather than hard-coded.
- The only values entered during owner setup are values returned by GitHub itself.
- Repair automation blocks safely when Jules PR-feedback behavior is unavailable.
- The plan contains no unresolved implementation placeholders.