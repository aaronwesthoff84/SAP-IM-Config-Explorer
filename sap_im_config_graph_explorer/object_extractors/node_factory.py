from __future__ import annotations

import hashlib
from collections import defaultdict

from sap_im_config_graph_explorer.models import NODE_TYPES, GraphNode
from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionContext,
    ObjectCandidate,
)
from sap_im_config_graph_explorer.object_extractors.common import (
    normalize_identity,
    trim_raw_xml,
)


class NodeFactory:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.identity_counts: dict[tuple[str, str, str, str], int] = {}
        self.node_id_by_element: dict[int, str] = {}
        self._nodes_by_duplicate_group: dict[
            tuple[str, str], list[GraphNode]
        ] = defaultdict(list)

    def build(
        self, candidates: list[ObjectCandidate], context: ExtractionContext
    ) -> list[GraphNode]:
        for candidate in candidates:
            if candidate.node_type not in NODE_TYPES:
                raise ValueError(f"Unsupported graph node type: {candidate.node_type}")

        nodes: list[GraphNode] = []
        for candidate in candidates:
            element = candidate.element
            source_id = element.get("ID") or element.get("OBJECT_ID")
            identity = normalize_identity(source_id or candidate.label)
            canonical_segments = [normalize_identity(candidate.node_type)]
            scope = normalize_identity(candidate.identity_scope)
            if scope:
                canonical_segments.append(scope)
            canonical_segments.append(identity)
            canonical_key = ":".join(canonical_segments)
            xml_path = context.document.path_by_element[id(element)]

            count_key = (
                context.snapshot_id,
                context.document.source_file,
                canonical_key,
                xml_path,
            )
            occurrence = self.identity_counts.get(count_key, 0) + 1
            self.identity_counts[count_key] = occurrence
            node_id = self._instance_id(
                context.snapshot_id,
                context.document.source_file,
                canonical_key,
                xml_path,
                occurrence,
            )

            metadata = dict(candidate.metadata)
            metadata["tag"] = element.tag
            metadata["attributes"] = dict(element.attrib)
            if source_id:
                metadata["sourceId"] = source_id

            node = GraphNode(
                id=node_id,
                canonicalKey=canonical_key,
                snapshotId=context.snapshot_id,
                label=candidate.label,
                type=candidate.node_type,
                sourceFile=context.document.source_file,
                xmlPath=xml_path,
                rawXml=trim_raw_xml(element),
                metadata=metadata,
            )
            nodes.append(node)
            self.node_id_by_element[id(element)] = node.id
            self._record_duplicate_group(node)

        return nodes

    def finalize(self, nodes: list[GraphNode]) -> None:
        groups: dict[tuple[str, str], list[GraphNode]] = defaultdict(list)
        for node in nodes:
            groups[(node.snapshotId, node.canonicalKey)].append(node)
        for (_, canonical_key), members in groups.items():
            if len(members) > 1:
                for member in members:
                    member.metadata["duplicateKey"] = canonical_key

    def _record_duplicate_group(self, node: GraphNode) -> None:
        group = self._nodes_by_duplicate_group[(node.snapshotId, node.canonicalKey)]
        group.append(node)
        if len(group) > 1:
            for member in group:
                member.metadata["duplicateKey"] = node.canonicalKey

    @staticmethod
    def _instance_id(
        snapshot_id: str,
        source_file: str,
        canonical_key: str,
        xml_path: str,
        occurrence: int,
    ) -> str:
        identity = "\x1f".join(
            (snapshot_id, source_file, canonical_key, xml_path, str(occurrence))
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        return f"node-{digest}"
