# Jules Automation

This repository uses GitHub Issues as work contracts and Google Jules as the implementation agent. The native `jules` label is the dispatch trigger.

## Safe foundation

Until automated queue dispatch is enabled, the owner starts Jules by applying `jules` only to an implementation-ready Issue. Jules must create a pull request; it must never write directly to `master`.

## Issue readiness

A ready Issue includes the problem, goal, user-visible behavior, scope, non-goals, acceptance criteria, required tests, dependencies, security/privacy considerations, examples when applicable, and definition of done.

Default new-Issue state is `state:needs-details`. A reviewed Issue may be changed to `state:ready`, assigned `agent:jules`, classified with exactly one `risk:*` label and at least one `area:*` label, and then dispatched.

## Risk policy

Low- and medium-risk changes may eventually auto-merge after every required check passes. High-risk changes always require approval from `@aaronwesthoff84`.

High risk includes external XML/configuration transmission, authentication or credentials, persisted file-format or graph-schema changes, destructive behavior, major architecture changes, and changes to privacy or local-first guarantees.

## Required checks

- Python tests and XML-to-HTML acceptance validation
- JavaScript syntax validation
- Playwright Chromium smoke tests
- CodeQL
- Dependency review

## Initial manual workflow

1. Refine an Issue until it is complete.
2. Add appropriate `risk:*` and `area:*` labels.
3. Apply `jules` to start work.
4. Review the linked pull request and GitHub Actions checks.
5. Merge only after all required checks pass.

## Planned queue states

Idea, Needs Details, Ready for Jules, Jules Working, PR Validation, Waiting for Aaron, Blocked, Ready to Merge, and Done.

## Planned owner commands

`/approve`, `/request-changes`, `/retry`, `/block`, `/cancel`, `/needs-details`, `/ready`, `/pause`, and `/resume` will be implemented in the later orchestration stage. Until then, use labels and normal PR review controls.

## One-time owner settings

After this foundation PR merges:

1. Enable GitHub Actions for the repository.
2. Configure a branch ruleset for `master` requiring pull requests and the checks created by this repository.
3. Enable squash merge and automatic branch deletion.
4. Keep Jules authorized for this repository.
5. Do not enable auto-merge until the merge-controller stage is installed.

The repository workflows document any Project token or permission needed by the later queue-dispatch stage.
