CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE clips (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    duration REAL NOT NULL CHECK (duration > 0),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    seed INTEGER NOT NULL,
    theme TEXT NOT NULL,
    clip_id TEXT NOT NULL REFERENCES clips(id),
    current_revision_id TEXT,
    approved_revision_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE revisions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    number INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'initial',
    note TEXT,
    parent_id TEXT REFERENCES revisions(id),
    story TEXT,
    summary TEXT,
    narrator TEXT,
    evaluation_json TEXT,
    audio_duration REAL,
    placement TEXT NOT NULL DEFAULT 'lower_middle',
    posting_copy_json TEXT,
    audio_path TEXT,
    captions_path TEXT,
    video_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, number)
);

CREATE TABLE stage_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    revision_id TEXT NOT NULL REFERENCES revisions(id),
    stage TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    error TEXT,
    UNIQUE(revision_id, stage, attempt)
);

CREATE INDEX idx_runs_status_created ON runs(status, created_at);
CREATE INDEX idx_revisions_run_number ON revisions(run_id, number);
