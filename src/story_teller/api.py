import json
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from .posting import PostingCopy
from .service import (
    MODELS,
    Settings,
    add_clip,
    approve_revision,
    connect,
    create_run,
    delete_run,
    get_settings,
    request_revision,
    save_settings,
)
from .storage import resolve_artifact


class RunRequest(BaseModel):
    overrides: dict[str, object] = Field(default_factory=dict)


class RevisionRequest(BaseModel):
    kind: str
    note: str = Field(min_length=1, max_length=1000)


class ApprovalRequest(BaseModel):
    revision_no: int


def router(root: Path) -> APIRouter:
    api = APIRouter(prefix="/api/v1")

    @api.get("/models")
    def list_models() -> list[dict[str, str]]:
        return [{"id": f"{provider}/{model}", "provider": provider, "model": model}
                for provider, models in MODELS.items() for model in models]

    @api.get("/settings")
    def read_settings() -> Settings:
        with connect(root) as conn:
            return get_settings(conn)

    @api.put("/settings")
    def update_settings(settings: Settings) -> Settings:
        with connect(root) as conn:
            save_settings(conn, settings)
        return settings

    @api.get("/clips")
    def list_clips() -> list[dict[str, object]]:
        with connect(root) as conn:
            return [dict(row) for row in conn.execute("SELECT id,duration,width,height,created_at FROM clips WHERE active=1 ORDER BY created_at DESC")]

    @api.post("/clips", status_code=201)
    async def upload_clip(file: UploadFile) -> dict[str, object]:
        with connect(root) as conn:
            return await add_clip(conn, root, file)

    @api.delete("/clips/{clip_id}", status_code=204)
    def deactivate_clip(clip_id: str) -> None:
        with connect(root) as conn:
            result = conn.execute("UPDATE clips SET active=0 WHERE id=? AND active=1", (clip_id,))
            conn.commit()
            if not result.rowcount:
                raise HTTPException(404, detail={"code": "clip_not_found", "message": "Clip not found"})

    @api.get("/runs")
    def list_runs() -> list[dict[str, object]]:
        with connect(root) as conn:
            rows = conn.execute("SELECT r.id,r.status,r.theme,r.created_at,r.error,v.model_info_json FROM runs r JOIN revisions v ON v.id=r.current_revision_id ORDER BY r.created_at DESC,r.id DESC LIMIT 100")
            result = []
            for row in rows:
                item = dict(row)
                item["title"] = json.loads(item.pop("model_info_json") or "{}").get("story_title")
                result.append(item)
            return result

    @api.post("/runs", status_code=202)
    def start_run(request: RunRequest) -> dict[str, str]:
        with connect(root) as conn:
            try:
                run_id = create_run(conn, request.overrides, secrets.randbits(31))
            except (ValueError, ValidationError) as exc:
                raise HTTPException(422, detail={"code": "invalid_run", "message": str(exc)}) from exc
        return {"id": run_id, "status": "queued"}

    @api.get("/runs/{run_id}")
    def read_run(run_id: str) -> dict[str, object]:
        with connect(root) as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise HTTPException(404, detail={"code": "run_not_found", "message": "Run not found"})
            result = dict(row)
            result["inputs"] = json.loads(result.pop("inputs_json"))
            result["revisions"] = [dict(r) for r in conn.execute("SELECT id,number,kind,placement,created_at FROM revisions WHERE run_id=? ORDER BY number", (run_id,))]
            return result

    @api.delete("/runs/{run_id}", status_code=204)
    def remove_run(run_id: str) -> None:
        with connect(root) as conn:
            try:
                delete_run(conn, root, run_id)
            except LookupError as exc:
                raise HTTPException(404, detail={"code": "run_not_found", "message": str(exc)}) from exc
            except ValueError as exc:
                raise HTTPException(409, detail={"code": "delete_conflict", "message": str(exc)}) from exc

    @api.get("/runs/{run_id}/revisions/{number}")
    def read_revision(run_id: str, number: int) -> dict[str, object]:
        with connect(root) as conn:
            row = conn.execute("SELECT * FROM revisions WHERE run_id=? AND number=?", (run_id, number)).fetchone()
            if not row:
                raise HTTPException(404, detail={"code": "revision_not_found", "message": "Revision not found"})
            result = dict(row)
            for field in ("evaluation_json", "posting_copy_json", "model_info_json"):
                result[field.removesuffix("_json")] = json.loads(result.pop(field)) if result[field] else None
            copy = result["posting_copy"]
            if isinstance(copy, dict) and "title" not in copy:
                result["posting_copy"] = next(iter(copy.values()), None)
            return result

    @api.post("/runs/{run_id}/revisions", status_code=202)
    def revise(run_id: str, request: RevisionRequest) -> dict[str, int]:
        with connect(root) as conn:
            try:
                number = request_revision(conn, run_id, request.kind, request.note)
            except ValueError as exc:
                raise HTTPException(409, detail={"code": "revision_conflict", "message": str(exc)}) from exc
            return {"number": number}

    @api.put("/runs/{run_id}/revisions/{number}/posting-copy")
    def edit_copy(run_id: str, number: int, copy: PostingCopy) -> dict[str, object]:
        with connect(root) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT r.status,r.current_revision_id,v.id FROM runs r JOIN revisions v ON v.run_id=r.id WHERE r.id=? AND v.number=?", (run_id, number)).fetchone()
            if not row or row["status"] != "awaiting_review" or row["current_revision_id"] != row["id"]:
                raise HTTPException(409, detail={"code": "copy_conflict", "message": "Only current review copy can be edited"})
            conn.execute("UPDATE revisions SET posting_copy_json=? WHERE id=?", (copy.model_dump_json(), row["id"]))
            conn.commit()
        return {"posting_copy": copy.model_dump()}

    @api.post("/runs/{run_id}/retry", status_code=202)
    def retry(run_id: str) -> dict[str, str]:
        with connect(root) as conn:
            result = conn.execute("UPDATE runs SET status='queued',error=NULL WHERE id=? AND status='failed'", (run_id,))
            conn.commit()
            if not result.rowcount:
                raise HTTPException(409, detail={"code": "retry_conflict", "message": "Run is not failed"})
        return {"status": "queued"}

    @api.post("/runs/{run_id}/approve")
    def approve(run_id: str, request: ApprovalRequest) -> dict[str, str]:
        with connect(root) as conn:
            try:
                approve_revision(conn, run_id, request.revision_no)
            except ValueError as exc:
                raise HTTPException(409, detail={"code": "approval_conflict", "message": str(exc)}) from exc
        return {"status": "approved"}

    @api.get("/runs/{run_id}/video")
    def video(run_id: str, download: bool = False) -> FileResponse:
        with connect(root) as conn:
            run = conn.execute("SELECT status,current_revision_id,approved_revision_id FROM runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                raise HTTPException(404, detail={"code": "run_not_found", "message": "Run not found"})
            revision_id = run["approved_revision_id"] if download or run["status"] != "awaiting_review" else run["current_revision_id"]
            row = conn.execute("SELECT video_path,model_info_json FROM revisions WHERE id=?", (revision_id,)).fetchone() if revision_id else None
            if not row or not row["video_path"]:
                raise HTTPException(404, detail={"code": "video_not_ready", "message": "Video is not ready"})
            path = resolve_artifact(root, row["video_path"])
            if not path.is_file():
                raise HTTPException(404, detail={"code": "video_missing", "message": "Video file is missing"})
        filename = None
        if download:
            title = json.loads(row["model_info_json"] or "{}").get("story_title") or "story"
            safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', title).strip(' .') or "story"
            filename = f"{safe_title}.mp4"
        return FileResponse(path, media_type="video/mp4", filename=filename)

    return api
