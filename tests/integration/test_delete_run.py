from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from story_teller.app import create_app
from story_teller.service import connect, create_run, request_revision


def _run(conn, root: Path, status: str = "awaiting_review") -> str:
    run_id = create_run(conn, {}, 1)
    conn.execute("UPDATE runs SET status=? WHERE id=?", (status, run_id))
    conn.commit()
    directory = root / "runs" / run_id / "revisions" / "1"
    directory.mkdir(parents=True)
    (directory / "preview.mp4").write_bytes(b"preview")
    return run_id


def test_delete_run_removes_its_revisions_attempts_and_files_only(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        clip = tmp_path / "clips" / "c" / "source.mp4"
        clip.parent.mkdir(parents=True)
        clip.write_bytes(b"clip")
        doomed = _run(conn, tmp_path)
        kept = _run(conn, tmp_path)
        assert request_revision(conn, doomed, "story", "change ending") == 2
        conn.execute("UPDATE runs SET status='failed' WHERE id=?", (doomed,))
        revision = conn.execute("SELECT id FROM revisions WHERE run_id=? AND number=2", (doomed,)).fetchone()[0]
        conn.execute("INSERT INTO stage_attempts(revision_id,stage,attempt,status) VALUES(?, 'writing', 1, 'failed')", (revision,))
        conn.commit()
        second = tmp_path / "runs" / doomed / "revisions" / "2"
        second.mkdir()
        (second / "draft.txt").write_text("draft")
    client = TestClient(create_app(tmp_path))
    assert client.delete(f"/api/v1/runs/{doomed}").status_code == 204
    assert client.get(f"/api/v1/runs/{doomed}").status_code == 404
    assert client.get(f"/api/v1/runs/{kept}").status_code == 200
    assert not (tmp_path / "runs" / doomed).exists()
    assert (tmp_path / "runs" / kept / "revisions" / "1" / "preview.mp4").read_bytes() == b"preview"
    assert clip.read_bytes() == b"clip"
    with connect(tmp_path) as conn:
        assert conn.execute("SELECT count(*) FROM revisions WHERE run_id=?", (doomed,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM stage_attempts WHERE revision_id=?", (revision,)).fetchone()[0] == 0


def test_delete_run_rejects_active_missing_and_unsafe_paths(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = _run(conn, tmp_path, "queued")
    client = TestClient(create_app(tmp_path))
    assert client.delete(f"/api/v1/runs/{run_id}").status_code == 409
    assert client.delete("/api/v1/runs/" + "f" * 32).status_code == 404
    assert client.delete("/api/v1/runs/../clips").status_code != 204
    with connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET status='failed' WHERE id=?", (run_id,))
        conn.commit()
    directory = tmp_path / "runs" / run_id
    outside = tmp_path / "runs" / "other"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    import shutil

    shutil.rmtree(directory)
    directory.symlink_to(outside, target_is_directory=True)
    assert client.delete(f"/api/v1/runs/{run_id}").status_code == 409
    assert (outside / "keep.txt").read_text() == "keep"
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 200


def test_delete_run_keeps_metadata_if_file_move_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = _run(conn, tmp_path)

    def fail_move(self: Path, target: Path) -> Path:
        raise OSError("move failed")

    monkeypatch.setattr(Path, "rename", fail_move)
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    assert client.delete(f"/api/v1/runs/{run_id}").status_code == 500
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 200
    assert (tmp_path / "runs" / run_id / "revisions" / "1" / "preview.mp4").exists()


def test_delete_run_restores_files_if_database_delete_fails(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = _run(conn, tmp_path)
        conn.execute("CREATE TRIGGER prevent_delete BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        conn.commit()
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    assert client.delete(f"/api/v1/runs/{run_id}").status_code == 500
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 200
    assert (tmp_path / "runs" / run_id / "revisions" / "1" / "preview.mp4").read_bytes() == b"preview"
    with connect(tmp_path) as conn:
        assert conn.execute("SELECT count(*) FROM revisions WHERE run_id=?", (run_id,)).fetchone()[0] == 1
