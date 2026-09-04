# Open Issues Inventory

**Total Open Issues:** 26  
**Generated via:** `scripts/export_open_issues.py`

---

## [#58: [Maintenance] Upgrade Playwright past the affected 1.55.0 dev dependency](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/58)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-30
* **Labels:** `bug`

### Details & Requirements

## Context

Final closeout validation found no production npm vulnerabilities with `npm audit --omit=dev`, but the full npm audit reports two high-severity findings against the pinned `@playwright/test` 1.55.0 development dependency, including GHSA-7mvr-c777-76hp.

## Acceptance criteria

- Upgrade Playwright to a supported version that is not affected by the reported advisory.
- Regenerate the lockfile intentionally.
- `npm audit` reports no high-severity finding for Playwright.
- All browser tests pass with the upgraded version.
- Document any browser-runtime installation change needed for local Windows development or CI.
- Do not add a production runtime dependency.

---

## [#56: [Analysis] Make migration-risk weights configurable and show every object factor](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/56)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-30
* **Labels:** `enhancement`

### Details & Requirements

## Context

Follow-up from merged PR #54 and closed issue #13. The original goal called for a transparent, configurable migration-risk assessment and object-level risk indicators.

## Current gaps

- Risk weights are fixed Python constants.
- Node details use the first matching factor only, so an object associated with multiple factors does not show every reason its risk increased.
- The browser test verifies only that the score is greater than zero and that one factor is visible.

## Acceptance criteria

- Provide a documented local configuration mechanism for risk weights with stable defaults.
- Validate configuration values and fail with a clear local error for invalid values.
- Use the configured weights consistently in score calculation and the displayed explanation.
- Show every migration-risk factor associated with a selected object.
- Add exact unit and browser assertions for configured weights, overall scores, factor ordering, and multiple factors on one object.
- Preserve the local-first design and make no production-system connection.

---

## [#53: [Backlog] Dependency-ordered implementation sequence](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/53)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `backlog`

### Details & Requirements

## Purpose

Provide one dependency-ordered execution list for the SAP IM Config Explorer backlog.

## Project pause status

- Development is paused after master commit `1a5e08e783e5529c5c149a9888e282cab4ee3e59` and merged PR #54.
- No issue is currently in progress and no pull request is open.
- Jules automation workflows are manually disabled. Do not re-enable them until development is intentionally resumed.
- XML Atlas is a separate alternative-view prototype and is not part of this repository's implementation sequence.

## Operating rules

- Work top to bottom unless a dependency or production defect requires an explicit reorder.
- Phase trackers are closed only after all of their leaf issues are complete.
- Preserve the local-first application, strict graph allowlist, snapshot-scoped resolution, legacy converter command, and one-primary-issue-per-PR rule.
- Independent items in the same stage may run concurrently only when they do not share an implementation area.
- When development resumes, explicitly select the next issue and re-enable only the minimum Jules workflow needed for that work.

## Current active work

- None. Issue #13 was completed by PR #54; follow-up review findings are recorded below.

## Stage 1 â€” Safety, correctness, and foundations

- [ ] #55 Make shared-containment migration scoring deterministic
- [ ] #41 Sandbox generated HTML and escape XML-derived content
- [ ] #56 Make migration-risk weights configurable and show every object factor
- [ ] #58 Upgrade Playwright past the affected 1.55.0 dev dependency
- [ ] #31 Resolve the Starlette TestClient/httpx deprecation warning
- [ ] #32 Number generic attributes in rendered action output
- [ ] #51 Preserve duplicate objects in generated reports
- [ ] #48 Support SAP XML namespaces, encodings, and version profiles
- [ ] #42 Add Core and Full allowlisted graph modes
- [ ] #12 Compare two XML exports
- [ ] #19 Large-file performance improvements

## Stage 2 â€” Analysis, filtering, and navigation

- [ ] #14 Advanced search and filters
- [ ] #33 Apply graph filters to the HTML preview and download
- [ ] #43 Interactive findings workbench and local waivers
- [ ] #45 Cross-link Graph, Findings, HTML, and XML evidence
- [ ] #44 Effective-date as-of view and temporal validation
- [ ] #17 Rule lineage view
- [ ] #27 Pipeline execution flow view
- [ ] #15 Phase 3 tracker â€” close after its required leaf issues are complete

