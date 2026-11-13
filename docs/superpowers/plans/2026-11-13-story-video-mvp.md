# Story Video MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a local, on-demand app that creates, reviews, revises, approves, and exports narrated portrait story videos and posting copy.

**Architecture:** One FastAPI server and one supervised worker process share SQLite state and managed local media. Ollama handles story, evaluation, revision, and posting copy; local speech, word timing, and FFmpeg handle media. The CLI calls the same loopback API as the web UI.

**Tech Stack:** Python 3.11, uv, FastAPI with Pydantic v2, server-rendered HTML, SQLite (`sqlite3`), Ollama HTTP API, a benchmark-selected local Chatterbox model, `faster-whisper`, FFmpeg/ffprobe, pytest, Ruff, mypy.

**Spec:** `docs/product-requirements.md` and `docs/architecture-proposal.md`.

## Global Constraints

- **Approval gate:** The owner approved the architecture on 2026-11-13. This plan is documentation only; review its milestones and execution method before starting product code, scaffolding, dependency setup, or the benchmark.
- Phase one is local, single-user, on-demand, and fully local for inference. No scheduling, cloud API, automatic publishing, agent framework, Redis, or Celery.
- Validated defaults: English, first person, 90-second audio target, 180 words/minute, female narrator unless the story explicitly identifies a male narrator. Use the five named themes for random selection; `other` requires a custom theme.
- The output video ends with the **final story audio**. Trim longer clips; loop and trim shorter clips. Allow only frame/codec rounding. Target 1080 × 1920 H.264/AAC with burned-in captions.
- Captions default to five-to-seven-word groups, shorter at natural breaks. Story feedback invalidates story and all downstream artifacts; subtitle-position feedback rerenders only.
- Preserve approved output; only the current reviewable revision may be approved. Treat Ollama output and uploaded files as untrusted. Bind HTTP to `127.0.0.1`.
- Use Pydantic v2 for API and Ollama JSON shape/type validation. Run separate deterministic story and media checks; a schema-valid response is not automatically accepted.
- The current `samples/` scripts and media are references, not production modules. Keep runtime files outside Git.

## Review Focus

1. A long or short landscape clip must produce a portrait MP4 ending with the final audio; Task 9 tests both branches.
2. Transcription that omits or changes story words must stop before rendering; Task 8 tests this.
3. A worker interrupted between artifact creation and DB update must retry without replacing approved files; Task 5 tests this.
4. A stale revision or simultaneous change request must receive `409`, never approve an old preview; Task 10 tests this.
5. Corrupt uploads, path traversal, or a hostile browser origin must be rejected; Tasks 3 and 4 test these boundaries.

## File Map

| File or directory | Responsibility |
| --- | --- |
| `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md` | Reproducible Python 3.11 setup, local commands, runtime exclusions. |
| `src/story_teller/app.py`, `api.py`, `cli.py`, `templates/`, `static/` | Loopback server, JSON API, CLI client, local review UI. |
| `src/story_teller/service.py`, `worker.py`, `pipeline.py` | Input resolution, lifecycle and approval rules, single worker, stage ordering. |
| `src/story_teller/storage.py`, `migrations/0001.sql` | SQLite schema, transactions, managed media paths. |
| `src/story_teller/story.py`, `posting.py` | Ollama story/evaluation/revision and platform posting copy. |
| `src/story_teller/speech.py`, `captions.py`, `render.py` | Local TTS, word timing/cues, FFmpeg/ffprobe rendering. |
| `tests/unit/`, `tests/integration/`, `tests/fixtures/` | Fast deterministic tests, API/worker/media tests, tiny generated media. |
| `docs/model-benchmark.md` | Chosen model/voice evidence, throughput, audio quality, timing findings. |

These are responsibility boundaries, not a requirement to add empty modules. Each task creates a file when it first needs it. Do not change existing `samples/` files as part of the MVP.

---

## Milestone 0 — Approval and local feasibility

