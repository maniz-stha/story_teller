import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from story_teller import service
from story_teller.app import create_app
from story_teller.service import connect, inspect_video


def test_settings_defaults_and_other_validation(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    settings = client.get("/api/v1/settings").json()
    assert settings["theme"] == "random"
    assert settings["target_duration"] == 90
    assert client.put("/api/v1/settings", json={**settings, "theme": "other"}).status_code == 422
    assert client.put("/api/v1/settings", json={**settings, "theme": "other", "custom_theme": "Lost pets"}).status_code == 200


def test_saved_platform_selection_is_ignored_for_shared_copy(tmp_path: Path):
    with connect(tmp_path) as conn:
        conn.execute("INSERT INTO settings(key,value) VALUES('defaults',?)", ('{"theme":"family conflict","platforms":["youtube"]}',))
        conn.commit()
    client = TestClient(create_app(tmp_path))
    settings = client.get("/api/v1/settings").json()
    assert settings["theme"] == "family conflict"
    assert "platforms" not in settings
    assert client.put("/api/v1/settings", json=settings).status_code == 200


def test_clip_upload_and_deactivation(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-c:v", "libx264", "-y", str(clip)], check=True)
    client = TestClient(create_app(tmp_path / "data"))
    with clip.open("rb") as file:
        uploaded = client.post("/api/v1/clips", files={"file": ("clip.mp4", file, "video/mp4")})
    assert uploaded.status_code == 201
    clip_id = uploaded.json()["id"]
    assert len(client.get("/api/v1/clips").json()) == 1
    assert client.delete(f"/api/v1/clips/{clip_id}").status_code == 204
    assert client.get("/api/v1/clips").json() == []


def test_copied_clips_are_discovered_and_available_for_random_runs(tmp_path: Path):
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-c:v", "libx264", "-y", str(source)], check=True)
    root = tmp_path / "data"
    folder = service.BACKGROUND_DIR
    folder.mkdir(parents=True)
    shutil.copyfile(source, folder / "first.mp4")
    shutil.copyfile(source, folder / "second.mp4")
    client = TestClient(create_app(root))
    clips = client.get("/api/v1/clips").json()
    assert {clip["name"] for clip in clips} == {"first.mp4", "second.mp4"}
    assert len(client.get("/api/v1/clips").json()) == 2
    created = client.post("/api/v1/runs", json={"overrides": {}})
    assert created.status_code == 202
    assert client.get(f"/api/v1/runs/{created.json()['id']}").json()["clip_id"] in {clip["id"] for clip in clips}
    first_id = next(clip["id"] for clip in clips if clip["name"] == "first.mp4")
    selected = client.post("/api/v1/runs", json={"overrides": {}, "clip_id": first_id})
    assert client.get(f"/api/v1/runs/{selected.json()['id']}").json()["clip_id"] == first_id
    (folder / "first.mp4").unlink()
    with connect(root) as conn:
        assert (root / conn.execute("SELECT path FROM clips WHERE id=?", (first_id,)).fetchone()[0]).is_file()
    (folder / "broken.mp4").write_bytes(b"not a video")
    assert {clip["name"] for clip in client.get("/api/v1/clips").json()} == {"second.mp4"}
    next_run = client.post("/api/v1/runs", json={"overrides": {}})
    assert client.get(f"/api/v1/runs/{next_run.json()['id']}").json()["clip_id"] == next(clip["id"] for clip in clips if clip["name"] == "second.mp4")


def test_run_uses_selected_uploaded_clip_and_keeps_it_for_later(tmp_path: Path):
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-c:v", "libx264", "-y", str(source)], check=True)
    root = tmp_path / "data"
    client = TestClient(create_app(root))
    with source.open("rb") as file:
        uploaded = client.post("/api/v1/clips", files={"file": ("source.mp4", file, "video/mp4")})
    assert uploaded.status_code == 201
    clip_id = uploaded.json()["id"]
    assert any(path.is_file() for path in service.BACKGROUND_DIR.iterdir())
    created = client.post("/api/v1/runs", json={"overrides": {}, "clip_id": clip_id})
    assert created.status_code == 202
    assert client.get(f"/api/v1/runs/{created.json()['id']}").json()["clip_id"] == clip_id
    assert len(client.get("/api/v1/clips").json()) == 1
    assert client.post("/api/v1/runs", json={"overrides": {}, "clip_id": "missing"}).status_code == 422


def test_corrupt_clip_and_hostile_origin_rejected(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/v1/clips", files={"file": ("bad.mp4", b"not video", "video/mp4")}).status_code == 422
    assert client.get("/api/v1/settings", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/v1/settings", headers={"Host": "evil.example"}).status_code == 400


def test_clip_with_valid_header_but_truncated_frames_is_rejected(tmp_path: Path):
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:duration=2", "-c:v", "libx264", "-movflags", "+faststart", "-y", str(source)], check=True)
    damaged = source.read_bytes()
    source.write_bytes(damaged[:len(damaged) // 2])
    client = TestClient(create_app(tmp_path / "data"))
    with source.open("rb") as file:
        result = client.post("/api/v1/clips", files={"file": ("source.mp4", file, "video/mp4")})
    assert result.status_code == 422


def test_clip_uses_video_stream_duration_when_source_audio_runs_longer(tmp_path: Path):
    clip = tmp_path / "uneven.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-c:a", "aac", "-y", str(clip)], check=True)
    assert abs(inspect_video(clip)[0] - 1) < .05
