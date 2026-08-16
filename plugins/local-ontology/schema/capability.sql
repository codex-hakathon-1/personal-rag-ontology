PRAGMA foreign_keys = ON;

CREATE TABLE nodes (
  node_id TEXT PRIMARY KEY,
  world_id TEXT NOT NULL,
  type TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  summary TEXT,
  state TEXT NOT NULL,
  sensitivity TEXT NOT NULL,
  valid_from TEXT,
  valid_to TEXT,
  last_seen_at TEXT,
  superseded_by TEXT,
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
  world_id TEXT NOT NULL,
  from_node_id TEXT NOT NULL REFERENCES nodes(node_id),
  relation TEXT NOT NULL,
  to_node_id TEXT NOT NULL REFERENCES nodes(node_id),
  state TEXT NOT NULL,
  valid_from TEXT,
  valid_to TEXT,
  confidence REAL NOT NULL,
  evidence_count INTEGER NOT NULL,
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

CREATE INDEX nodes_by_type_state ON nodes(type, state);
CREATE INDEX nodes_by_name ON nodes(canonical_name);
CREATE INDEX aliases_by_alias ON node_aliases(alias);
CREATE INDEX edges_by_source_state ON edges(from_node_id, state);
CREATE INDEX edges_by_target_state ON edges(to_node_id, state);
CREATE INDEX evidence_by_node_date ON evidence(node_id, occurred_at);
