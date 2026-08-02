from __future__ import annotations

import codecs
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sap_im_config_graph_explorer.app import app
from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.xml_loader import (
    XmlLoadError,
    load_xml_file,
    load_xml_text,
)


FIXTURES = Path(__file__).parent / "fixtures" / "compatibility"
BASE_TEXT = (FIXTURES / "base_profile.xml").read_text(encoding="utf-8")
NAMESPACE_PATH = FIXTURES / "namespace_profile.xml"
NAMESPACE_URI = "urn:sap:incentive-management:configuration:16.0"

EXPECTED_CANONICAL_GRAPH = {
    "nodes": [
        {
            "label": "Compatibility Component",
            "type": "PlanComponent",
            "xmlPath": "/DATA_IMPORT[1]/PLANCOMPONENT_SET[1]/PLANCOMPONENT[1]",
        },
        {
            "label": "Compatibility Plan",
            "type": "Plan",
            "xmlPath": "/DATA_IMPORT[1]/PLAN_SET[1]/PLAN[1]",
        },
        {
            "label": "Compatibility Rule",
            "type": "Rule",
            "xmlPath": "/DATA_IMPORT[1]/RULE_SET[1]/RULE[1]",
        },
    ],
    "links": [
        {
            "source": "Compatibility Component",
            "target": "Compatibility Plan",
            "relationship": "belongs_to_plan",
            "confidence": "high",
        },
        {
            "source": "Compatibility Rule",
            "target": "Compatibility Component",
            "relationship": "belongs_to_plan_component",
            "confidence": "high",
        },
    ],
    "findings": [],
}


def _encoded_variants() -> list[tuple[str, bytes, str]]:
    utf16_text = BASE_TEXT.replace('encoding="UTF-8"', 'encoding="UTF-16"')
    return [
        ("utf8.xml", BASE_TEXT.encode("utf-8"), "utf-8"),
        ("utf8-bom.xml", codecs.BOM_UTF8 + BASE_TEXT.encode("utf-8"), "utf-8"),
        (
            "utf16-le.xml",
            codecs.BOM_UTF16_LE + utf16_text.encode("utf-16-le"),
            "utf-16-le",
        ),
        (
            "utf16-be.xml",
            codecs.BOM_UTF16_BE + utf16_text.encode("utf-16-be"),
            "utf-16-be",
        ),
        (
            "utf16-le-declaration.xml",
            utf16_text.encode("utf-16-le"),
            "utf-16-le",
        ),
        (
            "utf16-be-declaration.xml",
            utf16_text.encode("utf-16-be"),
            "utf-16-be",
        ),
    ]


def _canonical_graph(graph: dict[str, object]) -> dict[str, object]:
    nodes = graph["nodes"]
    label_by_id = {node["id"]: node["label"] for node in nodes}
    return {
        "nodes": sorted(
            (
                {
                    "label": node["label"],
                    "type": node["type"],
                    "xmlPath": node["xmlPath"],
                }
                for node in nodes
            ),
            key=lambda node: node["label"],
        ),
        "links": sorted(
            (
                {
                    "source": label_by_id[link["source"]],
                    "target": label_by_id[link["target"]],
                    "relationship": link["relationship"],
                    "confidence": link["confidence"],
                }
                for link in graph["links"]
            ),
            key=lambda link: (link["source"], link["target"]),
        ),
        "findings": graph["findings"],
    }


@pytest.mark.parametrize(("filename", "content", "encoding"), _encoded_variants())
def test_supported_encoding_matrix_loads_files_and_uploads_deterministically(
    tmp_path: Path,
    filename: str,
    content: bytes,
    encoding: str,
) -> None:
    path = tmp_path / filename
    path.write_bytes(content)

    file_document = load_xml_file(path)
    upload_document = load_xml_text(content, filename)
    path_graph = GraphBuilder().build_from_paths([path]).to_dict()

    for document in (file_document, upload_document):
        assert document.encoding == encoding
        assert document.namespace_uri is None
        assert document.export_version == "16.0"
        assert document.root.tag == "DATA_IMPORT"
        assert document.raw_text.startswith('<?xml version="1.0"')
    assert _canonical_graph(path_graph) == EXPECTED_CANONICAL_GRAPH


def test_namespace_profile_normalizes_tags_attributes_and_xml_paths() -> None:
    document = load_xml_file(NAMESPACE_PATH)
    graph = GraphBuilder().build_from_paths([NAMESPACE_PATH]).to_dict()

    assert document.namespace_uri == NAMESPACE_URI
    assert document.export_version == "16.0"
    assert document.root.tag == "DATA_IMPORT"
    assert document.root.attrib == {"VERSION": "16.0"}
    assert "sap:DATA_IMPORT" in document.raw_text
    assert _canonical_graph(graph) == EXPECTED_CANONICAL_GRAPH


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        *((filename, content) for filename, content, _encoding in _encoded_variants()),
        ("namespace.xml", NAMESPACE_PATH.read_bytes()),
    ],
)
def test_compatibility_matrix_uploads_produce_the_same_canonical_graph(
    filename: str, content: bytes
) -> None:
    graph = GraphBuilder().build_from_uploads([(filename, content)]).to_dict()

    assert _canonical_graph(graph) == EXPECTED_CANONICAL_GRAPH


