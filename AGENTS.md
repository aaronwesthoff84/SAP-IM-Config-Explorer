# SAP IM Config Explorer Agent Instructions

## Required setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
npm ci
npx playwright install chromium
```

## Required validation

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python scripts\validate.py --mode full
```

## Product invariants

- The application is local-first. XML and configuration content must not leave the workstation unless an approved Issue explicitly requires an external provider and the pull request is marked high risk.
- Preserve the strict graph node allowlist documented in `README.md`.
- Preserve snapshot-scoped reference resolution.
- Never create inferred or placeholder graph nodes for unresolved references.
- Keep Formula and Rule internals as metadata or reference evidence unless a separately approved graph-schema change says otherwise.

## Change contract

- Implement one primary GitHub Issue per pull request.
- Treat the Issue acceptance criteria and non-goals as binding.
- Add targeted regression tests for every behavior change.
- Add or update Playwright coverage for browser-visible behavior where practical.
- Explain every dependency addition or upgrade in the pull-request description.
- Stop and request clarification when product behavior, privacy, schema, destructive behavior, or architecture is unresolved.
- Do not hide or suppress failures, warnings, browser console errors, or validation findings instead of fixing their cause.
- Do not write directly to `master`; use a feature branch and pull request.

## Pull-request requirements

Every pull request must identify one primary Issue, map changes to its acceptance criteria, list validation performed, document dependency changes, classify risk, and state whether local-first or graph-contract behavior changed.