**Dependency:** Owner reviews this plan and selects an execution method. **Exit:** Exact Ollama and speech models, Python environment, suitability of the supplied voice references, and performance threshold are recorded before the main implementation.

### Task 1: Qualify the local model chain

**Files:** Create `docs/model-benchmark.md`; no production code.

**Interfaces:** Consumes the PRD's 90-second / ~270-word target and `samples/female_voice_reference.mp3` / `samples/male_voice_reference.mp3`. Produces model names and versions, measured synthesis/transcription times, audio duration, and a go/no-go decision for Chatterbox plus faster-whisper.

- [ ] Record available CPU/GPU memory, Python 3.11 availability, Ollama model, FFmpeg build, free disk space, and provenance/checksums of the two supplied MP3 references. Leave their sample originals untouched.
- [ ] Synthesize a complete female and male sample, time the **final** audio locally, and inspect transcript agreement with the source text.
- [ ] Listen to both voices, measure runtime and actual duration, and record any clipping, missing words, or timing drift in `docs/model-benchmark.md`.
- [ ] Choose and pin the working versions. If Chatterbox fails, stop and bring a local TTS alternative back for an architecture amendment; do not silently replace the approved engine.

## Milestone 1 — Local foundation and durable data

**Exit:** A loopback app starts, preflight reports missing tools, uploaded media is validated, and SQLite migrations preserve state across restarts.

### Task 2: Package, loopback app, and preflight

**Files:** Create `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md`, `src/story_teller/app.py`, `src/story_teller/cli.py`, `tests/unit/test_preflight.py`.

**Interfaces:** `create_app(data_root: Path) -> FastAPI`; `check_environment() -> list[Check]` with `Check` defined in `app.py` as a name/status result; CLI `main(argv: Sequence[str] | None = None) -> int`.

- [ ] Add the runtime and development dependencies to `pyproject.toml`; run `uv sync --python 3.11 --group dev` and confirm `.venv/bin/python` reports Python 3.11 and `uv.lock` exists.
- [ ] Write `test_preflight.py::test_missing_ollama_is_reported` and `::test_missing_ffmpeg_is_reported`; assert clear failed checks. Run `.venv/bin/python -m pytest tests/unit/test_preflight.py -q` and confirm failure.
- [ ] Implement the smallest app/CLI bootstrap and preflight. Pin dependencies; do not install unrelated agent or queue libraries.
- [ ] Run the focused tests and confirm pass. Verify the app binds to `127.0.0.1`; worker and launcher locking arrive in Task 5.
- [ ] Document setup/start/stop commands in `README.md`; commit the milestone task with the tests.

### Task 3: SQLite state and managed files

**Files:** Create `src/story_teller/storage.py`, `src/story_teller/migrations/0001.sql`, `tests/integration/test_storage.py`.

**Interfaces:** `open_db(path: Path) -> sqlite3.Connection`, `migrate(conn: sqlite3.Connection) -> None`, `resolve_artifact(root: Path, relative_path: str) -> Path`. Schema: `settings`, `clips`, `runs`, `revisions`, `stage_attempts` as specified in the architecture.

- [ ] Write tests for migration idempotency, foreign keys, WAL mode, preserved rows after reopen, and `resolve_artifact` rejecting `../` or absolute paths; run and confirm failure.
- [ ] Implement versioned SQL migration and managed directories using SQLite transactions and relative paths. Keep large media out of SQLite.
- [ ] Run `.venv/bin/python -m pytest tests/integration/test_storage.py -q`; confirm pass and that a fresh DB can be reopened without data loss.
- [ ] Commit schema, storage, and tests together.

### Task 4: Clip library and settings API

**Files:** Create `src/story_teller/api.py`; modify `app.py`, `service.py` (create when first needed); test `tests/integration/test_api_inputs.py`.

**Interfaces:** `GET/PUT /api/v1/settings`; `GET/POST/DELETE /api/v1/clips`. API accepts IDs and validated values, never arbitrary filesystem paths.

