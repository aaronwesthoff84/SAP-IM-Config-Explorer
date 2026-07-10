"""Graph object extractor framework."""

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionBatch,
    ExtractionContext,
    ObjectCandidate,
    ObjectExtractor,
    ReferenceCandidate,
)
from sap_im_config_graph_explorer.object_extractors.node_factory import NodeFactory
from sap_im_config_graph_explorer.object_extractors.registry import ExtractorRegistry


__all__ = [
    "ExtractionBatch",
    "ExtractionContext",
    "ExtractorRegistry",
    "NodeFactory",
    "ObjectCandidate",
    "ObjectExtractor",
    "ReferenceCandidate",
]
