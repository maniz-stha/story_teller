ALTER TABLE runs ADD COLUMN story_approved_revision_id TEXT REFERENCES revisions(id);
