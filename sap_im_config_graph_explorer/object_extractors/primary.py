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


PRIMARY_TAG_TYPES = {
    "FIXED_VALUE": "FixedValue",
    "MDLT": "LookupTable",
    "MD_LOOKUP_TABLE": "LookupTable",
    "LOOKUP_TABLE": "LookupTable",
    "LOOKUPTABLE": "LookupTable",
    "QUOTA": "Quota",
    "RATE_TABLE": "RateTable",
    "RATETABLE": "RateTable",
    "TERRITORY": "Territory",
    "VARIABLE": "Variable",
}


class PrimaryObjectExtractor:
    def matches(self, element: ET.Element) -> bool:
        tag = element.tag.upper()
        return not tag.endswith("_REF") and tag in PRIMARY_TAG_TYPES

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
                    node_type=PRIMARY_TAG_TYPES[element.tag.upper()],
                    label=label,
                    metadata=normalized_dates(element),
                )
            ]
        )


PRIMARY_EXTRACTORS = [PrimaryObjectExtractor()]
