from pathlib import Path

from story_teller.service import connect, create_run
from story_teller.worker import process_next_run, recover_interrupted


def test_recovery_marks_active_stage_retryable(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        revision_id = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        conn.execute("UPDATE runs SET status='narrating' WHERE id=?", (run_id,))
        conn.execute("INSERT INTO stage_attempts(revision_id,stage,attempt,status) VALUES(?,'narrating',1,'running')", (revision_id,))
        conn.commit()
        recover_interrupted(conn)
        assert conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0] == "failed"
        assert conn.execute("SELECT status FROM stage_attempts").fetchone()[0] == "interrupted"


def test_retry_after_promoted_artifact_reuses_completed_stages(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        revision_id = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        for stage in ("writing", "evaluating"):
            conn.execute("INSERT INTO stage_attempts(revision_id,stage,attempt,status) VALUES(?,?,1,'complete')", (revision_id, stage))
        conn.execute("INSERT INTO stage_attempts(revision_id,stage,attempt,status) VALUES(?,'narrating',1,'running')", (revision_id,))
        conn.execute("UPDATE runs SET status='narrating' WHERE id=?", (run_id,))
        conn.commit()
        artifact = tmp_path / "promoted.wav"
        artifact.write_bytes(b"old complete file")
        recover_interrupted(conn)
        conn.execute("UPDATE runs SET status='queued' WHERE id=?", (run_id,))
        conn.commit()
        seen = []

        def stage_fn(stage, conn, root, run, revision):
            seen.append(stage)
            if stage == "narrating":
                assert artifact.read_bytes() == b"old complete file"
                artifact.write_bytes(b"replacement")

        assert process_next_run(conn, tmp_path, stage_fn)
        assert seen == ["narrating", "timing", "rendering", "copy"]
        assert artifact.read_bytes() == b"replacement"
