import sqlite3
from pathlib import Path

import pytest

from story_teller.storage import migrate, open_db, resolve_artifact


def test_migration_persists_and_enforces_foreign_keys(tmp_path: Path):
    path = tmp_path / "app.sqlite3"
    conn = open_db(path)
    migrate(conn)
    migrate(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert "model_info_json" in {row[1] for row in conn.execute("PRAGMA table_info(revisions)")}
    assert "story_approved_revision_id" in {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.execute("INSERT INTO settings(key, value) VALUES ('defaults', '{}')")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO revisions(id, run_id, number) VALUES ('r', 'missing', 1)")
    conn.close()
    reopened = open_db(path)
    assert reopened.execute("SELECT value FROM settings WHERE key='defaults'").fetchone()[0] == "{}"


@pytest.mark.parametrize("path", ["../secret", "/tmp/secret", "clips/../../secret"])
def test_artifact_paths_cannot_escape_root(tmp_path: Path, path: str):
    with pytest.raises(ValueError):
        resolve_artifact(tmp_path, path)


def test_artifact_path_can_resolve_inside_root(tmp_path: Path):
    assert resolve_artifact(tmp_path, "runs/a/story.txt") == tmp_path / "runs/a/story.txt"


def test_migration_upgrades_existing_version_one_without_losing_rows(tmp_path: Path):
    conn = open_db(tmp_path / "old.sqlite3")
    schema = (Path(__file__).resolve().parents[2] / "src/story_teller/migrations/0001.sql").read_text()
    conn.executescript(schema + "\nPRAGMA user_version=1;")
    conn.execute("INSERT INTO settings(key,value) VALUES('defaults','{}')")
    conn.commit()
    migrate(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert conn.execute("SELECT value FROM settings WHERE key='defaults'").fetchone()[0] == "{}"


def test_migration_upgrades_existing_version_two_without_losing_runs(tmp_path: Path):
    conn = open_db(tmp_path / "old.sqlite3")
    migrations = Path(__file__).resolve().parents[2] / "src/story_teller/migrations"
    conn.executescript((migrations / "0001.sql").read_text() + (migrations / "0002.sql").read_text() + "\nPRAGMA user_version=2;")
    conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c.mp4','sha',1,320,240)")
    conn.execute("INSERT INTO runs(id,status,inputs_json,seed,theme,clip_id) VALUES('r','awaiting_review','{}',1,'mystery','c')")
    conn.commit()
    migrate(conn)
    row = conn.execute("SELECT status,story_approved_revision_id FROM runs WHERE id='r'").fetchone()
    assert tuple(row) == ("awaiting_review", None)
