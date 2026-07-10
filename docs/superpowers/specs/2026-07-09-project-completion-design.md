# SAP Incentive Management XML-to-Graph Project Completion Design

**Date:** 2026-07-09
**Status:** Approved in conversation; awaiting written-spec review
**Baseline:** Commit `25def49d98c3ddafc7d3b45aaf3d362af9971600`

## Purpose

Complete the open GitHub backlog for the SAP Incentive Management XML-to-Graph project without replacing the working XML-to-HTML converter or weakening the strict graph-node allowlist. The result remains a local-first FastAPI application with locally vendored browser assets, deterministic graph/validation/analysis logic, portable exports, and optional AI features that use a local model endpoint by default.

The 27 open GitHub issues are implemented as dependency-ordered work groups. Issues #5, #10, #15, #20, #23, and #26 are phase trackers and close only after their child issues are verified.

## Fixed Product Constraints

- Preserve `python sap_im_transformer.py input.xml [output.html] [--variant=A|B]` and the browser HTML-generation workflow.
- Do not require cloud services, runtime CDN assets, React, or a Node build system.
- Use plain JavaScript for the browser application and vendor third-party runtime assets locally.
- Only these categories may become graph nodes:
  - Fixed values
  - Formulas
  - Lookup tables
  - Quotas
  - Rate tables
  - Territories
  - Variables
  - Rules
  - Plans
  - Plan components
  - Event types
  - Credit types
  - Earning codes
  - Earning groups
  - Business units
  - Processing units
  - Calendars
- Formula functions, parameters, conditions, actions, and other object internals remain metadata or reference evidence and never become graph nodes.
- Custom extractors may emit only the established allowlisted types. Adding a new node type requires an intentional application/schema/UI/test update.
- Migration analysis covers promotion from non-production to production only.
- Neo4j support produces an offline import bundle and does not connect to a database.
- A saved session is one ZIP containing separate `session.json` and `graph.png` files.
- The performance target is 100 MB of combined XML, 25,000 nodes, 75,000 links, graph generation within 30 seconds, and search/filter response within one second on a typical modern workstation.
- AI uses a loopback/local provider by default. The provider abstraction permits explicitly configured online models later without coupling graph correctness to AI output.

## Non-Goals

- Rewriting the legacy XML-to-HTML converter.
- Automatically treating unknown XML elements as nodes.
- Allowing AI to determine extraction, relationship resolution, validation findings, comparison results, or migration-risk scores.
- Shipping or installing a local language model runtime as part of the application.
- Connecting directly to Neo4j in the initial implementation.
- Inventing pipeline order when the source XML contains no authoritative ordering evidence.

## Architecture

### 1. Snapshot-Aware XML Loading

Every graph input belongs to a snapshot with a stable identifier and role:

- `configuration` for ordinary graph exploration
- `non_production` for the source side of promotion analysis
- `production` for the target side of promotion analysis

The graph loader gains a streaming path based on iterative XML parsing. It retains only the state needed for allowlisted objects, source provenance, bounded raw XML, and references. The HTML converter continues using its existing parser and rendering code.

Upload bytes are processed through temporary local files when streaming is required. Temporary files are removed in `finally` blocks. Filenames are treated as display/provenance values, never as trusted filesystem paths.

### 2. Extractor Protocol, Registry, and Shared Node Factory

The generic extractor is replaced as the graph-building engine by small domain extractors registered through an internal extractor registry. The registry provides a future extension point but is not a user-supplied code loader.

Extractor families are:

- Plan and Plan Component
- Credit, Measurement, Incentive, and Deposit Rule
- Fixed Value, Lookup Table, Quota, Rate Table, Territory, and Variable
- Formula
- Event Type, Credit Type, Earning Code, Earning Group, Business Unit, Processing Unit, and Calendar

All four rule extractors emit `type="Rule"` and place their normalized family/subtype in metadata. Deposit includes the supported deposit XML aliases encountered in fixtures, including `DETAIL_DEPOSIT` when represented as a rule type.

Each extractor returns object candidates and reference candidates. A shared node factory alone creates `GraphNode` instances. It enforces the allowlist, normalizes metadata, allocates IDs, records duplicate grouping, and rejects attempts to emit unsupported types.

