from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from sap_im_config_graph_explorer.models import SourceProfile


class XmlLoadError(ValueError):
    """Raised when a local XML input cannot be loaded safely."""


@dataclass
class XmlDocument:
    source_file: str
    root: ET.Element
    raw_text: str
    path_by_element: dict[int, str]
    encoding: str
    namespace_uri: str | None
    export_version: str | None

    def to_source_profile(self) -> SourceProfile:
        return SourceProfile(
            sourceFile=self.source_file,
            encoding=self.encoding,
            namespaceUri=self.namespace_uri,
            exportVersion=self.export_version,
        )


_XML_DECLARATION_ENCODING = re.compile(
    r"^\s*<\?xml\s+[^>]*\bencoding\s*=\s*(['\"])(?P<encoding>[^'\"]+)\1",
    re.IGNORECASE,
)

_SUPPORTED_ENCODING_ALIASES = {
    "utf8": "utf-8",
    "utf-8": "utf-8",
    "utf16": "utf-16",
    "utf-16": "utf-16",
    "utf16le": "utf-16-le",
    "utf-16le": "utf-16-le",
    "utf-16-le": "utf-16-le",
    "utf16be": "utf-16-be",
    "utf-16be": "utf-16-be",
    "utf-16-be": "utf-16-be",
}


def load_xml_file(path: str | Path) -> XmlDocument:
    path = Path(path)
    if path.suffix.lower() != ".xml":
        raise XmlLoadError(f"Unsupported file type: {path.name}. Only .xml files are supported.")
    if not path.exists():
        raise XmlLoadError(f"XML file not found: {path}")
    return load_xml_text(path.read_bytes(), path.name)


def load_xml_text(raw_text: str | bytes, source_file: str) -> XmlDocument:
    if not source_file.lower().endswith(".xml"):
        raise XmlLoadError(f"Unsupported file type: {source_file}. Only .xml files are supported.")
    if isinstance(raw_text, bytes):
        raw_text, encoding = _decode_xml_bytes(raw_text, source_file)
    else:
        raw_text, encoding = _validate_decoded_text(raw_text, source_file)
    if not raw_text.strip():
        raise XmlLoadError(f"Empty XML file: {source_file}")
    try:
        root = ET.fromstring(raw_text)
    except ET.ParseError as exc:
        raise XmlLoadError(f"Malformed XML in {source_file}: {exc}") from exc
    namespace_uri, root_name = _qualified_name(root.tag)
    if root_name != "DATA_IMPORT":
        raise XmlLoadError(
            f"Unsupported XML profile in {source_file}: expected DATA_IMPORT root, "
            f"found {root_name}."
        )
    export_version = _root_export_version(root)
    _normalize_names(root, source_file)
    return XmlDocument(
        source_file=source_file,
        root=root,
        raw_text=raw_text,
        path_by_element=_build_paths(root),
        encoding=encoding,
        namespace_uri=namespace_uri,
        export_version=export_version,
    )


def _decode_xml_bytes(content: bytes, source_file: str) -> tuple[str, str]:
    if content.startswith(codecs.BOM_UTF32_LE):
        raise XmlLoadError(
            f"Unsupported XML encoding in {source_file}: detected utf-32-le BOM."
        )
    if content.startswith(codecs.BOM_UTF32_BE):
        raise XmlLoadError(
            f"Unsupported XML encoding in {source_file}: detected utf-32-be BOM."
        )
    if content.startswith(codecs.BOM_UTF8):
        decoder = "utf-8-sig"
        detected_encoding = "utf-8"
    elif content.startswith(codecs.BOM_UTF16_LE):
        decoder = "utf-16"
        detected_encoding = "utf-16-le"
    elif content.startswith(codecs.BOM_UTF16_BE):
        decoder = "utf-16"
        detected_encoding = "utf-16-be"
    elif content.startswith(b"<\x00?\x00x\x00m\x00l\x00"):
        decoder = "utf-16-le"
        detected_encoding = "utf-16-le"
    elif content.startswith(b"\x00<\x00?\x00x\x00m\x00l"):
        decoder = "utf-16-be"
        detected_encoding = "utf-16-be"
    else:
        decoder = "utf-8"
        detected_encoding = "utf-8"

    declaration_prefix = content[:1024].decode(decoder, errors="ignore")
    _validate_declared_encoding(
        declaration_prefix, source_file, detected_encoding
    )

    try:
        decoded = content.decode(decoder, errors="strict")
    except UnicodeDecodeError as exc:
        raise XmlLoadError(
            f"Unable to decode XML in {source_file} as {detected_encoding}: "
            "invalid byte sequence."
        ) from exc

    _validate_declared_encoding(decoded, source_file, detected_encoding)
    return decoded, detected_encoding


def _validate_decoded_text(raw_text: str, source_file: str) -> tuple[str, str]:
    if raw_text.startswith("\ufeff"):
        raw_text = raw_text[1:]
    declared = _declared_encoding(raw_text)
    if declared is None:
        return raw_text, "utf-8"
    normalized = _normalize_declared_encoding(declared, source_file)
    if normalized == "utf-16":
        raise XmlLoadError(
            f"Ambiguous XML encoding in {source_file}: declared {declared} but "
            "decoded text has no byte-order evidence."
        )
    return raw_text, normalized


def _validate_declared_encoding(
    raw_text: str, source_file: str, detected_encoding: str
) -> None:
    declared = _declared_encoding(raw_text)
    if declared is None:
        return
    normalized = _normalize_declared_encoding(declared, source_file)
    if normalized == "utf-16" and detected_encoding.startswith("utf-16-"):
        return
    if normalized != detected_encoding:
        raise XmlLoadError(
            f"XML encoding mismatch in {source_file}: declared {declared} but "
            f"detected {detected_encoding}."
        )


def _declared_encoding(raw_text: str) -> str | None:
    match = _XML_DECLARATION_ENCODING.match(raw_text)
    return match.group("encoding") if match else None


def _normalize_declared_encoding(declared: str, source_file: str) -> str:
    normalized = _SUPPORTED_ENCODING_ALIASES.get(
        declared.strip().lower().replace("_", "-")
    )
    if normalized is None:
        raise XmlLoadError(
            f"Unsupported XML encoding in {source_file}: {declared.strip()}."
        )
    return normalized


def _qualified_name(name: str) -> tuple[str | None, str]:
    if name.startswith("{") and "}" in name:
        namespace_uri, local_name = name[1:].split("}", 1)
        return namespace_uri, local_name
    return None, name


def _root_export_version(root: ET.Element) -> str | None:
    for attribute, value in root.attrib.items():
        _, local_name = _qualified_name(attribute)
        if local_name == "VERSION" and value.strip():
            return value.strip()
    return None


def _normalize_names(root: ET.Element, source_file: str) -> None:
    for element in root.iter():
        if isinstance(element.tag, str):
            _, element.tag = _qualified_name(element.tag)

        normalized_attributes: dict[str, str] = {}
        for attribute, value in element.attrib.items():
            _, local_name = _qualified_name(attribute)
            if local_name in normalized_attributes:
                raise XmlLoadError(
                    f"Conflicting namespace-qualified attribute in {source_file}: "
                    f"{local_name}."
                )
            normalized_attributes[local_name] = value
        element.attrib.clear()
        element.attrib.update(normalized_attributes)


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
