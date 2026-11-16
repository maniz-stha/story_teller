import json
from pathlib import Path

import pytest

from story_teller.pipeline import run_stage
from story_teller.posting import PostingCopy
from story_teller.service import connect, create_run
from story_teller.speech import AudioInfo
from story_teller.story import Evaluation, StoryDraft


def test_writing_and_evaluation_persist_version(tmp_path: Path, monkeypatch):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        revision = conn.execute("SELECT * FROM revisions WHERE id=?", (run["current_revision_id"],)).fetchone()
        monkeypatch.setattr("story_teller.pipeline.generate_story", lambda *args, **kwargs: StoryDraft(script="I found a hidden letter. " * 78, summary="A hidden letter changes everything", narrator="female", title="The hidden letter"))
        def evaluate(*args, **kwargs):
            assert args[2].model == "gemma4:12b"
            return Evaluation.model_validate({"pass": True, "hook": 4, "coherence": 4, "ending": 4, "resolved": True, "reasons": []})

        monkeypatch.setattr("story_teller.pipeline.evaluate_story", evaluate)
        run_stage("writing", conn, tmp_path, run, revision)
        run_stage("evaluating", conn, tmp_path, run, revision)
        saved = conn.execute("SELECT story,evaluation_json,model_info_json FROM revisions WHERE id=?", (revision["id"],)).fetchone()
        assert saved["story"].startswith("I found")
        assert '"pass":true' in saved["evaluation_json"]
        assert json.loads(saved["model_info_json"])["writer"] == "ollama/gemma4:12b"
        assert json.loads(saved["model_info_json"])["writer_prompt"] == 4
        assert json.loads(saved["model_info_json"])["evaluation_prompt"] == 3
        assert json.loads(saved["model_info_json"])["story_title"] == "The hidden letter"
        assert json.loads(saved["model_info_json"])["word_count"] == 390
        assert json.loads(saved["model_info_json"])["estimated_duration_seconds"] == 90
        assert json.loads(saved["model_info_json"])["evaluator"] == "ollama/gemma4:12b"


def test_rejected_story_stops_before_narration_and_keeps_feedback(tmp_path: Path, monkeypatch):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        revision = conn.execute("SELECT * FROM revisions WHERE id=?", (run["current_revision_id"],)).fetchone()
        conn.execute("UPDATE revisions SET note='Keep the story in the office' WHERE id=?", (revision["id"],))
        conn.commit()
        calls = []

        def generate(*args, **kwargs):
            calls.append(kwargs)
            return StoryDraft(script="I found a hidden letter. " * 78, summary="A hidden letter changes everything", narrator="female")

        monkeypatch.setattr("story_teller.pipeline.generate_story", generate)
        monkeypatch.setattr("story_teller.pipeline.evaluate_story", lambda *args: Evaluation.model_validate({"pass": False, "hook": 4, "coherence": 2, "ending": 3, "resolved": False, "reasons": ["Contradictory timeline"]}))
        run_stage("writing", conn, tmp_path, run, revision)
        with pytest.raises(ValueError, match="failed evaluation"):
            run_stage("evaluating", conn, tmp_path, run, revision)
        assert len(calls) == 3
        assert all("Keep the story in the office" in call["note"] for call in calls)
        assert "Previous draft" in calls[1]["feedback"]
        row = conn.execute("SELECT evaluation_json,audio_path FROM revisions WHERE id=?", (revision["id"],)).fetchone()
        assert "Contradictory timeline" in row["evaluation_json"]
        assert row["audio_path"] is None


def test_off_length_draft_is_revised_before_model_evaluation(tmp_path: Path, monkeypatch):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        revision = conn.execute("SELECT * FROM revisions WHERE id=?", (run["current_revision_id"],)).fetchone()
        drafts = [StoryDraft(script="I left quickly. " * 8, summary="An abrupt departure", narrator="female"), StoryDraft(script="I found a hidden letter. " * 78, summary="A hidden letter changes everything", narrator="female")]
        prompts = []

        def generate(*args, **kwargs):
            prompts.append(kwargs)
            return drafts.pop(0)

        monkeypatch.setattr("story_teller.pipeline.generate_story", generate)
        monkeypatch.setattr("story_teller.pipeline.evaluate_story", lambda *args: Evaluation.model_validate({"pass": True, "hook": 4, "coherence": 4, "ending": 4, "resolved": True, "reasons": []}))
        run_stage("writing", conn, tmp_path, run, revision)
        run_stage("evaluating", conn, tmp_path, run, revision)
        assert len(prompts) == 2
        assert "words" in prompts[1]["feedback"]
        assert len(conn.execute("SELECT story FROM revisions WHERE id=?", (revision["id"],)).fetchone()[0].split()) >= 200


