from __future__ import annotations

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from sap_im_config_graph_explorer.app import app
from sap_im_config_graph_explorer.ai import (
    AIError,
    get_ai_provider,
    StubAIProvider,
    OpenAIProvider,
)

# Helper XML fixture content
MINIMAL_XML = """<DATA_IMPORT>
    <PLAN NAME="Alpha Plan">
        <PLAN_COMPONENT NAME="Alpha Component"/>
    </PLAN>
</DATA_IMPORT>"""


def test_ai_disabled_by_default(monkeypatch):
    """By default, AI features are disabled (SAP_IM_AI_PROVIDER is unset)."""
    monkeypatch.delenv("SAP_IM_AI_PROVIDER", raising=False)
    provider = get_ai_provider()
    assert provider is None

    # Test the API config endpoint reflects disabled state
    client = TestClient(app)
    response = client.get("/api/ai/config")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["provider"] == ""


def test_stub_provider_generation(monkeypatch):
    """StubAIProvider generates structured mock documentation and identifies source objects correctly."""
    monkeypatch.setenv("SAP_IM_AI_PROVIDER", "stub")
    monkeypatch.setenv("SAP_IM_AI_MODEL", "test-stub-model")

    provider = get_ai_provider()
    assert isinstance(provider, StubAIProvider)
    assert provider.model == "test-stub-model"

    nodes_info = [
        {"id": "p1", "label": "Alpha Plan", "type": "Plan", "canonicalKey": "plan:alpha-plan"},
        {"id": "c1", "label": "Alpha Component", "type": "PlanComponent", "canonicalKey": "plancomponent:alpha-component"}
    ]

    res = provider.generate_documentation("test.xml", b"<xml/>", nodes_info)
    assert res["provider"] == "stub"
    assert res["model"] == "test-stub-model"
    assert "AI-Generated Configuration Draft" in res["draft"]
    assert "Plan: Alpha Plan" in res["draft"]
    assert "PlanComponent: Alpha Component" in res["draft"]
    assert "CRITICAL" in res["draft"]  # Clearly labeled as draft
    assert res["source_objects"] == ["plan:alpha-plan", "plancomponent:alpha-component"]
    assert "requires human review" in res["disclaimer"]


def test_openai_provider_endpoint_validation():
    """OpenAIProvider strictly rejects remote endpoints by default."""
    p1 = OpenAIProvider(endpoint="http://127.0.0.1:11434/v1/chat/completions")
    p2 = OpenAIProvider(endpoint="http://localhost:8080/v1/chat/completions")
    p3 = OpenAIProvider(endpoint="http://[::1]:11434/v1")

    assert p1.endpoint == "http://127.0.0.1:11434/v1/chat/completions"
    assert p2.endpoint == "http://localhost:8080/v1/chat/completions"
    assert p3.endpoint == "http://[::1]:11434/v1"

    with pytest.raises(AIError, match="Remote AI endpoints are rejected by default"):
        OpenAIProvider(endpoint="https://api.openai.com/v1/chat/completions")

    with pytest.raises(AIError, match="Remote AI endpoints are rejected by default"):
        OpenAIProvider(endpoint="https://example.com/api")


def test_openai_provider_missing_endpoint(monkeypatch):
    """Setting provider to openai without endpoint raises AIError."""
    monkeypatch.setenv("SAP_IM_AI_PROVIDER", "openai")
    monkeypatch.delenv("SAP_IM_AI_ENDPOINT", raising=False)
    with pytest.raises(AIError, match="SAP_IM_AI_ENDPOINT is required"):
        get_ai_provider()


def test_openai_provider_generation_flow():
    """OpenAIProvider constructs correctly structured requests and parses OpenAI-compatible responses."""
    endpoint = "http://127.0.0.1:8000/v1/chat/completions"
    provider = OpenAIProvider(endpoint=endpoint, model="gpt-4-local")

    nodes_info = [
        {"id": "p1", "label": "Alpha Plan", "type": "Plan", "canonicalKey": "plan:alpha-plan", "xmlPath": "/DATA_IMPORT[1]/PLAN[1]"}
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "### AI Draft\nDocumented: Alpha Plan"
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        res = provider.generate_documentation("test.xml", b"<xml/>", nodes_info)

        assert res["provider"] == "openai"
        assert res["model"] == "gpt-4-local"
        assert res["draft"] == "### AI Draft\nDocumented: Alpha Plan"
        assert res["source_objects"] == ["plan:alpha-plan"]

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == endpoint
        payload = kwargs["json"]
        assert payload["model"] == "gpt-4-local"
        assert "messages" in payload
        assert payload["messages"][0]["role"] == "system"
        assert "SAP Incentive Management" in payload["messages"][0]["content"]


def test_api_config_endpoint(monkeypatch):
    """GET /api/ai/config returns configuration details correctly."""
    client = TestClient(app)

    monkeypatch.setenv("SAP_IM_AI_PROVIDER", "stub")
    monkeypatch.setenv("SAP_IM_AI_MODEL", "gpt-test")
    response = client.get("/api/ai/config")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["provider"] == "stub"
    assert data["model"] == "gpt-test"

    monkeypatch.setenv("SAP_IM_AI_PROVIDER", "openai")
    monkeypatch.setenv("SAP_IM_AI_ENDPOINT", "https://api.openai.com/v1")
    response = client.get("/api/ai/config")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert "Remote AI endpoints are rejected" in data["privacy_disclaimer"]


def test_api_generate_document_endpoint_disabled(monkeypatch):
    """POST /api/ai/generate-document fails with 400 when AI feature is disabled."""
    monkeypatch.delenv("SAP_IM_AI_PROVIDER", raising=False)
    client = TestClient(app)
    files = {"file": ("minimal.xml", MINIMAL_XML, "text/xml")}
    response = client.post("/api/ai/generate-document", files=files)
    assert response.status_code == 400
    assert "disabled" in response.json()["error"]


def test_api_generate_document_endpoint_enabled(monkeypatch):
    """POST /api/ai/generate-document returns draft with extracted authentic nodes when stub is enabled."""
    monkeypatch.setenv("SAP_IM_AI_PROVIDER", "stub")
    monkeypatch.setenv("SAP_IM_AI_MODEL", "stub-acceptance-model")
    client = TestClient(app)
    files = {"file": ("minimal.xml", MINIMAL_XML, "text/xml")}
    response = client.post("/api/ai/generate-document", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "stub"
    assert data["model"] == "stub-acceptance-model"
    assert "Plan: Alpha Plan" in data["draft"]
    assert "PlanComponent: Alpha Component" in data["draft"]
    assert "plan:alpha-plan" in data["source_objects"]
    assert "plancomponent:alpha-component" in data["source_objects"]


def test_api_generate_document_empty_file(monkeypatch):
    """POST /api/ai/generate-document fails with empty XML file."""
    monkeypatch.setenv("SAP_IM_AI_PROVIDER", "stub")
    client = TestClient(app)
    files = {"file": ("empty.xml", "", "text/xml")}
    response = client.post("/api/ai/generate-document", files=files)
    assert response.status_code == 400
    assert "Empty XML file" in response.json()["error"]
