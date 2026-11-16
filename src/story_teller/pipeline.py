import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .captions import CaptionCue, group_cues, time_words
from .posting import generate_posting_copy
from .render import render_video
from .service import resolve_artifact, selected_model
from .speech import managed_voice, synthesize
from .story import Ollama, OpenAI, StoryDraft, evaluate_story, generate_story, validate_story


def _model(name: str) -> Ollama | OpenAI:
    provider, model = selected_model(name)
    clients = {"ollama": Ollama, "openai": OpenAI}
    try:
        return clients[provider](model)
    except KeyError as exc:
        raise ValueError(f"Unsupported model provider: {provider}") from exc


def _story_note(conn: sqlite3.Connection, revision: sqlite3.Row) -> str | None:
    note = revision["note"]
    if revision["parent_id"]:
        parent = conn.execute("SELECT story FROM revisions WHERE id=?", (revision["parent_id"],)).fetchone()
        return f"Previous story: {parent[0]}. Requested change: {note}"
    return note


def run_stage(stage: str, conn: sqlite3.Connection, root: Path, run: sqlite3.Row, revision: sqlite3.Row) -> None:
    inputs = json.loads(run["inputs_json"])
    revision = conn.execute("SELECT * FROM revisions WHERE id=?", (revision["id"],)).fetchone()
    rel_dir = f"runs/{run['id']}/revisions/{revision['number']}"
    directory = resolve_artifact(root, rel_dir)
    directory.mkdir(parents=True, exist_ok=True)
    models = {"writing": ("writing_model", "ollama/gemma4:12b"),
              "evaluating": ("evaluation_model", "ollama/gemma4:12b"),
              "copy": ("posting_model", "ollama/qwen3:4b-instruct")}
    choice = inputs.get(*models[stage]) if stage in models else None
    llm = _model(choice) if choice else None
    if stage == "writing":
        recent = [row[0] for row in conn.execute("SELECT v.summary FROM revisions v JOIN runs r ON r.approved_revision_id=v.id WHERE v.summary IS NOT NULL ORDER BY r.updated_at DESC LIMIT 20")]
        assert llm is not None
        draft = generate_story(inputs, recent, llm, note=_story_note(conn, revision))
        metadata = {"writer": choice, "writer_prompt": 4, "story_title": draft.title, "word_count": len(draft.script.split()), "estimated_duration_seconds": len(draft.script.split()) * 60 / int(inputs["narration_speed"])}
        conn.execute("UPDATE revisions SET story=?,summary=?,narrator=?,model_info_json=? WHERE id=?", (draft.script, draft.summary, draft.narrator, json.dumps(metadata), revision["id"]))
        conn.commit()
    elif stage == "evaluating":
        recent = [row[0] for row in conn.execute("SELECT v.summary FROM revisions v JOIN runs r ON r.approved_revision_id=v.id WHERE v.summary IS NOT NULL ORDER BY r.updated_at DESC LIMIT 20")]
        metadata = json.loads(revision["model_info_json"] or "{}")
        draft = StoryDraft(script=revision["story"], summary=revision["summary"], narrator=revision["narrator"], title=metadata.get("story_title"))
        assert llm is not None
        metadata.update({"evaluator": choice, "evaluation_prompt": 3})
        for retry in range(3):
            try:
                target_words = round(int(inputs["target_duration"]) * int(inputs["narration_speed"]) / 60)
                validate_story(draft, target_words, recent)
            except ValueError as exc:
                passed = False
                reasons = [str(exc)]
                evaluation_json = json.dumps({"pass": False, "reasons": reasons, "source": "deterministic"})
            else:
                evaluation = evaluate_story(draft, inputs, llm)
                passed = evaluation.passed
                reasons = evaluation.reasons
                evaluation_json = evaluation.model_dump_json(by_alias=True)
            metadata.update({"story_title": draft.title, "word_count": len(draft.script.split()), "estimated_duration_seconds": len(draft.script.split()) * 60 / int(inputs["narration_speed"])})
            conn.execute("UPDATE revisions SET story=?,summary=?,narrator=?,evaluation_json=?,model_info_json=? WHERE id=?", (draft.script, draft.summary, draft.narrator, evaluation_json, json.dumps(metadata), revision["id"]))
            conn.commit()
            if passed:
                break
            if retry == 2:
                raise ValueError("Story failed evaluation after two revisions: " + "; ".join(reasons))
            draft = generate_story(inputs, recent, _model(inputs.get("writing_model", "ollama/gemma4:12b")), note=_story_note(conn, revision), feedback=f"Previous draft: {draft.script}. Evaluation: {'; '.join(reasons)}")
    elif stage == "narrating":
        metadata = json.loads(revision["model_info_json"] or "{}")
        draft = StoryDraft(script=revision["story"], summary=revision["summary"], narrator=revision["narrator"], title=metadata.get("story_title"))
        output = directory / "narration.wav"
        target_seconds = len(draft.script.split()) * 60 / int(inputs["narration_speed"])
        info = synthesize(draft, managed_voice(root, draft.narrator), output, target_seconds)
        conn.execute("UPDATE revisions SET audio_path=?,audio_duration=? WHERE id=?", (f"{rel_dir}/narration.wav", info.duration, revision["id"]))
        conn.commit()
    elif stage == "timing":
        audio = resolve_artifact(root, revision["audio_path"])
        cues = group_cues(time_words(audio, revision["story"]), revision["audio_duration"])
        output = directory / "captions.json"
        output.write_text(json.dumps([asdict(cue) for cue in cues]), encoding="utf-8")
        conn.execute("UPDATE revisions SET captions_path=? WHERE id=?", (f"{rel_dir}/captions.json", revision["id"]))
        conn.commit()
    elif stage == "rendering":
        clip = conn.execute("SELECT path FROM clips WHERE id=?", (run["clip_id"],)).fetchone()
        cues = [CaptionCue(**cue) for cue in json.loads(resolve_artifact(root, revision["captions_path"]).read_text())]
        output = directory / "preview.mp4"
        render_video(resolve_artifact(root, clip[0]), resolve_artifact(root, revision["audio_path"]), cues, revision["placement"], output)
        conn.execute("UPDATE revisions SET video_path=? WHERE id=?", (f"{rel_dir}/preview.mp4", revision["id"]))
        conn.commit()
    elif stage == "copy":
        draft = StoryDraft(script=revision["story"], summary=revision["summary"], narrator=revision["narrator"])
        assert llm is not None
        copy = generate_posting_copy(draft, llm)
        metadata = json.loads(revision["model_info_json"] or "{}")
        metadata.update({"posting": choice, "posting_prompt": 1})
        conn.execute("UPDATE revisions SET posting_copy_json=?,model_info_json=? WHERE id=?", (copy.model_dump_json(), json.dumps(metadata), revision["id"]))
        conn.commit()
    else:
        raise ValueError(f"Unknown stage: {stage}")