- [ ] Write tests for defaults, theme `other` without a custom value (`422`), one valid clip, corrupt/oversized media (`422`), hostile `Origin`/`Host`, and deactivation without deleting media referenced by a run; run and confirm failure.
- [ ] Implement Pydantic v2 request models for settings and run inputs, plus clip upload via bounded file copy and ffprobe inspection. Require JSON for non-upload mutations; return stable error codes.
- [ ] Run `.venv/bin/python -m pytest tests/integration/test_api_inputs.py -q` and confirm pass; inspect managed file paths.
- [ ] Commit API, service, and test changes.

## Milestone 2 — Runs, queue, and recovery

**Exit:** CLI and web/API submissions share resolved inputs; the single worker records stage progress, survives interruption, and never duplicates an approved artifact.

### Task 5: Run lifecycle and worker with fake stages

**Files:** Create `src/story_teller/worker.py`, `pipeline.py`; modify `service.py`, `api.py`, `cli.py`; test `tests/unit/test_lifecycle.py`, `tests/integration/test_worker.py`.

**Interfaces:** `create_run(conn: Connection, overrides: dict[str, object], seed: int) -> str`; `process_next_run(conn: Connection, data_root: Path) -> bool`; `POST/GET /api/v1/runs`, `GET /api/v1/runs/{id}`, CLI `generate` and `list`.

- [ ] Write tests for seeded theme/clip selection (excluding random `other`), resolved input snapshot, FIFO single-job claim, stage progress, a crash after artifact promotion but before DB completion, retry from the interrupted stage, and duplicate-launcher rejection; run and confirm failure.
- [ ] Implement queue claim in a short transaction, stage-attempt records, atomic artifact promotion, restart detection, and explicit retry. Use fake stage outputs in tests; no model call yet.
- [ ] Run `.venv/bin/python -m pytest tests/unit/test_lifecycle.py tests/integration/test_worker.py -q`; confirm pass. Exercise CLI against the local test server.
- [ ] Commit the lifecycle, worker, API, CLI, and tests.

## Milestone 3 — Creative pipeline

**Exit:** A run produces a validated story and posting copy or a flagged story draft, with no audio work on a failed story.

### Task 6: Ollama story, evaluator, and revision loop

**Files:** Create `src/story_teller/story.py`; modify `pipeline.py`, `worker.py`; test `tests/unit/test_story.py`, `tests/integration/test_story_pipeline.py`.

**Interfaces:** `generate_story(inputs: ResolvedInputs, recent: list[str]) -> StoryDraft`; `evaluate_story(draft: StoryDraft, inputs: ResolvedInputs) -> Evaluation`; `revise_story(draft: StoryDraft, feedback: Evaluation, note: str | None) -> StoryDraft`. Define `ResolvedInputs`, `StoryDraft`, and `Evaluation` in `story.py` before downstream tasks use them.

- [ ] Write tests for missing/extra Ollama fields, malformed JSON, invalid narrator identity or evaluation rating, schema-valid but off-target word count/perspective, automatic rejection/revision (maximum two revisions), and a persistent flagged draft after failure; run and confirm failure.
- [ ] Define Pydantic v2 story and evaluation models with strict fields and forbidden extras, send each model's JSON Schema to Ollama, then validate the returned JSON. Apply deterministic word-budget, perspective, and novelty checks after schema validation. Record prompt/model versions and evaluator reasons; use approved-story summaries for recent-plot context. Bound malformed-output retries before a visible failure.
- [ ] Run `.venv/bin/python -m pytest tests/unit/test_story.py tests/integration/test_story_pipeline.py -q`; confirm pass with a fake Ollama client. Run one optional local model contract check from the benchmark set.
- [ ] Commit story logic, prompts, and tests.

### Task 7: Platform posting copy

**Files:** Create `src/story_teller/posting.py`; modify `pipeline.py`; test `tests/unit/test_posting.py`.

