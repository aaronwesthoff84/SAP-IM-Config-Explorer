from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.xml_loader import load_xml_text


def test_single_pass_precalculation_correctness():
    """Verify that the optimized single-pass pre-calculated cache is correctly

    populated and preserved during graph builder execution.
    """
    xml_data = """<?xml version="1.0" encoding="UTF-8"?>
    <DATA_IMPORT VERSION="16.0">
      <PLAN_SET>
        <PLAN NAME="Enterprise Plan">
          <COMPONENT_REF NAME="Core Component" />
        </PLAN>
      </PLAN_SET>
      <PLANCOMPONENT_SET>
        <PLANCOMPONENT NAME="Core Component">
          <RULE_REFS>
            <RULE_REF NAME="Credit Rule" />
          </RULE_REFS>
        </PLANCOMPONENT>
      </PLANCOMPONENT_SET>
      <RULE_SET>
        <RULE NAME="Credit Rule" TYPE="DIRECT_TRANSACTION_CREDIT">
          <CONDITION_EXPRESSION>
            <FUNCTION ID="MDLT_FUNCTION">
              <MDLT_REF NAME="Rate Table" />
              <STRING_FORMULA_REF NAME="Eligibility Formula" ID="STRING_FORMULA_REF" />
            </FUNCTION>
          </CONDITION_EXPRESSION>
        </RULE>
      </RULE_SET>
      <FORMULA_SET>
        <FORMULA NAME="Eligibility Formula" RETURN_TYPE="Boolean">
          <EXPRESSION>
            <BOOLEAN VALUE="true" />
          </EXPRESSION>
        </FORMULA>
      </FORMULA_SET>
    </DATA_IMPORT>
    """
    doc = load_xml_text(xml_data.encode("utf-8"), "test.xml")

    # Build graph
    builder = GraphBuilder(topology_mode="full")
    graph_doc = builder.build_from_documents([doc])

    # Assert caches were created and stored on doc
    assert hasattr(doc, "_plan_component_refs")
    assert hasattr(doc, "_component_rule_refs")
    assert hasattr(doc, "_rule_formula_references")
    assert hasattr(doc, "_formula_expression_tags")

    # Verify contents
    assert len(doc._plan_component_refs) > 0
    assert len(doc._component_rule_refs) > 0
    assert len(doc._rule_formula_references) > 0
    assert len(doc._formula_expression_tags) > 0

    # Ensure there are nodes and links in the built graph
    assert len(graph_doc.nodes) > 0
    assert len(graph_doc.links) > 0
