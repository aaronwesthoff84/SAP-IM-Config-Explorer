from pathlib import Path
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import NODE_TYPES
from sap_im_config_graph_explorer.object_extractors.base import ExtractionContext
from sap_im_config_graph_explorer.object_extractors.formula import FormulaExtractor
from sap_im_config_graph_explorer.object_extractors.node_factory import NodeFactory
from sap_im_config_graph_explorer.object_extractors.registry import ExtractorRegistry
from sap_im_config_graph_explorer.xml_loader import load_xml_file, load_xml_text


FIXTURES = Path(__file__).parent / "fixtures"


def test_formula_extracts_one_allowlisted_object_with_normalized_metadata():
    document = load_xml_file(FIXTURES / "formula_dependencies.xml")
    context = ExtractionContext("configuration", "configuration", document)

    batch = ExtractorRegistry([FormulaExtractor()]).extract(context)

    assert len(batch.objects) == 1
    candidate = batch.objects[0]
    assert (candidate.label, candidate.node_type) == ("Commission Gate", "Formula")
    assert candidate.metadata == {
        "effectiveStartDate": "2026-01-01",
        "effectiveEndDate": "2200-01-01",
        "returnType": "Boolean",
        "description": "Eligibility gate",
        "expressionTags": [
            "EXPRESSION",
            "FUNCTION",
            "PARAMETER_LIST",
            "VARIABLE_REF",
            "FIXED_VALUE_REF",
            "MDLT_REF",
            "STRING_FORMULA_REF",
            "BOOLEAN",
            "INTERNAL",
        ],
    }

    nodes = NodeFactory().build(batch.objects, context)
    assert [(node.label, node.type) for node in nodes] == [
        ("Commission Gate", "Formula")
    ]


def test_formula_emits_ordered_unique_typed_input_references():
    document = load_xml_file(FIXTURES / "formula_dependencies.xml")
    formula = document.root.find("./FORMULA_SET/FORMULA")
    assert formula is not None
    context = ExtractionContext("configuration", "configuration", document)

    batch = ExtractorRegistry([FormulaExtractor()]).extract(context)

    assert [
        (ref.value, ref.expected_type, ref.relationship)
        for ref in batch.references
    ] == [
        ("Gate", "Variable", "uses_variable"),
        ("Cap", "FixedValue", "uses_fixed_value"),
        ("Commission Lookup", "LookupTable", "uses_lookup"),
        ("Eligibility", "Formula", "uses_formula"),
    ]
    assert all(ref.source_element is formula for ref in batch.references)
    assert all(ref.expected_type in NODE_TYPES for ref in batch.references)
    assert sum(ref.expected_type == "Variable" for ref in batch.references) == 1
    assert not any(ref.value == "not-a-graph-object" for ref in batch.references)


def test_formula_matches_definitions_only_and_never_emits_expression_nodes():
    extractor = FormulaExtractor()
    assert extractor.matches(ET.fromstring('<FORMULA NAME="Definition" />'))
    assert not extractor.matches(ET.fromstring('<FORMULA_REF NAME="Reference" />'))
    assert not extractor.matches(ET.fromstring('<FUNCTION ID="ifThenElse" />'))

    document = load_xml_text(
        """<DATA_IMPORT><FORMULA NAME="Only Node">
        <EXPRESSION><FUNCTION ID="ifThenElse"><PARAMETER_LIST>
        <BOOLEAN VALUE="true"/><STRING VALUE="approved"/>
        </PARAMETER_LIST></FUNCTION></EXPRESSION>
        </FORMULA></DATA_IMPORT>""",
        "formula_logic.xml",
    )
    context = ExtractionContext("configuration", "configuration", document)

    batch = ExtractorRegistry([extractor]).extract(context)

    assert [(obj.label, obj.node_type) for obj in batch.objects] == [
        ("Only Node", "Formula")
    ]
    assert not any(
        obj.label in {"ifThenElse", "PARAMETER_LIST", "true", "approved"}
        for obj in batch.objects
    )
