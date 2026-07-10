# SAP Incentive Management Config Graph Explorer

SAP Incentive Management Config Graph Explorer is a local-first tool for reviewing XML configuration exports. It preserves the existing XML-to-HTML conversion workflow and adds a browser-based dependency graph.

The application runs entirely on the workstation. It does not require cloud services or runtime CDN assets.

## Install

Use PowerShell from this project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

## Run The Local App

```powershell
.\.venv\Scripts\python -m uvicorn sap_im_config_graph_explorer.app:app --reload
```

Open `http://127.0.0.1:8000`.

To choose another port:

```powershell
.\.venv\Scripts\python -m uvicorn sap_im_config_graph_explorer.app:app --reload --port 8080
```

## Use The XML-To-HTML Converter

The legacy command remains supported:

```powershell
.\.venv\Scripts\python sap_im_transformer.py input.xml output.html --variant=A
```

If `output.html` is omitted, the converter writes beside the XML input using the same base name.

The local app also has a `Generate HTML` action. Select an XML file, choose `Auto`, `A`, or `B`, then generate and preview the HTML output in the browser. The generated HTML can be downloaded from the HTML tab.

## Use The Graph Explorer

1. Select one or more `.xml` export files.
2. Click `Generate Graph`.
3. Pan and zoom the graph area.
4. Search by object name or filter by object type.
5. Click a node to view its source file, XML path, metadata, and bounded raw XML.
6. Hover or click an edge to inspect its relationship.
7. Click `Export JSON` to download the current graph data.

## Strict Graph Node Allowlist

Only these object categories can become graph nodes:

- Fixed Value
- Formula
- Lookup Table
- Quota
- Rate Table
- Territory
- Variable
- Rule
- Plan
- Plan Component
- Event Type
- Credit Type
- Earning Code
- Earning Group
- Business Unit
- Processing Unit
- Calendar

The default graph builder uses ordered, object-specific extractors. Formula and Rule internals such as `FUNCTION`, `PARAMETER_LIST`, conditions, actions, and literals remain metadata or reference evidence and never become graph nodes. A caller can provide a custom `ExtractorRegistry`, but `NodeFactory` still rejects node types outside the allowlist.

## Dependency And Containment Direction

Dependency links point from the dependent object to the object it uses. For example, a Rule that uses a Formula produces `Rule -> Formula` with `uses_formula`.

Containment links point from the child to its owner:

- Plan Component to Plan: `belongs_to_plan`
- Rule to Plan Component: `belongs_to_plan_component`

Reference resolution is scoped to a snapshot. A name in a production snapshot cannot satisfy a reference in a non-production snapshot.

## Graph JSON Contract

The current schema version is `1.0`:

```json
{
  "schemaVersion": "1.0",
  "snapshots": [
    {
      "id": "configuration",
      "role": "configuration | non_production | production",
      "sourceFiles": ["export.xml"]
    }
  ],
  "nodes": [
    {
      "id": "node-instance-id",
      "canonicalKey": "formula:eligibility",
      "snapshotId": "configuration",
      "label": "Eligibility",
      "type": "Formula",
      "sourceFile": "export.xml",
      "xmlPath": "/DATA_IMPORT[1]/FORMULA_SET[1]/FORMULA[1]",
      "rawXml": "<FORMULA ... />",
      "metadata": {}
    }
  ],
  "links": [
    {
      "id": "link-stable-id",
      "source": "dependent-node-id",
      "target": "dependency-node-id",
      "relationship": "uses_formula",
      "confidence": "high | medium | low",
      "metadata": {}
    }
  ],
  "findings": [
    {
      "id": "finding-stable-id",
      "code": "missing_reference | ambiguous_reference",
      "severity": "error | warning | info",
      "snapshotId": "configuration",
      "nodeIds": ["source-node-id"],
      "message": "Missing Variable reference: Gate",
      "details": {}
    }
  ]
}
```

Allowed node type values are:

```text
FixedValue, Formula, LookupTable, Quota, RateTable, Territory, Variable,
Rule, Plan, PlanComponent, EventType, CreditType, EarningCode, EarningGroup,
BusinessUnit, ProcessingUnit, Calendar
```

Allowed relationship values are:

```text
uses_fixed_value, uses_formula, uses_lookup, uses_quota, uses_rate_table,
uses_classifier, uses_territory, uses_variable, uses_rule, belongs_to_plan,
belongs_to_plan_component, runs_in_pipeline, uses_event_type,
outputs_credit_type, uses_earning_code, uses_earning_group,
uses_business_unit, uses_processing_unit, uses_calendar, feeds_deposit,
depends_on_period, references_custom_object, references_report,
references_integration, parent_child, unknown_reference
```

Missing and ambiguous references are emitted as structured findings. They do not create placeholder graph nodes or links with non-node endpoints.

## Error Handling

The app reports useful local errors for:

- malformed XML
- empty XML files
- unsupported file types
- graph generation failures
- duplicate snapshot IDs
- unsupported graph node or relationship types

Duplicate source IDs remain separate node instances with stable generated IDs. Duplicate details are recorded in node metadata, and references to non-unique targets become ambiguity findings.

## Known Limitations

- Real SAP Incentive Management export shapes vary, so additional exact aliases may be added as representative exports are collected.
- The first graph renderer is a local Cytoscape-compatible 2D renderer focused on core interaction rather than advanced layout quality.
- Large-file performance has not yet been optimized.
- Validation beyond missing and ambiguous reference resolution remains future work.

## Future Roadmap

1. Locally vendored 3D graph mode.
2. Non-production vs production XML comparison.
3. Oracle vs HANA XML export comparison.
4. Impact analysis for upstream and downstream dependencies.
5. Orphaned object detection.
6. Unused rule, formula, and territory detection.
7. Duplicate object detection.
8. Broken reference detection.
9. Migration risk scoring.
10. Local-first AI-generated summaries of selected configuration objects, with optional online providers later.
11. AI-generated documentation from XML exports.
12. HTML documentation generator with graph screenshots.
13. Export to CSV, Markdown, and GraphML.
14. Offline Neo4j CSV/Cypher export bundle.
15. Pipeline execution flow view.
16. Rule lineage view.
17. Search by object type, file, relationship, and confidence.
18. Saved graph session ZIP containing `session.json` and `graph.png`.
19. Large-file performance improvements.

## Development Checks

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python sap_im_transformer.py tests\fixtures\minimal_plan.xml "$env:TEMP\minimal-plan-acceptance.html" --variant=A
.\.venv\Scripts\python -m uvicorn sap_im_config_graph_explorer.app:app --reload
```
