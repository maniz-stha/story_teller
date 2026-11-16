import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from story_teller.app import check_environment, create_app
from story_teller.pipeline import _model
from story_teller.posting import PostingCopy
from story_teller.service import Settings, connect, create_run, save_settings
from story_teller.story import Evaluation, Ollama, OpenAI, StoryOutput
from story_teller.worker import process_next_run


def test_model_provider_is_explicit_and_unknown_provider_is_rejected(tmp_path):
    assert isinstance(_model("ollama/gemma4:12b"), Ollama)
    assert isinstance(_model("openai/gpt-6-luna"), OpenAI)
    with pytest.raises(ValueError, match="provider"):
        _model("anthropic/claude-sonnet")
    client = TestClient(create_app(tmp_path))
    options = client.get("/api/v1/models").json()
    assert {option["id"] for option in options} == {
        "ollama/qwen3:4b-instruct", "ollama/gemma4:12b",
        "openai/gpt-6-luna", "openai/gpt-6.1-terra",
    }


def test_models_are_validated_and_frozen(tmp_path):
    with pytest.raises(ValueError, match="Invalid model selection"):
        Settings(writing_model="unknown")
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clip','sha',1,320,240)")
        save_settings(conn, Settings(writing_model="openai/gpt-6-luna"))
        run_id = create_run(conn, {"evaluation_model": "openai/gpt-6.1-terra"}, 1)
        save_settings(conn, Settings())
        frozen = json.loads(conn.execute("SELECT inputs_json FROM runs WHERE id=?", (run_id,)).fetchone()[0])
    assert (frozen["writing_model"], frozen["evaluation_model"], frozen["posting_model"]) == (
        "openai/gpt-6-luna", "openai/gpt-6.1-terra", "ollama/qwen3:4b-instruct")
    client = TestClient(create_app(tmp_path))
    assert "OPENAI_API_KEY" not in client.get("/api/v1/settings").text
    assert client.put("/api/v1/settings", json={**Settings().model_dump(), "openai_api_key": "secret"}).status_code == 422


def test_openai_requires_key_and_validates_structured_response(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("story_teller.story.__file__", str(tmp_path / "src/story_teller/story.py"))
    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        OpenAI("gpt-6-luna").structured("write", StoryOutput)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=test-key\n")
    result = {"title": "A mystery", "narration": "I saw a letter. " * 20,
              "word_count": 80, "estimated_duration_seconds": 30.0,
              "continuity_note": "A letter changed my life.", "narrator": "female"}

    def respond(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert kwargs["json"]["model"] == "gpt-6-luna"
        assert kwargs["json"]["text"]["format"]["strict"] is True
        assert kwargs["json"]["text"]["format"]["schema"]["properties"]["narration"]["maxLength"] == 10000
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}]},
            request=httpx.Request("POST", url))

    with patch("story_teller.story.httpx.post", side_effect=respond) as post:
        assert OpenAI("gpt-6-luna").structured("write", StoryOutput).title == "A mystery"
        assert post.call_count == 1
    result["word_count"] = "invalid"
    with patch("story_teller.story.httpx.post", side_effect=respond) as post:
        with pytest.raises(ValueError, match="did not return valid StoryOutput"):
            OpenAI("gpt-6-luna").structured("write", StoryOutput)
        assert post.call_count == 2


def test_preflight_checks_only_selected_providers(tmp_path, monkeypatch):
    with connect(tmp_path) as conn:
        save_settings(conn, Settings(writing_model="openai/gpt-6-luna", evaluation_model="openai/gpt-6-luna", posting_model="openai/gpt-6-luna"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("story_teller.story.__file__", str(tmp_path / "src/story_teller/story.py"))
    checks = check_environment(tmp_path)
    assert any(check.name == "openai_api_key" and not check.ok for check in checks)
    assert not any(check.name in ("ollama", "ollama_model") for check in checks)


def test_openai_evaluation_schema_limits_reason_count(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def respond(url, **kwargs):
        shape = kwargs["json"]["text"]["format"]["schema"]
        assert shape["properties"]["reasons"]["maxItems"] == 5
        result = {"pass": False, "hook": 3, "coherence": 3, "ending": 3,
                  "resolved": False, "reasons": ["The ending is unresolved."]}
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}]},
            request=httpx.Request("POST", url))

    with patch("story_teller.story.httpx.post", side_effect=respond):
        assert OpenAI("gpt-6-luna").structured("evaluate", Evaluation).reasons == ["The ending is unresolved."]


@pytest.mark.parametrize("schema", [StoryOutput, Evaluation, PostingCopy])
def test_openai_schema_shape_and_refusal(tmp_path, monkeypatch, schema):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def respond(url, **kwargs):
        shape = kwargs["json"]["text"]["format"]["schema"]
        assert shape["additionalProperties"] is False
        assert set(shape["required"]) == set(shape["properties"])
        return httpx.Response(200, json={"status": "completed", "output": [
            {"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]},
            request=httpx.Request("POST", url))

    with patch("story_teller.story.httpx.post", side_effect=respond) as post:
        with pytest.raises(ValueError, match="possibly refused"):
            OpenAI("gpt-6-luna").structured("prompt", schema)
        assert post.call_count == 2


def test_openai_incomplete_response_fails_clearly(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = httpx.Response(200, json={"status": "incomplete", "output": []},
                              request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    with patch("story_teller.story.httpx.post", return_value=response), pytest.raises(
        ValueError, match="response status: incomplete"
    ):
        OpenAI("gpt-6-luna").structured("prompt", StoryOutput)


def test_missing_key_becomes_visible_worker_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("story_teller.story.openai_api_key", lambda: None)
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clip','sha',1,320,240)")
        conn.commit()
        run_id = create_run(conn, {"writing_model": "openai/gpt-6-luna"}, 1)
        assert process_next_run(conn, tmp_path)
        run = conn.execute("SELECT status,error FROM runs WHERE id=?", (run_id,)).fetchone()
    assert run["status"] == "failed"
    assert "OPENAI_API_KEY is required" in run["error"]
