"""Deterministic, local-only portable serializers for ``GraphDocument`` values."""

from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import (
    CONFIDENCE_LEVELS,
    FINDING_SEVERITIES,
    GRAPH_SCHEMA_VERSION,
    GRAPH_TOPOLOGIES,
    MIGRATION_RISK_SEVERITIES,
    NODE_TYPES,
    RELATIONSHIP_TYPES,
    SNAPSHOT_ROLES,
    TOPOLOGY_MODES,
    FindingWaiver,
    GraphDocument,
    GraphLink,
    GraphNode,
    GraphProvenance,
    MigrationRiskFactor,
    MigrationRiskReport,
    Snapshot,
    SourceProfile,
    ValidationFinding,
)


CSV_NODE_COLUMNS = (
    "id",
    "canonicalKey",
    "snapshotId",
    "type",
    "label",
    "sourceFile",
    "xmlPath",
    "metadataJson",
)
CSV_LINK_COLUMNS = (
    "id",
    "source",
    "target",
    "relationship",
    "confidence",
    "metadataJson",
)
CSV_FINDING_COLUMNS = (
    "id",
    "code",
    "severity",
    "snapshotId",
    "nodeIds",
    "message",
    "detailsJson",
)

CSV_BUNDLE_FILENAME = "sap-im-config-graph-csv.zip"
MARKDOWN_FILENAME = "sap-im-config-graph.md"
GRAPHML_FILENAME = "sap-im-config-graph.graphml"
NEO4J_BUNDLE_FILENAME = "sap-im-config-graph-neo4j.zip"
CYTOSCAPE_JSON_FILENAME = "sap-im-config-graph-cytoscape.json"
GEXF_FILENAME = "sap-im-config-graph.gexf"
STANDALONE_SVG_FILENAME = "sap-im-config-graph-interactive.svg"

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_GRAPHML_NAMESPACE = "http://graphml.graphdrawing.org/xmlns"
_GEXF_NAMESPACE = "http://www.gexf.net/1.2draft"
_GEXF_VIZ_NAMESPACE = "http://www.gexf.net/1.2draft/viz"
_GEXF_XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


class PortableGraphExportError(ValueError):
    """Raised when an API payload is not a complete, valid graph document."""


def graph_document_from_payload(payload: Mapping[str, Any]) -> GraphDocument:
    """Deserialize the browser's complete graph payload into the graph contract.

    The application only posts its current in-memory graph to portable export routes.
    Reconstructing the model here prevents a caller from serializing unknown graph
    types, malformed findings, or arbitrary payload fields as portable exports.
    """

    data = _mapping(payload, "Graph export payload")
    _keys(
        data,
        "Graph export payload",
        required={
            "schemaVersion",
            "topologyMode",
            "provenance",
            "snapshots",
            "nodes",
            "links",
            "findings",
        },
        optional={"migrationRisk", "waivers", "asOfDate"},
    )
    snapshots = [_snapshot_from_payload(item) for item in _list(data, "snapshots")]
    nodes = [_node_from_payload(item) for item in _list(data, "nodes")]
    links = [_link_from_payload(item) for item in _list(data, "links")]
    findings = [_finding_from_payload(item) for item in _list(data, "findings")]
    waivers = (
        [_waiver_from_payload(item) for item in _list(data, "waivers")]
        if "waivers" in data
        else []
    )
    migration_risk = _migration_risk_from_payload(data.get("migrationRisk"))
    provenance = _graph_provenance_from_payload(data.get("provenance"))
    as_of_date = _optional_string(data, "asOfDate") if "asOfDate" in data else None

    try:
        document = GraphDocument(
            schemaVersion=_string(data, "schemaVersion"),
            topologyMode=_string(data, "topologyMode"),
            snapshots=snapshots,
            nodes=nodes,
            links=links,
            findings=findings,
            waivers=waivers,
            migrationRisk=migration_risk,
            provenance=provenance,
            asOfDate=as_of_date,
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc

    validate_graph_document(document)
    return document


def _validate_document_header(document: GraphDocument) -> GraphTopology:
    if not isinstance(document, GraphDocument):
        raise PortableGraphExportError("Portable exports require a GraphDocument.")
    if document.schemaVersion != GRAPH_SCHEMA_VERSION:
        raise PortableGraphExportError(
            f"Unsupported graph schema version: {document.schemaVersion}"
        )
    if document.topologyMode not in TOPOLOGY_MODES:
        raise PortableGraphExportError(
            f"Unsupported topology mode: {document.topologyMode}"
        )
    topology = GRAPH_TOPOLOGIES[document.topologyMode]
    if not isinstance(document.provenance, GraphProvenance):
        raise PortableGraphExportError("provenance must be an object.")
    if document.provenance.origin == "xml":
        if document.provenance.fileName is not None:
            raise PortableGraphExportError(
                "XML graph provenance must not include a JSON filename."
            )
    elif document.provenance.origin == "imported":
        if not document.provenance.fileName:
            raise PortableGraphExportError(
                "Imported graph provenance requires a JSON filename."
            )
        if (
            document.provenance.fileName != document.provenance.fileName.replace("\\", "/").split("/")[-1]
            or not document.provenance.fileName.lower().endswith(".json")
            or any(ord(character) < 32 for character in document.provenance.fileName)
        ):
            raise PortableGraphExportError(
                "Imported graph provenance contains an unsafe JSON filename."
            )
    else:
        raise PortableGraphExportError(
            f"Unsupported graph provenance origin: {document.provenance.origin}"
        )
    return topology


def _validate_snapshots(snapshots: Sequence[Snapshot]) -> set[str]:
    snapshot_ids: set[str] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, Snapshot):
            raise PortableGraphExportError("snapshots must contain only objects.")
        _non_empty_model_string(snapshot.id, "snapshot.id")
        if snapshot.id in snapshot_ids:
            raise PortableGraphExportError(f"Duplicate snapshot ID: {snapshot.id}")
        snapshot_ids.add(snapshot.id)
        if snapshot.role not in SNAPSHOT_ROLES:
            raise PortableGraphExportError(
                f"Unsupported snapshot role: {snapshot.role}"
            )
        if not isinstance(snapshot.sourceFiles, list) or not all(
            isinstance(source_file, str) for source_file in snapshot.sourceFiles
        ):
            raise PortableGraphExportError(
                "snapshot.sourceFiles must contain only strings."
            )
        if len(snapshot.sourceFiles) != len(set(snapshot.sourceFiles)):
            raise PortableGraphExportError(
                f"Snapshot {snapshot.id} has duplicate sourceFiles."
            )
        if not isinstance(snapshot.sourceProfiles, list):
            raise PortableGraphExportError(
                "snapshot.sourceProfiles must be an array."
            )
        profile_files: set[str] = set()
        for profile in snapshot.sourceProfiles:
            if not isinstance(profile, SourceProfile):
                raise PortableGraphExportError(
                    "snapshot.sourceProfiles must contain only objects."
                )
            _model_string(profile.sourceFile, "source profile.sourceFile")
            _model_string(profile.encoding, "source profile.encoding")
            if profile.namespaceUri is not None:
                _model_string(profile.namespaceUri, "source profile.namespaceUri")
            if profile.exportVersion is not None:
                _model_string(profile.exportVersion, "source profile.exportVersion")
            if profile.sourceFile not in snapshot.sourceFiles:
                raise PortableGraphExportError(
                    f"Snapshot {snapshot.id} source profile references unknown file: "
                    f"{profile.sourceFile}"
                )
            if profile.sourceFile in profile_files:
                raise PortableGraphExportError(
                    f"Snapshot {snapshot.id} has duplicate source profile for: "
                    f"{profile.sourceFile}"
                )
            profile_files.add(profile.sourceFile)
        _json_value(snapshot.to_dict(), "snapshot")
    return snapshot_ids


