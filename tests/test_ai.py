import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from sap_im_config_graph_explorer.app import app
from sap_im_config_graph_explorer.ai_provider import (
    check_ai_configuration,
    generate_summary,
    generate_documentation,
    AIProviderError,
)

@pytest.fixture(autouse=True)
def clean_env():
    """Ensure environment is pristine before each test."""
    original_env = dict(os.environ)
    to_delete = ["SAP_IM_AI_ENDPOINT", "SAP_IM_AI_MODEL", "SAP_IM_AI_API_KEY"]
    for key in to_delete:
        os.environ.pop(key, None)
    yield
    os.environ.clear()
    os.environ.update(original_env)


def test_ai_unconfigured_by_default():
    assert check_ai_configuration()[0] is False
    with pytest.raises(AIProviderError) as exc_info:
        generate_summary({"id": "test-node", "label": "test"})
    assert "unconfigured" in str(exc_info.value)


def test_ai_mock_configuration():
    os.environ["SAP_IM_AI_ENDPOINT"] = "http://localhost:11434/v1"
    os.environ["SAP_IM_AI_MODEL"] = "mock"

    configured, msg = check_ai_configuration()
    assert configured is True
    assert msg == ""


def test_ai_remote_endpoint_rejected():
    os.environ["SAP_IM_AI_ENDPOINT"] = "https://api.openai.com/v1"
    os.environ["SAP_IM_AI_MODEL"] = "gpt-4"

    configured, msg = check_ai_configuration()
    assert configured is False
    assert "Remote AI endpoints are rejected" in msg


def test_ai_generate_summary_mock():
    os.environ["SAP_IM_AI_ENDPOINT"] = "http://localhost:11434/v1"
    os.environ["SAP_IM_AI_MODEL"] = "mock"

    node = {
        "id": "formula-1",
        "label": "EligibilityFormula",
        "type": "Formula",
        "sourceFile": "export.xml",
        "xmlPath": "/DATA_IMPORT/FORMULA",
        "rawXml": "<FORMULA NAME='EligibilityFormula'/>",
        "metadata": {"test": "val"}
    }

    res = generate_summary(node)
    assert res["model"] == "mock"
    assert "EligibilityFormula" in res["text"]
    assert "Formula" in res["text"]
    assert "test-val" not in res["text"]  # formatted as bold val
    assert "val" in res["text"]
    assert res["source_identifiers"] == ["formula-1"]
    assert "disclaimer" in res


def test_ai_generate_documentation_mock():
    os.environ["SAP_IM_AI_ENDPOINT"] = "http://localhost:11434/v1"
    os.environ["SAP_IM_AI_MODEL"] = "mock"

    graph_doc = {
        "topologyMode": "core",
        "snapshots": [{"id": "snapshot-1", "role": "configuration"}],
        "nodes": [
            {"id": "node-1", "label": "PlanA", "type": "Plan"},
            {"id": "node-2", "label": "RuleB", "type": "Rule"}
        ],
        "links": [
            {"source": "node-2", "target": "node-1", "relationship": "belongs_to_plan"}
        ],
        "findings": []
    }

    res = generate_documentation(graph_doc)
    assert res["model"] == "mock"
    assert "Plan" in res["text"]
    assert "Rule" in res["text"]
    assert "PlanA" in res["text"]
    assert "RuleB" in res["text"]
    assert "snapshot-1" in res["text"]
    assert res["source_identifiers"] == ["snapshot-1"]


def test_api_ai_config_endpoint():
    client = TestClient(app)

    # 1. Unconfigured
    res = client.get("/api/ai/config")
    assert res.status_code == 200
    assert res.json()["enabled"] is False
    assert "unconfigured" in res.json()["message"]

    # 2. Configured as mock
    os.environ["SAP_IM_AI_ENDPOINT"] = "http://localhost:11434/v1"
    os.environ["SAP_IM_AI_MODEL"] = "mock"
    res = client.get("/api/ai/config")
    assert res.status_code == 200
    assert res.json()["enabled"] is True
    assert res.json()["model"] == "mock"


def test_api_ai_endpoints_with_mock():
    client = TestClient(app)
    os.environ["SAP_IM_AI_ENDPOINT"] = "http://localhost:11434/v1"
    os.environ["SAP_IM_AI_MODEL"] = "mock"

    # Summary
    node = {"id": "node-1", "label": "MyNode", "type": "Rule"}
    res = client.post("/api/ai/summary", json=node)
    assert res.status_code == 200
    assert res.json()["model"] == "mock"
    assert "MyNode" in res.json()["text"]

    # Documentation
    graph_doc = {"topologyMode": "core", "nodes": []}
    res = client.post("/api/ai/documentation", json=graph_doc)
    assert res.status_code == 200
    assert res.json()["model"] == "mock"


@patch("httpx.Client.post")
def test_real_loopback_openai_endpoint_summary(mock_post):
    os.environ["SAP_IM_AI_ENDPOINT"] = "http://127.0.0.1:11434/v1"
    os.environ["SAP_IM_AI_MODEL"] = "llama3"
    os.environ["SAP_IM_AI_API_KEY"] = "secret-key"

    # Mock the HTTP response from OpenAI completion endpoint
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "This is a real generated summary from loopback endpoint."
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    node = {
        "id": "formula-123",
        "label": "MyFormula",
        "type": "Formula"
    }

    res = generate_summary(node)
    assert res["model"] == "llama3"
    assert res["provider"] == "Local OpenAI-Compatible"
    assert res["text"] == "This is a real generated summary from loopback endpoint."

    # Verify endpoint call
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://127.0.0.1:11434/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer secret-key"
    assert kwargs["json"]["model"] == "llama3"
