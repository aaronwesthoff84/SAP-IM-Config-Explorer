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


CREDIT_TYPES = {"DIRECT_TRANSACTION_CREDIT", "ROLLUP_TRANSACTION_CREDIT"}
MEASUREMENT_TYPES = {"PRIMARY_MEASUREMENT", "SECONDARY_MEASUREMENT"}
INCENTIVE_TYPES = {"BULK_COMMISSION", "COMMISSION"}
DEPOSIT_TYPES = {"DEPOSIT", "DETAIL_DEPOSIT"}

_DEDICATED_TYPES = CREDIT_TYPES | MEASUREMENT_TYPES | INCENTIVE_TYPES | DEPOSIT_TYPES


def _normalized_rule_subtype(element: ET.Element) -> str:
    return (element.get("TYPE") or "").strip().upper()


class _RuleExtractor:
    family = "other"
    rule_subtypes: set[str] = set()

    def matches(self, element: ET.Element) -> bool:
        return (
            element.tag.upper() == "RULE"
            and _normalized_rule_subtype(element) in self.rule_subtypes
        )

    def extract(
        self, element: ET.Element, context: ExtractionContext
    ) -> ExtractionBatch:
        label = infer_label(element)
        if not label:
            return ExtractionBatch()

        metadata = {
            "ruleFamily": self.family,
            "ruleSubtype": element.get("TYPE") or "",
            **normalized_dates(element),
        }
        description = element.get("DESCRIPTION")
        if description and description.strip():
            metadata["description"] = description.strip()

        return ExtractionBatch(
            objects=[
                ObjectCandidate(
                    element=element,
                    node_type="Rule",
                    label=label,
                    metadata=metadata,
                )
            ],
            references=reference_candidates(element, context),
        )


class CreditRuleExtractor(_RuleExtractor):
    family = "credit"
    rule_subtypes = CREDIT_TYPES


class MeasurementRuleExtractor(_RuleExtractor):
    family = "measurement"
    rule_subtypes = MEASUREMENT_TYPES


class IncentiveRuleExtractor(_RuleExtractor):
    family = "incentive"
    rule_subtypes = INCENTIVE_TYPES


class DepositRuleExtractor(_RuleExtractor):
    family = "deposit"
    rule_subtypes = DEPOSIT_TYPES


class FallbackRuleExtractor(_RuleExtractor):
    def matches(self, element: ET.Element) -> bool:
        return (
            element.tag.upper() == "RULE"
            and _normalized_rule_subtype(element) not in _DEDICATED_TYPES
        )


RULE_EXTRACTORS = [
    CreditRuleExtractor(),
    MeasurementRuleExtractor(),
    IncentiveRuleExtractor(),
    DepositRuleExtractor(),
    FallbackRuleExtractor(),
]
