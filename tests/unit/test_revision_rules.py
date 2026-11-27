from pathlib import Path

import pytest

from story_teller import service
from story_teller.service import approve_revision, connect, create_run, request_revision


def test_stale_approval_and_position_revision_reuse_audio(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        current = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        conn.execute("UPDATE runs SET status='awaiting_review' WHERE id=?", (run_id,))
        conn.execute("UPDATE revisions SET story='I saw it',audio_path='runs/a/voice.wav',captions_path='runs/a/captions.json',video_path='runs/a/video.mp4' WHERE id=?", (current,))
        conn.commit()
        number = request_revision(conn, run_id, "subtitle_position", "move captions higher")
        assert number == 2
        row = conn.execute("SELECT * FROM revisions WHERE run_id=? AND number=2", (run_id,)).fetchone()
        assert row["story"] == "I saw it"
        assert row["audio_path"] == "runs/a/voice.wav"
        assert row["placement"] == "upper_middle"
        with pytest.raises(ValueError):
            approve_revision(conn, run_id, 1)


def test_story_revision_invalidates_downstream_artifacts(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        current = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        conn.execute("UPDATE revisions SET story='Old story',audio_path='voice.wav',captions_path='captions.json',video_path='preview.mp4' WHERE id=?", (current,))
        conn.execute("UPDATE runs SET status='awaiting_review' WHERE id=?", (run_id,))
        conn.commit()
        assert request_revision(conn, run_id, "story", "Make the ending more surprising") == 2
        revised = conn.execute("SELECT story,audio_path,captions_path,video_path FROM revisions WHERE run_id=? AND number=2", (run_id,)).fetchone()
        assert tuple(revised) == (None, None, None, None)


def test_new_revision_keeps_previous_approval_pointer(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        first = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        conn.execute("UPDATE revisions SET video_path='first.mp4' WHERE id=?", (first,))
        conn.execute("UPDATE runs SET status='awaiting_review' WHERE id=?", (run_id,))
        conn.commit()
        approve_revision(conn, run_id, 1)
        request_revision(conn, run_id, "story", "Change the ending")
        row = conn.execute("SELECT approved_revision_id,current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()
        assert row["approved_revision_id"] == first
        assert row["current_revision_id"] != first


def test_story_approval_requires_current_passing_revision(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        current = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        conn.execute("UPDATE revisions SET story='I found it',evaluation_json=? WHERE id=?", ('{"pass":false}', current))
        conn.execute("UPDATE runs SET status='awaiting_story_approval' WHERE id=?", (run_id,))
        conn.commit()
        with pytest.raises(ValueError):
            service.approve_story(conn, run_id, 1)
        conn.execute("UPDATE revisions SET evaluation_json=? WHERE id=?", ('{"pass":true}', current))
        conn.commit()
        assert request_revision(conn, run_id, "story", "Change the ending") == 2
        with pytest.raises(ValueError):
            service.approve_story(conn, run_id, 1)
        row = conn.execute("SELECT status,story_approved_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()
        assert row["status"] == "queued"
        assert row["story_approved_revision_id"] is None
