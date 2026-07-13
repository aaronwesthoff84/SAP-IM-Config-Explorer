from __future__ import annotations

from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionBatch,
    ExtractionContext,
    ObjectCandidate,
    ReferenceCandidate,
)
from sap_im_config_graph_explorer.object_extractors.common import (
    infer_label,
    normalized_dates,
)


def _metadata(element: ET.Element) -> dict[str, str]:
    metadata = normalized_dates(element)
    description = (element.get("DESCRIPTION") or "").strip()
    if description:
        metadata["description"] = description
    return metadata


def _descendant_references(
    owner: ET.Element,
    reference_tag: str,
    expected_type: str,
    relationship: str,
) -> list[ReferenceCandidate]:
    references: list[ReferenceCandidate] = []
    for descendant in owner.iter():
        if descendant.tag.upper() != reference_tag:
            continue
        value = (
            descendant.get("NAME")
            or descendant.get("ID")
            or (descendant.text or "")
        ).strip()
        if not value:
            continue
        references.append(
            ReferenceCandidate(
                source_element=owner,
                value=value,
                hint=reference_tag,
                origin=f"tag:{descendant.tag}",
                expected_type=expected_type,
                relationship=relationship,
                reverse=True,
            )
        )
    return references


class PlanExtractor:
    def matches(self, element: ET.Element) -> bool:
        return element.tag.upper() == "PLAN"

    def extract(
        self, element: ET.Element, context: ExtractionContext
    ) -> ExtractionBatch:
        label = infer_label(element)
        if not label:
            return ExtractionBatch()
        return ExtractionBatch(
            objects=[
                ObjectCandidate(
                    element=element,
                    node_type="Plan",
                    label=label,
                    metadata=_metadata(element),
                )
            ],
            references=_descendant_references(
                element,
                "COMPONENT_REF",
                "PlanComponent",
                "belongs_to_plan",
            ),
        )


class PlanComponentExtractor:
    def matches(self, element: ET.Element) -> bool:
        return element.tag.upper() in {"PLAN_COMPONENT", "PLANCOMPONENT"}

    def extract(
        self, element: ET.Element, context: ExtractionContext
    ) -> ExtractionBatch:
        label = infer_label(element)
        if not label:
            return ExtractionBatch()
        return ExtractionBatch(
            objects=[
                ObjectCandidate(
                    element=element,
                    node_type="PlanComponent",
                    label=label,
                    metadata=_metadata(element),
                )
            ],
            references=_descendant_references(
                element,
                "RULE_REF",
                "Rule",
                "belongs_to_plan_component",
            ),
        )


PLAN_EXTRACTORS = [PlanExtractor(), PlanComponentExtractor()]
