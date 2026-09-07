from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, Field, model_validator


GRAPH_SCHEMA_VERSION = "1.3"
SNAPSHOT_ROLES = {"configuration", "non_production", "production"}
FINDING_SEVERITIES = {"error", "warning", "info"}
MIGRATION_RISK_SEVERITIES = {"high", "medium", "low"}
GRAPH_PROVENANCE_ORIGINS = {"xml", "imported"}

NODE_TYPES = {
    "FixedValue",
    "Formula",
    "LookupTable",
    "Quota",
    "RateTable",
    "Territory",
    "Variable",
    "Rule",
    "Plan",
    "PlanComponent",
    "EventType",
    "CreditType",
    "EarningCode",
    "EarningGroup",
    "BusinessUnit",
    "ProcessingUnit",
    "Calendar",
}

RELATIONSHIP_TYPES = {
    "uses_fixed_value",
    "uses_formula",
    "uses_lookup",
    "uses_quota",
    "uses_rate_table",
    "uses_classifier",
    "uses_territory",
    "uses_variable",
    "uses_rule",
    "belongs_to_plan",
    "belongs_to_plan_component",
    "runs_in_pipeline",
    "uses_event_type",
    "outputs_credit_type",
    "uses_earning_code",
    "uses_earning_group",
    "uses_business_unit",
    "uses_processing_unit",
    "uses_calendar",
    "feeds_deposit",
    "depends_on_period",
    "references_custom_object",
    "references_report",
    "references_integration",
    "parent_child",
    "unknown_reference",
}

CONFIDENCE_LEVELS = {"high", "medium", "low"}
SOURCE_PROFILE_ENCODINGS = frozenset({"utf-8", "utf-16-le", "utf-16-be"})


@dataclass(frozen=True)
class GraphTopology:
    node_types: frozenset[str]
    relationship_types: frozenset[str]


GRAPH_TOPOLOGIES = {
    "core": GraphTopology(
        node_types=frozenset({"Plan", "PlanComponent", "Rule"}),
        relationship_types=frozenset(
            {"belongs_to_plan", "belongs_to_plan_component"}
        ),
    ),
    "full": GraphTopology(
        node_types=frozenset(NODE_TYPES),
        relationship_types=frozenset(RELATIONSHIP_TYPES),
    ),
}
TOPOLOGY_MODES = frozenset(GRAPH_TOPOLOGIES)


@dataclass(frozen=True)
class SourceProfile:
    sourceFile: str
    encoding: str
    namespaceUri: str | None
    exportVersion: str | None

    def __post_init__(self) -> None:
        if self.encoding not in SOURCE_PROFILE_ENCODINGS:
            raise ValueError(f"Unsupported source profile encoding: {self.encoding}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceFile": self.sourceFile,
            "encoding": self.encoding,
            "namespaceUri": self.namespaceUri,
            "exportVersion": self.exportVersion,
        }


@dataclass(frozen=True)
class Snapshot:
    id: str
    role: str
    sourceFiles: list[str] = field(default_factory=list)
    sourceProfiles: list[SourceProfile] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.role not in SNAPSHOT_ROLES:
            raise ValueError(f"Unsupported snapshot role: {self.role}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "sourceFiles": self.sourceFiles,
            "sourceProfiles": [profile.to_dict() for profile in self.sourceProfiles],
        }


@dataclass
class GraphNode:
    id: str
    label: str
    type: str
    sourceFile: str
    xmlPath: str
    rawXml: str
    canonicalKey: str = ""
    snapshotId: str = "configuration"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in NODE_TYPES:
            raise ValueError(f"Unsupported graph node type: {self.type}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "canonicalKey": self.canonicalKey,
            "snapshotId": self.snapshotId,
            "label": self.label,
            "type": self.type,
            "sourceFile": self.sourceFile,
            "xmlPath": self.xmlPath,
            "rawXml": self.rawXml,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GraphLink:
    source: str
    target: str
    relationship: str
    confidence: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if self.relationship not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unsupported graph relationship: {self.relationship}")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Unsupported confidence level: {self.confidence}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ValidationFinding:
    id: str
    code: str
    severity: str
    snapshotId: str
    nodeIds: tuple[str, ...]
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in FINDING_SEVERITIES:
            raise ValueError(f"Unsupported finding severity: {self.severity}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "severity": self.severity,
            "snapshotId": self.snapshotId,
            "nodeIds": list(self.nodeIds),
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class MigrationRiskFactor:
    code: str
    severity: str
    message: str
    weight: float
    nodeIds: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.severity not in MIGRATION_RISK_SEVERITIES:
            raise ValueError(
                f"Unsupported migration risk severity: {self.severity}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "weight": self.weight,
            "nodeIds": list(self.nodeIds),
        }


@dataclass
class MigrationRiskReport:
    score: float
    factors: list[MigrationRiskFactor] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "factors": [factor.to_dict() for factor in self.factors],
        }


@dataclass(frozen=True)
class GraphProvenance:
    origin: str = "xml"
    fileName: str | None = None

    def __post_init__(self) -> None:
        if self.origin not in GRAPH_PROVENANCE_ORIGINS:
            raise ValueError(f"Unsupported graph provenance origin: {self.origin}")
        if self.origin == "xml" and self.fileName is not None:
            raise ValueError("XML graph provenance must not include a JSON filename.")
        if self.origin == "imported" and not self.fileName:
            raise ValueError("Imported graph provenance requires a JSON filename.")

    def to_dict(self) -> dict[str, Any]:
        return {"origin": self.origin, "fileName": self.fileName}


@dataclass(frozen=True)
class FindingWaiver:
    findingId: str
    reason: str
    reviewer: str
    createdAt: str = ""
    expiresAt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "findingId": self.findingId,
            "reason": self.reason,
            "reviewer": self.reviewer,
            "createdAt": self.createdAt,
            "expiresAt": self.expiresAt,
        }


