from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionContext,
    ReferenceCandidate,
)


TEXT_LABEL_TAGS = {
    "EVENT_TYPE",
    "CREDIT_TYPE",
    "EARNING_CODE",
    "EARNINGCODE",
    "EARNING_GROUP",
    "EARNINGGROUP",
    "BUSINESS_UNIT",
    "BUSINESSUNIT",
    "PROCESSING_UNIT",
    "PROCESSINGUNIT",
    "CALENDAR",
}

REFERENCE_ATTRIBUTE_SUFFIXES = ("_NAME", "_REF", "_PATH")
NON_REFERENCE_NAME_ATTRIBUTES = {"DISPLAY_NAME"}

TEXT_REFERENCE_TYPES = {
    "EVENT_TYPE": "EventType",
    "EVENTTYPE": "EventType",
    "CREDIT_TYPE": "CreditType",
    "CREDITTYPE": "CreditType",
    "EARNING_CODE": "EarningCode",
    "EARNINGCODE": "EarningCode",
    "EARNING_GROUP": "EarningGroup",
    "EARNINGGROUP": "EarningGroup",
    "BUSINESS_UNIT": "BusinessUnit",
    "BUSINESSUNIT": "BusinessUnit",
    "PROCESSING_UNIT": "ProcessingUnit",
    "PROCESSINGUNIT": "ProcessingUnit",
    "CALENDAR": "Calendar",
}

RELATIONSHIP_BY_TYPE = {
    "FixedValue": "uses_fixed_value",
    "Formula": "uses_formula",
    "LookupTable": "uses_lookup",
    "Quota": "uses_quota",
    "RateTable": "uses_rate_table",
    "Territory": "uses_territory",
    "Variable": "uses_variable",
    "Rule": "uses_rule",
    "Plan": "belongs_to_plan",
    "PlanComponent": "belongs_to_plan_component",
    "EventType": "uses_event_type",
    "CreditType": "outputs_credit_type",
    "EarningCode": "uses_earning_code",
    "EarningGroup": "uses_earning_group",
    "BusinessUnit": "uses_business_unit",
    "ProcessingUnit": "uses_processing_unit",
    "Calendar": "uses_calendar",
}


def normalize_identity(value: str) -> str:
    segments = value.split(":")
    return ":".join(
        re.sub(r"[^a-z0-9]+", "-", segment.strip().lower()).strip("-")
        for segment in segments
    )


def infer_label(element: ET.Element) -> str:
    for attribute in ("NAME", "DISPLAY_NAME", "ID", "OBJECT_ID", "CODE", "SEQUENCE"):
        value = element.get(attribute)
        if value:
            return value.strip()
    if element.tag.upper() in TEXT_LABEL_TAGS:
        return (element.text or "").strip()
    return ""


def normalized_dates(element: ET.Element) -> dict[str, str]:
    dates: dict[str, str] = {}
    start = element.get("EFFECTIVE_START_DATE")
    end = element.get("EFFECTIVE_END_DATE")
    if start and start.strip():
        dates["effectiveStartDate"] = start.strip()
    if end and end.strip():
        dates["effectiveEndDate"] = end.strip()
    return dates


def normalize_hint(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def expected_type_for_hint(hint: str) -> str | None:
    normalized = normalize_hint(hint)
    if "PLAN_COMPONENT" in normalized or "PLANCOMPONENT" in normalized:
        return "PlanComponent"
    if "COMPONENT" in normalized:
        return "PlanComponent"
    if "FIXED_VALUE" in normalized or "FIXEDVALUE" in normalized:
        return "FixedValue"
    if "FORMULA" in normalized:
        return "Formula"
    if "RATE_TABLE" in normalized or "RATETABLE" in normalized:
        return "RateTable"
    if "MDLT" in normalized or "LOOKUP" in normalized:
        return "LookupTable"
    if "QUOTA" in normalized:
        return "Quota"
    if "TERRITORY" in normalized or "CLASSIFIER" in normalized:
        return "Territory"
    if "VARIABLE" in normalized:
        return "Variable"
    if "RULE" in normalized:
        return "Rule"
    if "PLAN" in normalized:
        return "Plan"
    if "EVENT" in normalized:
        return "EventType"
    if "CREDIT" in normalized:
        return "CreditType"
    if "EARNING_CODE" in normalized or "EARNINGCODE" in normalized:
        return "EarningCode"
    if "EARNING_GROUP" in normalized or "EARNINGGROUP" in normalized:
        return "EarningGroup"
    if "BUSINESS" in normalized:
        return "BusinessUnit"
    if "PROCESSING" in normalized:
        return "ProcessingUnit"
    if "CALENDAR" in normalized:
        return "Calendar"
    return None


def relationship_for_reference(hint: str, target_type: str | None) -> str:
    normalized = normalize_hint(hint)
    if "CLASSIFIER" in normalized:
        return "uses_classifier"
    if target_type:
        return RELATIONSHIP_BY_TYPE[target_type]
    if "REPORT" in normalized:
        return "references_report"
    if "INTEGRATION" in normalized:
        return "references_integration"
    if "CUSTOM" in normalized:
        return "references_custom_object"
    return "unknown_reference"


def reference_candidates(
    source_element: ET.Element,
    context: ExtractionContext,
    *,
    include_untyped: bool = False,
) -> list[ReferenceCandidate]:
    """Collect unique semantic references owned by one graph object."""

    references: list[ReferenceCandidate] = []
    seen: set[tuple[str, str]] = set()

    def append(value: str, hint: str, origin: str, expected_type: str | None) -> None:
        normalized_value = value.strip()
        if not normalized_value or (expected_type is None and not include_untyped):
            return
        semantic_type = expected_type or normalize_hint(hint)
        key = (normalized_value.casefold(), semantic_type)
        if key in seen:
            return
        seen.add(key)
        references.append(
            ReferenceCandidate(
                source_element=source_element,
                value=normalized_value,
                hint=hint,
                origin=origin,
                expected_type=expected_type,
                relationship=relationship_for_reference(hint, expected_type),
            )
        )

    for reference_element in source_element.iter():
        tag = reference_element.tag.upper()
        path = context.document.path_by_element.get(
            id(reference_element), f"tag:{reference_element.tag}"
        )

        if tag.endswith("_REF") or tag == "COMPONENT_REF":
            value = (
                reference_element.get("NAME")
                or reference_element.get("ID")
                or (reference_element.text or "")
            )
            append(value, tag, path, expected_type_for_hint(tag))
            continue

        for attribute, value in reference_element.attrib.items():
            hint = attribute.upper()
            if hint in NON_REFERENCE_NAME_ATTRIBUTES or not hint.endswith(
                REFERENCE_ATTRIBUTE_SUFFIXES
            ):
                continue
            append(
                value,
                hint,
                f"{path}/@{attribute}",
                expected_type_for_hint(hint),
            )

        text_reference_type = TEXT_REFERENCE_TYPES.get(tag)
        if text_reference_type:
            append(
                reference_element.text or "",
                tag,
                f"{path}/text()",
                text_reference_type,
            )

    return references


def trim_raw_xml(element: ET.Element, limit: int = 4000) -> str:
    raw = ET.tostring(element, encoding="unicode")
    if len(raw) <= limit:
        return raw
    marker = "\n..."
    if limit <= len(marker):
        return raw[: max(0, limit)]
    return raw[: limit - len(marker)] + marker
