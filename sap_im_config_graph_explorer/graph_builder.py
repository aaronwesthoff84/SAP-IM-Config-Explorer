from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sap_im_config_graph_explorer.models import (
    NODE_TYPES,
    RELATIONSHIP_TYPES,
    GraphDocument,
    GraphNode,
    Snapshot,
)
from sap_im_config_graph_explorer.object_extractors import (
    ExtractionContext,
    ExtractorRegistry,
    NodeFactory,
    ReferenceCandidate,
    default_registry,
)
from sap_im_config_graph_explorer.reference_resolver import ReferenceResolver
from sap_im_config_graph_explorer.validation import ValidationEngine
from sap_im_config_graph_explorer.xml_loader import (
    XmlDocument,
    load_xml_file,
    load_xml_text,
)


@dataclass(frozen=True)
class SnapshotInput:
    id: str
    role: str
    uploads: list[tuple[str, bytes | str]]


@dataclass(frozen=True)
class _SnapshotDocuments:
    snapshot: Snapshot
    documents: list[XmlDocument]


CORE_GRAPH_NODE_TYPES = frozenset({"Plan", "PlanComponent", "Rule"})
CORE_GRAPH_RELATIONSHIP_TYPES = frozenset(
    {"belongs_to_plan", "belongs_to_plan_component"}
)


class GraphBuilder:
    """Build an allowlisted graph, scoped to the currently enabled topology."""

    def __init__(
        self,
        registry: ExtractorRegistry | None = None,
        validation_engine: ValidationEngine | None = None,
        node_types: Iterable[str] = CORE_GRAPH_NODE_TYPES,
        relationship_types: Iterable[str] = CORE_GRAPH_RELATIONSHIP_TYPES,
    ) -> None:
        self.node_types = frozenset(node_types)
        self.relationship_types = frozenset(relationship_types)
        unsupported_node_types = self.node_types - NODE_TYPES
        unsupported_relationship_types = self.relationship_types - RELATIONSHIP_TYPES
        if unsupported_node_types:
            raise ValueError(
                "Unsupported graph node types: "
                f"{', '.join(sorted(unsupported_node_types))}"
            )
        if unsupported_relationship_types:
            raise ValueError(
                "Unsupported graph relationship types: "
                f"{', '.join(sorted(unsupported_relationship_types))}"
            )
        self.registry = registry if registry is not None else default_registry()
        self.node_factory = NodeFactory()
        self.validation_engine = validation_engine or ValidationEngine()

    def build_from_paths(
        self,
        paths: list[str | Path],
        snapshot_id: str = "configuration",
        role: str = "configuration",
    ) -> GraphDocument:
        documents = [load_xml_file(path) for path in paths]
        return self.build_from_documents(documents, snapshot_id=snapshot_id, role=role)

    def build_from_uploads(
        self,
        uploads: list[tuple[str, bytes | str]],
        snapshot_id: str = "configuration",
        role: str = "configuration",
    ) -> GraphDocument:
        documents = [
            load_xml_text(content, filename) for filename, content in uploads
        ]
        return self.build_from_documents(documents, snapshot_id=snapshot_id, role=role)

    def build_from_documents(
        self,
        documents: list[XmlDocument],
        snapshot_id: str = "configuration",
        role: str = "configuration",
    ) -> GraphDocument:
        snapshot = Snapshot(
            id=snapshot_id,
            role=role,
            sourceFiles=[document.source_file for document in documents],
        )
        return self._build([_SnapshotDocuments(snapshot, documents)])

    def build_snapshots(self, inputs: list[SnapshotInput]) -> GraphDocument:
        snapshot_ids = [snapshot_input.id for snapshot_input in inputs]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("Snapshot IDs must be unique")

        bundles: list[_SnapshotDocuments] = []
        for snapshot_input in inputs:
            documents = [
                load_xml_text(content, filename)
                for filename, content in snapshot_input.uploads
            ]
            bundles.append(
                _SnapshotDocuments(
                    Snapshot(
                        id=snapshot_input.id,
                        role=snapshot_input.role,
                        sourceFiles=[document.source_file for document in documents],
                    ),
                    documents,
                )
            )
        return self._build(bundles)

    def _build(self, bundles: list[_SnapshotDocuments]) -> GraphDocument:
        nodes: list[GraphNode] = []
        references: list[ReferenceCandidate] = []
        self.node_factory.reset()

        for bundle in bundles:
            for document in bundle.documents:
                context = ExtractionContext(
                    snapshot_id=bundle.snapshot.id,
                    snapshot_role=bundle.snapshot.role,
                    document=document,
                )
                batch = self.registry.extract(context)
                nodes.extend(
                    self.node_factory.build(
                        [
                            candidate
                            for candidate in batch.objects
                            if candidate.node_type in self.node_types
                        ],
                        context,
                    )
                )
                references.extend(
                    reference
                    for reference in batch.references
                    if self._reference_is_in_scope(reference)
                )

        self.node_factory.finalize(nodes)
        resolution = ReferenceResolver(
            nodes=nodes,
            references=references,
            node_id_by_element=self.node_factory.node_id_by_element,
        ).resolve()
        findings = self.validation_engine.validate(
            nodes,
            resolution.links,
            resolution.findings,
        )
        return GraphDocument(
            snapshots=[bundle.snapshot for bundle in bundles],
            nodes=nodes,
            links=resolution.links,
            findings=findings,
        )

    def _reference_is_in_scope(self, reference: ReferenceCandidate) -> bool:
        return (
            reference.expected_type in self.node_types
            and reference.relationship in self.relationship_types
        )
