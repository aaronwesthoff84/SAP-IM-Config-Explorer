# SAP IM Config Graph Explorer

SAP IM Config Graph Explorer is a local-first tool for reviewing SAP Incentive Management XML configuration exports. It keeps the existing XML-to-HTML conversion workflow and adds a browser-based dependency graph for exploring fixed values, formulas, lookup tables, quotas, rate tables, territories, variables, rules, plans, plan components, event types, credit types, earning codes, earning groups, business units, processing units, and calendars.

The application runs on your machine. It does not require cloud services or runtime CDN assets.

## Install

Use PowerShell from this project directory:

```powershell
python -m pip install -r requirements.txt
```

For tests:

```powershell
python -m pip install -r requirements-dev.txt
```

## Run The Local App

```powershell
python -m uvicorn sap_im_config_graph_explorer.app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Use The XML-To-HTML Converter

The legacy command still works:

```powershell
python sap_im_transformer.py input.xml output.html --variant=A
```

If `output.html` is omitted, the converter writes beside the XML input using the same base name.

The local app also has a `Generate HTML` action. Select an XML file, choose `Auto`, `A`, or `B`, then generate and preview the HTML output in the browser. The generated HTML can be downloaded from the HTML tab.

## Use The Graph Explorer

1. Select one or more `.xml` export files.
2. Click `Generate Graph`.
3. Pan and zoom the graph area.
4. Search by object name.
5. Filter by object type.
6. Click a node to view its source file, XML path, metadata, and raw XML snippet.
7. Hover or click an edge to inspect the relationship.
8. Click `Export JSON` to download the current graph data.

## Graph JSON Schema

```json
{
  "nodes": [
    {
      "id": "string",
      "label": "string",
      "type": "FixedValue | Formula | LookupTable | Quota | RateTable | Territory | Variable | Rule | Plan | PlanComponent | EventType | CreditType | EarningCode | EarningGroup | BusinessUnit | ProcessingUnit | Calendar",
      "sourceFile": "string",
      "xmlPath": "string",
      "rawXml": "string",
      "metadata": {}
    }
  ],
  "links": [
    {
      "source": "string",
      "target": "string",
      "relationship": "uses_formula | uses_lookup | uses_classifier | belongs_to_plan | runs_in_pipeline | uses_event_type | outputs_credit_type | feeds_deposit | depends_on_period | references_custom_object | references_report | references_integration | parent_child | unknown_reference",
      "confidence": "high | medium | low",
      "metadata": {}
    }
  ]
}
```

## Error Handling

The app reports useful local errors for:

- malformed XML
- empty XML files
- unsupported file types
- graph generation failures
- unresolved references
- duplicate object IDs

Duplicate source IDs are kept as separate graph nodes with stable generated IDs. Duplicate details are recorded in node metadata.

## Known Limitations

- Relationship inference is generic and conservative because real SAP Incentive Management export shapes vary.
- Some unresolved references are emitted as low-confidence `unknown_reference` links.
- The first graph renderer is a local Cytoscape-compatible 2D renderer focused on MVP interaction, not advanced layout quality.
- Large-file performance has not been optimized yet.
- More object-specific extractors should be added as real export examples are collected.

## Future Roadmap

1. 3D graph mode using `react-force-graph-3d` or `3d-force-graph`.
2. DEV vs QA XML comparison.
3. Oracle vs HANA XML export comparison.
4. Impact analysis for upstream and downstream dependencies.
5. Orphaned object detection.
6. Unused rule, formula, and territory detection.
7. Duplicate object detection.
8. Broken reference detection.
9. Migration risk scoring.
10. AI-generated summaries of selected config objects.
11. AI-generated documentation from XML exports.
12. HTML documentation generator with graph screenshots.
13. Export to CSV, Markdown, and GraphML.
14. Optional Neo4j export.
15. Pipeline execution flow view.
16. Rule lineage view.
17. Search by object type, file, relationship, and confidence.
18. Saved graph sessions.
19. Large-file performance improvements.
20. Support for custom SAP Incentive Management object-specific extractors as more real export examples are collected.

## Development Checks

```powershell
python -m pytest -v
python sap_im_transformer.py tests\fixtures\minimal_plan.xml tests\fixtures\minimal_plan.html
python -m uvicorn sap_im_config_graph_explorer.app:app --reload
```
