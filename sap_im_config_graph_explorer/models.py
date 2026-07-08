from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
