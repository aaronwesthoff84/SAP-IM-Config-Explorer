#!/usr/bin/env python3
import argparse
import os
import resource
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.xml_loader import load_xml_text
from sap_im_config_graph_explorer.portable_exports import (
    graph_document_from_payload,
    serialize_csv_bundle,
    serialize_graphml,
    serialize_markdown,
)


def generate_representative_xml(
    num_plans: int,
    components_per_plan: int,
    rules_per_component: int,
    formulas_per_rule: int,
) -> bytes:
    """Generate a highly structured SAP IM XML configuration export."""
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<DATA_IMPORT VERSION="16.0">')

    # 1. PLAN_SET
    lines.append("  <PLAN_SET>")
    for p in range(num_plans):
        plan_name = f"Plan_{p}"
        lines.append(
            f'    <PLAN NAME="{plan_name}" EFFECTIVE_START_DATE="2026-01-01" '
            f'EFFECTIVE_END_DATE="2200-01-01" DESCRIPTION="Plan {p}">'
        )
        for c in range(components_per_plan):
            comp_name = f"Plan_{p}_Comp_{c}"
            lines.append(f'      <COMPONENT_REF NAME="{comp_name}" />')
        lines.append("    </PLAN>")
    lines.append("  </PLAN_SET>")

    # 2. PLANCOMPONENT_SET
    lines.append("  <PLANCOMPONENT_SET>")
    for p in range(num_plans):
        for c in range(components_per_plan):
            comp_name = f"Plan_{p}_Comp_{c}"
            lines.append(
                f'    <PLANCOMPONENT NAME="{comp_name}" EFFECTIVE_START_DATE="2026-01-01" '
                f'EFFECTIVE_END_DATE="2200-01-01" DESCRIPTION="Component {p}_{c}">'
            )
            lines.append("      <RULE_REFS>")
            for r in range(rules_per_component):
                rule_name = f"Plan_{p}_Comp_{c}_Rule_{r}"
                lines.append(f'        <RULE_REF NAME="{rule_name}" />')
            lines.append("      </RULE_REFS>")
            lines.append("    </PLANCOMPONENT>")
    lines.append("  </PLANCOMPONENT_SET>")

    # 3. RULE_SET
    lines.append("  <RULE_SET>")
    for p in range(num_plans):
        for c in range(components_per_plan):
            for r in range(rules_per_component):
                rule_name = f"Plan_{p}_Comp_{c}_Rule_{r}"
                lines.append(
                    f'    <RULE NAME="{rule_name}" TYPE="DIRECT_TRANSACTION_CREDIT" '
                    f'EFFECTIVE_START_DATE="2026-01-01" EFFECTIVE_END_DATE="2200-01-01">'
                )
                lines.append("      <CONDITION_EXPRESSION>")
                lines.append('        <FUNCTION ID="MDLT_FUNCTION">')
                lines.append('          <MDLT_REF NAME="Rate Table" />')
                for f in range(formulas_per_rule):
                    formula_name = f"Plan_{p}_Comp_{c}_Rule_{r}_Formula_{f}"
                    lines.append(
                        f'          <STRING_FORMULA_REF NAME="{formula_name}" ID="STRING_FORMULA_REF" />'
                    )
                lines.append("        </FUNCTION>")
                lines.append("      </CONDITION_EXPRESSION>")
                lines.append("      <ACTION_EXPRESSION_SET>")
                lines.append("        <ACTION_EXPRESSION>")
                lines.append('          <FUNCTION ID="DIRECT_TRANSACTION_CREDIT_ALLGAs">')
                lines.append("            <CREDIT_TYPE>Revenue Credit</CREDIT_TYPE>")
                lines.append("          </FUNCTION>")
                lines.append("        </ACTION_EXPRESSION>")
                lines.append("      </ACTION_EXPRESSION_SET>")
                lines.append("    </RULE>")
    lines.append("  </RULE_SET>")

    # 4. FORMULA_SET
    lines.append("  <FORMULA_SET>")
    for p in range(num_plans):
        for c in range(components_per_plan):
            for r in range(rules_per_component):
                for f in range(formulas_per_rule):
                    formula_name = f"Plan_{p}_Comp_{c}_Rule_{r}_Formula_{f}"
                    lines.append(
                        f'    <FORMULA NAME="{formula_name}" RETURN_TYPE="Boolean" '
                        f'EFFECTIVE_START_DATE="2026-01-01" EFFECTIVE_END_DATE="2200-01-01">'
                    )
                    lines.append("      <EXPRESSION>")
                    lines.append('        <BOOLEAN VALUE="true" />')
                    lines.append("      </EXPRESSION>")
                    lines.append("    </FORMULA>")
    lines.append("  </FORMULA_SET>")

    # 5. MD_LOOKUP_TABLE_SET
    lines.append("  <MD_LOOKUP_TABLE_SET>")
    lines.append(
        '    <MD_LOOKUP_TABLE NAME="Rate Table" EFFECTIVE_START_DATE="2026-01-01" EFFECTIVE_END_DATE="2200-01-01">'
    )
    lines.append("      <DIM_NAMES>")
    lines.append('        <DIM_NAME NAME="Product" />')
    lines.append("      </DIM_NAMES>")
    lines.append("    </MD_LOOKUP_TABLE>")
    lines.append("  </MD_LOOKUP_TABLE_SET>")

    lines.append("</DATA_IMPORT>")
    return "\n".join(lines).encode("utf-8")