def _validate_nodes(
    nodes: Sequence[GraphNode],
    topology: GraphTopology,
    topology_mode: str,
    snapshot_ids: set[str],
) -> tuple[set[str], dict[str, str]]:
    node_ids: set[str] = set()
    node_snapshot_ids: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, GraphNode):
            raise PortableGraphExportError("nodes must contain only objects.")
        _non_empty_model_string(node.id, "node.id")
        if node.type not in NODE_TYPES:
            raise PortableGraphExportError(f"Unsupported graph node type: {node.type}")
        if node.type not in topology.node_types:
            raise PortableGraphExportError(
                f"Node type {node.type} is not allowed in {topology_mode} topology."
            )
        if node.id in node_ids:
            raise PortableGraphExportError(f"Duplicate graph node ID: {node.id}")
        node_ids.add(node.id)
        node_snapshot_ids[node.id] = node.snapshotId
        if node.snapshotId not in snapshot_ids:
            raise PortableGraphExportError(
                f"Graph node {node.id} references unknown snapshot: {node.snapshotId}"
            )
        for field_name in (
            "canonicalKey",
            "snapshotId",
            "label",
            "type",
            "sourceFile",
            "xmlPath",
            "rawXml",
        ):
            _model_string(getattr(node, field_name), f"node.{field_name}")
        if not isinstance(node.metadata, dict):
            raise PortableGraphExportError(f"node metadata for {node.id} must be an object.")
        _json_value(node.metadata, f"node metadata for {node.id}")
    return node_ids, node_snapshot_ids


def _validate_links(
    links: Sequence[GraphLink],
    topology: GraphTopology,
    topology_mode: str,
    node_ids: set[str],
    node_snapshot_ids: dict[str, str],
) -> None:
    link_ids: set[str] = set()
    for link in links:
        if not isinstance(link, GraphLink):
            raise PortableGraphExportError("links must contain only objects.")
        _non_empty_model_string(link.id, "link.id")
        if link.relationship not in RELATIONSHIP_TYPES:
            raise PortableGraphExportError(
                f"Unsupported graph relationship: {link.relationship}"
            )
        if link.relationship not in topology.relationship_types:
            raise PortableGraphExportError(
                f"Relationship {link.relationship} is not allowed in "
                f"{topology_mode} topology."
            )
        if link.confidence not in CONFIDENCE_LEVELS:
            raise PortableGraphExportError(
                f"Unsupported confidence level: {link.confidence}"
            )
        if link.id in link_ids:
            raise PortableGraphExportError(f"Duplicate graph link ID: {link.id}")
        link_ids.add(link.id)
        if link.source not in node_ids or link.target not in node_ids:
            raise PortableGraphExportError(
                f"Graph link {link.id} must reference existing node IDs."
            )
        if node_snapshot_ids[link.source] != node_snapshot_ids[link.target]:
            raise PortableGraphExportError(
                f"Graph link {link.id} crosses snapshot boundaries."
            )
        for field_name in ("source", "target", "relationship", "confidence"):
            _model_string(getattr(link, field_name), f"link.{field_name}")
        if not isinstance(link.metadata, dict):
            raise PortableGraphExportError(f"link metadata for {link.id} must be an object.")
        _json_value(link.metadata, f"link metadata for {link.id}")


def _validate_findings(
    findings: Sequence[ValidationFinding],
    snapshot_ids: set[str],
    node_ids: set[str],
    node_snapshot_ids: dict[str, str],
) -> None:
    finding_ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, ValidationFinding):
            raise PortableGraphExportError("findings must contain only objects.")
        _non_empty_model_string(finding.id, "finding.id")
        if finding.severity not in FINDING_SEVERITIES:
            raise PortableGraphExportError(
                f"Unsupported finding severity: {finding.severity}"
            )
        if finding.id in finding_ids:
            raise PortableGraphExportError(
                f"Duplicate validation finding ID: {finding.id}"
            )
        finding_ids.add(finding.id)
        if finding.snapshotId not in snapshot_ids:
            raise PortableGraphExportError(
                f"Validation finding {finding.id} references unknown snapshot: "
                f"{finding.snapshotId}"
            )
        for node_id in finding.nodeIds:
            if node_id not in node_ids:
                raise PortableGraphExportError(
                    f"Validation finding {finding.id} references unknown node IDs."
                )
            if node_snapshot_ids[node_id] != finding.snapshotId:
                raise PortableGraphExportError(
                    f"Validation finding {finding.id} crosses snapshot boundaries."
                )
        for field_name in ("code", "severity", "snapshotId", "message"):
            _model_string(getattr(finding, field_name), f"finding.{field_name}")
        if not isinstance(finding.nodeIds, tuple) or not all(
            isinstance(node_id, str) for node_id in finding.nodeIds
        ):
            raise PortableGraphExportError("finding.nodeIds must contain only strings.")
        if not isinstance(finding.details, dict):
            raise PortableGraphExportError(f"finding details for {finding.id} must be an object.")
        _json_value(finding.details, f"finding details for {finding.id}")


def _validate_waivers(waivers: Sequence[FindingWaiver]) -> None:
    waiver_ids: set[str] = set()
    for waiver in waivers:
        if not isinstance(waiver, FindingWaiver):
            raise PortableGraphExportError("waivers must contain only objects.")
        _non_empty_model_string(waiver.findingId, "waiver.findingId")
        if waiver.findingId in waiver_ids:
            raise PortableGraphExportError(
                f"Duplicate waiver for finding ID: {waiver.findingId}"
            )
        waiver_ids.add(waiver.findingId)
        _non_empty_model_string(waiver.reason, "waiver.reason")
        _non_empty_model_string(waiver.reviewer, "waiver.reviewer")
        _model_string(waiver.createdAt, "waiver.createdAt")
        if waiver.expiresAt is not None:
            _model_string(waiver.expiresAt, "waiver.expiresAt")


def _validate_migration_risk(
    migration_risk: MigrationRiskReport | None,
    node_ids: set[str],
) -> None:
    if migration_risk is not None:
        if not isinstance(migration_risk, MigrationRiskReport):
            raise PortableGraphExportError("migrationRisk must be an object.")
        if not _finite_number(migration_risk.score):
            raise PortableGraphExportError("migrationRisk.score must be a finite number.")
        for factor in migration_risk.factors:
            if not isinstance(factor, MigrationRiskFactor):
                raise PortableGraphExportError(
                    "migrationRisk.factors must contain only objects."
                )
            if factor.severity not in MIGRATION_RISK_SEVERITIES:
                raise PortableGraphExportError(
                    f"Unsupported migration risk severity: {factor.severity}"
                )
            if not _finite_number(factor.weight):
                raise PortableGraphExportError(
                    "migration risk factor weight must be a finite number."
                )
            for node_id in factor.nodeIds:
                if node_id not in node_ids:
                    raise PortableGraphExportError(
                        f"Migration risk factor {factor.code} references unknown node IDs."
                    )
        _json_value(migration_risk.to_dict(), "migration risk report")


def validate_graph_document(document: GraphDocument) -> None:
    """Validate the mutable dataclass contract before a portable serialization."""
    if getattr(document, "_validated", False):
        return

    topology = _validate_document_header(document)
    snapshot_ids = _validate_snapshots(document.snapshots)
    node_ids, node_snapshot_ids = _validate_nodes(
        document.nodes, topology, document.topologyMode, snapshot_ids
    )
    _validate_links(
        document.links, topology, document.topologyMode, node_ids, node_snapshot_ids
    )
    _validate_findings(
        document.findings, snapshot_ids, node_ids, node_snapshot_ids
    )
    _validate_waivers(document.waivers)
    _validate_migration_risk(document.migrationRisk, node_ids)
    document._validated = True