**Interfaces:** `generate_posting_copy(story: StoryDraft, platforms: list[str]) -> dict[str, PostingCopy]` with `PostingCopy` defined in `posting.py` as title, caption, and hashtags.

- [ ] Write tests asserting entries only for selected platforms, bounded nonempty fields, and rejection of malformed or schema-invalid Ollama output; run and confirm failure.
- [ ] Implement the posting-copy prompt and Pydantic v2 validation in `posting.py`, using the final story version. Persist copy for later manual editing; do not call platform APIs.
- [ ] Run `.venv/bin/python -m pytest tests/unit/test_posting.py -q`; confirm pass.
- [ ] Commit posting-copy logic and tests.

## Milestone 4 — Narration, captions, and video

**Exit:** One script and one uploaded clip produce a verified portrait MP4 whose duration follows the final audio.

### Task 8: Local narration and word-timed captions

**Files:** Create `src/story_teller/speech.py`, `captions.py`; modify `pipeline.py`; test `tests/unit/test_captions.py`, `tests/integration/test_speech.py`.

**Interfaces:** `synthesize(story: StoryDraft, voice_ref: Path, output: Path) -> AudioInfo`; `time_words(audio: Path, script: str) -> list[TimedWord]`; `group_cues(words: list[TimedWord]) -> list[CaptionCue]`. Put `AudioInfo` in `speech.py`; `TimedWord` and `CaptionCue` in `captions.py`.

- [ ] Write tests for narrator-to-voice selection, actual WAV duration, mismatched or missing transcribed words stopping before render, five-to-seven-word groups, punctuation/long-line breaks, and no cue beyond audio end; run and confirm failure.
- [ ] Validate and copy the supplied MP3 references into managed local voice storage, then implement benchmark-selected local TTS and faster-whisper on final audio. Do not assume 180 WPM from a word count; inspect actual audio and regenerate when outside the approved duration band.
- [ ] Run `.venv/bin/python -m pytest tests/unit/test_captions.py tests/integration/test_speech.py -q`; confirm pass with a fake TTS in fast tests. Perform a separate full narration listening check.
- [ ] Commit speech, timing, and tests.

### Task 9: FFmpeg render and media verification

**Files:** Create `src/story_teller/render.py`; modify `pipeline.py`; test `tests/integration/test_render.py`, tiny assets in `tests/fixtures/`.

**Interfaces:** `render_video(clip: Path, audio: Path, cues: list[CaptionCue], placement: CaptionPlacement, output: Path) -> VideoInfo`. Define `CaptionPlacement` and `VideoInfo` in `render.py`. Inspect output with ffprobe before marking the stage complete.

- [ ] Write tests for a longer landscape clip being cropped and trimmed, a shorter clip looping then trimming, source audio muted, caption presence, a failed FFmpeg subprocess, and output ending with story audio within one frame/codec rounding; run and confirm failure.
- [ ] Implement fixed FFmpeg argument templates, escaped subtitle assets, temporary output, atomic promotion, and ffprobe checks. Never pass user notes as raw filter syntax.
- [ ] Run `.venv/bin/python -m pytest tests/integration/test_render.py -q`; confirm pass. Inspect a real portrait frame and listen to its final seconds.
- [ ] Commit renderer, fixtures, and tests.

## Milestone 5 — Review, revision, and export

**Exit:** A user can review and revise a draft through the local UI, edit copy, approve only the current version, and download immutable output.

### Task 10: Revision and approval contracts

**Files:** Modify `service.py`, `api.py`, `worker.py`, `pipeline.py`; test `tests/unit/test_revision_rules.py`, `tests/integration/test_review_api.py`.

**Interfaces:** `request_revision(conn: Connection, run_id: str, kind: Literal["story", "subtitle_position"], note: str) -> int`; `approve_revision(conn: Connection, run_id: str, revision_no: int) -> None`; `POST /api/v1/runs/{id}/revisions`, `PUT /api/v1/runs/{id}/revisions/{n}/posting-copy`, `POST /api/v1/runs/{id}/approve`, `GET /api/v1/runs/{id}/video`.