Formula extractors parse expression structure only to identify inputs and produce readable expression metadata. Nested `FUNCTION`, `PARAMETER_LIST`, literal, condition, and action elements never become nodes.

### 3. Stable Identity and Duplicate Scope

Each node has two identities:

- `id`: unique object-instance identity within the graph document
- `canonicalKey`: normalized identity used to match the same logical object across snapshots

The canonical key is built from normalized node type plus a trusted source ID when present; otherwise it uses normalized name and the minimum hierarchy required to disambiguate legitimate same-name objects. It never includes the upload filename.

The instance ID includes snapshot, source provenance, canonical key, and deterministic occurrence information. Duplicate detection is scoped within one snapshot. The same canonical object in non-production and production is a comparison match, not a duplicate.

Every member of a duplicate group receives the same `duplicateKey`; no group member is silently preferred for authoritative resolution.

### 4. Reference Resolution and Link Direction

References are collected once with XML-path origin evidence. A reference has a normalized target hint, expected target type, raw value, source node, and source location.

Resolution status is explicit:

- `resolved`: exactly one valid target
- `missing`: no valid target
- `ambiguous`: multiple valid targets with no authoritative discriminator

Only resolved references create graph links. Missing and ambiguous references create validation findings. This keeps GraphML and Neo4j exports closed over real nodes.

Dependency links point from the dependent object to the object it consumes. Therefore:

- Upstream means dependencies reachable by following outgoing dependency links.
- Downstream means dependents reachable by following incoming dependency links.

Containment links point from child to owner:

- Plan Component to Plan via `belongs_to_plan`
- Rule to Plan Component via `belongs_to_plan_component`

Pipeline links point from the earlier executable object to the later executable object and are marked with a pipeline-direction metadata category so they are not confused with dependency traversal.

One XML reference produces at most one semantic link. Link metadata retains origin path, raw reference, resolution evidence, snapshot, and confidence.

### 5. Versioned Data Contract

The graph document becomes a versioned contract with:

- `schemaVersion`
- `snapshots`
- `nodes`
- `links`
- `findings`

Nodes retain the existing display and provenance fields and add `snapshotId` and `canonicalKey`. Links receive stable IDs and always reference existing nodes. Findings use a common schema:

- stable finding ID
- code
- severity (`error`, `warning`, or `info`)
- snapshot ID
- affected node IDs
- message
- structured evidence/details

The README, API tests, browser code, export formats, and saved-session schema use the same documented vocabulary. Relationship constants that cannot connect allowlisted nodes are removed unless they represent a verified relationship between allowed types.

### 6. Shared Validation Engine

One deterministic validation engine builds indexes once and runs these detectors:

- Duplicate objects: repeated canonical identities within a snapshot.
- Broken references: missing targets.
- Ambiguous references: multiple possible targets.
- Unused objects: allowlisted objects with no inbound semantic dependency, subject to explicit root/leaf exemptions by type.
- Orphaned objects: no inbound or outbound semantic or containment relationship.

Unused and orphaned detectors share adjacency indexes but emit distinct findings. Containment alone prevents an object from being orphaned but does not automatically prove that it is semantically used. Finding evidence identifies the rule and indexes that produced the result.

### 7. Non-Production-to-Production Comparison and Risk

Comparison requires exactly one non-production snapshot and one production snapshot. It matches objects by canonical key and reports:

- added objects
- removed objects
- modified normalized metadata
- modified effective dates
- added and removed relationships
- changed validation findings

Raw XML formatting, attribute order, upload filename, and positional XML-path noise do not produce a modification by themselves.

Migration risk is deterministic and specific to non-production-to-production promotion. A local JSON profile defines weights and thresholds for factors such as:

- broken or ambiguous references
- production-only removals
- changed high-impact dependencies
- duplicate identities
- effective-date gaps or overlaps
- rule/formula changes with broad downstream impact
- new or worsened validation findings

The result includes a bounded score, rating, every contributing factor, its evidence, and recommended review actions. Editing the profile changes policy without changing comparison code.

### 8. Analysis Views

Impact analysis uses cycle-safe traversal and the defined link direction. Selecting a node highlights upstream dependencies and downstream dependents while dimming unrelated nodes.

