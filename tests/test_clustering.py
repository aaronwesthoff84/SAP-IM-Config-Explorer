from __future__ import annotations

import time
import pytest

from sap_im_config_graph_explorer.clustering import (
    GraphPartitioner,
    LouvainCommunityDetector,
    PlanTypePartitioner,
)
from sap_im_config_graph_explorer.models import (
    ClusteringResult,
    ClusterMetanode,
    GraphLink,
    GraphNode,
)


def _make_node(nid: str, ntype: str, label: str | None = None) -> GraphNode:
    return GraphNode(
        id=nid,
        label=label or nid,
        type=ntype,
        sourceFile="test.xml",
        xmlPath=f"/ROOT/{ntype}[@id='{nid}']",
        rawXml=f"<{ntype} id='{nid}'/>",
        canonicalKey=f"{ntype.lower()}:{nid}",
    )


def _make_link(
    src: str, tgt: str, rel: str = "uses_formula", confidence: str = "high"
) -> GraphLink:
    return GraphLink(
        id=f"link-{src}-{tgt}",
        source=src,
        target=tgt,
        relationship=rel,
        confidence=confidence,
    )


def test_louvain_simple_two_cliques():
    # Two cliques of 4 nodes each, joined by a single bridge edge (n3 - n4)
    nodes = [_make_node(f"n{i}", "Rule" if i < 4 else "Formula") for i in range(8)]
    links = [
        # Clique 1: 0, 1, 2, 3
        _make_link("n0", "n1"),
        _make_link("n0", "n2"),
        _make_link("n0", "n3"),
        _make_link("n1", "n2"),
        _make_link("n1", "n3"),
        _make_link("n2", "n3"),
        # Bridge
        _make_link("n3", "n4"),
        # Clique 2: 4, 5, 6, 7
        _make_link("n4", "n5"),
        _make_link("n4", "n6"),
        _make_link("n4", "n7"),
        _make_link("n5", "n6"),
        _make_link("n5", "n7"),
        _make_link("n6", "n7"),
    ]

    detector = LouvainCommunityDetector()
    node_to_cluster, q, clusters = detector.detect(nodes, links)

    assert len(clusters) == 2
    assert q > 0.35  # Strong modularity
    # All nodes in clique 1 share the same community
    c1 = node_to_cluster["n0"]
    assert node_to_cluster["n1"] == c1
    assert node_to_cluster["n2"] == c1
    assert node_to_cluster["n3"] == c1

    # All nodes in clique 2 share a different community
    c2 = node_to_cluster["n4"]
    assert c2 != c1
    assert node_to_cluster["n5"] == c2
    assert node_to_cluster["n6"] == c2
    assert node_to_cluster["n7"] == c2


def test_louvain_boundary_cases():
    detector = LouvainCommunityDetector()
    # Empty graph
    node_to_cluster, q, clusters = detector.detect([], [])
    assert node_to_cluster == {}
    assert q == 0.0
    assert clusters == []

    # Single node
    single = [_make_node("node1", "Plan")]
    node_to_cluster, q, clusters = detector.detect(single, [])
    assert node_to_cluster == {"node1": "c0"}
    assert len(clusters) == 1

    # Disconnected nodes (no edges)
    disc = [_make_node(f"n{i}", "Rule" if i % 2 == 0 else "Formula") for i in range(4)]
    node_to_cluster, q, clusters = detector.detect(disc, [])
    assert len(node_to_cluster) == 4
    assert len(clusters) == 2  # 2 types: Rule and Formula


def test_plan_type_partitioning():
    # 2 Plans
    p1 = _make_node("plan_sales", "Plan", "Direct Sales Plan")
    p2 = _make_node("plan_partner", "Plan", "Partner Plan")

    # Components
    c1 = _make_node("comp_sales_tier1", "PlanComponent", "Direct Tier 1")
    c2 = _make_node("comp_partner_base", "PlanComponent", "Partner Base")

    # Rules
    r1 = _make_node("rule_comm", "Rule", "Commission Rule")
    r2 = _make_node("rule_bonus", "Rule", "Bonus Rule")

    # Dedicated formulas
    f_dedicated1 = _make_node("f_sales_rate", "Formula", "Sales Rate Formula")
    f_dedicated2 = _make_node("f_partner_tier", "Formula", "Partner Tier Formula")

    # Shared formula
    f_shared = _make_node("f_fx_convert", "Formula", "Currency FX Converter")

    # Unassigned formula
    f_unassigned = _make_node("f_unused", "Formula", "Unused Formula")

    nodes = [
        p1, p2, c1, c2, r1, r2, f_dedicated1, f_dedicated2, f_shared, f_unassigned
    ]

    links = [
        _make_link("comp_sales_tier1", "plan_sales", "belongs_to_plan"),
        _make_link("comp_partner_base", "plan_partner", "belongs_to_plan"),
        _make_link("rule_comm", "comp_sales_tier1", "belongs_to_plan_component"),
        _make_link("rule_bonus", "comp_partner_base", "belongs_to_plan_component"),
        _make_link("rule_comm", "f_sales_rate", "uses_formula"),
        _make_link("rule_bonus", "f_partner_tier", "uses_formula"),
        # Both rules use the shared formula
        _make_link("rule_comm", f_shared.id, "uses_formula"),
        _make_link("rule_bonus", f_shared.id, "uses_formula"),
    ]

    partitioner = PlanTypePartitioner()
    node_to_cluster, q, clusters = partitioner.partition(nodes, links)

    # p1, c1, r1, f_dedicated1 must be in plan_sales cluster
    plan1_cid = node_to_cluster["plan_sales"]
    assert node_to_cluster["comp_sales_tier1"] == plan1_cid
    assert node_to_cluster["rule_comm"] == plan1_cid
    assert node_to_cluster["f_sales_rate"] == plan1_cid

    # p2, c2, r2, f_dedicated2 must be in plan_partner cluster
    plan2_cid = node_to_cluster["plan_partner"]
    assert plan2_cid != plan1_cid
    assert node_to_cluster["comp_partner_base"] == plan2_cid
    assert node_to_cluster["rule_bonus"] == plan2_cid
    assert node_to_cluster["f_partner_tier"] == plan2_cid

    # Shared formula must be in cluster_shared
    assert node_to_cluster[f_shared.id] == "cluster_shared"

    # Unassigned formula must be in cluster_unassigned
    assert node_to_cluster[f_unassigned.id] == "cluster_unassigned"


