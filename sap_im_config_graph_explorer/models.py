from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GRAPH_SCHEMA_VERSION = "1.0"
SNAPSHOT_ROLES = {"configuration", "non_production", "production"}
FINDING_SEVERITIES = {"error", "warning", "info"}

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


@dataclass(frozen=True)
class Snapshot:
    id: str
    role: str
    sourceFiles: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.role not in SNAPSHOT_ROLES:
            raise ValueError(f"Unsupported snapshot role: {self.role}")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "role": self.role, "sourceFiles": self.sourceFiles}


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


@dataclass
class GraphDocument:
    snapshots: list[Snapshot] = field(default_factory=list)
    nodes: list[GraphNode] = field(default_factory=list)
    links: list[GraphLink] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)
    schemaVersion: str = GRAPH_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schemaVersion,
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "nodes": [node.to_dict() for node in self.nodes],
            "links": [link.to_dict() for link in self.links],
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass
class ConversionResult:
    ok: bool
    html: str = ""
    outputFile: str = ""
    variant: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "html": self.html,
            "outputFile": self.outputFile,
            "variant": self.variant,
            "error": self.error,
        }


@dataclass
class AppError:
    message: str
    code: str = "app_error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.message, "code": self.code, "details": self.details}
