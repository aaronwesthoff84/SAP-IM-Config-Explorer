from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import (
    ChangedObjectRecord,
    ComparisonResult,
    ComparisonSummary,
    DifferenceDetail,
    GraphDocument,
    GraphNode,
    ObjectRecord,
)
from sap_im_config_graph_explorer.object_extractors.common import normalize_identity
from sap_im_config_graph_explorer.xml_loader import XmlDocument, XmlLoadError, load_xml_file, load_xml_text


IGNORED_ATTRIBUTES = frozenset(
    {
        "NAME",
        "DISPLAY_NAME",
        "DESCRIPTION",
        "EFFECTIVE_START_DATE",
        "EFFECTIVE_END_DATE",
        "ID",
        "OBJECT_ID",
        "TAG",
    }
)


class ConfigComparator:
    """Deterministic comparison engine for SAP Incentive Management XML configurations."""

    def __init__(self, topology_mode: str = "full") -> None:
        self.topology_mode = topology_mode

    def compare_files(
        self,
        baseline_path: str | Path,
        candidate_path: str | Path,
        as_of_date: str | None = None,
    ) -> ComparisonResult:
        baseline_path = Path(baseline_path)
        candidate_path = Path(candidate_path)

        baseline_doc = load_xml_file(baseline_path)
        candidate_doc = load_xml_file(candidate_path)

        return self.compare_xml_documents(
            baseline_doc=baseline_doc,
            candidate_doc=candidate_doc,
            baseline_filename=baseline_path.name,
            candidate_filename=candidate_path.name,
            as_of_date=as_of_date,
        )

    def compare_xml_texts(
        self,
        baseline_content: str | bytes,
        candidate_content: str | bytes,
        baseline_filename: str = "baseline.xml",
        candidate_filename: str = "candidate.xml",
        as_of_date: str | None = None,
    ) -> ComparisonResult:
        baseline_doc = load_xml_text(baseline_content, baseline_filename)
        candidate_doc = load_xml_text(candidate_content, candidate_filename)

        return self.compare_xml_documents(
            baseline_doc=baseline_doc,
            candidate_doc=candidate_doc,
            baseline_filename=baseline_filename,
            candidate_filename=candidate_filename,
            as_of_date=as_of_date,
        )

    def compare_xml_documents(
        self,
        baseline_doc: XmlDocument,
        candidate_doc: XmlDocument,
        baseline_filename: str = "baseline.xml",
        candidate_filename: str = "candidate.xml",
        as_of_date: str | None = None,
    ) -> ComparisonResult:
        builder = GraphBuilder(topology_mode=self.topology_mode)
        baseline_graph = builder.build_from_documents(
            [baseline_doc], snapshot_id="baseline", role="configuration"
        )
        candidate_graph = builder.build_from_documents(
            [candidate_doc], snapshot_id="candidate", role="non_production"
        )

        return self.compare_graphs(
            baseline_graph=baseline_graph,
            candidate_graph=candidate_graph,
            baseline_filename=baseline_filename,
            candidate_filename=candidate_filename,
            as_of_date=as_of_date,
        )

    def compare_graphs(
        self,
        baseline_graph: GraphDocument,
        candidate_graph: GraphDocument,
        baseline_filename: str = "baseline.xml",
        candidate_filename: str = "candidate.xml",
        as_of_date: str | None = None,
    ) -> ComparisonResult:
        b_node_by_id = {node.id: node for node in baseline_graph.nodes}
        c_node_by_id = {node.id: node for node in candidate_graph.nodes}

        b_children, b_parents, b_refs = self._index_graph_links(baseline_graph, b_node_by_id)
        c_children, c_parents, c_refs = self._index_graph_links(candidate_graph, c_node_by_id)

        # Index nodes by stable identity: (type, normalized_label)
        b_groups: dict[tuple[str, str], list[GraphNode]] = defaultdict(list)
        for node in baseline_graph.nodes:
            b_groups[(node.type, normalize_identity(node.label))].append(node)

        c_groups: dict[tuple[str, str], list[GraphNode]] = defaultdict(list)
        for node in candidate_graph.nodes:
            c_groups[(node.type, normalize_identity(node.label))].append(node)

        all_keys = sorted(set(b_groups) | set(c_groups), key=lambda k: (k[0], k[1]))

        added: list[ObjectRecord] = []
        removed: list[ObjectRecord] = []
        changed: list[ChangedObjectRecord] = []
        unchanged: list[ObjectRecord] = []

        for key in all_keys:
            b_list = b_groups.get(key, [])
            c_list = c_groups.get(key, [])

            # Match instances up to min(len(b_list), len(c_list))
            matched_count = min(len(b_list), len(c_list))

            for i in range(matched_count):
                b_node = b_list[i]
                c_node = c_list[i]

                diffs = self._diff_nodes(
                    b_node=b_node,
                    c_node=c_node,
                    b_children=b_children.get(b_node.id, []),
                    c_children=c_children.get(c_node.id, []),
                    b_parents=b_parents.get(b_node.id, []),
                    c_parents=c_parents.get(c_node.id, []),
                    b_refs=b_refs.get(b_node.id, []),
                    c_refs=c_refs.get(c_node.id, []),
                )

                if diffs:
                    summary = "; ".join(d.description for d in diffs)
                    changed.append(
                        ChangedObjectRecord(
                            type=c_node.type,
                            label=c_node.label,
                            canonicalKey=c_node.canonicalKey,
                            differences=diffs,
                            summary=summary,
                            sourceFile=b_node.sourceFile,
                            candidateSourceFile=c_node.sourceFile,
                            metadata=c_node.metadata,
                        )
                    )
                else:
                    unchanged.append(
                        ObjectRecord(
                            type=c_node.type,
                            label=c_node.label,
                            canonicalKey=c_node.canonicalKey,
                            sourceFile=c_node.sourceFile,
                            metadata=c_node.metadata,
                            containment=c_children.get(c_node.id, []),
                            references=[
                                {"relationship": rel, "target": target}
                                for rel, target in c_refs.get(c_node.id, [])
                            ],
                        )
                    )

            # Any remaining candidate nodes are added
            for c_node in c_list[matched_count:]:
                added.append(
                    ObjectRecord(
                        type=c_node.type,
                        label=c_node.label,
                        canonicalKey=c_node.canonicalKey,
                        sourceFile=c_node.sourceFile,
                        metadata=c_node.metadata,
                        containment=c_children.get(c_node.id, []),
                        references=[
                            {"relationship": rel, "target": target}
                            for rel, target in c_refs.get(c_node.id, [])
                        ],
                    )
                )

            # Any remaining baseline nodes are removed
            for b_node in b_list[matched_count:]:
                removed.append(
                    ObjectRecord(
                        type=b_node.type,
                        label=b_node.label,
                        canonicalKey=b_node.canonicalKey,
                        sourceFile=b_node.sourceFile,
                        metadata=b_node.metadata,
                        containment=b_children.get(b_node.id, []),
                        references=[
                            {"relationship": rel, "target": target}
                            for rel, target in b_refs.get(b_node.id, [])
                        ],
                    )
                )

        # Sort all result lists deterministically by (type, label)
        added.sort(key=lambda r: (r.type, r.label.casefold()))
        removed.sort(key=lambda r: (r.type, r.label.casefold()))
        changed.sort(key=lambda r: (r.type, r.label.casefold()))
        unchanged.sort(key=lambda r: (r.type, r.label.casefold()))

        by_type: dict[str, dict[str, int]] = defaultdict(
            lambda: {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
        )
        for item in added:
            by_type[item.type]["added"] += 1
        for item in removed:
            by_type[item.type]["removed"] += 1
        for item in changed:
            by_type[item.type]["changed"] += 1
        for item in unchanged:
            by_type[item.type]["unchanged"] += 1

        summary = ComparisonSummary(
            totalAdded=len(added),
            totalRemoved=len(removed),
            totalChanged=len(changed),
            totalUnchanged=len(unchanged),
            byType=dict(by_type),
        )

        return ComparisonResult(
            ok=True,
            baselineFile=baseline_filename,
            candidateFile=candidate_filename,
            summary=summary,
            added=added,
            removed=removed,
            changed=changed,
            unchanged=unchanged,
            asOfDate=as_of_date,
        )

    def _index_graph_links(
        self, graph: GraphDocument, node_by_id: dict[str, GraphNode]
    ) -> tuple[
        dict[str, list[str]],
        dict[str, list[str]],
        dict[str, list[tuple[str, str]]],
    ]:
        children: dict[str, list[str]] = defaultdict(list)
        parents: dict[str, list[str]] = defaultdict(list)
        references: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for link in graph.links:
            source_node = node_by_id.get(link.source)
            target_node = node_by_id.get(link.target)
            if not source_node or not target_node:
                continue

            rel = link.relationship

            # Containment links:
            # 'belongs_to_plan': source is PlanComponent, target is Plan
            # 'belongs_to_plan_component': source is Rule, target is PlanComponent
            if rel in {"belongs_to_plan", "belongs_to_plan_component"}:
                children[target_node.id].append(source_node.label)
                parents[source_node.id].append(target_node.label)
            else:
                references[source_node.id].append((rel, target_node.label))

        for k in children:
            children[k].sort(key=str.casefold)
        for k in parents:
            parents[k].sort(key=str.casefold)
        for k in references:
            references[k].sort(key=lambda x: (x[0], x[1].casefold()))

        return children, parents, references

    def _diff_nodes(
        self,
        b_node: GraphNode,
        c_node: GraphNode,
        b_children: list[str],
        c_children: list[str],
        b_parents: list[str],
        c_parents: list[str],
        b_refs: list[tuple[str, str]],
        c_refs: list[tuple[str, str]],
    ) -> list[DifferenceDetail]:
        diffs: list[DifferenceDetail] = []

        # 1. Effective dates
        b_meta = b_node.metadata or {}
        c_meta = c_node.metadata or {}

        b_start = b_meta.get("effectiveStartDate") or ""
        c_start = c_meta.get("effectiveStartDate") or ""
        b_end = b_meta.get("effectiveEndDate") or ""
        c_end = c_meta.get("effectiveEndDate") or ""

        if b_start != c_start or b_end != c_end:
            b_range = f"{b_start} to {b_end}".strip(" to ") or "none"
            c_range = f"{c_start} to {c_end}".strip(" to ") or "none"
            diffs.append(
                DifferenceDetail(
                    field="effectiveDates",
                    baseline={"effectiveStartDate": b_start, "effectiveEndDate": b_end},
                    candidate={"effectiveStartDate": c_start, "effectiveEndDate": c_end},
                    description=f"Effective dates changed from '{b_range}' to '{c_range}'",
                )
            )

        # 2. Description
        b_desc = (
            b_meta.get("description")
            or b_meta.get("attributes", {}).get("DESCRIPTION")
            or ""
        ).strip()
        c_desc = (
            c_meta.get("description")
            or c_meta.get("attributes", {}).get("DESCRIPTION")
            or ""
        ).strip()

        if b_desc != c_desc:
            diffs.append(
                DifferenceDetail(
                    field="description",
                    baseline=b_desc,
                    candidate=c_desc,
                    description=f"Description changed from '{b_desc}' to '{c_desc}'",
                )
            )

        # 3. Attributes
        b_attrs = {
            k: str(v).strip()
            for k, v in b_meta.get("attributes", {}).items()
            if k.upper() not in IGNORED_ATTRIBUTES and v is not None
        }
        c_attrs = {
            k: str(v).strip()
            for k, v in c_meta.get("attributes", {}).items()
            if k.upper() not in IGNORED_ATTRIBUTES and v is not None
        }

        all_attr_keys = sorted(set(b_attrs) | set(c_attrs))
        for attr in all_attr_keys:
            if attr in b_attrs and attr in c_attrs:
                if b_attrs[attr] != c_attrs[attr]:
                    diffs.append(
                        DifferenceDetail(
                            field=f"attribute:{attr}",
                            baseline=b_attrs[attr],
                            candidate=c_attrs[attr],
                            description=f"Attribute '{attr}' changed from '{b_attrs[attr]}' to '{c_attrs[attr]}'",
                        )
                    )
            elif attr in c_attrs:
                diffs.append(
                    DifferenceDetail(
                        field=f"attribute:{attr}",
                        baseline=None,
                        candidate=c_attrs[attr],
                        description=f"Attribute '{attr}' added with value '{c_attrs[attr]}'",
                    )
                )
            else:
                diffs.append(
                    DifferenceDetail(
                        field=f"attribute:{attr}",
                        baseline=b_attrs[attr],
                        candidate=None,
                        description=f"Attribute '{attr}' removed (was '{b_attrs[attr]}')",
                    )
                )

        # 4. Containment: Children
        b_kid_set = set(b_children)
        c_kid_set = set(c_children)

        added_kids = sorted(c_kid_set - b_kid_set, key=str.casefold)
        removed_kids = sorted(b_kid_set - c_kid_set, key=str.casefold)

        child_label = (
            "Plan Component"
            if b_node.type == "Plan"
            else "Rule"
            if b_node.type == "PlanComponent"
            else "child"
        )

        for kid in added_kids:
            diffs.append(
                DifferenceDetail(
                    field="containment:child",
                    baseline=None,
                    candidate=kid,
                    description=f"Added {child_label} containment: '{kid}'",
                )
            )
        for kid in removed_kids:
            diffs.append(
                DifferenceDetail(
                    field="containment:child",
                    baseline=kid,
                    candidate=None,
                    description=f"Removed {child_label} containment: '{kid}'",
                )
            )

        # 5. Containment: Parents
        b_parent_set = set(b_parents)
        c_parent_set = set(c_parents)

        if b_parent_set != c_parent_set:
            parent_label = (
                "Plan"
                if b_node.type == "PlanComponent"
                else "Plan Component"
                if b_node.type == "Rule"
                else "parent"
            )
            b_p_str = ", ".join(sorted(b_parent_set, key=str.casefold)) or "none"
            c_p_str = ", ".join(sorted(c_parent_set, key=str.casefold)) or "none"
            diffs.append(
                DifferenceDetail(
                    field="containment:parent",
                    baseline=sorted(b_parent_set),
                    candidate=sorted(c_parent_set),
                    description=f"Parent {parent_label} changed from '{b_p_str}' to '{c_p_str}'",
                )
            )

        # 6. References
        b_ref_set = set(b_refs)
        c_ref_set = set(c_refs)

        added_refs = sorted(c_ref_set - b_ref_set, key=lambda x: (x[0], x[1].casefold()))
        removed_refs = sorted(b_ref_set - c_ref_set, key=lambda x: (x[0], x[1].casefold()))

        for rel, target in added_refs:
            clean_rel = rel.replace("uses_", "Uses ").replace("outputs_", "Outputs ").replace("_", " ")
            diffs.append(
                DifferenceDetail(
                    field=f"reference:{rel}",
                    baseline=None,
                    candidate=target,
                    description=f"Added reference ({clean_rel}): '{target}'",
                )
            )
        for rel, target in removed_refs:
            clean_rel = rel.replace("uses_", "Uses ").replace("outputs_", "Outputs ").replace("_", " ")
            diffs.append(
                DifferenceDetail(
                    field=f"reference:{rel}",
                    baseline=target,
                    candidate=None,
                    description=f"Removed reference ({clean_rel}): '{target}'",
                )
            )

        return diffs
