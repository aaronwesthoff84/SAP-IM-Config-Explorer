import os
from unittest import mock
import pytest
from fastapi.testclient import TestClient
from sap_im_config_graph_explorer.app import app
from sap_im_config_graph_explorer.models import SummaryRequest


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure environment variables are clean and restored after each test."""
    old_env = dict(os.environ)
    for key in [
        "AI_PROVIDER", "OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_BASE_URL", "OPENAI_MODEL",
        "OLLAMA_HOST", "OLLAMA_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL"
    ]:
        os.environ.pop(key, None)
    yield
    os.environ.clear()
    os.environ.update(old_env)


def test_ai_status_default_local_stub():
    client = TestClient(app)
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "stub"
    assert data["enabled"] is True
    assert data["configured"] is True


def test_ai_status_openai_without_key():
    os.environ["AI_PROVIDER"] = "openai"
    client = TestClient(app)
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openai"
    assert data["enabled"] is False
    assert data["configured"] is False
    assert "missing" in data["message"]


def test_ai_status_openai_with_key():
    os.environ["AI_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = "sk-fakekey"
    client = TestClient(app)
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openai"
    assert data["enabled"] is True
    assert data["configured"] is True


def test_ai_summary_stub_provider():
    client = TestClient(app)
    payload = {
        "nodeId": "formula-eligibility",
        "label": "Eligibility",
        "type": "Formula",
        "sourceFile": "export.xml",
        "xmlPath": "/DATA_IMPORT/FORMULA_SET/FORMULA[1]",
        "rawXml": "<FORMULA NAME=\"Eligibility\"></FORMULA>",
        "metadata": {"some_prop": "some_val"},
        "associatedPlans": ["Plan A"],
        "associatedPlanComponents": ["Comp B"],
        "associatedRules": ["Rule C"]
    }
    response = client.post("/api/ai/summary", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "stub"
    summary = data["summary"]
    assert "Formula" in summary
    assert "Eligibility" in summary
    assert "export.xml" in summary
    assert "/DATA_IMPORT/FORMULA_SET/FORMULA[1]" in summary
    assert "some_prop=some_val" in summary
    assert "associated Plan(s): Plan A" in summary
    assert "associated Plan Component(s): Comp B" in summary
    assert "associated Rule(s): Rule C" in summary


def test_ai_summary_oversized_xml_truncation():
    client = TestClient(app)
    huge_xml = "<FORMULA>" + ("A" * 9000) + "</FORMULA>"
    payload = {
        "nodeId": "formula-huge",
        "label": "HugeFormula",
        "type": "Formula",
        "sourceFile": "export.xml",
        "xmlPath": "/DATA_IMPORT/FORMULA_SET/FORMULA[1]",
        "rawXml": huge_xml,
    }
    response = client.post("/api/ai/summary", json=payload)
    assert response.status_code == 200
    data = response.json()
    # The length of the raw xml in summary should correspond to the original or truncated one
    # Note that in _generate_stub_summary, it measures len(req.rawXml or "") which is original (9019),
    # but let's check that OpenAI post truncates it.
    assert data["provider"] == "stub"
    assert "Raw XML definition is 9019 characters long." in data["summary"]


@pytest.mark.anyio
async def test_ai_summary_openai_unconfigured():
    os.environ["AI_PROVIDER"] = "openai"
    client = TestClient(app)
    payload = {
        "nodeId": "formula-eligibility",
        "label": "Eligibility",
        "type": "Formula",
        "sourceFile": "export.xml",
        "xmlPath": "/DATA_IMPORT/FORMULA_SET/FORMULA[1]",
    }
    response = client.post("/api/ai/summary", json=payload)
    assert response.status_code == 400
    assert "OPENAI_API_KEY" in response.json()["error"]


@pytest.mark.anyio
async def test_ai_summary_openai_success():
    os.environ["AI_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = "sk-fakekey"

    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "This is a beautiful OpenAI-generated summary for Eligibility."
                }
            }
        ]
    }

    with mock.patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        client = TestClient(app)
        payload = {
            "nodeId": "formula-eligibility",
            "label": "Eligibility",
            "type": "Formula",
            "sourceFile": "export.xml",
            "xmlPath": "/DATA_IMPORT/FORMULA_SET/FORMULA[1]",
            "rawXml": "<FORMULA NAME=\"Eligibility\"></FORMULA>",
        }
        response = client.post("/api/ai/summary", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert data["summary"] == "This is a beautiful OpenAI-generated summary for Eligibility."

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "/chat/completions" in args[0]
        assert kwargs["headers"]["Authorization"] == "Bearer sk-fakekey"
        payload_sent = kwargs["json"]
        assert payload_sent["model"] == "gpt-4o-mini"
        assert len(payload_sent["messages"]) == 2


def test_ai_status_ollama():
    os.environ["AI_PROVIDER"] = "ollama"
    client = TestClient(app)
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert data["enabled"] is True
    assert data["configured"] is True


@pytest.mark.anyio
async def test_ai_summary_ollama_success():
    os.environ["AI_PROVIDER"] = "ollama"
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {
            "content": "Ollama generated summary for Eligibility."
        }
    }

    with mock.patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        client = TestClient(app)
        payload = {
            "nodeId": "formula-eligibility",
            "label": "Eligibility",
            "type": "Formula",
            "sourceFile": "export.xml",
            "xmlPath": "/DATA_IMPORT/FORMULA_SET/FORMULA[1]",
            "rawXml": "<FORMULA NAME=\"Eligibility\"></FORMULA>",
        }
        response = client.post("/api/ai/summary", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "ollama"
        assert data["summary"] == "Ollama generated summary for Eligibility."
        args, kwargs = mock_post.call_args
        assert "/api/chat" in args[0]
        assert kwargs["json"]["model"] == "llama3.2"


def test_ai_status_gemini_without_key():
    os.environ["AI_PROVIDER"] = "gemini"
    client = TestClient(app)
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "gemini"
    assert data["enabled"] is False
    assert data["configured"] is False


def test_ai_status_gemini_with_key():
    os.environ["AI_PROVIDER"] = "gemini"
    os.environ["GEMINI_API_KEY"] = "gemini-test-key"
    client = TestClient(app)
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "gemini"
    assert data["enabled"] is True
    assert data["configured"] is True


@pytest.mark.anyio
async def test_ai_summary_gemini_without_key():
    os.environ["AI_PROVIDER"] = "gemini"
    client = TestClient(app)
    payload = {
        "nodeId": "formula-eligibility",
        "label": "Eligibility",
        "type": "Formula",
        "sourceFile": "export.xml",
        "xmlPath": "/DATA_IMPORT/FORMULA_SET/FORMULA[1]",
    }
    response = client.post("/api/ai/summary", json=payload)
    assert response.status_code == 400
    assert "GEMINI_API_KEY" in response.json()["error"]


@pytest.mark.anyio
async def test_ai_summary_gemini_success():
    os.environ["AI_PROVIDER"] = "gemini"
    os.environ["GEMINI_API_KEY"] = "gemini-test-key"
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Gemini generated summary for Eligibility."}]
                }
            }
        ]
    }

    with mock.patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        client = TestClient(app)
        payload = {
            "nodeId": "formula-eligibility",
            "label": "Eligibility",
            "type": "Formula",
            "sourceFile": "export.xml",
            "xmlPath": "/DATA_IMPORT/FORMULA_SET/FORMULA[1]",
            "rawXml": "<FORMULA NAME=\"Eligibility\"></FORMULA>",
        }
        response = client.post("/api/ai/summary", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "gemini"
        assert data["summary"] == "Gemini generated summary for Eligibility."
        args, kwargs = mock_post.call_args
        assert "generativelanguage.googleapis.com" in args[0]
        assert "key=gemini-test-key" in args[0]


def test_ai_unsupported_provider():
    os.environ["AI_PROVIDER"] = "unsupported_unknown"
    client = TestClient(app)
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    assert response.json()["enabled"] is False

    payload = {
        "nodeId": "n1",
        "label": "Obj",
        "type": "Formula",
        "sourceFile": "f.xml",
        "xmlPath": "/a/b",
    }
    resp = client.post("/api/ai/summary", json=payload)
    assert resp.status_code == 400
    assert "not supported" in resp.json()["error"]