def test_snapshot_serializes_source_profiles_in_input_order() -> None:
    utf16_le = _encoded_variants()[2][1]
    graph = GraphBuilder().build_from_uploads(
        [
            ("utf16-le.xml", utf16_le),
            ("namespace.xml", NAMESPACE_PATH.read_bytes()),
        ]
    ).to_dict()

    assert graph["schemaVersion"] == "1.2"
    assert graph["snapshots"] == [
        {
            "id": "configuration",
            "role": "configuration",
            "sourceFiles": ["utf16-le.xml", "namespace.xml"],
            "sourceProfiles": [
                {
                    "sourceFile": "utf16-le.xml",
                    "encoding": "utf-16-le",
                    "namespaceUri": None,
                    "exportVersion": "16.0",
                },
                {
                    "sourceFile": "namespace.xml",
                    "encoding": "utf-8",
                    "namespaceUri": NAMESPACE_URI,
                    "exportVersion": "16.0",
                },
            ],
        }
    ]


@pytest.mark.parametrize(
    ("source_file", "content", "reason"),
    [
        (
            "unsupported-encoding.xml",
            b'<?xml version="1.0" encoding="ISO-8859-1"?>'
            b'<DATA_IMPORT DESCRIPTION="\xe9" />',
            "Unsupported XML encoding in unsupported-encoding.xml: ISO-8859-1.",
        ),
        (
            "malformed-bytes.xml",
            b'<DATA_IMPORT NAME="\xff" />',
            "Unable to decode XML in malformed-bytes.xml as utf-8: invalid byte sequence.",
        ),
        (
            "encoding-mismatch.xml",
            codecs.BOM_UTF16_LE
            + '<?xml version="1.0" encoding="UTF-8"?><DATA_IMPORT />'.encode(
                "utf-16-le"
            ),
            "XML encoding mismatch in encoding-mismatch.xml: declared UTF-8 but detected utf-16-le.",
        ),
        (
            "unsupported-utf32-le.xml",
            codecs.BOM_UTF32_LE + b"<DATA_IMPORT />",
            "Unsupported XML encoding in unsupported-utf32-le.xml: detected utf-32-le BOM.",
        ),
        (
            "unsupported-utf32-be.xml",
            codecs.BOM_UTF32_BE + b"<DATA_IMPORT />",
            "Unsupported XML encoding in unsupported-utf32-be.xml: detected utf-32-be BOM.",
        ),
        (
            "unsupported-profile.xml",
            b"<NOT_DATA_IMPORT />",
            "Unsupported XML profile in unsupported-profile.xml: expected DATA_IMPORT root, found NOT_DATA_IMPORT.",
        ),
    ],
)
def test_unsupported_encodings_bytes_and_profiles_fail_safely(
    source_file: str, content: bytes, reason: str
) -> None:
    with pytest.raises(XmlLoadError) as exc_info:
        load_xml_text(content, source_file)

    assert str(exc_info.value) == reason


def test_decoded_text_rejects_ambiguous_utf16_profile_evidence() -> None:
    with pytest.raises(XmlLoadError) as exc_info:
        load_xml_text(
            '<?xml version="1.0" encoding="UTF-16"?><DATA_IMPORT />',
            "decoded.xml",
        )

    assert str(exc_info.value) == (
        "Ambiguous XML encoding in decoded.xml: declared UTF-16 but decoded text "
        "has no byte-order evidence."
    )


@pytest.mark.parametrize("attribute", ["version", "Version"])
def test_export_version_requires_exact_version_attribute(attribute: str) -> None:
    document = load_xml_text(
        f'<DATA_IMPORT {attribute}="16.0" />', "case-sensitive-version.xml"
    )

    assert document.export_version is None


def test_graph_api_exposes_namespace_profile_and_canonical_graph() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/graph",
        files={
            "files": (
                "namespace.xml",
                NAMESPACE_PATH.read_bytes(),
                "application/xml",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "1.2"
    assert payload["snapshots"][0]["sourceProfiles"] == [
        {
            "sourceFile": "namespace.xml",
            "encoding": "utf-8",
            "namespaceUri": NAMESPACE_URI,
            "exportVersion": "16.0",
        }
    ]
    assert _canonical_graph(payload) == EXPECTED_CANONICAL_GRAPH


def test_graph_api_reports_unsupported_encoding_with_filename() -> None:
    client = TestClient(app)
    content = (
        b'<?xml version="1.0" encoding="Windows-1252"?>'
        b'<DATA_IMPORT DESCRIPTION="\x80" />'
    )

    response = client.post(
        "/api/graph",
        files={"files": ("legacy.xml", content, "application/xml")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "Unsupported XML encoding in legacy.xml: Windows-1252."
    }