def test_metanode_condensation_and_bridge_links():
    nodes = [_make_node(f"n{i}", "Rule" if i < 4 else "Formula") for i in range(8)]
    links = [
        _make_link("n0", "n1"),
        _make_link("n1", "n2"),
        _make_link("n2", "n3"),
        # 2 cross-cluster links between cluster 1 and cluster 2
        _make_link("n2", "n4"),
        _make_link("n3", "n5"),
        _make_link("n4", "n5"),
        _make_link("n5", "n6"),
        _make_link("n6", "n7"),
    ]

    coordinator = GraphPartitioner()
    clustering = coordinator.partition(nodes, links, mode="louvain")

    metanodes, bridge_links = coordinator.condense_metagraph(nodes, links, clustering)

    assert len(metanodes) == clustering.clusterCount
    assert all(m.type == "ClusterMetanode" for m in metanodes)
    assert all(m.metadata.get("isMetanode") is True for m in metanodes)

    # Inter-cluster links should be aggregated into bridge links
    assert len(bridge_links) >= 1
    bridge = bridge_links[0]
    assert bridge.relationship == "cluster_bridge"
    assert bridge.metadata["isBridge"] is True
    assert bridge.metadata["bridgeEdgeCount"] >= 1


def test_compound_node_enrichment():
    nodes = [_make_node("p1", "Plan"), _make_node("r1", "Rule")]
    links = [_make_link("r1", "p1", "belongs_to_plan")]

    coordinator = GraphPartitioner()
    clustering = coordinator.partition(nodes, links, mode="plan_type")

    enriched_nodes, enriched_links = coordinator.enrich_graph_with_clusters(
        nodes, links, clustering, as_compound_nodes=True
    )

    # Contains compound parent metanodes + original nodes
    assert len(enriched_nodes) > len(nodes)
    parents = [n for n in enriched_nodes if n.metadata.get("isCompoundParent")]
    assert len(parents) == clustering.clusterCount
    assert all(p.type == "ClusterMetanode" for p in parents)

    # Original nodes have parent metadata referencing compound node
    regular_nodes = [n for n in enriched_nodes if not n.metadata.get("isCompoundParent")]
    for rn in regular_nodes:
        assert "parent" in rn.metadata
        assert "clusterId" in rn.metadata
        assert rn.metadata["parent"] == f"cluster-parent-{rn.metadata['clusterId']}"


def test_performance_10k_nodes_sub_250ms():
    """Validates Acceptance Criterion 3:

    Partitions a 10,000-node graph in under 250ms on standard workstation hardware.
    """
    n_nodes = 10000
    n_clusters = 20
    cluster_size = n_nodes // n_clusters

    nodes: list[GraphNode] = []
    for i in range(n_nodes):
        c = i // cluster_size
        ntype = "Rule" if (i % 3 == 0) else ("Formula" if i % 3 == 1 else "LookupTable")
        nodes.append(_make_node(f"node_{i}", ntype, f"Object {i} (Group {c})"))

    links: list[GraphLink] = []
    # Create internal chain and cross edges in each cluster (approx 2 edges per node)
    for c in range(n_clusters):
        start = c * cluster_size
        for offset in range(cluster_size - 1):
            u = start + offset
            v = start + offset + 1
            links.append(_make_link(f"node_{u}", f"node_{v}"))
            if offset + 2 < cluster_size:
                links.append(_make_link(f"node_{u}", f"node_{start + offset + 2}"))

        # Add a few inter-cluster bridge links to the next cluster
        next_start = ((c + 1) % n_clusters) * cluster_size
        links.append(_make_link(f"node_{start + 5}", f"node_{next_start + 5}"))

    coordinator = GraphPartitioner()

    t0 = time.perf_counter()
    clustering = coordinator.partition(nodes, links, mode="louvain", max_clusters=50)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n10,000-node partitioning completed in: {duration_ms:.2f}ms (modularity Q={clustering.modularity:.3f})")

    assert clustering.clusterCount > 1
    assert clustering.modularity > 0.4
    assert duration_ms < 250.0, f"Partitioning took {duration_ms:.2f}ms, exceeding 250ms limit"