## Stage 3 â€” Export, persistence, visualization, and accessibility

- [ ] #57 Prevent graph-label collisions and resolve Cytoscape warnings
- [ ] #21 Export graph to CSV, Markdown, and GraphML
- [ ] #22 Optional Neo4j export
- [ ] #47 Validate and restore versioned Graph JSON
- [ ] #18 Saved graph sessions
- [ ] #50 Keyboard, screen-reader, and non-color interaction baseline
- [ ] #46 Graph layout controls and PNG/SVG export
- [ ] #16 Optional 3D graph mode
- [ ] #20 Phase 4 tracker â€” close after #16, #17, #18, and #19 are complete
- [ ] #23 Phase 5 tracker â€” close after #21 and #22 are complete

## Stage 4 â€” Automation and distribution

- [ ] #49 Batch validation and reporting for folders
- [ ] #52 Reproducible offline Windows package and launcher

## Stage 5 â€” Optional AI features

- [ ] #25 Summaries for selected configuration objects
- [ ] #24 Generate documentation from XML exports
- [ ] #26 Phase 6 tracker â€” close after #24 and #25 are complete

## Already completed prerequisites

- #1â€“#10 extractor and deterministic validation foundation
- #11 dependency impact highlighting
- #13 migration risk scoring baseline (PR #54); follow-up defects and completion gaps are #55 and #56
- #29 dark mode

## Maintenance

Update this tracker when an item is completed, split, superseded, or explicitly reordered. Do not rewrite leaf-issue acceptance criteria from this tracker.

---

## [#52: [Distribution] Reproducible offline Windows package and launcher](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/52)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `enhancement`

### Details & Requirements

## Goal

Provide a predictable Windows-first way to run the local application without manually assembling its development environment.

## Scope

- Produce a versioned offline package or installer containing required runtime application assets.
- Provide start, stop, health-check, upgrade, and uninstall guidance.
- Bind to loopback by default and avoid runtime CDN or cloud dependencies.
- Include license notices and component versions.

## Acceptance criteria

- A clean supported Windows machine can launch the app and reach the health endpoint using documented steps.
- The package includes real locally vendored browser assets and does not download dependencies at runtime.
- User data and saved sessions have a documented location and upgrade policy.
- Removal does not delete user-created exports or sessions without explicit confirmation.
- Build steps are reproducible and tested in CI or a documented release workflow.

## Dependencies

- Package after the primary deterministic, export, and session workflows stabilize.

---

## [#51: [HTML] Preserve duplicate objects in generated reports](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/51)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `bug`

### Details & Requirements

## Goal

Prevent same-name Rules or Plan Components from being silently overwritten in generated HTML output.

## Scope

- Preserve every duplicate object instance in source order or another documented deterministic order.
- Display source identity and duplicate evidence so instances can be distinguished.
- Keep graph duplicate findings aligned with the objects shown in HTML.
- Generate collision-safe internal anchors and links.

## Acceptance criteria

- Two same-name objects from one or multiple selected exports both appear in the report.
- Each instance identifies its source file and available source ID or XML path.
- Internal links resolve to the intended instance.
- Duplicate findings link to every rendered duplicate.
- Add Rule and Plan Component duplicate regression fixtures.
- Do not weaken duplicate detection.

---

## [#50: [Accessibility] Keyboard, screen-reader, and non-color interaction baseline](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/50)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `enhancement`

### Details & Requirements

## Goal

Make the core local explorer usable without a mouse and without relying only on color.

## Scope

- Provide keyboard access to upload, filters, tabs, findings, graph selection, and details.
- Add visible focus states and semantic labels.
- Provide a list or tree alternative for graph navigation where canvas content is not accessible.
- Distinguish status, severity, selection, and impact with text or shape in addition to color.
- Respect reduced-motion and high-contrast preferences where practical.

## Acceptance criteria

- Core Graph and HTML Output workflows can be completed with a keyboard.
- Screen readers can identify status, active filters, finding counts, selected object, and relationship details.
- Light and dark themes meet documented contrast targets.
- Automated accessibility checks and focused Playwright keyboard tests are included.
- The accessible alternative uses the same graph data and filters.

---

## [#49: [CLI] Batch validation and reporting for folders](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/49)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `enhancement`

### Details & Requirements

## Goal

