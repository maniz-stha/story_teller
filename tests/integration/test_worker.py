from pathlib import Path

from story_teller import worker
from story_teller.service import connect, create_run
from story_teller.worker import process_next_run


def test_worker_runs_each_stage_and_records_attempts(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        seen = []

        def fake(stage, conn, root, run, revision):
            seen.append(stage)

        assert process_next_run(conn, tmp_path, fake)
        assert seen == ["writing", "evaluating", "narrating", "timing", "rendering", "copy"]
        assert conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0] == "awaiting_review"
        assert conn.execute("SELECT COUNT(*) FROM stage_attempts WHERE status='complete'").fetchone()[0] == 6


def test_failed_stage_is_retryable_without_rerunning_success(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)

        def fail(stage, conn, root, run, revision):
            if stage == "timing":
                raise ValueError("transcript mismatch")

        assert process_next_run(conn, tmp_path, fail)
        assert conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0] == "failed"
        conn.execute("UPDATE runs SET status='queued' WHERE id=?", (run_id,))
        conn.commit()
        seen = []
        assert process_next_run(conn, tmp_path, lambda stage, *_: seen.append(stage))
        assert seen == ["timing", "rendering", "copy"]


def test_orphan_worker_exits_before_claiming_another_run(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(worker.os, "getppid", lambda: 1)
    monkeypatch.setattr(worker.time, "sleep", lambda _: (_ for _ in ()).throw(AssertionError("orphan kept running")))
    worker.worker_loop(tmp_path)
