from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.xml_loader import XmlDocument


@dataclass(frozen=True)
class ExtractionContext:
    snapshot_id: str
    snapshot_role: str
    document: XmlDocument


@dataclass(frozen=True)
class ObjectCandidate:
    element: ET.Element
    node_type: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)
    identity_scope: str = ""


@dataclass(frozen=True)
class ReferenceCandidate:
    source_element: ET.Element
    value: str
    hint: str
    origin: str
    expected_type: str | None = None
    relationship: str | None = None
    reverse: bool = False


@dataclass
class ExtractionBatch:
    objects: list[ObjectCandidate] = field(default_factory=list)
    references: list[ReferenceCandidate] = field(default_factory=list)


class ObjectExtractor(Protocol):
    def matches(self, element: ET.Element) -> bool: ...

    def extract(
        self, element: ET.Element, context: ExtractionContext
    ) -> ExtractionBatch: ...
