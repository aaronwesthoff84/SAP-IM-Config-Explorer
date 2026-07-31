# Domain Docs

This repository uses a single-context domain-documentation layout.

## Before exploring the codebase

Read these documents when they exist and are relevant:

- `CONTEXT.md` at the repository root
- Architecture decision records under `docs/adr/`

If either location does not exist, proceed silently. Do not treat its absence as a defect or create placeholder documentation.

The `/domain-modeling` workflow creates or expands these documents when terminology, boundaries, or architectural decisions are actually resolved.

## Layout

```text
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       ├── 0001-example-decision.md
│       └── 0002-example-decision.md
└── sap_im_config_graph_explorer/
```

## Domain vocabulary

Use the repository's established SAP Incentive Management terminology consistently.

Important current concepts include:

- XML configuration export
- Snapshot
- Graph node
- Graph relationship
- Canonical object identity
- Reference resolution
- Validation finding
- Plan
- Plan Component
- Rule
- Strict graph node allowlist
- Local-first processing

Do not abbreviate SAP Incentive Management as `SIM`.

When `CONTEXT.md` defines a preferred term, use that term in issue titles, Agent Briefs, tests, refactoring proposals, and documentation. Avoid introducing competing synonyms.

If a required concept is missing from the glossary, determine whether the proposed language is unnecessary or whether the domain model has a genuine documentation gap.

## Architectural decisions

Read relevant records under `docs/adr/` before proposing or implementing an architectural change.

If proposed work contradicts an existing decision, surface the conflict explicitly rather than silently overriding the decision:

> Contradicts ADR-0007 — reconsider this decision because…

Current repository invariants in `AGENTS.md` and `README.md` remain authoritative even when no corresponding ADR exists.
