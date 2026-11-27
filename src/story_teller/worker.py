import fcntl
import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from .service import connect

StageFn = Callable[[str, sqlite3.Connection, Path, sqlite3.Row, sqlite3.Row], None]
STAGES = ("writing", "evaluating", "narrating", "timing", "rendering", "copy")


def recover_interrupted(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE stage_attempts SET status='interrupted',ended_at=CURRENT_TIMESTAMP WHERE status='running'")
    conn.execute("UPDATE runs SET status='failed',error='Worker interrupted; retry this run' WHERE status IN ('working','writing','evaluating','narrating','timing','rendering','copy')")
    conn.commit()


def process_next_run(conn: sqlite3.Connection, root: Path, stage_fn: StageFn | None = None) -> bool:
    if stage_fn is None:
        from .pipeline import run_stage

        stage_fn = run_stage
    conn.execute("BEGIN IMMEDIATE")
    run = conn.execute("SELECT * FROM runs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
    if run is None:
        conn.commit()
        return False
    conn.execute("UPDATE runs SET status='working',updated_at=CURRENT_TIMESTAMP,error=NULL WHERE id=?", (run["id"],))
    conn.commit()
    revision = conn.execute("SELECT * FROM revisions WHERE id=?", (run["current_revision_id"],)).fetchone()
    stages = ("rendering",) if revision["kind"] == "subtitle_position" else STAGES
    for stage in stages:
        if stage == "narrating" and run["story_approved_revision_id"] != revision["id"]:
            conn.execute("UPDATE runs SET status='awaiting_story_approval',updated_at=CURRENT_TIMESTAMP WHERE id=?", (run["id"],))
            conn.commit()
            return True
        completed = conn.execute("SELECT 1 FROM stage_attempts WHERE revision_id=? AND stage=? AND status='complete'", (revision["id"], stage)).fetchone()
        if completed:
            continue
        attempt = conn.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM stage_attempts WHERE revision_id=? AND stage=?", (revision["id"], stage)).fetchone()[0]
        cursor = conn.execute("INSERT INTO stage_attempts(revision_id,stage,attempt,status) VALUES(?,?,?,'running')", (revision["id"], stage, attempt))
        conn.execute("UPDATE runs SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (stage, run["id"]))
        conn.commit()
        try:
            stage_fn(stage, conn, root, run, revision)
            conn.execute("UPDATE stage_attempts SET status='complete',ended_at=CURRENT_TIMESTAMP WHERE id=?", (cursor.lastrowid,))
            conn.commit()
            revision = conn.execute("SELECT * FROM revisions WHERE id=?", (revision["id"],)).fetchone()
        except Exception as exc:  # noqa: BLE001 - persist any stage failure for retry
            conn.rollback()
            conn.execute("UPDATE stage_attempts SET status='failed',ended_at=CURRENT_TIMESTAMP,error=? WHERE id=?", (str(exc)[:500], cursor.lastrowid))
            conn.execute("UPDATE runs SET status='failed',error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (f"{stage}: {exc}"[:500], run["id"]))
            conn.commit()
            return True
    conn.execute("UPDATE runs SET status='awaiting_review',updated_at=CURRENT_TIMESTAMP WHERE id=?", (run["id"],))
    conn.commit()
    return True


def worker_loop(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with connect(root) as conn:
            recover_interrupted(conn)
        try:
            while os.getppid() != 1:
                with connect(root) as conn:
                    worked = process_next_run(conn, root)
                if not worked:
                    time.sleep(1)
        except KeyboardInterrupt:
            return
