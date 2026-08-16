PRAGMA foreign_keys = ON;

CREATE TABLE worlds (
  world_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE nodes (
  node_id TEXT PRIMARY KEY,
  world_id TEXT NOT NULL REFERENCES worlds(world_id),
  type TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  summary TEXT,
  state TEXT NOT NULL CHECK (state IN ('active', 'dormant', 'superseded')),
  sensitivity TEXT NOT NULL DEFAULT 'normal',
  valid_from TEXT,
  valid_to TEXT,
  last_seen_at TEXT,
  superseded_by TEXT REFERENCES nodes(node_id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE node_aliases (
  alias TEXT NOT NULL,
  node_id TEXT NOT NULL REFERENCES nodes(node_id),
  source TEXT NOT NULL,
  confidence REAL NOT NULL,
  PRIMARY KEY (alias, node_id)
);

CREATE TABLE edges (
  edge_id TEXT PRIMARY KEY,
  world_id TEXT NOT NULL REFERENCES worlds(world_id),
  from_node_id TEXT NOT NULL REFERENCES nodes(node_id),
  relation TEXT NOT NULL,
  to_node_id TEXT NOT NULL REFERENCES nodes(node_id),
  state TEXT NOT NULL CHECK (state IN ('active', 'dormant', 'superseded')),
  valid_from TEXT,
  valid_to TEXT,
  confidence REAL NOT NULL,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE evidence (
  evidence_id TEXT PRIMARY KEY,
  node_id TEXT REFERENCES nodes(node_id),
  edge_id TEXT REFERENCES edges(edge_id),
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  occurred_at TEXT,
  observed_at TEXT NOT NULL,
  excerpt TEXT,
  content_hash TEXT NOT NULL
);

CREATE TABLE browser_history_records (
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

CREATE INDEX nodes_by_world_type_state ON nodes(world_id, type, state);
CREATE INDEX nodes_by_world_name ON nodes(world_id, canonical_name);
CREATE INDEX aliases_by_alias ON node_aliases(alias);
CREATE INDEX edges_by_world_source_state ON edges(world_id, from_node_id, state);
CREATE INDEX edges_by_world_target_state ON edges(world_id, to_node_id, state);
CREATE INDEX evidence_by_node_date ON evidence(node_id, occurred_at);
CREATE INDEX browser_history_by_world_host
  ON browser_history_records(world_id, host);
