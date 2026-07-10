"""Graph object extractor framework."""

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionBatch,
    ExtractionContext,
    ObjectCandidate,
    ObjectExtractor,
    ReferenceCandidate,
)
from sap_im_config_graph_explorer.object_extractors.auxiliary import (
    AUXILIARY_EXTRACTORS,
    AuxiliaryObjectExtractor,
)
from sap_im_config_graph_explorer.object_extractors.formula import (
    FORMULA_EXTRACTORS,
    FormulaExtractor,
)
from sap_im_config_graph_explorer.object_extractors.node_factory import NodeFactory
from sap_im_config_graph_explorer.object_extractors.plans import (
    PLAN_EXTRACTORS,
    PlanComponentExtractor,
    PlanExtractor,
)
from sap_im_config_graph_explorer.object_extractors.primary import (
    PRIMARY_EXTRACTORS,
    PrimaryObjectExtractor,
)
from sap_im_config_graph_explorer.object_extractors.registry import ExtractorRegistry
from sap_im_config_graph_explorer.object_extractors.rules import (
    RULE_EXTRACTORS,
    CreditRuleExtractor,
    DepositRuleExtractor,
    FallbackRuleExtractor,
    IncentiveRuleExtractor,
    MeasurementRuleExtractor,
)


DEFAULT_EXTRACTORS = (
    *PLAN_EXTRACTORS,
    *RULE_EXTRACTORS,
    *FORMULA_EXTRACTORS,
    *PRIMARY_EXTRACTORS,
    *AUXILIARY_EXTRACTORS,
)


def default_registry() -> ExtractorRegistry:
    return ExtractorRegistry(DEFAULT_EXTRACTORS)


__all__ = [
    "AUXILIARY_EXTRACTORS",
    "AuxiliaryObjectExtractor",
    "CreditRuleExtractor",
    "DEFAULT_EXTRACTORS",
    "DepositRuleExtractor",
    "ExtractionBatch",
    "ExtractionContext",
    "ExtractorRegistry",
    "FallbackRuleExtractor",
    "FORMULA_EXTRACTORS",
    "FormulaExtractor",
    "IncentiveRuleExtractor",
    "MeasurementRuleExtractor",
    "NodeFactory",
    "ObjectCandidate",
    "ObjectExtractor",
    "PLAN_EXTRACTORS",
    "PRIMARY_EXTRACTORS",
    "PlanComponentExtractor",
    "PlanExtractor",
    "PrimaryObjectExtractor",
    "ReferenceCandidate",
    "RULE_EXTRACTORS",
    "default_registry",
]