Provide a reusable command-line workflow for validating multiple XML exports without opening the browser.

## Scope

- Accept explicit files or a directory with a documented recursion policy.
- Produce human-readable and machine-readable finding summaries.
- Support deterministic exit codes for clean, warning, validation-error, and processing-error outcomes.
- Reuse the application graph, validation, comparison, and export services rather than duplicating logic.

## Acceptance criteria

- The CLI processes files in deterministic order and identifies every source file in results.
- Output supports JSON and concise console formats.
- Exit-code behavior is documented and tested.
- Partial failures do not hide results from successfully processed files.
- No XML or results leave the workstation.
- Preserve the existing sap_im_transformer.py command unchanged.

---

## [#47: [Import] Validate and restore versioned Graph JSON](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/47)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Allow a previously exported graph document to be safely reopened without reprocessing its original XML files.

## Scope

- Add local Graph JSON import.
- Validate schema version, node and relationship vocabulary, endpoint closure, sizes, findings, and snapshot metadata.
- Reject unsupported future schemas and malformed or dangerous payloads.
- Define an explicit migration path for supported older schemas.

## Acceptance criteria

- A valid exported graph round-trips without identity or relationship loss.
- Invalid node types, relationships, dangling endpoints, duplicate IDs, and oversized documents are rejected clearly.
- Import never creates inferred nodes or modifies the original JSON file.
- Imported graphs remain visibly distinguishable from graphs generated from selected XML.
- Add schema, round-trip, malformed-input, and version-migration tests.

## Dependencies

- Keep the Graph JSON contract stable before saved-session import is finalized.

### Comments & Discussion

**@aaronwesthoff84** on 2026-08-01:

> ## Agent Brief
> 
> **Category:** enhancement
> 
> **Summary:** Validate and import a local Graph JSON document into the existing workspace without reprocessing XML.
> 
> ### Current behavior
> 
> - The app downloads Graph JSON but has no import control or model deserializer.
> - `/api/export/graph-json` accepts arbitrary JSON without validating the graph contract.
> 
> ### Desired behavior
> 
> - Add a reusable `GraphDocument` deserializer/validator and `/api/import/graph-json` upload route.
> - Accept at most 25 MiB, 50,000 nodes, 100,000 links, and 50,000 findings. Keep limits as named constants and return stable 400 errors naming the violated limit/file.
> - Validate current schema version, snapshots/roles, topology/profile/provenance metadata, enum vocabularies, unique snapshot/node/link/finding IDs, node snapshot membership, link endpoint closure, finding node references, field types, and required properties.
> - Reject unsupported future versions. Add explicit migrations for every older repository schema still supported at implementation time; at minimum, migrate baseline `1.0` by supplying the documented defaults introduced by #48/#42 without changing node or link identity.
> - Add top-level provenance distinguishing XML-generated and imported graphs. Imported provenance records the JSON filename but never modifies the uploaded file.
> - Add an accessible `.json` file control. A successful import replaces the current in-memory graph, populates filters/findings/risk/details normally, and clearly labels the workspace as imported.
> 
> ### Key interfaces
> 
> - `models.py` deserialization/validation and schema migrations (or a focused new module)
> - `app.py`, `templates/index.html`, `static/app.js`
> - Existing Graph JSON export as round-trip source
> 
> ### Testable acceptance criteria
> 
> - [ ] Export â†’ import â†’ export preserves schema/topology, snapshots, node/link/finding identities, metadata, and migration-risk data.
> - [ ] Invalid enums, duplicate IDs, dangling endpoints, invalid snapshot references, malformed JSON, future versions, and every size/count limit fail with exact safe errors.
> - [ ] The `1.0` migration is deterministic and documented; no placeholder/inferred node is created.
> - [ ] Imported workspaces are visibly distinguished and remain fully local.
> - [ ] Add model/API round-trip, malformed-input, boundary-limit, migration, and Playwright import tests.
> 
> ### Out of scope
> 
> - Importing XML through this endpoint, editing imported JSON, remote URLs, arbitrary schema repair, or persisting XML content.
> 
> ### Dependencies
> 
> Blocked by #48 and #42 so the current schema is settled before migrations are implemented.

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/600384270452521434). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/80) has been created.

---

## [#46: [Visualization] Graph layout controls and PNG/SVG export](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/46)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Give users reproducible 2D layout controls and portable graph images for documentation and review.

