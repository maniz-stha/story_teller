# Story Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pause each evaluated story for owner approval before narration, then retain final video approval before download.

**Architecture:** Reuse run status as the persisted gate. The worker stops after evaluation and resumes completed stages when a revision checked story approval action requeues the run. The existing preview approval and download contract remain.

**Tech Stack:** Python 3.11, FastAPI, SQLite, plain JavaScript, pytest.

**Spec:** [Story approval design](../specs/2026-11-26-story-approval-design.md).

## Global Constraints

- Keep existing run data and the `/approve` final approval contract.
- No new dependencies, automatic publishing, or real cloud model calls in tests.
- Story changes repeat the story gate; subtitle position changes reuse accepted media.

## Review Focus

- A stale story approval must not start work on a newer revision.
- Failed evaluation must not become approvable.
- Media retry must not demand a second story approval.
- A pending revised story must not expose its unapproved video for download.
- An older approved export must remain available during a pending revision.

---

### Task 1: Persist the story gate

**Files:** `src/story_teller/worker.py`, `src/story_teller/service.py`, `src/story_teller/storage.py`, `src/story_teller/migrations/0003.sql`, `tests/integration/test_worker.py`, `tests/unit/test_revision_rules.py`.

**Interfaces:** `approve_story(conn: sqlite3.Connection, run_id: str, revision_no: int) -> None` moves `awaiting_story_approval` to `queued` only for the current evaluated story without media. `process_next_run` pauses after evaluation and resumes after that approval.

- [x] Add failing tests for the pause, restart/resume, stale or invalid approval, story revision, and media retry.
- [x] Run focused tests and observe failure for the missing gate.
- [x] Implement the worker split and atomic story approval transition using a persisted approved story revision ID; allow story feedback and deletion at the story gate.
- [x] Run focused tests to green.

### Task 2: Expose and use both approvals

**Files:** `src/story_teller/api.py`, `src/story_teller/templates/index.html`, `src/story_teller/static/app.js`, `tests/integration/test_review_api.py`, `tests/integration/test_review_pages.py`, `tests/integration/test_end_to_end.py`.

**Interfaces:** `POST /api/v1/runs/{id}/approve-story` accepts `{revision_no}` and returns `202` with `queued`; existing `POST /approve` remains final approval. The review page enables story approval only at `awaiting_story_approval`, final approval only at `awaiting_review`, and download only for an approved revision.

- [x] Add failing API, UI, and end-to-end tests for both gates and download behavior.
- [x] Run focused tests and observe failure for the missing action or wrong UI state.
- [x] Add the endpoint and controls; adapt existing end-to-end test to approve the story before media.
- [x] Run focused tests to green.

### Task 3: Document and verify

**Files:** `docs/product-requirements.md`, `docs/architecture-proposal.md`, `README.md`, `plans/current.md` only where their workflow text needs updating.

- [x] Update current workflow and API descriptions to identify both approval gates.
- [x] Run `.venv/bin/python -m pytest -q`, `.venv/bin/ruff check src tests`, and `.venv/bin/mypy src/story_teller`.
- [x] Review `git diff --check` and the full diff for unintended changes.
