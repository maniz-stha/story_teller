import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import router
from .service import Settings, connect, get_settings
from .story import openai_api_key


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def check_environment(data_root: Path | None = None) -> list[Check]:
    settings = Settings()
    if data_root and (data_root / "story_teller.sqlite3").exists():
        with connect(data_root) as conn:
            settings = get_settings(conn)
    selected = {settings.writing_model, settings.evaluation_model, settings.posting_model}
    local = {name for name in selected if not name.startswith("gpt-")}
    checks = [Check(name, bool(shutil.which(name)), f"{name} executable {'found' if shutil.which(name) else 'is required'}") for name in (("ollama",) if local else ()) + ("ffmpeg", "ffprobe")]
    checks.append(Check("python", sys.version_info[:2] == (3, 11), f"Python {sys.version_info.major}.{sys.version_info.minor} active; 3.11 required"))
    if local:
        try:
            response = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2)
            response.raise_for_status()
            installed = {model["name"] for model in response.json()["models"]}
            missing = local - installed
            checks.append(Check("ollama_model", not missing, "Selected Ollama models installed" if not missing else "Missing Ollama models: " + ", ".join(sorted(missing))))
        except (httpx.HTTPError, ValueError, KeyError):
            checks.append(Check("ollama_model", False, "Ollama service is unavailable"))
    if selected - local:
        has_key = bool(openai_api_key())
        checks.append(Check("openai_api_key", has_key, "OPENAI_API_KEY found" if has_key else "Set OPENAI_API_KEY in an ignored .env file"))
    for narrator in ("female", "male"):
        source = Path(__file__).resolve().parents[2] / "samples" / f"{narrator}_voice_reference.mp3"
        checks.append(Check(f"{narrator}_voice", source.is_file(), str(source)))
    volume = data_root or Path.home() / "Library/Application Support/StoryTeller"
    while not volume.exists():
        volume = volume.parent
    checks.append(Check("disk", shutil.disk_usage(volume).free >= 2 * 1024**3, "At least 2 GB free space required"))
    checks.append(Check("data_root", os.access(volume, os.W_OK), f"Writable data folder required: {volume}"))
    return checks


def create_app(data_root: Path) -> FastAPI:
    data_root.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Story Teller")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_origin(request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in ("http://127.0.0.1:8765", "http://localhost:8765", "http://testserver"):
            return JSONResponse({"detail": {"code": "invalid_origin", "message": "Local origin required"}}, status_code=403)
        return await call_next(request)

    app.include_router(router(data_root))
    assets = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=assets / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(assets / "templates" / "index.html")

    @app.get("/api/v1/preflight")
    def preflight() -> list[Check]:
        return check_environment(data_root)

    return app
