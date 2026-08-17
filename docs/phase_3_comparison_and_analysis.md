# SAP IM Config Explorer: Phase 3 Comparison & Analysis Features

This document explains the capabilities, usage instructions, and test validation for Phase 3 of the SAP IM Config Explorer: **Comparison and Analysis**.

All capabilities described here run **entirely locally** on your workstation and maintain the local-first security and privacy contract of the application. No XML files, graph objects, comparison metrics, or scoring details leave your system.

---

## Capabilities Overview

### 1. Dependency Impact Highlighting (#11)
When reviewing highly interconnected configuration graphs, understanding the upstream and downstream impact of any given node is essential.
- **Upstream Dependencies:** The nodes that a selected node directly or indirectly uses or requires.
- **Downstream Dependents:** The nodes that directly or indirectly use or depend on the selected node.
- **Visual Dimming:** Unrelated nodes and edges are visually dimmed to an opacity of `0.1` so that the complete high-contrast path remains clear.

### 2. Compare Two XML Exports (#12)
Comparing snapshots is critical when analyzing differences between non-production (e.g., development or testing environment configuration) and production systems.
- **Canonical Object Identity:** Nodes are matched deterministically across snapshots using a `canonicalKey` built from normalized type and ID/name properties (independent of the upload filenames).
- **Structural Differences analyzed:**
  - Added objects
  - Removed objects
  - Modified metadata (such as description and custom properties)
  - Effective date changes (gaps and overlaps)
  - Added and removed relationships (such as uses, feeds, or pipeline links)
  - Changes in containment ownership

### 3. Migration Risk Scoring (#13)
The migration risk engine evaluates structural differences and validation findings between the non-production and production snapshots to calculate an overall risk score (bounded from `0` to `100`).
- **Score Severity Levels:**
  - **LOW RISK (0–29):** Minor changes (e.g., newly added isolated objects, minor dates modifications).
  - **MEDIUM RISK (30–69):** Structural updates (e.g., changed containment, missing non-critical relationships).
  - **HIGH RISK (70–100):** Serious or blocking issues (e.g., newly introduced duplicate objects, broken references, or ambiguous references in non-production).
- **Explanation and Transparency:** Every contributing risk factor is listed with its description, weight, level of severity, and the specific affected node IDs for review.

### 4. Advanced Search & Filters (#14)
Finding the needle in the haystack in a configuration containing thousands of objects is handled by advanced frontend filtering.
- **Search by Name:** Instant search/filter by object label (case-insensitive, debounced).
- **Filter by Object Type:** Narrow the active view to specific allowlisted types (e.g., `Rule`, `PlanComponent`, `Formula`).
- **Filter by Source File:** Isolate nodes originating from a specific file in multi-file snapshots.
- **Filter by Relationship & Confidence:** Filter elements based on semantic relationships and their mapping confidence.
- **Filter by Effective Date:** Input an effective date to inspect the graph configuration active on that specific date.
- **Active Filter Summary:** The UI displays a live summary of filtered elements (e.g., "Showing X of Y nodes") and list active filters with a one-click "Clear all filters" button.

---

## How to Run & Use the Capabilities

### Step-by-Step Instructions

1. **Start the Local Application Server:**
   ```powershell
   .\.venv\Scripts\python -m uvicorn sap_im_config_graph_explorer.app:app --reload
   ```
   Open `http://127.0.0.1:8000` in your web browser.

2. **Select Non-Production and Production Exports:**
   - In the **Files** panel, click the file picker under **Non-Production XML** and choose your development/staging XML export (e.g., `tests/fixtures/risk_high.xml`).
   - Click the file picker under **Production XML (optional)** and choose your production XML export (e.g., `tests/fixtures/risk_low.xml`).

3. **Choose Topology and Generate Graph:**
   - Choose either `Core` (Plan, Plan Component, Rule hierarchy only) or `Full` (all 17 allowlisted definition types).
   - Click **Generate Graph**.

4. **Explore Advanced Filters:**
   - Type an object name in the **Search** box to filter nodes in real-time.
   - Choose a type from **Object type** or use other filters such as **Source file**, **Relationship**, **Confidence**, or **Effective on** date.
   - The status bar and filter summary update instantly.

5. **Interact with the Graph and Highlighting:**
   - Click any node (e.g., a Formula or Rule) in the main viewport.
   - Unrelated elements instantly dim to `0.1` opacity, highlighting the active upstream/downstream dependency sub-graph.
   - Click the empty background to clear highlighting.

6. **Inspect Comparison & Risk Scoring:**
   - The **Migration Risk** widget in the details panel is displayed when both snapshots are loaded.
   - It shows the computed risk score (e.g., `52` - MEDIUM RISK) and lists all risk factors (e.g., `changed_containment` or `orphaned_object`).
   - Select any node to view its specific details, source file, XML path, bounded XML source, and associated plans/rules.

---

## How to Test and Verify

A comprehensive test suite verifies both the backend analysis algorithms and frontend user interactions.

### 1. Python Unit & Backend Tests
To run the deterministic validation and migration tests:
```powershell
.\.venv\Scripts\python -m pytest tests/test_migration.py tests/test_validation.py
```
Key tests covered:
- Identical snapshots yield a risk score of `0.0`.
- Missing references and duplicate canonical keys generate `high` severity factors.
- Changed containment hierarchies produce exact, deterministic `changed_containment` factors with stable sorting and identical output across hash seeds.
- Unused/orphaned nodes are detected correctly.

### 2. Playwright End-to-End Tests
To verify browser UI interactions, layout, filtering, and highlighting capabilities:
```powershell
# Set environment and execute all Playwright tests
$env:PATH=".\.venv\Scripts;\" + $env:PATH
npx playwright test
```
Specific test suites:
- `tests/e2e/dependency-highlighting.spec.ts`: Verifies node selection dims unrelated nodes, highlights related ones, and clears correctly when background is clicked.
- `tests/e2e/graph-filters.spec.ts`: Confirms that combining name search, type, source file, date bounds, relationship, and confidence filters works correctly without creating isolated nodes.
- `tests/e2e/migration-risk.spec.ts`: Validates that uploading both snapshots displays the migration risk container, calculated score, and factor details.
- `tests/e2e/graph-layout.spec.ts`: Ensures that cytoscape layout rendering, pan, zoom, and viewport controls are completely preserved without rendering warnings.
