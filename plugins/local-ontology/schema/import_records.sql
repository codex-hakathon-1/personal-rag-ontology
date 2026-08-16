CREATE TABLE IF NOT EXISTS import_records (
  record_id TEXT PRIMARY KEY,
  world_id TEXT NOT NULL REFERENCES worlds(world_id),
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  raw_text_or_metadata TEXT NOT NULL,
  candidate_entities TEXT NOT NULL,
  provenance TEXT NOT NULL,
  content_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS import_records_by_world_source_date
  ON import_records(world_id, source_kind, occurred_at);
