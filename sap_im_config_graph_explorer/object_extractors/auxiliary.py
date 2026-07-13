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
)


AUXILIARY_TAG_TYPES = {
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


class AuxiliaryObjectExtractor:
    def matches(self, element: ET.Element) -> bool:
        tag = element.tag.upper()
        return not tag.endswith("_REF") and tag in AUXILIARY_TAG_TYPES

    def extract(
        self, element: ET.Element, context: ExtractionContext
    ) -> ExtractionBatch:
        label = infer_label(element) or (element.text or "").strip()
        if not label:
            return ExtractionBatch()
        return ExtractionBatch(
            objects=[
                ObjectCandidate(
                    element=element,
                    node_type=AUXILIARY_TAG_TYPES[element.tag.upper()],
                    label=label,
                    metadata=normalized_dates(element),
                )
            ]
        )


AUXILIARY_EXTRACTORS = [AuxiliaryObjectExtractor()]
