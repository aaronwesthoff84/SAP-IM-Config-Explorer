# SAP IM Config Explorer

SAP IM Config Explorer is a local-first tool for reviewing XML configuration exports. It preserves the existing XML-to-HTML conversion workflow and adds a browser-based dependency graph.

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

The local app also has a `Generate HTML` action. Select an XML file, choose `Auto`, `A`, or `B`, then generate and preview the HTML output in the browser.

The output has its own download link for reuse outside the browser.

## HTML Ordering

The generated HTML sorts named objects alphabetically, without changing the displayed section order. Rules are sorted by rule family first, then alphabetically within each family: Credit, Measurement, Incentive, Deposit, and Detailed Deposit. Any unrecognized rule family is shown last as **Other Rules** rather than being incorrectly presented as a Credit Rule.

## Use The Graph Explorer

1. Select one or more `.xml` export files.
2. Click `Generate Graph`.
3. Pan and zoom the graph area.
4. Search by object name or filter by object type.
5. Click a node to view its source file, XML path, metadata, and bounded raw XML.
6. Hover or click an edge to inspect its relationship.
7. Click an export action to download the complete current graph in JSON, CSV, Markdown, or GraphML.

## Graph Topologies

Core is the default topology and preserves the plan hierarchy:

- Plan
- Plan Component
- Rule

It shows `Rule -> Plan Component -> Plan` containment, so selecting a Rule also lists its associated plan components and plans in the details panel. References inside rules, including action instructions such as `Release Immediately`, do not create graph nodes or broken-reference findings in Core.

Full enables all 17 approved graph node types and their approved, source-evidenced relationships. Select Core or Full before generating a graph; changing the selection regenerates from the currently selected local files. Validation findings, migration analysis, status counts, and JSON export use the selected topology.

## Strict Graph Node Allowlist

The graph model accepts only these approved object categories; no unknown XML element may become a graph node:

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

The Core graph builder is stricter than this allowlist and emits only the three core types above. Full emits all allowlisted definitions present in the source. Formula and Rule internals such as `FUNCTION`, `PARAMETER_LIST`, conditions, actions, `RULE_ELEMENT_REF`, and literals remain metadata or reference evidence and never become graph nodes. A caller can provide a custom `ExtractorRegistry`, but `NodeFactory` still rejects node types outside the allowlist.

## Dependency And Containment Direction

Dependency links point from the dependent object to the object it uses. For example, a Rule that uses a Formula produces `Rule -> Formula` with `uses_formula`.

Containment links point from the child to its owner:

- Plan Component to Plan: `belongs_to_plan`
- Rule to Plan Component: `belongs_to_plan_component`

Reference resolution is scoped to a snapshot. A name in a production snapshot cannot satisfy a reference in a non-production snapshot.

## Graph JSON Contract

The current schema version is `1.2`. Version `1.2` adds `topologyMode` so every graph identifies whether Core or Full produced it. Version `1.1` added ordered per-file compatibility evidence under each snapshot's `sourceProfiles`. See [XML Compatibility Matrix](docs/compatibility-matrix.md) for the supported encodings, namespace behavior, and sanitized regression profiles.