## Scope

- Add fit, reset, relayout, and supported layout selection controls.
- Preserve user-adjusted positions during ordinary filtering and selection.
- Export the visible graph to PNG and SVG with a legend and basic provenance.
- Clearly state whether an export represents the full or filtered graph.

## Acceptance criteria

- Search and filter changes do not unnecessarily destroy saved positions.
- Exports match the selected topology, filters, theme, and visible labels.
- Image exports include generation time, source-file names, and graph schema version without embedding full XML.
- Empty and oversized graphs fail with useful messages.
- Add deterministic state tests and browser coverage.

## Dependencies

- Large-file performance improvements should establish the supported graph envelope.
- Coordinate the image contract with saved sessions.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/1621681536494186780). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> I apologize, but I encountered an unexpected error and wasn't able to complete the [task](https://jules.google.com/task/1621681536494186780).

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/82) has been created.

---

## [#45: [Navigation] Cross-link Graph, Findings, HTML, and XML evidence](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/45)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Let users move between every representation of the same configuration object without manually searching.

## Scope

- Define stable object identity markers shared by graph nodes, findings, and generated HTML sections.
- Navigate from a graph node or finding to its HTML section and XML evidence.
- Navigate from supported HTML sections back to the corresponding graph object.
- Handle objects that appear in multiple Plans or Plan Components without ambiguous navigation.

## Acceptance criteria

- Cross-view links use canonical identity and snapshot context, not display text alone.
- Missing representations produce a clear unavailable state.
- Navigation preserves active filters, selection, theme, and current workspace.
- Generated downloads remain valid standalone HTML.
- Add duplicate-name, multi-container, and missing-representation regression coverage.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/2386414290899708229). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/79) has been created.

---

## [#44: [Analysis] Effective-date as-of view and temporal validation](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/44)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `enhancement`

### Details & Requirements

## Goal

Review which configuration objects and relationships are effective on a selected date and detect temporal configuration problems.

## Scope

- Add an optional as-of date applied to objects with supported effective-date metadata.
- Distinguish active, future, expired, and undated objects.
- Detect overlapping effective ranges and material coverage gaps where object semantics support it.
- Explain when an object lacks sufficient date metadata.

## Acceptance criteria

- Selecting or clearing an as-of date updates the visible result deterministically.
- Date filtering never changes source XML or the stored graph snapshot.
- Temporal findings include affected objects, date ranges, and source evidence.
- Unsupported or incomplete dates are shown as unknown rather than guessed.
- Comparison and export features can record the selected date context.
- Add boundary, overlap, gap, and missing-date fixtures.

## Dependencies

- Full allowlisted graph mode.
- Advanced filters.

---

## [#43: [Validation] Interactive findings workbench and local waivers](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/43)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `enhancement`

### Details & Requirements

## Goal

Turn validation findings into an actionable local review workflow.

## Scope

- Filter findings by code, severity, snapshot, source file, and affected object.
- Selecting a finding focuses its related graph objects and source evidence.
- Allow users to record a local waiver with reason, reviewer, and optional expiry.
- Keep original findings immutable; waivers are separate review metadata.
- Include waiver state in supported reports and session exports.

## Acceptance criteria

- Users can navigate from a finding to every affected node and its XML evidence.
- Active filters and result counts are visible and clearable.
- Waived findings remain visible and are never deleted or silently suppressed.
- Waiver data stays local and does not modify XML or graph correctness.
- Invalid or outdated waiver data fails safely.
- Add deterministic model, serialization, and browser coverage.

---

## [#41: [Security] Sandbox generated HTML and escape XML-derived content](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/41)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-15
* **Labels:** `bug`

### Details & Requirements

## Goal

Prevent uploaded XML content from executing markup or script in the application while preserving readable local HTML reports.

## Scope

- Escape every XML-derived text and attribute value before inserting it into generated HTML.
- Replace raw object-name anchors with safely encoded stable identifiers.
- Sandbox the HTML preview iframe with the minimum capabilities required for internal report navigation.
- Add a restrictive generated-report content security policy where compatible with offline downloads.
- Ensure previewed content cannot access the parent application, browser storage, or in-memory graph state.

## Non-goals

- Do not remove the local HTML preview or downloadable report.
- Do not send XML or reports to an external service.

## Acceptance criteria

