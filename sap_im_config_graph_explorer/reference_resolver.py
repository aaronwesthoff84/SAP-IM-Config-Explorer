from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import GraphLink, GraphNode
from sap_im_config_graph_explorer.xml_loader import XmlDocument


REFERENCE_ATTRS = {
    "NAME",
    "PLAN_NAME",
    "PLANCOMPONENT_NAME",
    "PLAN_COMPONENT_NAME",
    "OWNER_NAME",
    "TARGET_NAME",
    "SOURCE_NAME",
    "FIXED_VALUE_NAME",
    "FORMULA_NAME",
    "RULE_NAME",
    "LOOKUP_TABLE_NAME",
    "MDLT_NAME",
    "QUOTA_NAME",
    "RATE_TABLE_NAME",
    "RATETABLE_NAME",
    "TERRITORY_NAME",
    "VARIABLE_NAME",
    "EVENT_TYPE_NAME",
    "CREDIT_TYPE_NAME",
    "EARNING_CODE_NAME",
    "EARNING_GROUP_NAME",
    "BUSINESS_UNIT_NAME",
    "PROCESSING_UNIT_NAME",
    "CALENDAR_NAME",
}

TEXT_REFERENCE_TAGS = {
    "EVENT_TYPE",
    "CREDIT_TYPE",
    "EARNING_CODE",
    "EARNING_GROUP",
    "BUSINESS_UNIT",
    "PROCESSING_UNIT",
    "CALENDAR",
}


@dataclass
class ReferenceResolver:
    documents: list[XmlDocument]
    nodes: list[GraphNode]
    node_id_by_element: dict[int, str]

    def build_links(self) -> list[GraphLink]:
        links: list[GraphLink] = []
        seen: set[tuple[str, str, str, str]] = set()
        index = self._build_index()
        node_by_id = {node.id: node for node in self.nodes}

        for document in self.documents:
            for element in document.root.iter():
                source_id = self._nearest_source_id(element)
                if not source_id:
                    continue
                for child in list(element):
                    child_id = self.node_id_by_element.get(id(child))
                    if child_id and child_id != source_id:
                        self._append_link(
                            links,
                            seen,
                            source_id,
                            child_id,
                            "parent_child",
                            "high",
                            {"sourceFile": document.source_file},
                        )
                for ref_value, hint, origin in self._references_from_element(element):
                    target = self._resolve_reference(ref_value, hint, index)
                    if target and target.id != source_id:
                        if hint.upper() == "COMPONENT_REF" and node_by_id[source_id].type == "Plan":
                            self._append_link(
                                links,
                                seen,
                                target.id,
                                source_id,
                                "belongs_to_plan",
                                "high",
                                {"reference": ref_value, "origin": origin},
                            )
                            continue
                        self._append_link(
                            links,
                            seen,
                            source_id,
                            target.id,
                            relationship_for_hint(hint, target.type),
                            "high" if hint else "medium",
                            {"reference": ref_value, "origin": origin},
                        )
                    elif self._should_emit_unknown(element, ref_value, hint):
                        unknown_id = f"unknown:{hint or 'reference'}:{ref_value}".lower()
                        self._append_link(
                            links,
                            seen,
                            source_id,
                            unknown_id,
                            "unknown_reference",
                            "low",
                            {"reference": ref_value, "origin": origin},
                        )

        return links

    def _build_index(self) -> dict[str, list[GraphNode]]:
        index: dict[str, list[GraphNode]] = {}
        for node in self.nodes:
            keys = [node.label]
            source_id = node.metadata.get("sourceId")
            if source_id:
                keys.append(str(source_id))
            for key in keys:
                normalized = normalize_ref(key)
                index.setdefault(normalized, []).append(node)
        return index

    def _nearest_source_id(self, element: ET.Element) -> str | None:
        current_path = None
        for document in self.documents:
            current_path = document.path_by_element.get(id(element))
            if current_path:
                break
        if not current_path:
            return self.node_id_by_element.get(id(element))
        best_id = None
        best_len = -1
        for doc_element_id, node_id in self.node_id_by_element.items():
            doc_path = None
            for document in self.documents:
                doc_path = document.path_by_element.get(doc_element_id)
                if doc_path:
                    break
            if doc_path and current_path.startswith(doc_path) and len(doc_path) > best_len:
                best_id = node_id
                best_len = len(doc_path)
        return best_id

    def _references_from_element(self, element: ET.Element) -> list[tuple[str, str, str]]:
        refs: list[tuple[str, str, str]] = []
        tag = element.tag.upper()
        if tag.endswith("_REF") or tag in {"COMPONENT_REF"}:
            value = element.get("NAME") or element.get("ID") or (element.text or "").strip()
            if value:
                refs.append((value, tag, f"tag:{element.tag}"))
        for attr, value in element.attrib.items():
            if not value:
                continue
            upper_attr = attr.upper()
            if upper_attr in REFERENCE_ATTRS or upper_attr.endswith("_REF") or upper_attr.endswith("_PATH"):
                if upper_attr == "NAME" and not tag.endswith("_REF"):
                    continue
                refs.append((value, upper_attr, f"attribute:{attr}"))
        text = (element.text or "").strip()
        if text and tag in TEXT_REFERENCE_TAGS:
            refs.append((text, tag, f"text:{element.tag}"))
        return refs

    def _resolve_reference(
        self, ref_value: str, hint: str, index: dict[str, list[GraphNode]]
    ) -> GraphNode | None:
        candidates = index.get(normalize_ref(ref_value), [])
        if not candidates:
            return None
        preferred_type = preferred_type_for_hint(hint)
        if preferred_type:
            for candidate in candidates:
                if candidate.type == preferred_type:
                    return candidate
        return candidates[0]

    def _should_emit_unknown(self, element: ET.Element, ref_value: str, hint: str) -> bool:
        return bool(ref_value and hint and (hint.endswith("_REF") or hint.endswith("_NAME")))

    def _append_link(
        self,
        links: list[GraphLink],
        seen: set[tuple[str, str, str, str]],
        source: str,
        target: str,
        relationship: str,
        confidence: str,
        metadata: dict[str, str],
    ) -> None:
        key = (source, target, relationship, metadata.get("origin", ""))
        if key in seen:
            return
        seen.add(key)
        links.append(GraphLink(source, target, relationship, confidence, metadata))