def serialize_csv_bundle(document: GraphDocument) -> bytes:
    """Return a byte-stable CSV ZIP bundle without raw XML content."""

    validate_graph_document(document)
    members = (
        ("nodes.csv", _nodes_csv(document)),
        ("links.csv", _links_csv(document)),
        ("findings.csv", _findings_csv(document)),
        ("manifest.json", _pretty_json(_manifest(document))),
    )
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, content in members:
            entry = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content.encode("utf-8"), compresslevel=9)
    return output.getvalue()


def serialize_markdown(document: GraphDocument) -> bytes:
    """Return a readable, stable Markdown report without raw XML content."""

    validate_graph_document(document)
    lines = [
        "# SAP IM Config Explorer Graph Export",
        "",
        "## Schema and topology",
        "",
        *_markdown_table(
            ("Field", "Value"),
            (
                ("Schema version", document.schemaVersion),
                ("Topology mode", document.topologyMode),
                *(
                    (("As-of date", document.asOfDate),)
                    if document.asOfDate
                    else ()
                ),
            ),
        ),
        "",
        "## Provenance",
        "",
        "Portable exports contain only the current in-memory graph. JSON remains the lossless local graph export.",
        "",
        *_markdown_migration_risk(document),
        "",
        "## Snapshots",
        "",
        *_markdown_table(
            ("ID", "Role", "Source files", "Source profiles"),
            (
                (
                    snapshot.id,
                    snapshot.role,
                    ", ".join(sorted(snapshot.sourceFiles)),
                    _canonical_json(_source_profiles(snapshot)),
                )
                for snapshot in _sorted_snapshots(document)
            ),
        ),
        "",
        "## Counts",
        "",
        *_markdown_table(
            ("Object", "Count"),
            (
                ("Nodes", str(len(document.nodes))),
                ("Links", str(len(document.links))),
                ("Findings", str(len(document.findings))),
            ),
        ),
        "",
        "## Nodes",
        "",
        *_markdown_table(
            ("ID", "Canonical key", "Snapshot", "Type", "Label", "Source file", "XML path", "Metadata JSON"),
            (
                (
                    node.id,
                    node.canonicalKey,
                    node.snapshotId,
                    node.type,
                    node.label,
                    node.sourceFile,
                    node.xmlPath,
                    _canonical_json(node.metadata),
                )
                for node in _sorted_nodes(document)
            ),
        ),
        "",
        "## Links",
        "",
        *_markdown_table(
            ("ID", "Source", "Target", "Relationship", "Confidence", "Metadata JSON"),
            (
                (
                    link.id,
                    link.source,
                    link.target,
                    link.relationship,
                    link.confidence,
                    _canonical_json(link.metadata),
                )
                for link in _sorted_links(document)
            ),
        ),
        "",
        "## Findings",
        "",
        *_markdown_table(
            ("ID", "Code", "Severity", "Snapshot", "Node IDs", "Message", "Details JSON"),
            (
                (
                    finding.id,
                    finding.code,
                    finding.severity,
                    finding.snapshotId,
                    _canonical_json(list(finding.nodeIds)),
                    finding.message,
                    _canonical_json(finding.details),
                )
                for finding in _sorted_findings(document)
            ),
        ),
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def serialize_graphml(document: GraphDocument) -> bytes:
    """Return a deterministic GraphML document without raw XML content."""

    validate_graph_document(document)
    ET.register_namespace("", _GRAPHML_NAMESPACE)
    qualified = lambda name: f"{{{_GRAPHML_NAMESPACE}}}{name}"
    root = ET.Element(qualified("graphml"))
    for key_id, scope, name in (
        ("graphSchemaVersion", "graph", "schemaVersion"),
        ("graphTopologyMode", "graph", "topologyMode"),
        ("graphSnapshotsJson", "graph", "snapshotsJson"),
        ("graphFindingsJson", "graph", "findingsJson"),
        ("graphProvenanceJson", "graph", "provenanceJson"),
        ("nodeId", "node", "id"),
        ("nodeCanonicalKey", "node", "canonicalKey"),
        ("nodeSnapshotId", "node", "snapshotId"),
        ("nodeType", "node", "type"),
        ("nodeLabel", "node", "label"),
        ("nodeSourceFile", "node", "sourceFile"),
        ("nodeXmlPath", "node", "xmlPath"),
        ("nodeMetadataJson", "node", "metadataJson"),
        ("edgeId", "edge", "id"),
        ("edgeSource", "edge", "source"),
        ("edgeTarget", "edge", "target"),
        ("edgeRelationship", "edge", "relationship"),
        ("edgeConfidence", "edge", "confidence"),
        ("edgeMetadataJson", "edge", "metadataJson"),
    ):
        ET.SubElement(
            root,
            qualified("key"),
            {"id": key_id, "for": scope, "attr.name": name, "attr.type": "string"},
        )

    graph = ET.SubElement(
        root,
        qualified("graph"),
        {"id": "sap-im-config-graph", "edgedefault": "directed"},
    )
    _graphml_data(graph, qualified, "graphSchemaVersion", document.schemaVersion)
    _graphml_data(graph, qualified, "graphTopologyMode", document.topologyMode)
    _graphml_data(graph, qualified, "graphSnapshotsJson", _canonical_json(_snapshots_payload(document)))
    _graphml_data(graph, qualified, "graphFindingsJson", _canonical_json(_findings_payload(document)))
    _graphml_data(graph, qualified, "graphProvenanceJson", _canonical_json(_provenance(document)))

    for node in _sorted_nodes(document):
        element = ET.SubElement(graph, qualified("node"), {"id": node.id})
        for key, value in (
            ("nodeId", node.id),
            ("nodeCanonicalKey", node.canonicalKey),
            ("nodeSnapshotId", node.snapshotId),
            ("nodeType", node.type),
            ("nodeLabel", node.label),
            ("nodeSourceFile", node.sourceFile),
            ("nodeXmlPath", node.xmlPath),
            ("nodeMetadataJson", _canonical_json(node.metadata)),
        ):
            _graphml_data(element, qualified, key, value)

    for link in _sorted_links(document):
        element = ET.SubElement(
            graph,
            qualified("edge"),
            {"id": link.id, "source": link.source, "target": link.target},
        )
        for key, value in (
            ("edgeId", link.id),
            ("edgeSource", link.source),
            ("edgeTarget", link.target),
            ("edgeRelationship", link.relationship),
            ("edgeConfidence", link.confidence),
            ("edgeMetadataJson", _canonical_json(link.metadata)),
        ):
            _graphml_data(element, qualified, key, value)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def serialize_neo4j_bundle(document: GraphDocument) -> bytes:
    """Return a byte-stable Neo4j CSV/Cypher/README ZIP bundle without raw XML content."""

    validate_graph_document(document)

    cypher_script = """// SAP IM Config Explorer Neo4j Import Script
//
// 1. Copy 'nodes.csv' and 'relationships.csv' into your Neo4j database's 'import' directory.
// 2. Run this script in the Neo4j Browser or using 'cypher-shell'.

// --- Constraints and Indexes ---
CREATE CONSTRAINT config_node_id_unique FOR (n:ConfigNode) REQUIRE n.id IS UNIQUE;

// --- Load Nodes ---
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
MERGE (n:ConfigNode {id: row.id})
SET n.canonicalKey = row.canonicalKey,
    n.snapshotId = row.snapshotId,
    n.type = row.type,
    n.label = row.label,
    n.sourceFile = row.sourceFile,
    n.xmlPath = row.xmlPath,
    n.metadataJson = row.metadataJson;

// --- Apply Node Type Labels ---
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
MATCH (n:ConfigNode {id: row.id})
FOREACH (_ IN CASE WHEN row.type = 'Plan' THEN [1] ELSE [] END | SET n:Plan)
FOREACH (_ IN CASE WHEN row.type = 'PlanComponent' THEN [1] ELSE [] END | SET n:PlanComponent)
FOREACH (_ IN CASE WHEN row.type = 'Rule' THEN [1] ELSE [] END | SET n:Rule)
FOREACH (_ IN CASE WHEN row.type = 'FixedValue' THEN [1] ELSE [] END | SET n:FixedValue)
FOREACH (_ IN CASE WHEN row.type = 'Formula' THEN [1] ELSE [] END | SET n:Formula)
FOREACH (_ IN CASE WHEN row.type = 'LookupTable' THEN [1] ELSE [] END | SET n:LookupTable)
FOREACH (_ IN CASE WHEN row.type = 'Quota' THEN [1] ELSE [] END | SET n:Quota)
FOREACH (_ IN CASE WHEN row.type = 'RateTable' THEN [1] ELSE [] END | SET n:RateTable)
FOREACH (_ IN CASE WHEN row.type = 'Territory' THEN [1] ELSE [] END | SET n:Territory)
FOREACH (_ IN CASE WHEN row.type = 'Variable' THEN [1] ELSE [] END | SET n:Variable)
FOREACH (_ IN CASE WHEN row.type = 'EventType' THEN [1] ELSE [] END | SET n:EventType)
FOREACH (_ IN CASE WHEN row.type = 'CreditType' THEN [1] ELSE [] END | SET n:CreditType)
FOREACH (_ IN CASE WHEN row.type = 'EarningCode' THEN [1] ELSE [] END | SET n:EarningCode)
FOREACH (_ IN CASE WHEN row.type = 'EarningGroup' THEN [1] ELSE [] END | SET n:EarningGroup)
FOREACH (_ IN CASE WHEN row.type = 'BusinessUnit' THEN [1] ELSE [] END | SET n:BusinessUnit)
FOREACH (_ IN CASE WHEN row.type = 'ProcessingUnit' THEN [1] ELSE [] END | SET n:ProcessingUnit)
FOREACH (_ IN CASE WHEN row.type = 'Calendar' THEN [1] ELSE [] END | SET n:Calendar);

// --- Load Relationships ---
LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
MATCH (source:ConfigNode {id: row.source})
MATCH (target:ConfigNode {id: row.target})
FOREACH (_ IN CASE WHEN row.relationship = 'uses_fixed_value' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_fixed_value]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_formula' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_formula]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_lookup' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_lookup]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_quota' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_quota]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_rate_table' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_rate_table]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_classifier' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_classifier]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_territory' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_territory]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_variable' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_variable]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_rule' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_rule]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'belongs_to_plan' THEN [1] ELSE [] END |
    MERGE (source)-[r:belongs_to_plan]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'belongs_to_plan_component' THEN [1] ELSE [] END |
    MERGE (source)-[r:belongs_to_plan_component]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'runs_in_pipeline' THEN [1] ELSE [] END |
    MERGE (source)-[r:runs_in_pipeline]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_event_type' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_event_type]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'outputs_credit_type' THEN [1] ELSE [] END |
    MERGE (source)-[r:outputs_credit_type]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_earning_code' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_earning_code]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_earning_group' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_earning_group]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_business_unit' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_business_unit]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_processing_unit' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_processing_unit]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'uses_calendar' THEN [1] ELSE [] END |
    MERGE (source)-[r:uses_calendar]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'feeds_deposit' THEN [1] ELSE [] END |
    MERGE (source)-[r:feeds_deposit]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'depends_on_period' THEN [1] ELSE [] END |
    MERGE (source)-[r:depends_on_period]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'references_custom_object' THEN [1] ELSE [] END |
    MERGE (source)-[r:references_custom_object]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'references_report' THEN [1] ELSE [] END |
    MERGE (source)-[r:references_report]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'references_integration' THEN [1] ELSE [] END |
    MERGE (source)-[r:references_integration]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'parent_child' THEN [1] ELSE [] END |
    MERGE (source)-[r:parent_child]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
)
FOREACH (_ IN CASE WHEN row.relationship = 'unknown_reference' THEN [1] ELSE [] END |
    MERGE (source)-[r:unknown_reference]->(target)
    SET r.id = row.id, r.confidence = row.confidence, r.metadataJson = row.metadataJson
);
"""

    readme_content = """# SAP IM Config Explorer Neo4j Import Instructions

This package contains an offline Neo4j-compatible import bundle generated from the current allowlisted SAP IM Config graph.

## Package Members

- `nodes.csv`: CSV data for graph nodes.
- `relationships.csv`: CSV data for graph relationships.
- `import.cypher`: Cypher script to create uniqueness constraints, load nodes, apply node labels, and create relationships.
- `README.md`: This instruction document.

## Local Import Instructions

Follow these steps to import the graph into your local Neo4j instance:

1. **Locate the import directory**:
   - For Neo4j Desktop: Click on your project, select your active database, click **Open** > **Import**.
   - For Neo4j Aura / Cloud or Server: Place the CSV files in your server's configured `import/` directory.

2. **Copy the CSV files**:
   - Copy `nodes.csv` and `relationships.csv` into that `import/` directory.

3. **Run the Cypher import**:
   - Open Neo4j Browser or connect via `cypher-shell`.
   - Copy the Cypher statements from `import.cypher` and execute them. Note that you may need to execute the constraint creation line first, wait for it to complete, and then run the rest.

## Limitations

- **Offline Export**: This package does not connect to or store credentials for any Neo4j server directly. It is designed entirely for local file-based loading.
- **Node Type Scope**: Only allowlisted graph elements (Plans, Plan Components, Rules, Lookup Tables, Formulas, etc.) are exported. Formula internals and non-allowlisted objects are excluded.
- **Relationship Scope**: Only validated and resolved links between these allowlisted elements are included. Unresolved, missing, or ambiguous references are excluded to maintain graph integrity in Neo4j.
"""

    members = (
        ("nodes.csv", _nodes_csv(document)),
        ("relationships.csv", _links_csv(document)),
        ("import.cypher", cypher_script),
        ("README.md", readme_content),
    )
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, content in members:
            entry = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content.encode("utf-8"), compresslevel=9)
    return output.getvalue()