- Hostile XML values containing HTML, script, event-handler, URL, and quote-breaking payloads render only as text.
- Generated internal links continue to navigate within the preview.
- Downloaded reports remain readable offline.
- The preview cannot read or modify the parent application or local storage.
- Add converter, API, and Playwright regression tests for malicious fixtures.
- Preserve the strict graph allowlist and local-first behavior.

## Risk

High. This closes a same-origin generated-content execution path.

---

## [#31: Resolve the Starlette TestClient/httpx deprecation warning](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/31)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-13
* **Labels:** _None_

### Details & Requirements

## Problem

The full test suite passes, but emits this warning:

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.
```

## Goal

Remove the warning using a supported, maintainable approach without reducing API test coverage or changing application behavior.

## Scope

- Determine whether the correct fix is a compatible FastAPI/Starlette/httpx dependency upgrade, a supported test-client replacement, or another documented migration.
- Update dependency pins and development documentation as needed.
- Preserve the local-first application workflow and the existing test suite behavior.

## Acceptance criteria

- The full test suite passes.
- API tests continue to exercise the FastAPI application.
- The Starlette TestClient/httpx deprecation warning is gone.
- Dependency changes are documented and compatible with supported local setup.

---

## [#27: [Backlog] Pipeline execution flow view](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/27)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `backlog`

### Details & Requirements

## Goal

Visualize documented processing flow through SAP Incentive Management configuration without inventing runtime behavior.

## Scope

- Derive the view only from XML relationships and supported metadata that establish ordering or containment.
- Clearly mark relationships whose execution ordering cannot be determined from the export.
- Keep the current Plan, Plan Component, and Rule graph as the default view.

## Acceptance criteria

- The view explains the source evidence for each displayed sequence or dependency.
- Unknown execution order is shown as unknown rather than inferred.
- Formula internals and other non-allowlisted logic elements do not become graph nodes.
- The feature is local-first and can be disabled without affecting the default graph.
- Add fixtures covering known order and unknown-order cases.

---

## [#26: [Phase 6] Optional AI-powered features](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/26)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Provide optional AI enhancements without making AI or cloud access a requirement for the local explorer.

## Included work

- #24 Generate documentation from XML exports
- #25 Summaries for selected configuration objects

## Completion criteria

- Each included issue is implemented, tested, documented, and closed.
- The application remains fully usable without an AI provider.
- Any online-provider use requires explicit configuration and invocation.
- Source grounding, privacy behavior, and failure handling are documented.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/13295958280629036564). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/84) has been created.

**@google-labs-jules** on 2026-08-12:

> I apologize, but I encountered an unexpected error and wasn't able to complete the [task](https://jules.google.com/task/13295958280629036564).

---

## [#25: [AI] Summaries for selected configuration objects](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/25)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Optionally generate concise, source-grounded summaries for selected SAP Incentive Management configuration objects.

## Scope

- Work from the selected objectâ€™s existing XML, metadata, and resolved relationships.
- Keep the details panel useful when no AI provider is configured.
- Require explicit user action before sending content to an online provider.

## Acceptance criteria

- A selected object can receive a clearly labelled generated summary.
- The summary identifies the source object and avoids unsupported claims.
- No XML leaves the workstation unless the user explicitly configures and invokes an online provider.
- The feature handles unavailable providers and oversized input gracefully.
- Add tests with a deterministic local stub provider.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/14820240794425544253). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/76) has been created.

**@google-labs-jules** on 2026-08-12:

> Jules successfully generated the code for this issue, but was unable to push the branch feature/ai-summaries-14820240794425544253 to GitHub. You can review the changes and push the branch manually [here](https://jules.google.com/task/14820240794425544253).

---

## [#24: [AI] Generate documentation from XML exports](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/24)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Optionally generate a readable documentation draft from a selected SAP Incentive Management XML export.

## Scope

- Keep the existing deterministic HTML report available without an AI provider.
- Define a provider-neutral interface so an online model can be added later.
- Require explicit user action before any XML content is sent to an online model.
- Clearly label generated text as a draft and preserve source references.

## Acceptance criteria

- The feature is disabled by default until a provider is configured.
- Users can generate a structured documentation draft from a selected export.
- The output identifies the relevant source objects and does not invent graph nodes.
- Provider configuration, privacy behavior, and data flow are documented.
- Add fixture-based tests using a local stub provider.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/12731007256444917737). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> I apologize, but I encountered an unexpected error and wasn't able to complete the [task](https://jules.google.com/task/12731007256444917737).

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/85) has been created.

---

## [#23: [Phase 5] Export and integration options](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/23)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Deliver portable outputs and optional integrations for the established local graph model.

## Included work

- #21 CSV, Markdown, and GraphML export
- #22 Optional Neo4j export

## Completion criteria

- Each included issue is implemented, tested, documented, and closed.
- Exports preserve the strict graph schema and do not alter loaded XML.
- Remote integrations remain optional and require an explicit user action; local file exports remain the default.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/8050088755712484557). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/75) has been created.

---

## [#22: [Export] Optional Neo4j export](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/22)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Provide an optional, explicitly invoked export path for loading the current graph into Neo4j.

## Scope

- Generate a Cypher script or Neo4j-compatible import package from the current allowlisted graph.
- Do not connect to a Neo4j server by default or store connection credentials in the app.
- Map node labels, stable IDs, relationship types, and findings consistently with the JSON export.

## Acceptance criteria

- Users can download a documented Neo4j import artifact without providing a server connection.
- The artifact imports Plans, Plan Components, Rules, and supported relationships with stable IDs.
- The export does not create nodes for formula internals or any non-allowlisted object.
- Documentation includes local import instructions and limitations.
- Add regression tests for the generated artifact.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/3824745439979908839). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/73) has been created.

---

## [#20: [Phase 4] Visualization and UI improvements](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/20)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Deliver independently testable user-interface improvements on top of the current local graph explorer.

## Included work

- #16 Optional 3D graph mode
- #17 Rule lineage view
- #18 Saved graph sessions
- #19 Large-file performance improvements

## Status and completion criteria

- Dark mode is already complete in merged PR #36 and is not a remaining prerequisite.
- This phase remains open until each included issue is implemented, tested, and closed.
- New UI work must preserve the simple Graph and HTML Output workflow, local-first behavior, and strict graph allowlist.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/16880105265776301546). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/78) has been created.

---

## [#19: [Visualization] Large-file performance improvements](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/19)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Keep SAP Incentive Management XML loading, validation, and graph interaction responsive for large exports.

## Scope

- Establish representative file-size and object-count benchmarks before optimization.
- Measure upload parsing, validation, initial render, filtering, and memory use.
- Apply targeted improvements without changing graph results or the strict node allowlist.

## Acceptance criteria

- Document baseline and target performance thresholds using representative fixtures.
- The app remains responsive during supported large-file operations or provides visible progress feedback.
- Graph content and findings match the unoptimized behavior for the same input.
- Add performance-focused regression coverage or a reproducible benchmark command.
- Document known practical limits.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/3937694408738469294). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/83) has been created.

---

## [#18: [Visualization] Saved graph sessions](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/18)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Allow users to save and restore local graph exploration sessions.

## Scope

- Save selected XML file metadata, active filters, graph layout, selected item, and theme preference locally.
- Clearly distinguish a saved session from the XML files it references.
- Do not upload session data or XML content to a cloud service.

## Acceptance criteria

- A user can save a named session and restore it after reloading the app.
- Restoring a session explains when its original XML files must be reselected.
- Sessions can be renamed and deleted.
- Invalid or outdated session data fails safely with a useful message.
- Add tests for serialize, restore, and invalid-session handling.

### Comments & Discussion

**@aaronwesthoff84** on 2026-08-01:

> ## Agent Brief
> 
> **Category:** enhancement
> 
> **Summary:** Persist named local exploration-session metadata and restore it safely without storing XML content.
> 
> ### Current behavior
> 
> - Only the theme is persisted, under `sap-im-config-explorer-theme` in `localStorage`.
> - Graph data, filters, positions, selection, topology, and source-file descriptors are lost on reload.
> 
> ### Desired behavior
> 
> - Use browser IndexedDB with session schema version `1`; add no storage dependency.
> - A saved session contains: name, created/updated timestamps, Graph schema version, topology mode, source descriptors (`snapshotRole`, `name`, `size`, `lastModified`), active filters, Cytoscape node positions keyed by node ID, selected node identity, active workspace tab, and theme.
> - Store no XML bytes, `rawXml`, complete GraphDocument, provider credentials, or server-side state.
> - If the matching graph is still in memory, restore filters/layout/selection immediately. After reload, restore UI preferences and request reselection of the exact source descriptors; regenerate only after the user supplies matching files, then apply positions/selection for identities that still exist.
> - Provide named save, restore, rename, and delete actions with confirmation for delete. Duplicate names are rejected case-insensitively.
> - Reject malformed/unknown future session versions without deleting the saved record. Document/update the README roadmap so it no longer implies that this issue creates a ZIP containing graph data.
> 
> ### Key interfaces
> 
> - A focused browser session-store module or clearly isolated functions in `static/app.js`
> - `templates/index.html`, `static/styles.css`
> - Current filter state from #14, topology from #42, and Graph schema/provenance from #47
> 
> ### Testable acceptance criteria
> 
> - [ ] Serialization contains exactly the allowed fields and no XML/raw graph content.
> - [ ] Save/list/rename/delete and case-insensitive duplicate handling work across reloads.
> - [ ] Restore with matching files reproduces topology, filters, positions, selection, tab, and theme.
> - [ ] Missing/mismatched files produce a clear reselect message and do not corrupt/delete the session.
> - [ ] Malformed and future-version records fail safely and other sessions remain usable.
> - [ ] Add deterministic serialization tests and Playwright coverage across a page reload.
> 
> ### Out of scope
> 
> - Cloud sync, ZIP import/export, storing XML or full Graph JSON, automatic filesystem access after reload, and cross-device sessions.
> 
> ### Dependencies
> 
> Blocked by #14, #42, and #47 so persisted filters, topology, and schema/provenance are stable.

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/2869551196431622789). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/74) has been created.

---

## [#16: [Visualization] Optional 3D graph mode](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/16)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Offer an optional 3D visualization for exploring the existing graph without replacing the accessible 2D view.

## Scope

- Keep the current 2D graph as the default and fully supported mode.
- Load any 3D rendering dependency only when the user activates 3D mode.
- Preserve selection, filters, and details-panel behavior where feasible.

## Acceptance criteria

- Users can switch between 2D and 3D without re-uploading XML.
- The 3D view represents only existing allowlisted nodes and links.
- The 2D view remains available and usable if 3D rendering is unsupported.
- The implementation remains local-first and documents any added dependency.
- Add smoke coverage for mode switching.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/16724474767506742752). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/77) has been created.

---

## [#15: [Phase 3] Comparison and analysis features](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/15)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`, `jules`, `ready-for-agent`

