from __future__ import annotations

from collections.abc import Iterable

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionBatch,
    ExtractionContext,
    ObjectExtractor,
)


class ExtractorRegistry:
    def __init__(self, extractors: Iterable[ObjectExtractor] = ()) -> None:
        self.extractors = list(extractors)

    def register(self, extractor: ObjectExtractor, prepend: bool = False) -> None:
        if prepend:
            self.extractors.insert(0, extractor)
        else:
            self.extractors.append(extractor)

    def extract(self, context: ExtractionContext) -> ExtractionBatch:
        combined = ExtractionBatch()
        for element in context.document.root.iter():
            for extractor in self.extractors:
                if extractor.matches(element):
                    extracted = extractor.extract(element, context)
                    combined.objects.extend(extracted.objects)
                    combined.references.extend(extracted.references)
                    break
        return combined