Rule lineage is a focused traversal beginning with a Rule and includes related rules plus the allowlisted objects that provide material inputs or outputs. Relationship and confidence filters apply consistently.

Pipeline flow uses authoritative sequence/order fields from XML when available. It labels inferred partial ordering separately and displays unknown order rather than fabricating a sequence.

Advanced filters cover label, object type, source file, snapshot, relationship, confidence, effective date, and finding severity. Effective-date filtering supports an "active on date" mode and an interval-overlap mode.

### 9. Performance Strategy

Backend performance work includes:

- streaming graph parsing
- document-aware source lookup
- constant-time element-to-owner/reference indexes
- canonical-key and adjacency indexes
- bounded raw XML capture
- avoiding repeated full-document and full-node scans
- one-pass normalization where possible

Browser performance work includes:

- building reusable node/link indexes after load
- debounced search
- hiding/showing elements without destroying and recreating the graph
- avoiding a complete layout run for every filter change
- batching style and element updates
- lazy initialization of 3D mode
- clear progress and large-graph warnings

A deterministic synthetic benchmark fixture validates the agreed capacity and timing targets without committing a 100 MB fixture.

### 10. Browser Application

The existing plain-JavaScript/FastAPI structure remains. The application adds workspaces for:

- Graph, with 2D and 3D modes
- Validation findings
- Non-production/production comparison
- Promotion risk
- Rule lineage
- Pipeline flow

`3d-force-graph` and its required browser assets are vendored locally. The 2D view remains the default and fallback. Both views share selection, filter, details, impact, and color semantics.

The UI clearly distinguishes complete-graph scope from active-filter scope for exports. Unresolved references appear in findings rather than as invisible edges to nonexistent nodes.

### 11. Saved Sessions

Session export creates a ZIP with:

- `session.json`: schema version, graph snapshot, findings, filters, layout positions, active view, comparison/risk state, and selected item
- `graph.png`: an image of the active graph view at export time

The ZIP does not include the complete original XML uploads. The graph snapshot already contains bounded per-node raw XML evidence. Session import validates ZIP members, schema version, sizes, and JSON structure before restoring state. It rejects path traversal, unexpected executable content, and unsupported future schemas with a clear message.

### 12. Export and Integration

The user chooses complete-graph or active-filter scope.

- CSV produces separate node, link, and finding tables with spreadsheet-formula injection protection.
- Markdown produces a readable configuration, validation, and optional comparison/risk report.
- GraphML emits typed keys, real-node endpoints only, and escaped metadata.
- Neo4j export creates a ZIP containing nodes CSV, relationships CSV, constraints/indexes Cypher, and an import README. It performs no network or database operation.

### 13. AI Features

AI documentation and selected-object summaries share one provider interface, prompt builder, provenance model, and error path.

The initial provider targets an OpenAI-compatible endpoint on loopback. Model name and endpoint are local configuration. If no local endpoint/model is configured, deterministic graph, validation, comparison, and export features continue to work and the AI UI explains what local configuration is missing.

Remote endpoints are rejected by default. A later application update can add an explicitly enabled online provider and consent/data-boundary UI without modifying extractor or analysis code. API credentials are never written to session files or exports.

AI output includes the model/provider identity, generation timestamp, source node/finding identifiers, and a statement that the text requires human review. Prompts prefer normalized structured data and bounded evidence. AI output cannot mutate the graph or findings.

## API Shape

The existing health, HTML conversion, graph, and JSON-export routes remain available. The graph response advances to the versioned contract. New endpoint families cover:

- validation-ready graph creation
- non-production/production comparison
- risk scoring with a local profile
- scoped CSV, Markdown, GraphML, and Neo4j export
- session ZIP export/import
- AI summary/document generation through the configured local provider

Business logic lives in service modules rather than FastAPI route functions so it is independently testable. Export endpoints validate the versioned graph document instead of accepting arbitrary unvalidated dictionaries.

## Error Handling and Security

