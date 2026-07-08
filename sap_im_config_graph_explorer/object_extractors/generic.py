from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import GraphNode
from sap_im_config_graph_explorer.xml_loader import XmlDocument


KNOWN_TAG_TYPES = {
    "FIXED_VALUE": "FixedValue",
    "FORMULA": "Formula",
    "MDLT": "LookupTable",
    "MD_LOOKUP_TABLE": "LookupTable",
    "LOOKUP_TABLE": "LookupTable",
    "LOOKUPTABLE": "LookupTable",
    "QUOTA": "Quota",
    "RATE_TABLE": "RateTable",
    "RATETABLE": "RateTable",
    "TERRITORY": "Territory",
    "VARIABLE": "Variable",
    "RULE": "Rule",
    "PLAN": "Plan",
    "PLAN_COMPONENT": "PlanComponent",
    "PLANCOMPONENT": "PlanComponent",
    "EVENT_TYPE": "EventType",
    "CREDIT_TYPE": "CreditType",
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

REFERENCE_TAG_PATTERN = re.compile(r"(^|_)REF(S)?$")


class GenericObjectExtractor:
    def __init__(self) -> None:
        self.id_counts: dict[str, int] = {}

    def reset(self) -> None:
        self.id_counts.clear()

    def extract(self, document: XmlDocument) -> tuple[list[GraphNode], dict[int, str]]:
        nodes: list[GraphNode] = []
        node_id_by_element: dict[int, str] = {}

        for element in document.root.iter():
            node_type = infer_node_type(element)
            if node_type is None:
                continue
            label = infer_label(element)
            if not label:
                continue
            xml_path = document.path_by_element[id(element)]
            source_id = element.get("ID") or element.get("OBJECT_ID") or element.get("SEQUENCE")
            base_key = source_id or label or xml_path
            base_id = slug(f"{document.source_file}:{node_type}:{base_key}")
            self.id_counts[base_id] = self.id_counts.get(base_id, 0) + 1
            node_id = base_id if self.id_counts[base_id] == 1 else f"{base_id}--{self.id_counts[base_id]}"
            metadata = {
                "tag": element.tag,
                "attributes": dict(element.attrib),
            }
            if source_id:
                metadata["sourceId"] = source_id
            if self.id_counts[base_id] > 1:
                metadata["duplicateKey"] = base_id
            node = GraphNode(
                id=node_id,
                label=label,
                type=node_type,
                sourceFile=document.source_file,
                xmlPath=xml_path,
                rawXml=trim_raw_xml(element),
                metadata=metadata,
            )
            nodes.append(node)
            node_id_by_element[id(element)] = node.id

        return nodes, node_id_by_element


def infer_node_type(element: ET.Element) -> str | None:
    tag = element.tag.upper()
    if is_reference_only_tag(tag):
        return None
    if tag in KNOWN_TAG_TYPES:
        return KNOWN_TAG_TYPES[tag]
    return infer_type_from_object_hint(element.get("OBJECT_TYPE") or element.get("EXT_TYPE") or "")


def infer_type_from_object_hint(value: str) -> str | None:
    hint = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    if not hint:
        return None
    if "PLAN_COMPONENT" in hint or "PLANCOMPONENT" in hint:
        return "PlanComponent"
    if "FIXED_VALUE" in hint or "FIXEDVALUE" in hint:
        return "FixedValue"
    if "RATE_TABLE" in hint or "RATETABLE" in hint:
        return "RateTable"
    if "LOOKUP" in hint or "MDLT" in hint:
        return "LookupTable"
    if "EARNING_CODE" in hint or "EARNINGCODE" in hint:
        return "EarningCode"
    if "EARNING_GROUP" in hint or "EARNINGGROUP" in hint:
        return "EarningGroup"
    if "BUSINESS_UNIT" in hint or "BUSINESSUNIT" in hint:
        return "BusinessUnit"
    if "PROCESSING_UNIT" in hint or "PROCESSINGUNIT" in hint:
        return "ProcessingUnit"
    if "EVENT_TYPE" in hint or "EVENTTYPE" in hint:
        return "EventType"
    if "CREDIT_TYPE" in hint or "CREDITTYPE" in hint:
        return "CreditType"
    if "TERRITORY" in hint:
        return "Territory"
    if "VARIABLE" in hint:
        return "Variable"
    if "QUOTA" in hint:
        return "Quota"
    if "CALENDAR" in hint:
        return "Calendar"
    if "FORMULA" in hint:
        return "Formula"
    if "RULE" in hint:
        return "Rule"
    if "PLAN" in hint:
        return "Plan"
    return None


def infer_label(element: ET.Element) -> str:
    for attr in ("NAME", "DISPLAY_NAME", "ID", "OBJECT_ID", "CODE", "SEQUENCE"):
        value = element.get(attr)
        if value:
            return value.strip()
    if element.tag.upper() in TEXT_LABEL_TAGS:
        return (element.text or "").strip()
    return ""


def is_reference_only_tag(tag: str) -> bool:
    if tag in {"RULE_REFS", "COMPONENT_REF", "RULE_REF", "MDLT_REF", "STRING_FORMULA_REF"}:
        return True
    return bool(REFERENCE_TAG_PATTERN.search(tag))


def trim_raw_xml(element: ET.Element, limit: int = 4000) -> str:
    raw = ET.tostring(element, encoding="unicode")
    return raw if len(raw) <= limit else raw[:limit] + "\n..."


def slug(value: str) -> str:
    lowered = value.strip().lower()
    slugged = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slugged or "node"
