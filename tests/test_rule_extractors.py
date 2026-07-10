from pathlib import Path

from sap_im_config_graph_explorer.object_extractors.base import ExtractionContext
from sap_im_config_graph_explorer.object_extractors.node_factory import NodeFactory
from sap_im_config_graph_explorer.object_extractors.registry import ExtractorRegistry
from sap_im_config_graph_explorer.object_extractors.rules import (
    RULE_EXTRACTORS,
    CreditRuleExtractor,
    DepositRuleExtractor,
    FallbackRuleExtractor,
    IncentiveRuleExtractor,
    MeasurementRuleExtractor,
)
from sap_im_config_graph_explorer.xml_loader import load_xml_file, load_xml_text


FIXTURES = Path(__file__).parent / "fixtures"


def _extract_fixture():
    document = load_xml_file(FIXTURES / "rule_families.xml")
    context = ExtractionContext("configuration", "configuration", document)
    return document, context, ExtractorRegistry(RULE_EXTRACTORS).extract(context)


def test_rule_extractors_are_registered_in_specific_to_fallback_order():
    assert [type(extractor) for extractor in RULE_EXTRACTORS] == [
        CreditRuleExtractor,
        MeasurementRuleExtractor,
        IncentiveRuleExtractor,
        DepositRuleExtractor,
        FallbackRuleExtractor,
    ]


def test_rule_family_dispatch_keeps_every_definition_as_an_allowlisted_rule_node():
    _, context, batch = _extract_fixture()
    candidates = {candidate.label: candidate for candidate in batch.objects}

    expected_families = {
        "Direct Credit Rule": "credit",
        "Rollup Credit Rule": "credit",
        "Primary Measurement Rule": "measurement",
        "Secondary Measurement Rule": "measurement",
        "Bulk Incentive Rule": "incentive",
        "Commission Rule": "incentive",
        "Deposit Rule": "deposit",
        "Detailed Deposit Rule": "deposit",
        "Custom Existing Rule": "other",
        "Unspecified Rule": "other",
    }

    assert {
        label: candidate.metadata["ruleFamily"]
        for label, candidate in candidates.items()
    } == expected_families
    assert {candidate.node_type for candidate in batch.objects} == {"Rule"}
    assert {
        node.type for node in NodeFactory().build(batch.objects, context)
    } == {"Rule"}

    internal_ids = {"ifThenElse", "DIRECT_TRANSACTION_CREDIT_ALLGAs", "customAction"}
    assert internal_ids.isdisjoint(candidates)
    assert len(batch.objects) == len(expected_families)


def test_rule_metadata_preserves_subtype_and_normalizes_description_and_dates():
    _, _, batch = _extract_fixture()
    candidates = {candidate.label: candidate for candidate in batch.objects}

    assert candidates["Direct Credit Rule"].metadata == {
        "ruleFamily": "credit",
        "ruleSubtype": "DIRECT_TRANSACTION_CREDIT",
        "effectiveStartDate": "2026-01-01",
        "effectiveEndDate": "2200-01-01",
        "description": "Direct credit description",
    }
    assert (
        candidates["Custom Existing Rule"].metadata["ruleSubtype"]
        == "CUSTOM_EXISTING_RULE"
    )
    assert candidates["Unspecified Rule"].metadata == {
        "ruleFamily": "other",
        "ruleSubtype": "",
    }


def test_rule_references_cover_the_complete_subtree_and_are_semantically_unique():
    _, _, batch = _extract_fixture()
    direct_rule = next(
        candidate.element
        for candidate in batch.objects
        if candidate.label == "Direct Credit Rule"
    )
    references = [
        reference
        for reference in batch.references
        if reference.source_element is direct_rule
    ]

    semantic_references = {
        (reference.value, reference.expected_type) for reference in references
    }
    assert semantic_references == {
        ("Gate", "Variable"),
        ("Cap", "FixedValue"),
        ("Eligibility Formula", "Formula"),
        ("Payout Rates", "RateTable"),
        ("/reports/monthly", None),
        ("United States", "Territory"),
        ("Revenue Credit", "CreditType"),
        ("Sales Order", "EventType"),
    }
    assert len(references) == len(semantic_references)
    assert all(reference.origin for reference in references)
    assert any("NESTED_CONDITION" in reference.origin for reference in references)


def test_fallback_rule_extractor_accepts_unknown_or_missing_type_only():
    document = load_xml_text(
        """<DATA_IMPORT>
        <RULE NAME="Known" TYPE="COMMISSION"/>
        <RULE NAME="Unknown" TYPE="FUTURE_RULE_TYPE"/>
        <RULE NAME="Missing"/>
        </DATA_IMPORT>""",
        "fallback.xml",
    )
    context = ExtractionContext("configuration", "configuration", document)

    batch = ExtractorRegistry([FallbackRuleExtractor()]).extract(context)

    assert [candidate.label for candidate in batch.objects] == ["Unknown", "Missing"]
