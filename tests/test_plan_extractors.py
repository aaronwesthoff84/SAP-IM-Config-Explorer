from pathlib import Path

from sap_im_config_graph_explorer.object_extractors.base import ExtractionContext
from sap_im_config_graph_explorer.object_extractors.node_factory import NodeFactory
from sap_im_config_graph_explorer.object_extractors.plans import (
    PLAN_EXTRACTORS,
    PlanComponentExtractor,
    PlanExtractor,
)
from sap_im_config_graph_explorer.object_extractors.registry import ExtractorRegistry
from sap_im_config_graph_explorer.xml_loader import load_xml_file, load_xml_text


FIXTURES = Path(__file__).parent / "fixtures"


def test_plan_extractors_emit_allowlisted_objects_with_normalized_metadata():
    document = load_xml_file(FIXTURES / "minimal_plan.xml")
    context = ExtractionContext("configuration", "configuration", document)

    batch = ExtractorRegistry(PLAN_EXTRACTORS).extract(context)
    nodes = NodeFactory().build(batch.objects, context)

    assert [(node.label, node.type) for node in nodes] == [
        ("Enterprise Plan", "Plan"),
        ("Core Component", "PlanComponent"),
    ]
    assert nodes[0].metadata == {
        "effectiveStartDate": "2026-01-01",
        "effectiveEndDate": "2200-01-01",
        "description": "Demo plan",
        "tag": "PLAN",
        "attributes": {
            "NAME": "Enterprise Plan",
            "EFFECTIVE_START_DATE": "2026-01-01",
            "EFFECTIVE_END_DATE": "2200-01-01",
            "DESCRIPTION": "Demo plan",
        },
    }
    assert nodes[1].metadata["description"] == "Component"
    assert nodes[1].metadata["effectiveStartDate"] == "2026-01-01"
    assert nodes[1].metadata["effectiveEndDate"] == "2200-01-01"


def test_plan_extractors_emit_child_to_owner_containment_candidates():
    document = load_xml_file(FIXTURES / "minimal_plan.xml")
    context = ExtractionContext("configuration", "configuration", document)

    batch = ExtractorRegistry(PLAN_EXTRACTORS).extract(context)
    objects_by_type = {candidate.node_type: candidate for candidate in batch.objects}

    assert len(batch.references) == 2
    assert (
        batch.references[0].source_element,
        batch.references[0].value,
        batch.references[0].hint,
        batch.references[0].origin,
        batch.references[0].expected_type,
        batch.references[0].relationship,
        batch.references[0].reverse,
    ) == (
        objects_by_type["Plan"].element,
        "Core Component",
        "COMPONENT_REF",
        "tag:COMPONENT_REF",
        "PlanComponent",
        "belongs_to_plan",
        True,
    )
    assert (
        batch.references[1].source_element,
        batch.references[1].value,
        batch.references[1].hint,
        batch.references[1].origin,
        batch.references[1].expected_type,
        batch.references[1].relationship,
        batch.references[1].reverse,
    ) == (
        objects_by_type["PlanComponent"].element,
        "Credit Rule",
        "RULE_REF",
        "tag:RULE_REF",
        "Rule",
        "belongs_to_plan_component",
        True,
    )


def test_plan_extractors_match_only_definitions_and_support_component_aliases():
    document = load_xml_text(
        """<DATA_IMPORT>
        <PLAN NAME="Plan">
          <FUNCTION ID="ifThenElse" />
          <COMPONENT_REF NAME="Component reference" />
        </PLAN>
        <PLAN_REF NAME="Plan reference" />
        <PLAN_COMPONENT NAME="Underscore component">
          <RULE_REF NAME="Rule one" />
        </PLAN_COMPONENT>
        <PLANCOMPONENT NAME="Compact component">
          <RULE_REF NAME="Rule two" />
        </PLANCOMPONENT>
        <PLAN_COMPONENT_REF NAME="Component reference" />
        <PLANCOMPONENT_REF NAME="Compact component reference" />
        </DATA_IMPORT>""",
        "plan-aliases.xml",
    )
    context = ExtractionContext("configuration", "configuration", document)

    batch = ExtractorRegistry(
        [PlanExtractor(), PlanComponentExtractor()]
    ).extract(context)

    assert [(candidate.label, candidate.node_type) for candidate in batch.objects] == [
        ("Plan", "Plan"),
        ("Underscore component", "PlanComponent"),
        ("Compact component", "PlanComponent"),
    ]
    assert {reference.value for reference in batch.references} == {
        "Component reference",
        "Rule one",
        "Rule two",
    }


def test_plan_extractors_trim_optional_description_and_skip_unlabeled_objects():
    document = load_xml_text(
        """<DATA_IMPORT>
        <PLAN NAME="  Named plan  " DESCRIPTION="  Description  " />
        <PLAN DESCRIPTION="No label"><COMPONENT_REF NAME="Ignored" /></PLAN>
        <PLAN_COMPONENT NAME="  Named component  " DESCRIPTION="   " />
        <PLANCOMPONENT />
        </DATA_IMPORT>""",
        "plan-labels.xml",
    )
    context = ExtractionContext("configuration", "configuration", document)

    batch = ExtractorRegistry(PLAN_EXTRACTORS).extract(context)

    assert [(candidate.label, candidate.metadata) for candidate in batch.objects] == [
        ("Named plan", {"description": "Description"}),
        ("Named component", {}),
    ]
    assert batch.references == []
