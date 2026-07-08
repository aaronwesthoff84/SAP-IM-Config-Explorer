from __future__ import annotations

from pathlib import Path

from sap_im_config_graph_explorer.models import GraphDocument, GraphLink, GraphNode
from sap_im_config_graph_explorer.object_extractors.generic import GenericObjectExtractor
from sap_im_config_graph_explorer.reference_resolver import ReferenceResolver
from sap_im_config_graph_explorer.xml_loader import XmlDocument, load_xml_file, load_xml_text


class GraphBuilder:
    def __init__(self) -> None:
        self.extractor = GenericObjectExtractor()

    def build_from_paths(self, paths: list[str | Path]) -> GraphDocument:
        documents = [load_xml_file(path) for path in paths]
        return self.build_from_documents(documents)

    def build_from_uploads(self, uploads: list[tuple[str, bytes]]) -> GraphDocument:
        documents = [load_xml_text(content, filename) for filename, content in uploads]
        return self.build_from_documents(documents)

    def build_from_documents(self, documents: list[XmlDocument]) -> GraphDocument:
        nodes: list[GraphNode] = []
        node_id_by_element: dict[int, str] = {}
        self.extractor.reset()
        for document in documents:
            doc_nodes, doc_node_map = self.extractor.extract(document)
            nodes.extend(doc_nodes)
            node_id_by_element.update(doc_node_map)
        links = ReferenceResolver(documents, nodes, node_id_by_element).build_links()
        return GraphDocument(nodes=nodes, links=self._valid_links(links, nodes))

    def _valid_links(self, links: list[GraphLink], nodes: list[GraphNode]) -> list[GraphLink]:
        node_ids = {node.id for node in nodes}
        return [
            link
            for link in links
            if link.source in node_ids and (link.target in node_ids or link.target.startswith("unknown:"))
        ]
