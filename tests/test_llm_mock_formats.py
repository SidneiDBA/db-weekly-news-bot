import json
import sys
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from llm import call_llm


def test_mock_json_response_is_valid_json(monkeypatch):
    monkeypatch.setenv("USE_OLLAMA", "false")

    response = call_llm("classify this", response_format="json")
    payload = json.loads(response)

    assert payload["db_engine"] == "PostgreSQL"
    assert "relevance" in payload
    assert "production_impact" in payload


def test_mock_markdown_response_is_not_json(monkeypatch):
    monkeypatch.setenv("USE_OLLAMA", "false")

    response = call_llm(
        "- Example article (https://example.com/news)",
        response_format="markdown",
    )

    assert "## 📎 Sources" in response
    assert "https://example.com/news" in response
    with pytest.raises(json.JSONDecodeError):
        json.loads(response)
