from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import GraphNode
from sap_im_config_graph_explorer.xml_loader import XmlDocument


KNOWN_TAG_TYPES = {
    "PLAN": "Plan",
    "RULE": "Rule",
    "FORMULA": "Formula",
    "MD_LOOKUP_TABLE": "LookupTable",
    "LOOKUP_TABLE": "LookupTable",
    "TERRITORY": "Classifier",
    "CLASSIFIER": "Classifier",
    "PIPELINE": "Pipeline",
    "STAGE": "Stage",
    "PIPELINE_STAGE": "Stage",
    "EVENT_TYPE": "EventType",
    "CREDIT_TYPE": "CreditType",
    "DEPOSIT_TYPE": "DepositType",
    "CALENDAR": "Calendar",
    "PERIOD": "Period",
    "REPORT": "Report",
    "INTEGRATION": "Integration",
    "INTEGRATION_MAPPING": "Integration",
    "PROCESSING_UNIT": "ProcessingUnit",
    "VARIABLE": "CustomObject",
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
    object_type = (
        element.get("OBJECT_TYPE")
        or element.get("TYPE")
        or element.get("CLASS")
        or element.get("EXT_TYPE")
        or ""
    ).upper()
    if "PLAN" in object_type:
        return "Plan"
    if "RULE" in object_type:
        return "Rule"
    if "FORMULA" in object_type:
        return "Formula"
    if "LOOKUP" in object_type or "MDLT" in object_type:
        return "LookupTable"
    if "CLASSIFIER" in object_type or "TERRITORY" in object_type:
        return "Classifier"
    if "PIPELINE" in object_type:
        return "Pipeline"
    if "STAGE" in object_type:
        return "Stage"
    if "EVENT" in object_type:
        return "EventType"
    if "CREDIT" in object_type:
        return "CreditType"
    if "DEPOSIT" in object_type:
        return "DepositType"
    if "CALENDAR" in object_type:
        return "Calendar"
    if "PERIOD" in object_type:
        return "Period"
    if "REPORT" in object_type:
        return "Report"
    if "INTEGRATION" in object_type or "MAPPING" in object_type:
        return "Integration"
    if "PROCESSING" in object_type:
        return "ProcessingUnit"
    if has_identifier(element):
        return "Other"
    return None


def infer_label(element: ET.Element) -> str:
    for attr in ("NAME", "DISPLAY_NAME", "ID", "OBJECT_ID", "CODE", "SEQUENCE"):
        value = element.get(attr)
        if value:
            return value.strip()
    if element.tag.upper() in {"CREDIT_TYPE", "DEPOSIT_TYPE", "EVENT_TYPE", "PERIOD"}:
        return (element.text or "").strip()
    return ""


def has_identifier(element: ET.Element) -> bool:
    if any(element.get(attr) for attr in ("NAME", "DISPLAY_NAME", "ID", "OBJECT_ID", "CODE")):
        return True
    return any(key.endswith("_NAME") or key.endswith("_ID") for key in element.attrib)


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
