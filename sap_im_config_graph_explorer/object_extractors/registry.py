from __future__ import annotations

from collections.abc import Iterable
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionBatch,
    ExtractionContext,
    ObjectExtractor,
)


def _precalculate_document_caches(document, context: ExtractionContext) -> None:
    """Perform a single linear DFS traversal of the XML tree to precalculate

    all mappings and references for Plan, PlanComponent, Rule, and Formula objects.
    This avoids nested .iter() loops in extractors, improving performance from O(N^2) to O(N).
    """
    _plan_component_refs: dict[int, list] = {}
    _component_rule_refs: dict[int, list] = {}
    _rule_formula_references: dict[int, list] = {}
    _formula_expression_tags: dict[int, list[str]] = {}

    seen_refs: dict[int, set[tuple[str, str]]] = {}
    formula_seen_tags: dict[int, set[str]] = {}

    from sap_im_config_graph_explorer.object_extractors.base import ReferenceCandidate
    from sap_im_config_graph_explorer.object_extractors.common import (
        NON_REFERENCE_NAME_ATTRIBUTES,
        REFERENCE_ATTRIBUTE_SUFFIXES,
        TEXT_REFERENCE_TYPES,
        expected_type_for_hint,
        normalize_hint,
        relationship_for_reference,
    )

    def get_single_el_refs(el: ET.Element, path: str) -> list[tuple[str, str, str, str | None]]:
        results = []
        tag = el.tag.upper()
        if tag.endswith("_REF") or tag == "COMPONENT_REF":
            val = el.get("NAME") or el.get("ID") or (el.text or "")
            results.append((val, tag, path, expected_type_for_hint(tag)))
        else:
            for attribute, value in el.attrib.items():
                hint = attribute.upper()
                if hint in NON_REFERENCE_NAME_ATTRIBUTES or not hint.endswith(
                    REFERENCE_ATTRIBUTE_SUFFIXES
                ):
                    continue
                results.append(
                    (
                        value,
                        hint,
                        f"{path}/@{attribute}",
                        expected_type_for_hint(hint),
                    )
                )

            text_ref_type = TEXT_REFERENCE_TYPES.get(tag)
            if text_ref_type:
                results.append(
                    (
                        el.text or "",
                        tag,
                        f"{path}/text()",
                        text_ref_type,
                    )
                )
        return results

    stack = [(document.root, None, None, None, None)]
    while stack:
        el, plan, comp, rule, formula = stack.pop()
        tag = el.tag.upper()
        el_id = id(el)
        path = document.path_by_element.get(el_id, f"tag:{el.tag}")

        # Next owners
        if tag == "PLAN":
            next_plan = el
            _plan_component_refs[el_id] = []
        else:
            next_plan = plan

        if tag in {"PLAN_COMPONENT", "PLANCOMPONENT"}:
            next_component = el
            _component_rule_refs[el_id] = []
        else:
            next_component = comp

        if tag == "RULE":
            next_rule = el
            _rule_formula_references[el_id] = []
            seen_refs[el_id] = set()
        else:
            next_rule = rule

        if tag == "FORMULA":
            next_formula = el
            _rule_formula_references[el_id] = []
            seen_refs[el_id] = set()
            _formula_expression_tags[el_id] = []
            formula_seen_tags[el_id] = set()
        else:
            next_formula = formula

        # References under PLAN
        if plan is not None and tag == "COMPONENT_REF":
            value = (el.get("NAME") or el.get("ID") or (el.text or "")).strip()
            if value:
                _plan_component_refs[id(plan)].append(
                    ReferenceCandidate(
                        source_element=plan,
                        value=value,
                        hint="COMPONENT_REF",
                        origin=f"tag:{el.tag}",
                        expected_type="PlanComponent",
                        relationship="belongs_to_plan",
                        reverse=True,
                    )
                )

        # References under PLAN_COMPONENT
        if comp is not None and tag == "RULE_REF":
            value = (el.get("NAME") or el.get("ID") or (el.text or "")).strip()
            if value:
                _component_rule_refs[id(comp)].append(
                    ReferenceCandidate(
                        source_element=comp,
                        value=value,
                        hint="RULE_REF",
                        origin=f"tag:{el.tag}",
                        expected_type="Rule",
                        relationship="belongs_to_plan_component",
                        reverse=True,
                    )
                )

        # References under RULE
        if next_rule is not None:
            rule_id = id(next_rule)
            for val, hnt, orig, exp_type in get_single_el_refs(el, path):
                val_stripped = val.strip()
                if not val_stripped or exp_type is None:
                    continue
                sem_type = exp_type or normalize_hint(hnt)
                key = (val_stripped.casefold(), sem_type)
                rule_seen = seen_refs[rule_id]
                if key not in rule_seen:
                    rule_seen.add(key)
                    _rule_formula_references[rule_id].append(
                        ReferenceCandidate(
                            source_element=next_rule,
                            value=val_stripped,
                            hint=hnt,
                            origin=orig,
                            expected_type=exp_type,
                            relationship=relationship_for_reference(hnt, exp_type),
                        )
                    )

        # References under FORMULA
        if next_formula is not None:
            formula_id = id(next_formula)
            for val, hnt, orig, exp_type in get_single_el_refs(el, path):
                val_stripped = val.strip()
                if not val_stripped or exp_type is None:
                    continue
                sem_type = exp_type or normalize_hint(hnt)
                key = (val_stripped.casefold(), sem_type)
                formula_seen = seen_refs[formula_id]
                if key not in formula_seen:
                    formula_seen.add(key)
                    _rule_formula_references[formula_id].append(
                        ReferenceCandidate(
                            source_element=next_formula,
                            value=val_stripped,
                            hint=hnt,
                            origin=orig,
                            expected_type=exp_type,
                            relationship=relationship_for_reference(hnt, exp_type),
                        )
                    )

            if formula is not None:
                parent_formula_id = id(formula)
                formula_tags = _formula_expression_tags[parent_formula_id]
                formula_tags_seen = formula_seen_tags[parent_formula_id]
                if tag not in formula_tags_seen:
                    formula_tags_seen.add(tag)
                    formula_tags.append(tag)

        # Push children to stack in reverse
        for child in reversed(el):
            stack.append((child, next_plan, next_component, next_rule, next_formula))

    document._plan_component_refs = _plan_component_refs
    document._component_rule_refs = _component_rule_refs
    document._rule_formula_references = _rule_formula_references
    document._formula_expression_tags = _formula_expression_tags


class ExtractorRegistry:
    def __init__(self, extractors: Iterable[ObjectExtractor] = ()) -> None:
        self.extractors = list(extractors)

    def register(self, extractor: ObjectExtractor, prepend: bool = False) -> None:
        if prepend:
            self.extractors.insert(0, extractor)
        else:
            self.extractors.append(extractor)

    def extract(self, context: ExtractionContext) -> ExtractionBatch:
        if not hasattr(context.document, "_plan_component_refs"):
            _precalculate_document_caches(context.document, context)

        combined = ExtractionBatch()
        for element in context.document.root.iter():
            for extractor in self.extractors:
                if extractor.matches(element):
                    extracted = extractor.extract(element, context)
                    combined.objects.extend(extracted.objects)
                    combined.references.extend(extracted.references)
                    break
        return combined