### Details & Requirements

## Goal

Deliver the analysis layer built on the established local graph contract.

## Included work

- #11 Dependency impact highlighting
- #12 Compare two XML exports
- #13 Migration risk scoring
- #14 Advanced search and filters

## Completion criteria

- Each included issue is implemented, tested, and closed.
- Comparison and scoring remain local-first and do not connect to production systems.
- The strict graph node allowlist remains unchanged unless the user explicitly approves a change.
- The phase documentation explains how to run and test each capability.

### Comments & Discussion

**@google-labs-jules** on 2026-08-12:

> Jules is [on it](https://jules.google.com/task/11696532872323689031). When finished, you will see another comment and be able to review a PR.

**@google-labs-jules** on 2026-08-12:

> Ready for a review! A [PR](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/pull/81) has been created.

---

## [#12: [Analysis] Compare two XML exports](https://github.com/aaronwesthoff84/SAP-IM-Config-Explorer/issues/12)
* **Author:** @aaronwesthoff84
* **Created:** 2026-07-10
* **Labels:** `enhancement`

### Details & Requirements

## Goal

Allow a user to select any two SAP Incentive Management XML exports and receive a deterministic comparison of configuration changes.

## Scope

- Provide separate, clearly labelled baseline and candidate file inputs.
- Compare objects using stable type-and-name identity, not upload filenames.
- Report added, removed, and materially changed allowlisted objects and containment relationships.
- Keep the feature local-first; uploads must not leave the workstation.

## Acceptance criteria

- Two selected XML files can be compared regardless of their names.
- The results identify added, removed, and changed Plans, Plan Components, and Rules at minimum.
- A changed result identifies the relevant object and a concise description of the difference.
- Invalid or incomplete XML returns a useful error without replacing prior results.
- Add representative fixtures and regression tests for each change category.

---
