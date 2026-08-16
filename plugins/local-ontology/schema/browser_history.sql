CREATE TABLE IF NOT EXISTS browser_history_records (
  record_id TEXT PRIMARY KEY,
  world_id TEXT NOT NULL REFERENCES worlds(world_id),
  source_ref TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  host TEXT NOT NULL,
  visit_count INTEGER NOT NULL,
  last_visit_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  UNIQUE (world_id, url)
);

CREATE INDEX IF NOT EXISTS browser_history_by_world_host
  ON browser_history_records(world_id, host);