def normalize_ref(value: str) -> str:
    return value.strip().lower()


def preferred_type_for_hint(hint: str) -> str | None:
    hint = hint.upper()
    if "COMPONENT" in hint:
        return "PlanComponent"
    if "FIXED" in hint:
        return "FixedValue"
    if "FORMULA" in hint:
        return "Formula"
    if "RATE_TABLE" in hint or "RATETABLE" in hint:
        return "RateTable"
    if "MDLT" in hint or "LOOKUP" in hint:
        return "LookupTable"
    if "QUOTA" in hint:
        return "Quota"
    if "TERRITORY" in hint or "CLASSIFIER" in hint:
        return "Territory"
    if "VARIABLE" in hint:
        return "Variable"
    if "PLAN" in hint:
        return "Plan"
    if "EVENT" in hint:
        return "EventType"
    if "CREDIT" in hint:
        return "CreditType"
    if "EARNING_CODE" in hint or "EARNINGCODE" in hint:
        return "EarningCode"
    if "EARNING_GROUP" in hint or "EARNINGGROUP" in hint:
        return "EarningGroup"
    if "BUSINESS" in hint:
        return "BusinessUnit"
    if "PROCESSING" in hint:
        return "ProcessingUnit"
    if "CALENDAR" in hint:
        return "Calendar"
    return None


def relationship_for_hint(hint: str, target_type: str) -> str:
    hint = hint.upper()
    if target_type == "FixedValue" or "FIXED" in hint:
        return "uses_fixed_value"
    if target_type == "Formula" or "FORMULA" in hint:
        return "uses_formula"
    if target_type == "RateTable" or "RATE_TABLE" in hint or "RATETABLE" in hint:
        return "uses_rate_table"
    if target_type == "LookupTable" or "MDLT" in hint or "LOOKUP" in hint:
        return "uses_lookup"
    if target_type == "Quota" or "QUOTA" in hint:
        return "uses_quota"
    if target_type == "Territory" or "TERRITORY" in hint:
        return "uses_territory"
    if "CLASSIFIER" in hint:
        return "uses_classifier"
    if target_type == "Variable" or "VARIABLE" in hint:
        return "uses_variable"
    if target_type == "PlanComponent" or "COMPONENT" in hint:
        return "belongs_to_plan_component"
    if target_type == "Plan" or "PLAN" in hint:
        return "belongs_to_plan"
    if target_type == "EventType" or "EVENT" in hint:
        return "uses_event_type"
    if target_type == "CreditType" or "CREDIT" in hint:
        return "outputs_credit_type"
    if target_type == "EarningCode" or "EARNING_CODE" in hint or "EARNINGCODE" in hint:
        return "uses_earning_code"
    if target_type == "EarningGroup" or "EARNING_GROUP" in hint or "EARNINGGROUP" in hint:
        return "uses_earning_group"
    if target_type == "BusinessUnit" or "BUSINESS" in hint:
        return "uses_business_unit"
    if target_type == "ProcessingUnit" or "PROCESSING" in hint:
        return "uses_processing_unit"
    if target_type == "Calendar" or "CALENDAR" in hint:
        return "uses_calendar"
    return "unknown_reference"
