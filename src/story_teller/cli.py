import argparse
import fcntl
import multiprocessing
from collections.abc import Sequence
from pathlib import Path

import httpx
import uvicorn

from .app import check_environment, create_app
from .worker import worker_loop

BASE_URL = "http://127.0.0.1:8765"


def _call(method: str, path: str, **kwargs) -> dict:
    response = getattr(httpx, method)(BASE_URL + path, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="story-teller")
    parser.add_argument("command", choices=("preflight", "serve", "generate", "list", "status", "retry"))
    parser.add_argument("--data-root", type=Path, default=Path.home() / "Library/Application Support/StoryTeller")
    parser.add_argument("--theme")
    parser.add_argument("--premise")
    parser.add_argument("--duration", type=int)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    if args.command == "preflight":
        checks = check_environment(args.data_root)
        for check in checks:
            print(f"{'OK' if check.ok else 'MISSING'} {check.name}: {check.detail}")
        return 0 if all(check.ok for check in checks) else 1
    if args.command == "generate":
        overrides = {}
        if args.theme: overrides["theme"] = args.theme
        if args.premise: overrides["premise"] = args.premise
        if args.duration: overrides["target_duration"] = args.duration
        run = _call("post", "/api/v1/runs", json={"overrides": overrides})
        print(f"Queued {run['id']} · review at {BASE_URL}/")
        return 0
    if args.command == "list":
        for run in _call("get", "/api/v1/runs"):
            print(f"{run['id']}  {run['status']}  {run['theme']}")
        return 0
    if args.command in ("status", "retry"):
        if not args.run_id:
            parser.error("--run-id is required")
        result = _call("get" if args.command == "status" else "post", f"/api/v1/runs/{args.run_id}" + ("" if args.command == "status" else "/retry"))
        print(result.get("status"), result.get("error") or "")
        return 0
    args.data_root.mkdir(parents=True, exist_ok=True)
    with (args.data_root / "launcher.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Story Teller is already running")
            return 1
        worker = multiprocessing.get_context("spawn").Process(target=worker_loop, args=(args.data_root,))
        worker.start()
        try:
            uvicorn.run(create_app(args.data_root), host="127.0.0.1", port=8765)
        finally:
            worker.terminate()
            worker.join(timeout=10)
    return 0