```json
{
  "schemaVersion": "1.2",
  "topologyMode": "core | full",
  "snapshots": [
    {
      "id": "configuration",
      "role": "configuration | non_production | production",
      "sourceFiles": ["export.xml"],
      "sourceProfiles": [
        {
          "sourceFile": "export.xml",
          "encoding": "utf-8",
          "namespaceUri": null,
          "exportVersion": "16.0"
        }
      ]
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
      "code": "missing_reference | ambiguous_reference | duplicate_object | unused_object | orphaned_object",
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

## Portable Graph Exports

The export actions serialize the complete current in-memory graph, not the filtered graph view. They run only in the local browser and local application process; no XML, configuration content, or graph data is uploaded to an external service. The input is reconstructed against the versioned graph contract, so unsupported node types and relationship values cannot be exported.

`Export JSON` remains the lossless local graph export, including each node's `rawXml`. The portable CSV, Markdown, and GraphML exports deliberately exclude `rawXml` and contain no source XML bytes.

Every portable format sorts nodes by `(snapshotId, type, canonicalKey, id)`, links by `(source, target, relationship, id)`, and findings by `(snapshotId, severity, code, id)`. Snapshot source files, source profiles, and migration-risk factors are also sorted for stable output.

### CSV ZIP

`Export CSV` downloads `sap-im-config-graph-csv.zip`. It is a deterministic UTF-8 ZIP containing exactly these four members:

- `nodes.csv`
- `links.csv`
- `findings.csv`
- `manifest.json`

The CSV files always use these header columns, in this order. `metadataJson`, `detailsJson`, and `nodeIds` are compact, key-sorted JSON values.

| File | Columns |
| --- | --- |
| `nodes.csv` | `id, canonicalKey, snapshotId, type, label, sourceFile, xmlPath, metadataJson` |
| `links.csv` | `id, source, target, relationship, confidence, metadataJson` |
| `findings.csv` | `id, code, severity, snapshotId, nodeIds, message, detailsJson` |

To prevent spreadsheet applications from interpreting graph content as a formula, any CSV cell beginning with `=`, `+`, `-`, `@`, tab, carriage return, or line feed is prefixed with a single quote. This neutralization is part of the stable CSV mapping.

`manifest.json` contains the export format identifier, `schemaVersion`, `topologyMode`, node/link/finding counts, sorted snapshots and source profiles, plus local provenance. Provenance includes source profiles and migration-risk data when a migration-risk report is present.

### Markdown

`Export Markdown` downloads `sap-im-config-graph.md`. Table cell backslashes and pipes are escaped, and newlines are rendered as `<br>`, preserving readable one-row-per-object tables. Its stable section mapping is:

| Section | GraphDocument source | Output columns or values |
| --- | --- | --- |
| Schema and topology | `schemaVersion`, `topologyMode` | `Field, Value` |
| Provenance / Migration risk | `migrationRisk.score`, `migrationRisk.factors[]` | `Score, Factor count`; factors use `Code, Severity, Weight, Node IDs, Message` |
| Snapshots / profile provenance | `snapshots[]`, including `sourceFiles` and `sourceProfiles` | `ID, Role, Source files, Source profiles` |
| Counts | lengths of `nodes`, `links`, and `findings` | `Object, Count` |
| Nodes | `nodes[]` | `ID, Canonical key, Snapshot, Type, Label, Source file, XML path, Metadata JSON` |
| Links | `links[]` | `ID, Source, Target, Relationship, Confidence, Metadata JSON` |
| Findings | `findings[]` | `ID, Code, Severity, Snapshot, Node IDs, Message, Details JSON` |

### GraphML

`Export GraphML` downloads `sap-im-config-graph.graphml`. It uses each graph node/link ID as the GraphML `node/@id` or `edge/@id`, and each link source/target as `edge/@source` and `edge/@target`. All data keys have `attr.type="string"`; JSON values are compact and key-sorted.

| Scope | GraphDocument source | Key ID | `attr.name` |
| --- | --- | --- | --- |
| graph | `schemaVersion` | `graphSchemaVersion` | `schemaVersion` |
| graph | `topologyMode` | `graphTopologyMode` | `topologyMode` |
| graph | `snapshots[]` | `graphSnapshotsJson` | `snapshotsJson` |
| graph | `findings[]` | `graphFindingsJson` | `findingsJson` |
| graph | source profiles and `migrationRisk` | `graphProvenanceJson` | `provenanceJson` |
| node | `nodes[].id` | `nodeId` | `id` |
| node | `nodes[].canonicalKey` | `nodeCanonicalKey` | `canonicalKey` |
| node | `nodes[].snapshotId` | `nodeSnapshotId` | `snapshotId` |
| node | `nodes[].type` | `nodeType` | `type` |
| node | `nodes[].label` | `nodeLabel` | `label` |
| node | `nodes[].sourceFile` | `nodeSourceFile` | `sourceFile` |
| node | `nodes[].xmlPath` | `nodeXmlPath` | `xmlPath` |
| node | `nodes[].metadata` | `nodeMetadataJson` | `metadataJson` |
| edge | `links[].id` | `edgeId` | `id` |
| edge | `links[].source` | `edgeSource` | `source` |
| edge | `links[].target` | `edgeTarget` | `target` |
| edge | `links[].relationship` | `edgeRelationship` | `relationship` |
| edge | `links[].confidence` | `edgeConfidence` | `confidence` |
| edge | `links[].metadata` | `edgeMetadataJson` | `metadataJson` |

## Validation Findings

Graph construction runs a deterministic validation pass after reference resolution:

- `missing_reference` and `ambiguous_reference` are error-level broken-reference findings from resolution. In the current core graph, they apply only to missing or ambiguous Plan Component and Rule references.
- `duplicate_object` is an error when a canonical object identity repeats within one snapshot.
- `unused_object` is a warning when an object has no inbound semantic dependency or containment ownership. Plan is an explicit root exemption; a Rule or Plan Component attached to the core hierarchy is not unused.
- `orphaned_object` is a warning when an object has no inbound or outbound graph relationship of any kind.

Validation is snapshot-scoped. Findings identify the affected node IDs and include structured evidence for deterministic review and later migration analysis.

## Error Handling

The app reports useful local errors for:

- malformed XML
- empty XML files
- unsupported file types
- unsupported XML encodings and encoding mismatches
- malformed encoded byte sequences
- unsupported XML profiles whose root local name is not `DATA_IMPORT`
- graph generation failures
- duplicate snapshot IDs
- unsupported graph node or relationship types

Duplicate source IDs remain separate node instances with stable generated IDs. Duplicate details are recorded in node metadata, and references to non-unique targets become ambiguity findings.

## Known Limitations

- Real SAP Incentive Management export shapes vary, so additional exact aliases may be added as representative exports are collected.
- The first graph renderer is a local Cytoscape-compatible 2D renderer focused on core interaction rather than advanced layout quality.
- Large-file performance has not yet been optimized.
- Additional type-specific unused-object exemptions and richer migration rules remain future work.

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
