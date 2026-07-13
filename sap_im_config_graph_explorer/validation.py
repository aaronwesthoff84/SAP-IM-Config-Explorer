from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sap_im_config_graph_explorer.models import GraphLink, GraphNode, ValidationFinding


CONTAINMENT_RELATIONSHIPS = {
    "belongs_to_plan",
    "belongs_to_plan_component",
    "parent_child",
}
DEFAULT_UNUSED_EXEMPT_TYPES = frozenset({"Plan"})


@dataclass
class ValidationIndexes:
    duplicate_groups: dict[tuple[str, str], list[GraphNode]]
    inbound_semantic_links: dict[str, list[GraphLink]]
    linked_node_ids: set[str]


class ValidationEngine:
    """Run deterministic graph validation without creating new graph nodes or links."""

    def __init__(
        self,
        unused_exempt_types: Iterable[str] = DEFAULT_UNUSED_EXEMPT_TYPES,
    ) -> None:
        self.unused_exempt_types = frozenset(unused_exempt_types)

    def validate(
        self,
        nodes: list[GraphNode],
        links: list[GraphLink],
        existing_findings: list[ValidationFinding],
    ) -> list[ValidationFinding]:
        indexes = self._build_indexes(nodes, links)
        findings = list(existing_findings)
        findings.extend(self._duplicate_findings(indexes.duplicate_groups))
        findings.extend(self._unused_findings(nodes, indexes.inbound_semantic_links))
        findings.extend(self._orphaned_findings(nodes, indexes.linked_node_ids))
        return findings

    @staticmethod
    def _build_indexes(
        nodes: list[GraphNode],
        links: list[GraphLink],
    ) -> ValidationIndexes:
        node_ids = {node.id for node in nodes}
        duplicate_groups: dict[tuple[str, str], list[GraphNode]] = defaultdict(list)
        inbound_semantic_links: dict[str, list[GraphLink]] = defaultdict(list)
        linked_node_ids: set[str] = set()

        for node in nodes:
            if node.canonicalKey:
                duplicate_groups[(node.snapshotId, node.canonicalKey)].append(node)

        for link in links:
            if link.source not in node_ids or link.target not in node_ids:
                continue
            linked_node_ids.update((link.source, link.target))
            if link.relationship not in CONTAINMENT_RELATIONSHIPS:
                inbound_semantic_links[link.target].append(link)

        return ValidationIndexes(
            duplicate_groups=dict(duplicate_groups),
            inbound_semantic_links=dict(inbound_semantic_links),
            linked_node_ids=linked_node_ids,
        )

    @staticmethod
    def _duplicate_findings(
        duplicate_groups: dict[tuple[str, str], list[GraphNode]],
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for (snapshot_id, canonical_key), members in sorted(duplicate_groups.items()):
            if len(members) < 2:
                continue
            ordered_members = sorted(members, key=lambda node: node.id)
            node_ids = tuple(node.id for node in ordered_members)
            findings.append(
                ValidationFinding(
                    id=_finding_id(
                        snapshot_id,
                        "duplicate_object",
                        canonical_key,
                        *node_ids,
                    ),
                    code="duplicate_object",
                    severity="error",
                    snapshotId=snapshot_id,
                    nodeIds=node_ids,
                    message=(
                        f"Duplicate {ordered_members[0].type} object: {canonical_key}"
                    ),
                    details={
                        "canonicalKey": canonical_key,
                        "nodeCount": len(node_ids),
                        "sourceFiles": sorted(
                            {node.sourceFile for node in ordered_members}
                        ),
                    },
                )
            )
        return findings

    def _unused_findings(
        self,
        nodes: list[GraphNode],
        inbound_semantic_links: dict[str, list[GraphLink]],
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for node in _ordered_nodes(nodes):
            if node.type in self.unused_exempt_types:
                continue
            if inbound_semantic_links.get(node.id):
                continue
            findings.append(
                ValidationFinding(
                    id=_finding_id(node.snapshotId, "unused_object", node.id),
                    code="unused_object",
                    severity="warning",
                    snapshotId=node.snapshotId,
                    nodeIds=(node.id,),
                    message=f"Unused {node.type} object: {node.label}",
                    details={
                        "canonicalKey": node.canonicalKey,
                        "inboundSemanticLinkCount": 0,
                    },
                )
            )
        return findings

    @staticmethod
    def _orphaned_findings(
        nodes: list[GraphNode],
        linked_node_ids: set[str],
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for node in _ordered_nodes(nodes):
            if node.id in linked_node_ids:
                continue
            findings.append(
                ValidationFinding(
                    id=_finding_id(node.snapshotId, "orphaned_object", node.id),
                    code="orphaned_object",
                    severity="warning",
                    snapshotId=node.snapshotId,
                    nodeIds=(node.id,),
                    message=f"Orphaned {node.type} object: {node.label}",
                    details={
                        "canonicalKey": node.canonicalKey,
                        "inboundLinkCount": 0,
                        "outboundLinkCount": 0,
                    },
                )
            )
        return findings


def _ordered_nodes(nodes: list[GraphNode]) -> list[GraphNode]:
    return sorted(nodes, key=lambda node: (node.snapshotId, node.canonicalKey, node.id))


def _finding_id(snapshot_id: str, code: str, *parts: str) -> str:
    payload = "\x1f".join((snapshot_id, code, *parts))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"finding-{digest}"