def test_persistently_invalid_draft_is_flagged_without_narration(tmp_path: Path, monkeypatch):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        revision = conn.execute("SELECT * FROM revisions WHERE id=?", (run["current_revision_id"],)).fetchone()
        draft = StoryDraft(script="I left quickly. " * 8, summary="An abrupt departure", narrator="female")
        calls = []
        monkeypatch.setattr("story_teller.pipeline.generate_story", lambda *args, **kwargs: calls.append(1) or draft)
        monkeypatch.setattr("story_teller.pipeline.evaluate_story", lambda *args: pytest.fail("Off-length draft reached LLM evaluator"))
        run_stage("writing", conn, tmp_path, run, revision)
        with pytest.raises(ValueError, match="failed evaluation"):
            run_stage("evaluating", conn, tmp_path, run, revision)
        saved = conn.execute("SELECT story,evaluation_json,audio_path FROM revisions WHERE id=?", (revision["id"],)).fetchone()
        assert len(calls) == 3
        assert saved["story"] == draft.script
        assert "words" in saved["evaluation_json"]
        assert saved["audio_path"] is None


def test_narration_duration_uses_accepted_script_word_count(tmp_path: Path, monkeypatch):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        revision = conn.execute("SELECT * FROM revisions WHERE id=?", (run["current_revision_id"],)).fetchone()
        script = "I found the missing file. " * 76
        conn.execute("UPDATE revisions SET story=?,summary='The file was found.',narrator='female' WHERE id=?", (script, revision["id"]))
        conn.commit()
        targets = []
        monkeypatch.setattr("story_teller.pipeline.managed_voice", lambda *args: tmp_path / "voice.mp3")

        def synthesize(story, voice, output, target):
            targets.append(target)
            output.touch()
            return AudioInfo(output, target)

        monkeypatch.setattr("story_teller.pipeline.synthesize", synthesize)
        run_stage("narrating", conn, tmp_path, run, revision)
        assert targets == [76 * 5 * 60 / 260]


def test_each_stage_uses_its_frozen_model_and_revisions_use_writer(tmp_path: Path, monkeypatch):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clip','sha',1,320,240)")
        conn.commit()
        run_id = create_run(conn, {"writing_model": "openai/gpt-6-luna",
                                   "evaluation_model": "ollama/gemma4:12b",
                                   "posting_model": "openai/gpt-6.1-terra"}, 1)
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        revision = conn.execute("SELECT * FROM revisions WHERE id=?", (run["current_revision_id"],)).fetchone()
        draft = StoryDraft(script="I found a hidden letter. " * 78,
                           summary="A hidden letter changes everything", narrator="female")
        seen = []

        def write(inputs, recent, llm, **kwargs):
            seen.append(("writing", llm.model))
            return draft

        def evaluate(draft, inputs, llm):
            seen.append(("evaluating", llm.model))
            return Evaluation.model_validate({"pass": len(seen) > 2, "hook": 4,
                                              "coherence": 4, "ending": 4,
                                              "resolved": True, "reasons": ["Revise"]})

        def copy(draft, llm):
            seen.append(("copy", llm.model))
            return PostingCopy(title="The hidden letter", caption="A letter changed everything", hashtags=["#story"])

        monkeypatch.setattr("story_teller.pipeline.generate_story", write)
        monkeypatch.setattr("story_teller.pipeline.evaluate_story", evaluate)
        monkeypatch.setattr("story_teller.pipeline.generate_posting_copy", copy)
        for stage in ("writing", "evaluating", "copy"):
            run_stage(stage, conn, tmp_path, run, revision)
        assert seen == [("writing", "gpt-6-luna"), ("evaluating", "gemma4:12b"),
                        ("writing", "gpt-6-luna"), ("evaluating", "gemma4:12b"),
                        ("copy", "gpt-6.1-terra")]
        saved = conn.execute("SELECT model_info_json,posting_copy_json FROM revisions WHERE id=?",
                             (revision["id"],)).fetchone()
        info = json.loads(saved["model_info_json"])
        assert (info["writer"], info["evaluator"], info["posting"]) == (
            "openai/gpt-6-luna", "ollama/gemma4:12b", "openai/gpt-6.1-terra")
        assert json.loads(saved["posting_copy_json"])["title"] == "The hidden letter"
