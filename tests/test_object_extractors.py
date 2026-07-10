from dataclasses import dataclass
from xml.etree import ElementTree as ET

import pytest

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionBatch,
    ExtractionContext,
    ObjectCandidate,
    ReferenceCandidate,
)
from sap_im_config_graph_explorer.object_extractors.common import (
    infer_label,
    normalize_identity,
    normalized_dates,
    trim_raw_xml,
)
from sap_im_config_graph_explorer.object_extractors.node_factory import NodeFactory
from sap_im_config_graph_explorer.object_extractors.registry import ExtractorRegistry
from sap_im_config_graph_explorer.xml_loader import load_xml_text


@dataclass
class FormulaTestExtractor:
    def matches(self, element: ET.Element) -> bool:
        return element.tag.upper() == "FORMULA"

    def extract(self, element: ET.Element, context: ExtractionContext) -> ExtractionBatch:
        return ExtractionBatch(
            objects=[ObjectCandidate(element, "Formula", element.get("NAME", ""))]
        )


def test_registry_dispatches_and_node_factory_enforces_allowlist_and_identity():
    document = load_xml_text(
        '<DATA_IMPORT><FORMULA ID="F-1" NAME="Gate" /></DATA_IMPORT>', "one.xml"
    )
    context = ExtractionContext("non-prod", "non_production", document)
    batch = ExtractorRegistry([FormulaTestExtractor()]).extract(context)
    nodes = NodeFactory().build(batch.objects, context)
    assert len(nodes) == 1
    assert nodes[0].canonicalKey == "formula:f-1"
    assert nodes[0].snapshotId == "non-prod"

    unsupported = ObjectCandidate(document.root, "CustomObject", "Custom")
    with pytest.raises(ValueError, match="Unsupported graph node type"):
        NodeFactory().build([unsupported], context)


def test_duplicate_group_marks_every_member_and_is_snapshot_scoped():
    document = load_xml_text(
        '<DATA_IMPORT><FORMULA ID="DUP" NAME="A"/><FORMULA ID="DUP" NAME="B"/></DATA_IMPORT>',
        "dupes.xml",
    )
    context = ExtractionContext("configuration", "configuration", document)
    batch = ExtractorRegistry([FormulaTestExtractor()]).extract(context)
    nodes = NodeFactory().build(batch.objects, context)
    assert len({node.id for node in nodes}) == 2
    assert {node.metadata["duplicateKey"] for node in nodes} == {"formula:dup"}


def test_registry_uses_first_match_supports_prepend_and_ignores_unmatched_xml():
    document = load_xml_text(
        '<DATA_IMPORT><FORMULA NAME="Gate"/><UNKNOWN NAME="Ignore"/></DATA_IMPORT>',
        "dispatch.xml",
    )
    context = ExtractionContext("configuration", "configuration", document)

    @dataclass
    class NamedExtractor:
        label: str

        def matches(self, element: ET.Element) -> bool:
            return element.tag == "FORMULA"

        def extract(
            self, element: ET.Element, context: ExtractionContext
        ) -> ExtractionBatch:
            return ExtractionBatch(
                objects=[ObjectCandidate(element, "Formula", self.label)],
                references=[ReferenceCandidate(element, self.label, "test", "dispatch")],
            )

    registry = ExtractorRegistry([NamedExtractor("first"), NamedExtractor("second")])
    registry.register(NamedExtractor("prepended"), prepend=True)

    batch = registry.extract(context)

    assert [candidate.label for candidate in batch.objects] == ["prepended"]
    assert [candidate.value for candidate in batch.references] == ["prepended"]


def test_node_factory_preserves_identity_scope_metadata_and_cross_file_state():
    first_document = load_xml_text(
        '<DATA_IMPORT><FORMULA OBJECT_ID="Same ID" NAME="First" /></DATA_IMPORT>',
        "first.xml",
    )
    second_document = load_xml_text(
        '<DATA_IMPORT><FORMULA OBJECT_ID="Same ID" NAME="Second" /></DATA_IMPORT>',
        "second.xml",
    )
    first_element = first_document.root[0]
    second_element = second_document.root[0]
    first_context = ExtractionContext("non-prod", "non_production", first_document)
    second_context = ExtractionContext("non-prod", "non_production", second_document)
    factory = NodeFactory()
    first_nodes = factory.build(
        [
            ObjectCandidate(
                first_element,
                "Formula",
                "First",
                metadata={"returnType": "Boolean"},
                identity_scope="Plan A:Component 1",
            )
        ],
        first_context,
    )
    second_nodes = factory.build(
        [
            ObjectCandidate(
                second_element,
                "Formula",
                "Second",
                identity_scope="Plan A:Component 1",
            )
        ],
        second_context,
    )
    nodes = first_nodes + second_nodes

    factory.finalize(nodes)

    assert {node.canonicalKey for node in nodes} == {
        "formula:plan-a:component-1:same-id"
    }
    assert {node.metadata["duplicateKey"] for node in nodes} == {
        "formula:plan-a:component-1:same-id"
    }
    assert first_nodes[0].metadata["returnType"] == "Boolean"
    assert first_nodes[0].metadata["tag"] == "FORMULA"
    assert first_nodes[0].metadata["attributes"]["OBJECT_ID"] == "Same ID"
    assert first_nodes[0].metadata["sourceId"] == "Same ID"
    assert factory.node_id_by_element[id(first_element)] == first_nodes[0].id
    assert factory.node_id_by_element[id(second_element)] == second_nodes[0].id

    other_snapshot = ExtractionContext("prod", "production", first_document)
    isolated = factory.build(
        [ObjectCandidate(first_element, "Formula", "First")], other_snapshot
    )
    factory.finalize(nodes + isolated)
    assert "duplicateKey" not in isolated[0].metadata


def test_node_factory_ids_are_stable_and_reset_clears_build_state():
    document = load_xml_text(
        '<DATA_IMPORT><FORMULA NAME="Gate"/><FORMULA NAME="Gate"/></DATA_IMPORT>',
        "stable.xml",
    )
    context = ExtractionContext("configuration", "configuration", document)
    candidates = [ObjectCandidate(element, "Formula", "Gate") for element in document.root]
    factory = NodeFactory()

    first_ids = [node.id for node in factory.build(candidates, context)]
    assert len(set(first_ids)) == 2

    factory.reset()
    second_ids = [node.id for node in factory.build(candidates, context)]

    assert first_ids == second_ids
    assert len(factory.node_id_by_element) == 2


def test_common_helpers_normalize_labels_dates_identity_and_raw_xml():
    element = ET.fromstring(
        '<FIXED_VALUE DISPLAY_NAME="  Gate Value  " '
        'EFFECTIVE_START_DATE=" 2026-01-01 " '
        'EFFECTIVE_END_DATE=" 2200-01-01 ">abcdefghij</FIXED_VALUE>'
    )

    assert normalize_identity(" Plan A : Component/1 ") == "plan-a:component-1"
    assert infer_label(element) == "Gate Value"
    assert normalized_dates(element) == {
        "effectiveStartDate": "2026-01-01",
        "effectiveEndDate": "2200-01-01",
    }
    assert len(trim_raw_xml(element, limit=20)) <= 20
    assert trim_raw_xml(element, limit=20).endswith("\n...")