def get_memory_use() -> float:
    """Return max RSS in MB."""
    # resource.getrusage returns bytes on macOS but kilobytes on Linux
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    if sys.platform == "darwin":
        return rusage.ru_maxrss / (1024 * 1024)
    return rusage.ru_maxrss / 1024


def main() -> None:
    parser = argparse.ArgumentParser(description="Performance benchmark for SAP IM Config Explorer")
    parser.add_argument("--plans", type=int, default=5, help="Number of plans")
    parser.add_argument("--components", type=int, default=10, help="Components per plan")
    parser.add_argument("--rules", type=int, default=5, help="Rules per component")
    parser.add_argument("--formulas", type=int, default=2, help="Formulas per rule")
    args = parser.parse_args()

    print("=" * 60)
    print("SAP IM Config Explorer Performance Benchmark")
    print("=" * 60)
    print(f"Configuration profile:")
    print(f"  Plans:               {args.plans}")
    print(f"  Components/Plan:     {args.components}")
    print(f"  Rules/Component:     {args.rules}")
    print(f"  Formulas/Rule:       {args.formulas}")

    # Generate XML
    t0 = time.perf_counter()
    xml_data = generate_representative_xml(
        args.plans, args.components, args.rules, args.formulas
    )
    gen_time = time.perf_counter() - t0
    file_size_mb = len(xml_data) / (1024 * 1024)
    print(f"Generated representative XML: {file_size_mb:.2f} MB in {gen_time:.4f}s")

    # Step 1: XML Loading and Parsing
    t0 = time.perf_counter()
    doc = load_xml_text(xml_data, "benchmark_export.xml")
    parse_time = time.perf_counter() - t0
    print(f"1. XML Loading & Parsing:     {parse_time:.4f}s")

    # Step 2: Graph Construction (Full Topology)
    t0 = time.perf_counter()
    graph_builder = GraphBuilder(topology_mode="full")
    graph_doc = graph_builder.build_from_documents([doc])
    graph_time = time.perf_counter() - t0
    print(f"2. Graph Generation & Val:    {graph_time:.4f}s")
    print(f"   - Nodes: {len(graph_doc.nodes)}")
    print(f"   - Links: {len(graph_doc.links)}")
    print(f"   - Findings: {len(graph_doc.findings)}")

    # Step 3: Serialization
    payload = graph_doc.to_dict()

    t0 = time.perf_counter()
    _ = graph_document_from_payload(payload)
    csv_bytes = serialize_csv_bundle(graph_document_from_payload(payload))
    csv_time = time.perf_counter() - t0
    print(f"3. CSV Zip Serialization:     {csv_time:.4f}s (Size: {len(csv_bytes)/1024:.1f} KB)")

    t0 = time.perf_counter()
    markdown_str = serialize_markdown(graph_document_from_payload(payload))
    md_time = time.perf_counter() - t0
    print(f"4. Markdown Serialization:    {md_time:.4f}s (Size: {len(markdown_str)/1024:.1f} KB)")

    t0 = time.perf_counter()
    graphml_str = serialize_graphml(graph_document_from_payload(payload))
    graphml_time = time.perf_counter() - t0
    print(f"5. GraphML Serialization:     {graphml_time:.4f}s (Size: {len(graphml_str)/1024:.1f} KB)")

    mem_use = get_memory_use()
    print(f"Peak Memory Usage:            {mem_use:.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    main()
