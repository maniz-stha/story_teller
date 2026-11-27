from pathlib import Path

from fastapi.testclient import TestClient

from story_teller.app import create_app
from story_teller.service import connect, create_run


def test_run_revision_approval_and_download_contract(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
    client = TestClient(create_app(tmp_path))
    created = client.post("/api/v1/runs", json={})
    assert created.status_code == 202
    run_id = created.json()["id"]
    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "queued"
    assert client.post(f"/api/v1/runs/{run_id}/approve", json={"revision_no": 1}).status_code == 409
    with connect(tmp_path) as conn:
        rev = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        preview = tmp_path / "preview.mp4"
        preview.write_bytes(b"preview")
        conn.execute("UPDATE revisions SET video_path='preview.mp4',audio_path='audio.wav',captions_path='captions.json' WHERE id=?", (rev,))
        conn.execute("UPDATE runs SET status='awaiting_review' WHERE id=?", (run_id,))
        conn.commit()
    assert client.post(f"/api/v1/runs/{run_id}/revisions", json={"kind": "subtitle_position", "note": "move higher"}).status_code == 202
    assert client.post(f"/api/v1/runs/{run_id}/approve", json={"revision_no": 1}).status_code == 409


def test_story_approval_starts_media_only_for_current_passing_story(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
    client = TestClient(create_app(tmp_path))
    run_id = client.post("/api/v1/runs", json={}).json()["id"]
    with connect(tmp_path) as conn:
        rev = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        conn.execute("UPDATE revisions SET story='I found it',evaluation_json=? WHERE id=?", ('{"pass":true}', rev))
        conn.execute("UPDATE runs SET status='awaiting_story_approval' WHERE id=?", (run_id,))
        conn.commit()
    assert client.get(f"/api/v1/runs/{run_id}/video?download=true").status_code == 404
    assert client.post(f"/api/v1/runs/{run_id}/approve", json={"revision_no": 1}).status_code == 409
    response = client.post(f"/api/v1/runs/{run_id}/approve-story", json={"revision_no": 1})
    assert response.status_code == 202
    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "queued"
    assert client.post(f"/api/v1/runs/{run_id}/approve-story", json={"revision_no": 1}).status_code == 409


def test_approved_video_download_and_shared_copy_validation(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
    client = TestClient(create_app(tmp_path))
    run_id = client.post("/api/v1/runs", json={}).json()["id"]
    with connect(tmp_path) as conn:
        rev = conn.execute("SELECT current_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        (tmp_path / "preview.mp4").write_bytes(b"preview")
        conn.execute("UPDATE revisions SET video_path='preview.mp4',model_info_json=? WHERE id=?", ('{"writer":"qwen3:4b-instruct"}', rev))
        conn.execute("UPDATE runs SET status='awaiting_review' WHERE id=?", (run_id,))
        conn.commit()
    bad_copy = {"title": "Some title", "caption": "Some caption", "hashtags": ["not a hashtag"]}
    assert client.get(f"/api/v1/runs/{run_id}/revisions/1").json()["model_info"]["writer"] == "qwen3:4b-instruct"
    assert client.put(f"/api/v1/runs/{run_id}/revisions/1/posting-copy", json=bad_copy).status_code == 422
    assert client.post(f"/api/v1/runs/{run_id}/approve", json={"revision_no": 1}).status_code == 200
    downloaded = client.get(f"/api/v1/runs/{run_id}/video?download=true")
    assert downloaded.status_code == 200 and downloaded.content == b"preview"
    assert downloaded.headers["content-disposition"] == 'attachment; filename="story.mp4"'
    with connect(tmp_path) as conn:
        conn.execute("UPDATE revisions SET model_info_json=? WHERE id=?", ('{"story_title":"The Clinic: Wrong/Number"}', rev))
        conn.commit()
    titled_download = client.get(f"/api/v1/runs/{run_id}/video?download=true")
    assert titled_download.headers["content-disposition"] == "attachment; filename*=utf-8''The%20Clinic-%20Wrong-Number.mp4"
    assert client.post(f"/api/v1/runs/{run_id}/revisions", json={"kind": "story", "note": "Change the ending"}).status_code == 202
    assert client.get(f"/api/v1/runs/{run_id}/video?download=true").content == b"preview"


def test_copy_edit_claims_write_lock_before_reading_approval_state(tmp_path: Path, monkeypatch):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
    client = TestClient(create_app(tmp_path))
    run_id = client.post("/api/v1/runs", json={}).json()["id"]
    with connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET status='awaiting_review' WHERE id=?", (run_id,))
        conn.commit()
    statements = []
    original_connect = connect

    def traced_connect(root):
        conn = original_connect(root)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr("story_teller.api.connect", traced_connect)
    copy = {"title": "A short title", "caption": "A short caption. What would you do?", "hashtags": ["#story"], "pinned_comment": "Would you keep the secret?"}
    assert client.put(f"/api/v1/runs/{run_id}/revisions/1/posting-copy", json=copy).status_code == 200
    assert client.get(f"/api/v1/runs/{run_id}/revisions/1").json()["posting_copy"] == copy
    first_read = next(i for i, sql in enumerate(statements) if "SELECT r.status" in sql)
    assert any("BEGIN IMMEDIATE" in sql for sql in statements[:first_read])


def test_run_list_uses_current_story_title_and_falls_back_for_older_runs(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        older = create_run(conn, {"theme": "family conflict"}, 1)
        titled = create_run(conn, {"theme": "workplace drama"}, 2)
        conn.execute("UPDATE revisions SET model_info_json=? WHERE id=(SELECT current_revision_id FROM runs WHERE id=?)", ('{"story_title":"My manager took credit for my work"}', titled))
        conn.commit()
    runs = {run["id"]: run for run in TestClient(create_app(tmp_path)).get("/api/v1/runs").json()}
    assert runs[titled]["title"] == "My manager took credit for my work"
    assert runs[older]["title"] is None


def test_older_platform_copy_is_read_as_one_copy(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES('c','clips/c/source.mp4','sha',10,320,240)")
        conn.commit()
        run_id = create_run(conn, {}, 1)
        conn.execute("UPDATE revisions SET posting_copy_json=? WHERE id=(SELECT current_revision_id FROM runs WHERE id=?)", ('{"youtube":{"title":"Old title","caption":"Old caption","hashtags":["#story"]}}', run_id))
        conn.commit()
    assert TestClient(create_app(tmp_path)).get(f"/api/v1/runs/{run_id}/revisions/1").json()["posting_copy"]["title"] == "Old title"
