import subprocess
from pathlib import Path

from story_teller.captions import TimedWord
from story_teller.pipeline import run_stage
from story_teller.posting import PostingCopy
from story_teller.service import approve_revision, connect, create_run, request_revision
from story_teller.speech import AudioInfo
from story_teller.story import Evaluation, StoryDraft
from story_teller.worker import process_next_run


def test_generate_reposition_approve_survives_restart(tmp_path: Path, monkeypatch):
    clip = tmp_path / "clips" / "c" / "source.mp4"
    clip.parent.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=0.3", "-y", str(clip)], check=True)
    monkeypatch.setattr("story_teller.pipeline.generate_story", lambda *args, **kwargs: StoryDraft(script="I found a secret. " * 98, summary="A secret found at work", narrator="female"))
    monkeypatch.setattr("story_teller.pipeline.evaluate_story", lambda *args, **kwargs: Evaluation.model_validate({"pass": True, "hook": 4, "coherence": 4, "ending": 4, "resolved": True, "reasons": []}))
    monkeypatch.setattr("story_teller.pipeline.managed_voice", lambda *args: tmp_path / "voice.mp3")

    def fake_synthesize(story, voice, output, target):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-y", str(output)], check=True)
        return AudioInfo(output, 1)

    monkeypatch.setattr("story_teller.pipeline.synthesize", fake_synthesize)
    monkeypatch.setattr("story_teller.pipeline.time_words", lambda *args: [TimedWord("I", 0, .2), TimedWord("found", .2, .4), TimedWord("a", .4, .6), TimedWord("secret.", .6, .8)])
    monkeypatch.setattr("story_teller.pipeline.generate_posting_copy", lambda story, llm: PostingCopy(title="Secret", caption="A secret appeared", hashtags=["#story"]))

    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',0.3,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        assert process_next_run(conn, tmp_path, run_stage)
        assert conn.execute("SELECT posting_copy_json FROM revisions WHERE run_id=? AND number=1", (run_id,)).fetchone()[0].startswith('{"title":')
        first = conn.execute("SELECT audio_path FROM revisions WHERE run_id=? AND number=1", (run_id,)).fetchone()[0]
        assert request_revision(conn, run_id, "subtitle_position", "move higher") == 2
        assert process_next_run(conn, tmp_path, run_stage)
        second = conn.execute("SELECT audio_path,video_path FROM revisions WHERE run_id=? AND number=2", (run_id,)).fetchone()
        assert second["audio_path"] == first
        assert (tmp_path / second["video_path"]).is_file()
        approve_revision(conn, run_id, 2)
    with connect(tmp_path) as conn:
        row = conn.execute("SELECT status,approved_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()
        assert row["status"] == "approved"
        assert row["approved_revision_id"]
