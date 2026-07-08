from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


NODE_TYPES = {
    "Rule",
    "Formula",
    "Classifier",
    "LookupTable",
    "Plan",
    "Pipeline",
    "Stage",
    "EventType",
    "CreditType",
    "DepositType",
    "Calendar",
    "Period",
    "CustomObject",
    "Report",
    "Integration",
    "ProcessingUnit",
    "Other",
}

RELATIONSHIP_TYPES = {
    "uses_formula",
    "uses_lookup",
    "uses_classifier",
    "belongs_to_plan",
    "runs_in_pipeline",
    "uses_event_type",
    "outputs_credit_type",
    "feeds_deposit",
    "depends_on_period",
    "references_custom_object",
    "references_report",
    "references_integration",
    "parent_child",
    "unknown_reference",
}

CONFIDENCE_LEVELS = {"high", "medium", "low"}


@dataclass
class GraphNode:
    id: str
    label: str
    type: str
    sourceFile: str
    xmlPath: str
    rawXml: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class GraphDocument:
    nodes: list[GraphNode] = field(default_factory=list)
    links: list[GraphLink] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "links": [link.to_dict() for link in self.links],
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