@dataclass
class GraphDocument:
    snapshots: list[Snapshot] = field(default_factory=list)
    nodes: list[GraphNode] = field(default_factory=list)
    links: list[GraphLink] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)
    waivers: list[FindingWaiver] = field(default_factory=list)
    migrationRisk: MigrationRiskReport | None = None
    schemaVersion: str = GRAPH_SCHEMA_VERSION
    topologyMode: str = "core"
    provenance: GraphProvenance = field(default_factory=GraphProvenance)
    asOfDate: str | None = None

    def __post_init__(self) -> None:
        if self.topologyMode not in TOPOLOGY_MODES:
            raise ValueError(f"Unsupported topology mode: {self.topologyMode}")

    def to_dict(self) -> dict[str, Any]:
        data = {
            "schemaVersion": self.schemaVersion,
            "topologyMode": self.topologyMode,
            "provenance": self.provenance.to_dict(),
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "nodes": [node.to_dict() for node in self.nodes],
            "links": [link.to_dict() for link in self.links],
            "findings": [finding.to_dict() for finding in self.findings],
        }
        if self.asOfDate is not None:
            data["asOfDate"] = self.asOfDate
        if self.waivers:
            data["waivers"] = [waiver.to_dict() for waiver in self.waivers]
        if self.migrationRisk:
            data["migrationRisk"] = self.migrationRisk.to_dict()
        return data



@dataclass
class ConversionResult:
    ok: bool
    html: str = ""
    outputFile: str = ""
    variant: str = ""
    error: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    inputFiles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "html": self.html,
            "outputFile": self.outputFile,
            "variant": self.variant,
            "error": self.error,
            "findings": self.findings,
            "inputFiles": self.inputFiles,
        }


@dataclass
class AppError:
    message: str
    code: str = "app_error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.message, "code": self.code, "details": self.details}


class SummaryRequest(BaseModel):
    nodeId: str | None = None
    id: str | None = None
    label: str = ""
    type: str = ""
    sourceFile: str | None = ""
    xmlPath: str | None = ""
    rawXml: str | None = ""
    metadata: dict[str, Any] | None = Field(default_factory=dict)
    associatedPlans: list[str] | None = Field(default_factory=list)
    associatedPlanComponents: list[str] | None = Field(default_factory=list)
    associatedRules: list[str] | None = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def populate_node_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("nodeId") and data.get("id"):
                data["nodeId"] = data["id"]
        return data


class SummaryResponse(BaseModel):
    summary: str
    text: str = ""
    provider: str
    model: str = ""
    timestamp: str = ""
    source_identifiers: list[str] = Field(default_factory=list)
    disclaimer: str = "This documentation was generated by AI and requires human review."


@dataclass
class DifferenceDetail:
    field: str
    baseline: Any
    candidate: Any
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "baseline": self.baseline,
            "candidate": self.candidate,
            "description": self.description,
        }


@dataclass
class ChangedObjectRecord:
    type: str
    label: str
    canonicalKey: str
    differences: list[DifferenceDetail]
    summary: str
    sourceFile: str = ""
    candidateSourceFile: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "label": self.label,
            "canonicalKey": self.canonicalKey,
            "differences": [diff.to_dict() for diff in self.differences],
            "summary": self.summary,
            "sourceFile": self.sourceFile,
            "candidateSourceFile": self.candidateSourceFile,
            "metadata": self.metadata,
        }


@dataclass
class ObjectRecord:
    type: str
    label: str
    canonicalKey: str
    sourceFile: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    containment: list[str] = field(default_factory=list)
    references: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "label": self.label,
            "canonicalKey": self.canonicalKey,
            "sourceFile": self.sourceFile,
            "metadata": self.metadata,
            "containment": self.containment,
            "references": self.references,
        }


@dataclass
class ComparisonSummary:
    totalAdded: int
    totalRemoved: int
    totalChanged: int
    totalUnchanged: int
    byType: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "totalAdded": self.totalAdded,
            "totalRemoved": self.totalRemoved,
            "totalChanged": self.totalChanged,
            "totalUnchanged": self.totalUnchanged,
            "byType": self.byType,
        }


@dataclass
class ComparisonResult:
    ok: bool
    baselineFile: str = ""
    candidateFile: str = ""
    summary: ComparisonSummary = field(default_factory=lambda: ComparisonSummary(0, 0, 0, 0))
    added: list[ObjectRecord] = field(default_factory=list)
    removed: list[ObjectRecord] = field(default_factory=list)
    changed: list[ChangedObjectRecord] = field(default_factory=list)
    unchanged: list[ObjectRecord] = field(default_factory=list)
    error: str = ""
    asOfDate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "ok": self.ok,
            "baselineFile": self.baselineFile,
            "candidateFile": self.candidateFile,
            "summary": self.summary.to_dict(),
            "added": [item.to_dict() for item in self.added],
            "removed": [item.to_dict() for item in self.removed],
            "changed": [item.to_dict() for item in self.changed],
            "unchanged": [item.to_dict() for item in self.unchanged],
            "error": self.error,
        }
        if self.asOfDate is not None:
            data["asOfDate"] = self.asOfDate
        return data