_TYPE_RGB: dict[str, tuple[int, int, int]] = {
    "FixedValue": (129, 199, 132),
    "Formula": (46, 125, 50),
    "LookupTable": (129, 199, 132),
    "Quota": (255, 160, 0),
    "RateTable": (46, 125, 50),
    "Territory": (129, 199, 132),
    "Variable": (255, 160, 0),
    "Rule": (46, 125, 50),
    "Plan": (79, 70, 229),
    "PlanComponent": (14, 165, 233),
    "EventType": (255, 160, 0),
    "CreditType": (46, 125, 50),
    "EarningCode": (129, 199, 132),
    "EarningGroup": (46, 125, 50),
    "ClusterMetanode": (79, 70, 229),
}


def _color_for_type_rgb(node_type: str) -> tuple[int, int, int]:
    return _TYPE_RGB.get(node_type, (99, 102, 241))


def _color_for_type_hex(node_type: str) -> str:
    r, g, b = _color_for_type_rgb(node_type)
    return f"#{r:02x}{g:02x}{b:02x}"


def serialize_cytoscape_json(document: GraphDocument) -> bytes:
    """Return a deterministic Cytoscape.js elements JSON document without raw XML content."""
    validate_graph_document(document)

    sorted_nodes = _sorted_nodes(document)
    sorted_links = _sorted_links(document)
    cols = max(1, math.ceil(math.sqrt(len(sorted_nodes)))) if sorted_nodes else 1

    nodes_payload = []
    for idx, node in enumerate(sorted_nodes):
        data: dict[str, Any] = {
            "id": node.id,
            "label": node.label,
            "type": node.type,
            "canonicalKey": node.canonicalKey,
            "snapshotId": node.snapshotId,
            "sourceFile": node.sourceFile,
            "xmlPath": node.xmlPath,
            "displayColor": _color_for_type_hex(node.type),
        }
        if node.metadata:
            for k, v in sorted(node.metadata.items()):
                if k != "rawXml" and isinstance(v, (str, int, float, bool)):
                    data[k] = v
        x = float((idx % cols) * 180)
        y = float((idx // cols) * 100)
        nodes_payload.append({
            "data": data,
            "position": {"x": x, "y": y},
            "classes": f"type-{node.type} snapshot-{node.snapshotId}",
        })

    edges_payload = []
    for link in sorted_links:
        data = {
            "id": link.id,
            "source": link.source,
            "target": link.target,
            "relationship": link.relationship,
            "confidence": link.confidence,
        }
        if link.metadata:
            for k, v in sorted(link.metadata.items()):
                if isinstance(v, (str, int, float, bool)):
                    data[k] = v
        edges_payload.append({
            "data": data,
            "classes": f"rel-{link.relationship} conf-{link.confidence}",
        })

    payload = {
        "format_version": "1.0",
        "generated_by": "SAP IM Config Explorer",
        "schemaVersion": document.schemaVersion,
        "topologyMode": document.topologyMode,
        "elements": {
            "nodes": nodes_payload,
            "edges": edges_payload,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


def serialize_gexf(document: GraphDocument) -> bytes:
    """Return a deterministic Gephi GEXF 1.2 XML document without raw XML content."""
    validate_graph_document(document)

    ET.register_namespace("", _GEXF_NAMESPACE)
    ET.register_namespace("viz", _GEXF_VIZ_NAMESPACE)
    ET.register_namespace("xsi", _GEXF_XSI_NAMESPACE)

    q_gexf = lambda name: f"{{{_GEXF_NAMESPACE}}}{name}"
    q_viz = lambda name: f"{{{_GEXF_VIZ_NAMESPACE}}}{name}"
    q_xsi = lambda name: f"{{{_GEXF_XSI_NAMESPACE}}}{name}"

    root = ET.Element(
        q_gexf("gexf"),
        {
            q_xsi("schemaLocation"): f"{_GEXF_NAMESPACE} http://www.gexf.net/1.2draft/gexf.xsd",
            "version": "1.2",
        },
    )

    meta = ET.SubElement(root, q_gexf("meta"), {"lastmodifieddate": "2026-09-15"})
    creator = ET.SubElement(meta, q_gexf("creator"))
    creator.text = "SAP IM Config Explorer"
    desc = ET.SubElement(meta, q_gexf("description"))
    desc.text = "SAP Incentive Management configuration topology"

    graph = ET.SubElement(root, q_gexf("graph"), {"defaultedgetype": "directed", "mode": "static"})

    # Node attributes schema
    node_attrs = ET.SubElement(graph, q_gexf("attributes"), {"class": "node"})
    ET.SubElement(node_attrs, q_gexf("attribute"), {"id": "0", "title": "canonicalKey", "type": "string"})
    ET.SubElement(node_attrs, q_gexf("attribute"), {"id": "1", "title": "snapshotId", "type": "string"})
    ET.SubElement(node_attrs, q_gexf("attribute"), {"id": "2", "title": "type", "type": "string"})
    ET.SubElement(node_attrs, q_gexf("attribute"), {"id": "3", "title": "sourceFile", "type": "string"})
    ET.SubElement(node_attrs, q_gexf("attribute"), {"id": "4", "title": "xmlPath", "type": "string"})

    # Edge attributes schema
    edge_attrs = ET.SubElement(graph, q_gexf("attributes"), {"class": "edge"})
    ET.SubElement(edge_attrs, q_gexf("attribute"), {"id": "0", "title": "relationship", "type": "string"})
    ET.SubElement(edge_attrs, q_gexf("attribute"), {"id": "1", "title": "confidence", "type": "string"})

    sorted_nodes = _sorted_nodes(document)
    sorted_links = _sorted_links(document)
    cols = max(1, math.ceil(math.sqrt(len(sorted_nodes)))) if sorted_nodes else 1

    nodes_el = ET.SubElement(graph, q_gexf("nodes"))
    for idx, node in enumerate(sorted_nodes):
        node_el = ET.SubElement(nodes_el, q_gexf("node"), {"id": node.id, "label": node.label})
        attvalues = ET.SubElement(node_el, q_gexf("attvalues"))
        for attr_id, val in (
            ("0", node.canonicalKey),
            ("1", node.snapshotId),
            ("2", node.type),
            ("3", node.sourceFile),
            ("4", node.xmlPath),
        ):
            ET.SubElement(attvalues, q_gexf("attvalue"), {"for": attr_id, "value": val or ""})

        r, g, b = _color_for_type_rgb(node.type)
        ET.SubElement(node_el, q_viz("color"), {"r": str(r), "g": str(g), "b": str(b)})
        ET.SubElement(node_el, q_viz("size"), {"value": "20.0"})
        pos_x = float((idx % cols) * 180)
        pos_y = float((idx // cols) * 100)
        ET.SubElement(node_el, q_viz("position"), {"x": str(pos_x), "y": str(pos_y), "z": "0.0"})

    edges_el = ET.SubElement(graph, q_gexf("edges"))
    for link in sorted_links:
        edge_el = ET.SubElement(
            edges_el,
            q_gexf("edge"),
            {"id": link.id, "source": link.source, "target": link.target},
        )
        attvalues = ET.SubElement(edge_el, q_gexf("attvalues"))
        ET.SubElement(attvalues, q_gexf("attvalue"), {"for": "0", "value": link.relationship or ""})
        ET.SubElement(attvalues, q_gexf("attvalue"), {"for": "1", "value": link.confidence or ""})

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def serialize_standalone_svg(
    document: GraphDocument,
    layout_positions: dict[str, tuple[float, float]] | None = None,
) -> bytes:
    """Return a standalone, self-contained interactive SVG vector diagram with embedded CSS and JS."""
    validate_graph_document(document)

    sorted_nodes = _sorted_nodes(document)
    sorted_links = _sorted_links(document)
    node_count = len(sorted_nodes)

    cols = max(1, math.ceil(math.sqrt(node_count))) if node_count else 1
    spacing_x = 240.0
    spacing_y = 130.0
    margin_x = 60.0
    margin_y = 60.0
    card_w = 170.0
    card_h = 56.0

    positions: dict[str, tuple[float, float]] = {}
    for idx, node in enumerate(sorted_nodes):
        if layout_positions and node.id in layout_positions:
            positions[node.id] = layout_positions[node.id]
        else:
            gx = margin_x + float((idx % cols) * spacing_x)
            gy = margin_y + float((idx // cols) * spacing_y)
            positions[node.id] = (gx, gy)

    max_x = max((x + card_w for x, _ in positions.values()), default=800.0) + margin_x
    max_y = max((y + card_h for _, y in positions.values()), default=600.0) + margin_y
    view_width = max(800.0, max_x)
    view_height = max(600.0, max_y)

    SVG_NS = "http://www.w3.org/2000/svg"
    ET.register_namespace("", SVG_NS)
    q_svg = lambda name: f"{{{SVG_NS}}}{name}"

    root = ET.Element(
        q_svg("svg"),
        {
            "width": f"{int(view_width)}",
            "height": f"{int(view_height)}",
            "viewBox": f"0 0 {int(view_width)} {int(view_height)}",
            "version": "1.1",
        },
    )

    # Defs: Markers & Filters
    defs = ET.SubElement(root, q_svg("defs"))
    marker = ET.SubElement(
        defs,
        q_svg("marker"),
        {
            "id": "arrow-default",
            "viewBox": "0 0 10 10",
            "refX": "10",
            "refY": "5",
            "markerWidth": "6",
            "markerHeight": "6",
            "orient": "auto-start-reverse",
        },
    )
    ET.SubElement(marker, q_svg("path"), {"d": "M 0 0 L 10 5 L 0 10 z", "fill": "#64748b"})

    marker_active = ET.SubElement(
        defs,
        q_svg("marker"),
        {
            "id": "arrow-active",
            "viewBox": "0 0 10 10",
            "refX": "10",
            "refY": "5",
            "markerWidth": "6",
            "markerHeight": "6",
            "orient": "auto-start-reverse",
        },
    )
    ET.SubElement(marker_active, q_svg("path"), {"d": "M 0 0 L 10 5 L 0 10 z", "fill": "#f59e0b"})

    # Embedded CSS Style
    style = ET.SubElement(root, q_svg("style"))
    style.text = """
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --edge: #64748b;
      --highlight: #f59e0b;
      --accent: #38bdf8;
    }
    svg { background: #0f172a; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; user-select: none; }
    .edge { stroke: #64748b; stroke-width: 1.5; fill: none; transition: stroke 0.2s, stroke-width 0.2s; }
    .edge.highlighted { stroke: #f59e0b; stroke-width: 3.5; marker-end: url(#arrow-active); }
    .edge.dimmed { opacity: 0.12; }
    .node-group { cursor: pointer; transition: transform 0.2s ease; }
    .node-group:focus { outline: none; }
    .node-card { fill: #1e293b; stroke-width: 2; transition: stroke 0.2s, stroke-width 0.2s; }
    .node-group:hover .node-card { stroke: #38bdf8; stroke-width: 3; }
    .node-group.active .node-card { stroke: #f59e0b; stroke-width: 3.5; }
    .node-group.dimmed { opacity: 0.15; }
    .node-label { fill: #f8fafc; font-size: 11px; font-weight: 600; text-anchor: middle; pointer-events: none; }
    .type-pill { rx: 4; ry: 4; pointer-events: none; }
    .type-text { fill: #ffffff; font-size: 9px; font-weight: 700; text-anchor: middle; pointer-events: none; text-transform: uppercase; letter-spacing: 0.5px; }
    .tooltip-bg { fill: #020617; stroke: #475569; stroke-width: 1; rx: 6; ry: 6; filter: drop-shadow(0 4px 12px rgba(0,0,0,0.6)); }
    .tooltip-title { fill: #f8fafc; font-size: 11px; font-weight: 700; }
    .tooltip-sub { fill: #94a3b8; font-size: 10px; }
    """

    # Interactive Viewport container for pan & zoom
    viewport = ET.SubElement(root, q_svg("g"), {"id": "viewport"})

    # Edges layer
    edges_layer = ET.SubElement(viewport, q_svg("g"), {"id": "edges-layer"})
    for link in sorted_links:
        src_pos = positions.get(link.source)
        tgt_pos = positions.get(link.target)
        if not src_pos or not tgt_pos:
            continue

        sx, sy = src_pos[0] + card_w / 2.0, src_pos[1] + card_h / 2.0
        tx, ty = tgt_pos[0] + card_w / 2.0, tgt_pos[1] + card_h / 2.0

        # Adjust target end to card boundary
        dx = tx - sx
        dy = ty - sy
        dist = math.hypot(dx, dy)
        if dist > 1.0:
            target_offset_x = tx - (dx / dist) * (card_w / 2.0)
            target_offset_y = ty - (dy / dist) * (card_h / 2.0)
        else:
            target_offset_x, target_offset_y = tx, ty

        # Smooth quadratic curve
        mid_x = (sx + target_offset_x) / 2.0
        mid_y = (sy + target_offset_y) / 2.0
        # subtle curve offset perpendicular to line
        perp_x = -(dy / dist) * 15.0 if dist > 1.0 else 0.0
        perp_y = (dx / dist) * 15.0 if dist > 1.0 else 0.0
        ctrl_x = mid_x + perp_x
        ctrl_y = mid_y + perp_y

        d_str = f"M {sx:.1f} {sy:.1f} Q {ctrl_x:.1f} {ctrl_y:.1f} {target_offset_x:.1f} {target_offset_y:.1f}"
        ET.SubElement(
            edges_layer,
            q_svg("path"),
            {
                "id": f"edge-{link.id}",
                "class": "edge",
                "d": d_str,
                "marker-end": "url(#arrow-default)",
                "data-source": link.source,
                "data-target": link.target,
                "data-rel": link.relationship or "",
            },
        )

    # Nodes layer
    nodes_layer = ET.SubElement(viewport, q_svg("g"), {"id": "nodes-layer"})
    for node in sorted_nodes:
        pos = positions[node.id]
        nx, ny = pos[0], pos[1]
        border_color = _color_for_type_hex(node.type)

        node_g = ET.SubElement(
            nodes_layer,
            q_svg("g"),
            {
                "id": f"node-{node.id}",
                "class": "node-group",
                "data-id": node.id,
                "data-label": node.label,
                "data-type": node.type,
                "data-key": node.canonicalKey or "",
                "data-file": node.sourceFile or "",
                "tabindex": "0",
            },
        )

        # Card rect
        ET.SubElement(
            node_g,
            q_svg("rect"),
            {
                "class": "node-card",
                "x": f"{nx:.1f}",
                "y": f"{ny:.1f}",
                "width": f"{card_w:.1f}",
                "height": f"{card_h:.1f}",
                "rx": "8",
                "ry": "8",
                "stroke": border_color,
            },
        )

        # Type pill
        pill_w = max(60.0, len(node.type) * 7.0 + 12.0)
        ET.SubElement(
            node_g,
            q_svg("rect"),
            {
                "class": "type-pill",
                "x": f"{nx + 10.0:.1f}",
                "y": f"{ny + 8.0:.1f}",
                "width": f"{pill_w:.1f}",
                "height": "16.0",
                "fill": border_color,
            },
        )
        type_txt = ET.SubElement(
            node_g,
            q_svg("text"),
            {
                "class": "type-text",
                "x": f"{nx + 10.0 + pill_w / 2.0:.1f}",
                "y": f"{ny + 19.5:.1f}",
            },
        )
        type_txt.text = node.type

        # Label text (truncated if too long)
        display_label = node.label if len(node.label) <= 20 else node.label[:18] + "..."
        lbl_txt = ET.SubElement(
            node_g,
            q_svg("text"),
            {
                "class": "node-label",
                "x": f"{nx + card_w / 2.0:.1f}",
                "y": f"{ny + 42.0:.1f}",
            },
        )
        lbl_txt.text = display_label

    # Tooltip overlay
    tooltip_g = ET.SubElement(root, q_svg("g"), {"id": "svg-tooltip", "opacity": "0", "pointer-events": "none"})
    ET.SubElement(tooltip_g, q_svg("rect"), {"class": "tooltip-bg", "width": "220", "height": "56", "x": "0", "y": "0"})
    t_title = ET.SubElement(tooltip_g, q_svg("text"), {"class": "tooltip-title", "x": "12", "y": "22"})
    t_title.text = "Node Details"
    t_sub = ET.SubElement(tooltip_g, q_svg("text"), {"class": "tooltip-sub", "x": "12", "y": "40"})
    t_sub.text = ""

    # Embedded Vanilla JS Script for Pan/Zoom, Hover Tooltip, and Selection
    script = ET.SubElement(root, q_svg("script"), {"type": "text/javascript"})
    script.text = """
    (function() {
      const svg = document.querySelector('svg');
      const viewport = document.getElementById('viewport');
      const tooltip = document.getElementById('svg-tooltip');
      const tooltipTitle = tooltip.querySelector('.tooltip-title');
      const tooltipSub = tooltip.querySelector('.tooltip-sub');
      const nodeGroups = Array.from(document.querySelectorAll('.node-group'));
      const edges = Array.from(document.querySelectorAll('.edge'));

      let panX = 0, panY = 0, zoom = 1.0;
      let isPanning = false, startX = 0, startY = 0;
      let selectedNodeId = null;

      function updateTransform() {
        viewport.setAttribute('transform', `translate(${panX}, ${panY}) scale(${zoom})`);
      }

      svg.addEventListener('mousedown', (e) => {
        if (e.target.closest('.node-group')) return;
        isPanning = true;
        startX = e.clientX - panX;
        startY = e.clientY - panY;
      });

      window.addEventListener('mousemove', (e) => {
        if (isPanning) {
          panX = e.clientX - startX;
          panY = e.clientY - startY;
          updateTransform();
        }
      });

      window.addEventListener('mouseup', () => { isPanning = false; });

      svg.addEventListener('wheel', (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        const newZoom = Math.min(Math.max(0.2, zoom * factor), 4.0);
        const rect = svg.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        panX = mouseX - (mouseX - panX) * (newZoom / zoom);
        panY = mouseY - (mouseY - panY) * (newZoom / zoom);
        zoom = newZoom;
        updateTransform();
      }, { passive: false });

      // Node selection & highlight
      nodeGroups.forEach((ng) => {
        const id = ng.dataset.id;
        ng.addEventListener('click', (e) => {
          e.stopPropagation();
          if (selectedNodeId === id) {
            // Deselect
            selectedNodeId = null;
            nodeGroups.forEach(n => n.classList.remove('active', 'dimmed'));
            edges.forEach(ed => ed.classList.remove('highlighted', 'dimmed'));
          } else {
            selectedNodeId = id;
            const connectedNodeIds = new Set([id]);
            edges.forEach((ed) => {
              const src = ed.dataset.source;
              const tgt = ed.dataset.target;
              if (src === id || tgt === id) {
                ed.classList.add('highlighted');
                ed.classList.remove('dimmed');
                connectedNodeIds.add(src);
                connectedNodeIds.add(tgt);
              } else {
                ed.classList.remove('highlighted');
                ed.classList.add('dimmed');
              }
            });
            nodeGroups.forEach((n) => {
              const nid = n.dataset.id;
              if (connectedNodeIds.has(nid)) {
                n.classList.remove('dimmed');
                n.classList.toggle('active', nid === id);
              } else {
                n.classList.remove('active');
                n.classList.add('dimmed');
              }
            });
          }
        });

        ng.addEventListener('mouseenter', (e) => {
          const rect = svg.getBoundingClientRect();
          const label = ng.dataset.label;
          const type = ng.dataset.type;
          const key = ng.dataset.key;
          tooltipTitle.textContent = label;
          tooltipSub.textContent = `${type} • ${key}`;
          const mx = e.clientX - rect.left + 15;
          const my = e.clientY - rect.top + 15;
          tooltip.setAttribute('transform', `translate(${mx}, ${my})`);
          tooltip.setAttribute('opacity', '1');
        });

        ng.addEventListener('mouseleave', () => {
          tooltip.setAttribute('opacity', '0');
        });
      });

      svg.addEventListener('click', () => {
        selectedNodeId = null;
        nodeGroups.forEach(n => n.classList.remove('active', 'dimmed'));
        edges.forEach(ed => ed.classList.remove('highlighted', 'dimmed'));
      });
    })();
    """

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"



def _nodes_csv(document: GraphDocument) -> str:
    return _csv_text(
        CSV_NODE_COLUMNS,
        (
            (
                node.id,
                node.canonicalKey,
                node.snapshotId,
                node.type,
                node.label,
                node.sourceFile,
                node.xmlPath,
                _canonical_json(node.metadata),
            )
            for node in _sorted_nodes(document)
        ),
    )


def _links_csv(document: GraphDocument) -> str:
    return _csv_text(
        CSV_LINK_COLUMNS,
        (
            (
                link.id,
                link.source,
                link.target,
                link.relationship,
                link.confidence,
                _canonical_json(link.metadata),
            )
            for link in _sorted_links(document)
        ),
    )


def _findings_csv(document: GraphDocument) -> str:
    return _csv_text(
        CSV_FINDING_COLUMNS,
        (
            (
                finding.id,
                finding.code,
                finding.severity,
                finding.snapshotId,
                _canonical_json(list(finding.nodeIds)),
                finding.message,
                _canonical_json(finding.details),
            )
            for finding in _sorted_findings(document)
        ),
    )


def _manifest(document: GraphDocument) -> dict[str, Any]:
    return {
        "format": "sap-im-config-graph-csv",
        "schemaVersion": document.schemaVersion,
        "topologyMode": document.topologyMode,
        "counts": {
            "nodes": len(document.nodes),
            "links": len(document.links),
            "findings": len(document.findings),
        },
        "snapshots": _snapshots_payload(document),
        "provenance": _provenance(document),
    }


def _snapshots_payload(document: GraphDocument) -> list[dict[str, Any]]:
    return [
        {
            "id": snapshot.id,
            "role": snapshot.role,
            "sourceFiles": sorted(snapshot.sourceFiles),
            "sourceProfiles": _source_profiles(snapshot),
        }
        for snapshot in _sorted_snapshots(document)
    ]


def _source_profiles(snapshot: Snapshot) -> list[dict[str, Any]]:
    return [
        profile.to_dict()
        for profile in sorted(
            snapshot.sourceProfiles,
            key=lambda profile: (
                profile.sourceFile,
                profile.encoding,
                profile.namespaceUri or "",
                profile.exportVersion or "",
            ),
        )
    ]


def _findings_payload(document: GraphDocument) -> list[dict[str, Any]]:
    return [finding.to_dict() for finding in _sorted_findings(document)]


def _provenance(document: GraphDocument) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        **document.provenance.to_dict(),
        "sourceProfiles": [
            {"snapshotId": snapshot.id, "profiles": _source_profiles(snapshot)}
            for snapshot in _sorted_snapshots(document)
        ]
    }
    if document.migrationRisk is not None:
        provenance["migrationRisk"] = {
            "score": document.migrationRisk.score,
            "factors": [
                factor.to_dict() for factor in _sorted_migration_risk_factors(document)
            ],
        }
    return provenance


def _markdown_migration_risk(document: GraphDocument) -> list[str]:
    lines = ["### Migration risk", ""]
    if document.migrationRisk is None:
        return [*lines, "No migration-risk report is available."]
    lines.extend(
        _markdown_table(
            ("Score", "Factor count"),
            (
                (
                    str(document.migrationRisk.score),
                    str(len(document.migrationRisk.factors)),
                ),
            ),
        )
    )
    lines.extend(
        [
            "",
            "#### Migration-risk factors",
            "",
            *_markdown_table(
                ("Code", "Severity", "Weight", "Node IDs", "Message"),
                (
                    (
                        factor.code,
                        factor.severity,
                        str(factor.weight),
                        _canonical_json(list(factor.nodeIds)),
                        factor.message,
                    )
                    for factor in _sorted_migration_risk_factors(document)
                ),
            ),
        ]
    )
    return lines


def _sorted_migration_risk_factors(
    document: GraphDocument,
) -> list[MigrationRiskFactor]:
    if document.migrationRisk is None:
        return []
    return sorted(
        document.migrationRisk.factors,
        key=lambda factor: (
            factor.severity,
            factor.code,
            factor.message,
            factor.weight,
            factor.nodeIds,
        ),
    )


def _sorted_nodes(document: GraphDocument) -> list[GraphNode]:
    return sorted(
        document.nodes,
        key=lambda node: (node.snapshotId, node.type, node.canonicalKey, node.id),
    )


def _sorted_links(document: GraphDocument) -> list[GraphLink]:
    return sorted(
        document.links,
        key=lambda link: (link.source, link.target, link.relationship, link.id),
    )


def _sorted_findings(document: GraphDocument) -> list[ValidationFinding]:
    return sorted(
        document.findings,
        key=lambda finding: (
            finding.snapshotId,
            finding.severity,
            finding.code,
            finding.id,
        ),
    )


def _sorted_snapshots(document: GraphDocument) -> list[Snapshot]:
    return sorted(document.snapshots, key=lambda snapshot: (snapshot.id, snapshot.role))


def _csv_text(columns: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_safe_csv_cell(column) for column in columns)
    for row in rows:
        writer.writerow(_safe_csv_cell(value) for value in row)
    return output.getvalue()


def _safe_csv_cell(value: object) -> str:
    text = str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _markdown_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    escaped_headers = [_escape_markdown_cell(value) for value in headers]
    lines = [
        f"| {' | '.join(escaped_headers)} |",
        f"| {' | '.join('---' for _ in headers)} |",
    ]
    lines.extend(
        f"| {' | '.join(_escape_markdown_cell(value) for value in row)} |"
        for row in rows
    )
    return lines


def _escape_markdown_cell(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )


def _graphml_data(element: ET.Element, qualified: Any, key: str, value: str) -> None:
    child = ET.SubElement(element, qualified("data"), {"key": key})
    child.text = value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PortableGraphExportError(f"Value is not portable JSON: {exc}") from exc


def _pretty_json(value: object) -> str:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise PortableGraphExportError(f"Value is not portable JSON: {exc}") from exc


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PortableGraphExportError(f"{name} must be an object.")
    return value


def _keys(
    data: Mapping[str, Any],
    name: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = sorted(required - set(data))
    if missing:
        raise PortableGraphExportError(
            f"{name} is missing required field: {missing[0]}."
        )
    unexpected = sorted(set(data) - required - optional)
    if unexpected:
        raise PortableGraphExportError(
            f"{name} contains unsupported field: {unexpected[0]}."
        )


def _list(data: Mapping[str, Any], name: str) -> list[Any]:
    value = data.get(name)
    if not isinstance(value, list):
        raise PortableGraphExportError(f"{name} must be an array.")
    return value


def _string(data: Mapping[str, Any], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str):
        raise PortableGraphExportError(f"{name} must be a string.")
    return value


def _string_list(data: Mapping[str, Any], name: str) -> list[str]:
    values = _list(data, name)
    if not all(isinstance(value, str) for value in values):
        raise PortableGraphExportError(f"{name} must contain only strings.")
    return values


def _object(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise PortableGraphExportError(f"{name} must be an object.")
    return value


def _snapshot_from_payload(value: object) -> Snapshot:
    data = _mapping(value, "snapshot")
    _keys(
        data,
        "snapshot",
        required={"id", "role", "sourceFiles", "sourceProfiles"},
    )
    try:
        profiles = []
        for profile_value in _list(data, "sourceProfiles"):
            profile = _mapping(profile_value, "source profile")
            _keys(
                profile,
                "source profile",
                required={"sourceFile", "encoding", "namespaceUri", "exportVersion"},
            )
            profiles.append(
                SourceProfile(
                    sourceFile=_string(profile, "sourceFile"),
                    encoding=_string(profile, "encoding"),
                    namespaceUri=_optional_string(profile, "namespaceUri"),
                    exportVersion=_optional_string(profile, "exportVersion"),
                )
            )
        return Snapshot(
            id=_string(data, "id"),
            role=_string(data, "role"),
            sourceFiles=_string_list(data, "sourceFiles"),
            sourceProfiles=profiles,
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _node_from_payload(value: object) -> GraphNode:
    data = _mapping(value, "node")
    _keys(
        data,
        "node",
        required={
            "id",
            "canonicalKey",
            "snapshotId",
            "label",
            "type",
            "sourceFile",
            "xmlPath",
            "rawXml",
            "metadata",
        },
    )
    try:
        return GraphNode(
            id=_string(data, "id"),
            canonicalKey=_string(data, "canonicalKey"),
            snapshotId=_string(data, "snapshotId"),
            label=_string(data, "label"),
            type=_string(data, "type"),
            sourceFile=_string(data, "sourceFile"),
            xmlPath=_string(data, "xmlPath"),
            rawXml=_string(data, "rawXml"),
            metadata=_object(data, "metadata"),
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _link_from_payload(value: object) -> GraphLink:
    data = _mapping(value, "link")
    _keys(
        data,
        "link",
        required={
            "id",
            "source",
            "target",
            "relationship",
            "confidence",
            "metadata",
        },
    )
    try:
        return GraphLink(
            id=_string(data, "id"),
            source=_string(data, "source"),
            target=_string(data, "target"),
            relationship=_string(data, "relationship"),
            confidence=_string(data, "confidence"),
            metadata=_object(data, "metadata"),
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _finding_from_payload(value: object) -> ValidationFinding:
    data = _mapping(value, "finding")
    _keys(
        data,
        "finding",
        required={
            "id",
            "code",
            "severity",
            "snapshotId",
            "nodeIds",
            "message",
            "details",
        },
    )
    try:
        return ValidationFinding(
            id=_string(data, "id"),
            code=_string(data, "code"),
            severity=_string(data, "severity"),
            snapshotId=_string(data, "snapshotId"),
            nodeIds=tuple(_string_list(data, "nodeIds")),
            message=_string(data, "message"),
            details=_object(data, "details"),
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _waiver_from_payload(value: object) -> FindingWaiver:
    data = _mapping(value, "waiver")
    _keys(
        data,
        "waiver",
        required={"findingId", "reason", "reviewer"},
        optional={"createdAt", "expiresAt"},
    )
    try:
        return FindingWaiver(
            findingId=_string(data, "findingId"),
            reason=_string(data, "reason"),
            reviewer=_string(data, "reviewer"),
            createdAt=(
                _string(data, "createdAt")
                if "createdAt" in data and data["createdAt"] is not None
                else ""
            ),
            expiresAt=_optional_string(data, "expiresAt"),
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _migration_risk_from_payload(value: object) -> MigrationRiskReport | None:
    if value is None:
        return None
    data = _mapping(value, "migrationRisk")
    _keys(data, "migrationRisk", required={"score", "factors"})
    score = data.get("score")
    if not _finite_number(score):
        raise PortableGraphExportError("migrationRisk.score must be a finite number.")
    factors = []
    for item in _list(data, "factors"):
        factor = _mapping(item, "migration risk factor")
        _keys(
            factor,
            "migration risk factor",
            required={"code", "severity", "message", "weight", "nodeIds"},
        )
        weight = factor.get("weight")
        if not _finite_number(weight):
            raise PortableGraphExportError(
                "migration risk factor weight must be a finite number."
            )
        try:
            factors.append(
                MigrationRiskFactor(
                    code=_string(factor, "code"),
                    severity=_string(factor, "severity"),
                    message=_string(factor, "message"),
                    weight=weight,
                    nodeIds=tuple(_string_list(factor, "nodeIds")),
                )
            )
        except ValueError as exc:
            raise PortableGraphExportError(str(exc)) from exc
    return MigrationRiskReport(score=score, factors=factors)


def _graph_provenance_from_payload(value: object) -> GraphProvenance:
    data = _mapping(value, "provenance")
    _keys(data, "provenance", required={"origin", "fileName"})
    try:
        return GraphProvenance(
            origin=_string(data, "origin"),
            fileName=_optional_string(data, "fileName"),
        )
    except ValueError as exc:
        raise PortableGraphExportError(str(exc)) from exc


def _optional_string(data: Mapping[str, Any], name: str) -> str | None:
    value = data.get(name)
    if value is None or isinstance(value, str):
        return value
    raise PortableGraphExportError(f"{name} must be a string or null.")


def _is_json_serializable_fast(val: object) -> bool:
    val_type = type(val)
    if val_type in (str, int, float, bool, type(None)):
        return True
    if val_type is dict:
        for k, v in val.items():
            if type(k) is not str or not _is_json_serializable_fast(v):
                return False
        return True
    if val_type in (list, tuple):
        for v in val:
            if not _is_json_serializable_fast(v):
                return False
        return True
    return False


def _json_value(value: object, name: str) -> None:
    if _is_json_serializable_fast(value):
        return
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (RecursionError, TypeError, ValueError) as exc:
        raise PortableGraphExportError(f"{name} is not portable JSON: {exc}") from exc


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _model_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise PortableGraphExportError(f"{name} must be a string.")


def _non_empty_model_string(value: object, name: str) -> None:
    _model_string(value, name)
    if not value:
        raise PortableGraphExportError(f"{name} must not be empty.")