- [ ] Write tests for story notes rerunning story-to-copy, position notes rerunning render only, copy edits preserving media, stale approval and simultaneous revision requests returning `409`, and approved files remaining unchanged after a later failed revision; run and confirm failure.
- [ ] Implement revision invalidation and immutable approval in transactions. Map positioning notes to constrained placements; never treat them as FFmpeg commands.
- [ ] Run `.venv/bin/python -m pytest tests/unit/test_revision_rules.py tests/integration/test_review_api.py -q`; confirm pass.
- [ ] Commit lifecycle, API, and tests.

### Task 11: Local review UI and CLI handoff

**Files:** Create `src/story_teller/templates/`, `static/`; modify `app.py`, `cli.py`; test `tests/integration/test_review_pages.py`.

**Interfaces:** Pages for settings/clips, run list/status, portrait video preview, story/position feedback, editable platform copy, approval, and download. CLI exposes run ID, status, failure reason, and local review URL.

- [ ] Write page/API tests for visible run state, generated copy fields, preview URL, notes, approval, and download. Run and confirm failure.
- [ ] Implement server-rendered pages with minimal JavaScript polling. Show errors near the action and keep controls usable without guessing stage state.
- [ ] Run `.venv/bin/python -m pytest tests/integration/test_review_pages.py -q`; confirm pass. Visually inspect the portrait preview and subtitle safe area in a browser.
- [ ] Commit UI, CLI handoff, and tests.

## Milestone 6 — End-to-end release gate

**Exit:** The app passes the PRD's acceptance criteria on this computer and has repeatable setup and recovery instructions.

### Task 12: Full workflow, recovery, and documentation

**Files:** Update `README.md`, `docs/model-benchmark.md`, and `AGENTS.md` when implemented commands differ from the guide; add `tests/integration/test_end_to_end.py` where deterministic fakes can cover the workflow.

**Interfaces:** No new public API. Verify one real end-to-end run and one position-only revision with the selected models and uploaded footage.

- [x] Deterministic fake-stage integration test covers storage through render, review, position revision, approval, and persisted approved artifact paths after reconnect (`tests/integration/test_end_to_end.py`).
- [x] Release verification on 2026-11-14: `pytest -q` 58 passed, Ruff clean, mypy clean for 13 source files. Local preflight passed when run with access to Ollama.
- [x] Real acceptance evidence: prior full-length short-clip loop, long-clip trim, story and position revisions; newer approved gameplay preview and owner listening confirmation; ffprobe, portrait frame inspection, restart, platform-copy and approved-download checks. Details and historical/current distinction are in `docs/model-benchmark.md`.
- [x] README covers setup, preflight, startup, backup, recovery, and limitations. Reviewed release files and retained generated media outside Git. The repository still has no initial commit, so a commit remains a separate repository-initialization step.

## Dependency and release summary

| Milestone | Depends on | Reviewable deliverable |
| --- | --- | --- |
| 0. Approval and feasibility | Owner architecture approval | Measured model/voice choice and benchmark report |
| 1. Foundation | 0 | Loopback app, preflight, SQLite, validated clip/settings API |
| 2. Runs and recovery | 1 | CLI/API runs, one durable worker, restart/retry behavior |
| 3. Creative pipeline | 2 | Validated script, evaluation revisions, posting copy |
| 4. Media pipeline | 3 | Local narration, timed captions, verified portrait MP4 |
| 5. Review and export | 4 | Notes, copy edits, latest-only approval, download |
| 6. Release gate | 5 | Complete local acceptance run and operating guide |

The go/no-go for each milestone is its listed tests and a review of the deliverable. A failing model benchmark or architecture-changing result returns to the owner before proceeding; routine implementation choices remain with the engineer.
