import json
from pathlib import Path

from story_teller.service import Settings, connect, create_run


def test_default_narration_pace_is_about_1_75_times_reviewed_audio():
    assert Settings().narration_speed == 260


def test_run_resolves_seeded_theme_and_clip(tmp_path: Path):
    with connect(tmp_path) as conn:
        for clip_id in ("a", "b"):
            conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES(?,?,?,?,?,?)", (clip_id, f"clips/{clip_id}/source.mp4", "sha", 10, 320, 240))
        conn.commit()
        run_id = create_run(conn, {}, seed=7)
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        assert row["theme"] != "other"
        assert row["clip_id"] in ("a", "b")
        assert json.loads(row["inputs_json"])["theme"] == row["theme"]
        assert row["status"] == "queued"


def test_run_requires_clip(tmp_path: Path):
    with connect(tmp_path) as conn:
        try:
            create_run(conn, {}, seed=1)
        except ValueError as exc:
            assert "clip" in str(exc).lower()
        else:
            raise AssertionError("Expected missing clip failure")
