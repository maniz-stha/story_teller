import hashlib
import json
import random
import sqlite3
import subprocess
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .storage import migrate, open_db, resolve_artifact

THEMES = ("workplace drama", "family conflict", "everyday mystery", "betrayal", "wholesome surprise")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    theme: str = "random"
    custom_theme: str | None = Field(default=None, max_length=100)
    target_duration: int = Field(default=90, ge=15, le=180)
    narration_speed: int = Field(default=260, ge=100, le=300)
    tone: str | None = Field(default=None, max_length=120)
    perspective: str = "first person"
    audience: str = Field(default="general adult audience", max_length=100)
    language: str = "English"
    premise: str = Field(default="", max_length=1000)
    avoid: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_choices(self) -> "Settings":
        if self.theme not in (*THEMES, "random", "other"):
            raise ValueError("Invalid theme")
        if self.theme == "other" and not self.custom_theme:
            raise ValueError("Custom theme is required")
        if self.perspective != "first person" or self.language != "English":
            raise ValueError("Only first-person English is validated")
        return self


def connect(root: Path) -> sqlite3.Connection:
    conn = open_db(root / "story_teller.sqlite3")
    migrate(conn)
    return conn


def get_settings(conn: sqlite3.Connection) -> Settings:
    row = conn.execute("SELECT value FROM settings WHERE key='defaults'").fetchone()
    if not row:
        return Settings()
    data = json.loads(row[0])
    data.pop("platforms", None)
    return Settings.model_validate(data)


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    conn.execute("INSERT INTO settings(key,value) VALUES('defaults',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (settings.model_dump_json(),))
    conn.commit()


TONE_BY_THEME = {
    "workplace drama": "believable, tense, emotionally engaging",
    "family conflict": "emotionally engaging, believable",
    "everyday mystery": "suspenseful, believable",
    "betrayal": "tense, emotionally engaging",
    "wholesome surprise": "warm, believable, emotionally engaging",
}


def create_run(conn: sqlite3.Connection, overrides: dict[str, object], seed: int) -> str:
    settings = Settings.model_validate({**get_settings(conn).model_dump(), **overrides})
    rng = random.Random(seed)
    clips = [row[0] for row in conn.execute("SELECT id FROM clips WHERE active=1 ORDER BY id")]
    if not clips:
        raise ValueError("At least one uploaded clip is required")
    theme = rng.choice(THEMES) if settings.theme == "random" else settings.theme
    resolved = settings.model_dump()
    resolved["theme"] = settings.custom_theme if theme == "other" else theme
    resolved["tone"] = settings.tone or TONE_BY_THEME.get(theme, "believable, emotionally engaging")
    run_id = uuid.uuid4().hex
    revision_id = uuid.uuid4().hex
    conn.execute("INSERT INTO runs(id,status,inputs_json,seed,theme,clip_id,current_revision_id) VALUES(?,?,?,?,?,?,?)", (run_id, "queued", json.dumps(resolved), seed, resolved["theme"], rng.choice(clips), revision_id))
    conn.execute("INSERT INTO revisions(id,run_id,number) VALUES(?,?,1)", (revision_id, run_id))
    conn.commit()
    return run_id


def _placement_from_note(note: str, current: str) -> str:
    lowered = note.lower()
    if any(word in lowered for word in ("higher", "up", "upper", "top")):
        return "upper_middle"
    if any(word in lowered for word in ("center", "centre", "middle")):
        return "middle"
    if any(word in lowered for word in ("lower", "down", "bottom")):
        return "lower_middle"
    raise ValueError("Position note must say higher, middle, or lower")


def request_revision(conn: sqlite3.Connection, run_id: str, kind: str, note: str) -> int:
    if kind not in ("story", "subtitle_position") or not note.strip() or len(note) > 1000:
        raise ValueError("Invalid revision request")
    conn.execute("BEGIN IMMEDIATE")
    try:
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not run or run["status"] not in ("awaiting_review", "approved"):
            raise ValueError("Run is not ready for revision")
        parent = conn.execute("SELECT * FROM revisions WHERE id=?", (run["current_revision_id"],)).fetchone()
        number = parent["number"] + 1
        new_id = uuid.uuid4().hex
        if kind == "subtitle_position":
            if not parent["audio_path"] or not parent["captions_path"]:
                raise ValueError("Cannot reposition missing captions")
            placement = _placement_from_note(note, parent["placement"])
            conn.execute("INSERT INTO revisions(id,run_id,number,kind,note,parent_id,story,summary,narrator,evaluation_json,audio_duration,placement,posting_copy_json,audio_path,captions_path,model_info_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (new_id, run_id, number, kind, note, parent["id"], parent["story"], parent["summary"], parent["narrator"], parent["evaluation_json"], parent["audio_duration"], placement, parent["posting_copy_json"], parent["audio_path"], parent["captions_path"], parent["model_info_json"]))
        else:
            conn.execute("INSERT INTO revisions(id,run_id,number,kind,note,parent_id,placement) VALUES(?,?,?,?,?,?,?)", (new_id, run_id, number, kind, note, parent["id"], parent["placement"]))
        conn.execute("UPDATE runs SET current_revision_id=?,status='queued',error=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_id, run_id))
        conn.commit()
        return number
    except Exception:
        conn.rollback()
        raise


def approve_revision(conn: sqlite3.Connection, run_id: str, revision_no: int) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        revision = conn.execute("SELECT * FROM revisions WHERE run_id=? AND number=?", (run_id, revision_no)).fetchone()
        if not run or not revision or run["status"] != "awaiting_review" or run["current_revision_id"] != revision["id"] or not revision["video_path"]:
            raise ValueError("Only the latest complete preview can be approved")
        conn.execute("UPDATE runs SET status='approved',approved_revision_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (revision["id"], run_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def inspect_video(path: Path) -> tuple[float, int, int]:
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration:format=duration", "-of", "json", str(path)], capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    duration = float(stream.get("duration") or info["format"]["duration"])
    width, height = int(stream["width"]), int(stream["height"])
    if duration <= 0 or width <= 0 or height <= 0:
        raise ValueError("Invalid video")
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-an", "-f", "null", "-", "-progress", "pipe:1", "-nostats"],
        capture_output=True,
        text=True,
        check=True,
        timeout=min(600, max(30, duration * 1.2)),
    )
    times = [int(line.split("=", 1)[1]) / 1_000_000 for line in decoded.stdout.splitlines() if line.startswith("out_time_us=")]
    if not times or times[-1] < duration - .25:
        raise ValueError("Video ends before declared duration")
    return duration, width, height


async def add_clip(conn: sqlite3.Connection, root: Path, upload: UploadFile) -> dict[str, object]:
    clip_id = uuid.uuid4().hex
    relative = f"clips/{clip_id}/source.mp4"
    path = resolve_artifact(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("wb") as out:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > 500 * 1024 * 1024:
                    raise ValueError("Clip exceeds 500 MB")
                digest.update(chunk)
                out.write(chunk)
        duration, width, height = inspect_video(path)
    except (OSError, ValueError, KeyError, IndexError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, detail={"code": "invalid_clip", "message": "Clip must be a decodable video under 500 MB"}) from exc
    conn.execute("INSERT INTO clips(id,path,sha256,duration,width,height) VALUES(?,?,?,?,?,?)", (clip_id, relative, digest.hexdigest(), duration, width, height))
    conn.commit()
    return {"id": clip_id, "duration": duration, "width": width, "height": height}