- Malformed, empty, unsupported, and oversized inputs report the affected filename and safe reason.
- Validation findings are returned as data rather than converting analyzable configuration problems into HTTP failures.
- Temporary files are removed even after failures.
- XML parsing does not resolve external entities or retrieve network resources.
- ZIP import/export applies safe member names, member-count limits, decompressed-size limits, and schema validation.
- CSV, Markdown, XML, HTML, and Cypher output use format-specific escaping.
- Browser details use text-safe rendering for XML and metadata.
- Local AI connection errors are isolated to AI actions.
- No source XML or normalized graph data is sent to a non-loopback endpoint by default.

## Testing and Verification

Implementation follows red-green-refactor for every feature or defect.

Required automated coverage includes:

- dedicated fixtures for all extractor families and Rule subtypes
- regression coverage proving formula internals are never nodes
- runtime enforcement of the exact node allowlist
- stable identity, duplicate grouping, and cross-snapshot matching
- missing, ambiguous, duplicate, unused, and orphan findings
- reference de-duplication and direction semantics
- non-production/production comparison and explainable risk factors
- active-date and interval-overlap filtering
- impact, lineage, and pipeline traversal including cycles
- session ZIP contents, PNG presence, restore behavior, and malicious ZIP rejection
- CSV, Markdown, GraphML, and Neo4j output validity/escaping
- local-provider AI request/response behavior using a fake loopback service
- remote-provider rejection by default
- legacy CLI and HTML-output regression tests
- FastAPI endpoint contracts and error responses
- synthetic performance benchmarks for the agreed envelope

Browser verification covers graph generation, 2D/3D switching, filters, selection/details, impact highlighting, validation navigation, comparison/risk display, scoped exports, session restore, and graph-image creation.

Dependency versions are constrained to compatible ranges or exact lock inputs so a fresh environment cannot reproduce the current `pydantic`/`pydantic-core` mismatch. Python bytecode/cache files are removed from version control and excluded through `.gitignore`.

## Work Groups and Issue Mapping

### Work Group 1: Foundation and Extractors

- Repository hygiene and reproducible dependencies
- Extractor protocol, registry, node factory, identity, reference contract
- #3 primary objects and restricted custom mechanism
- #4 Formula
- #2 Rule families
- #1 Plan and Plan Component
- #5 Phase 1 tracker

After the shared foundation lands, non-overlapping extractor modules may be developed by separate agents, but integration occurs through reviewed sequential commits.

### Work Group 2: Performance Foundation

- #19 large-file performance

Performance changes land before higher-level features multiply data processing and UI state.

### Work Group 3: Validation

- #8 broken references
- #6 duplicates
- #7 unused objects
- #9 orphaned objects
- #10 Phase 2 tracker

### Work Group 4: Comparison and Analysis

- #12 non-production/production comparison
- #14 advanced search and filters
- #11 impact analysis
- #17 rule lineage
- #13 non-production-to-production promotion risk
- #27 pipeline execution flow
- #15 Phase 3 tracker

### Work Group 5: Export, Sessions, and Visualization

- #21 CSV, Markdown, and GraphML
- #22 offline Neo4j bundle
- #18 saved session ZIP with graph PNG
- #16 locally vendored 3D graph
- #20 Phase 4 tracker
- #23 Phase 5 tracker

### Work Group 6: Local AI

- shared local provider/provenance layer
- #25 selected-object summaries
- #24 generated documentation
- #26 Phase 6 tracker

## Delivery and GitHub Closure

Each independently testable task receives:

1. A failing regression or feature test.
2. The minimum implementation to pass it.
3. Focused verification.
4. A subagent specification/compliance and code-quality review.
5. A reviewed commit with the relevant issue reference.

Critical and important review findings are fixed before the next dependent task. Full automated and browser verification runs before the branch is presented for integration. Leaf issues are closed only after their implementation is integrated and verified; phase trackers close after all children meet the same standard. Work is not merged into the primary branch without explicit user approval.

## Approved Decisions Summary

- Local AI by default, with a provider extension seam for future online models.
- Custom extractors cannot create node types outside the fixed allowlist.
- Migration risk covers non-production-to-production promotion only.
- Neo4j output is an offline bundle.
- Sessions are ZIP files with separate JSON and PNG members.
- 3D uses locally vendored plain JavaScript without React or a Node build system.
- The performance envelope is 100 MB, 25,000 nodes, 75,000 links, 30-second generation, and one-second search/filter response.
