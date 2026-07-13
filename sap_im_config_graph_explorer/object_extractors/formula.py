from __future__ import annotations

from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionBatch,
    ExtractionContext,
    ObjectCandidate,
)
from sap_im_config_graph_explorer.object_extractors.common import (
    infer_label,
    normalized_dates,
    reference_candidates,
)


class FormulaExtractor:
    def matches(self, element: ET.Element) -> bool:
        return element.tag.upper() == "FORMULA"

    def extract(
        self, element: ET.Element, context: ExtractionContext
    ) -> ExtractionBatch:
        label = infer_label(element)
        if not label:
            return ExtractionBatch()

        metadata = normalized_dates(element)
        return_type = element.get("RETURN_TYPE")
        if return_type and return_type.strip():
            metadata["returnType"] = return_type.strip()
        description = element.get("DESCRIPTION")
        if description and description.strip():
            metadata["description"] = description.strip()
        metadata["expressionTags"] = _ordered_descendant_tags(element)

        return ExtractionBatch(
            objects=[
                ObjectCandidate(
                    element=element,
                    node_type="Formula",
                    label=label,
                    metadata=metadata,
                )
            ],
            references=reference_candidates(element, context),
        )


def _ordered_descendant_tags(element: ET.Element) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for descendant in element.iter():
        if descendant is element:
            continue
        tag = descendant.tag.upper()
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


FORMULA_EXTRACTORS = [FormulaExtractor()]
