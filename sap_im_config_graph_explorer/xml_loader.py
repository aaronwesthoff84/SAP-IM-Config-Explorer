from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


class XmlLoadError(ValueError):
    """Raised when a local XML input cannot be loaded safely."""


@dataclass
class XmlDocument:
    source_file: str
    root: ET.Element
    raw_text: str
    path_by_element: dict[int, str]


def load_xml_file(path: str | Path) -> XmlDocument:
    path = Path(path)
    if path.suffix.lower() != ".xml":
        raise XmlLoadError(f"Unsupported file type: {path.name}. Only .xml files are supported.")
    if not path.exists():
        raise XmlLoadError(f"XML file not found: {path}")
    raw_text = path.read_text(encoding="utf-8-sig")
    return load_xml_text(raw_text, path.name)


def load_xml_text(raw_text: str | bytes, source_file: str) -> XmlDocument:
    if not source_file.lower().endswith(".xml"):
        raise XmlLoadError(f"Unsupported file type: {source_file}. Only .xml files are supported.")
    if isinstance(raw_text, bytes):
        raw_text = raw_text.decode("utf-8-sig")
    if not raw_text.strip():
        raise XmlLoadError(f"Empty XML file: {source_file}")
    try:
        root = ET.fromstring(raw_text)
    except ET.ParseError as exc:
        raise XmlLoadError(f"Malformed XML in {source_file}: {exc}") from exc
    return XmlDocument(
        source_file=source_file,
        root=root,
        raw_text=raw_text,
        path_by_element=_build_paths(root),
    )


def _build_paths(root: ET.Element) -> dict[int, str]:
    paths: dict[int, str] = {}

    def visit(element: ET.Element, path: str) -> None:
        paths[id(element)] = path
        tag_counts: dict[str, int] = {}
        for child in list(element):
            tag_counts[child.tag] = tag_counts.get(child.tag, 0) + 1
            visit(child, f"{path}/{child.tag}[{tag_counts[child.tag]}]")

    visit(root, f"/{root.tag}[1]")
    return paths
