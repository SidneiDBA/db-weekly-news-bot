import json
import sys
from pathlib import Path
from types import SimpleNamespace
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


def test_live_json_path_uses_configured_model_and_extracts_fenced_json(monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout='Here is the result:\n```json\n{"db_engine":"Oracle","topic":"Security","relevance":0.9}\n```\n',
            stderr="",
        )

    monkeypatch.setenv("USE_OLLAMA", "true")
    monkeypatch.setenv("OLLAMA_MODEL", "custom-model")
    monkeypatch.setattr("llm.shutil.which", lambda name: "/usr/local/bin/ollama")
    monkeypatch.setattr("llm.subprocess.run", fake_run)

    response = call_llm("classify this", response_format="json")
    payload = json.loads(response)

    assert commands[0][0] == ["ollama", "run", "custom-model"]
    assert "Return exactly one valid JSON object and nothing else." in commands[0][1]["input"]
    assert payload["db_engine"] == "Oracle"
    assert payload["topic"] == "Security"


def test_live_json_path_normalizes_list_payloads(monkeypatch):
    def fake_run(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout='[{"db_engine":"PostgreSQL","topic":"Release","relevance":0.8}]',
            stderr="",
        )

    monkeypatch.setenv("USE_OLLAMA", "true")
    monkeypatch.setattr("llm.shutil.which", lambda name: "/usr/local/bin/ollama")
    monkeypatch.setattr("llm.subprocess.run", fake_run)

    response = call_llm("classify this", response_format="json")
    payload = json.loads(response)

    assert payload["db_engine"] == "PostgreSQL"
    assert payload["topic"] == "Release"


def test_live_json_path_normalizes_nested_response_object(monkeypatch):
    def fake_run(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout='{"response":{"db_engine":"MySQL","topic":"Performance","relevance":0.8}}',
            stderr="",
        )

    monkeypatch.setenv("USE_OLLAMA", "true")
    monkeypatch.setattr("llm.shutil.which", lambda name: "/usr/local/bin/ollama")
    monkeypatch.setattr("llm.subprocess.run", fake_run)

    response = call_llm("classify this", response_format="json")
    payload = json.loads(response)

    assert payload["db_engine"] == "MySQL"
    assert payload["topic"] == "Performance"
