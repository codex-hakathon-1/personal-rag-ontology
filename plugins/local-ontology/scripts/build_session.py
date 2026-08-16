#!/usr/bin/env python3
"""Build a canonical fixture graph and a selected-world capability database."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = PLUGIN_ROOT / "schema" / "canonical.sql"
CAPABILITY_SCHEMA = PLUGIN_ROOT / "schema" / "capability.sql"

TABLE_COLUMNS = {
    "worlds": ("world_id", "name", "description", "enabled"),
    "nodes": (
        "node_id", "world_id", "type", "canonical_name", "summary", "state",
        "sensitivity", "valid_from", "valid_to", "last_seen_at", "superseded_by",
        "created_at", "updated_at",
    ),
    "node_aliases": ("alias", "node_id", "source", "confidence"),
    "edges": (
        "edge_id", "world_id", "from_node_id", "relation", "to_node_id", "state",
        "valid_from", "valid_to", "confidence", "evidence_count", "created_at",
        "updated_at",
    ),
    "evidence": (
        "evidence_id", "node_id", "edge_id", "source_kind", "source_ref",
        "occurred_at", "observed_at", "excerpt", "content_hash",
    ),
}


def _insert_rows(connection: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    columns = TABLE_COLUMNS[table]
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        [tuple(row.get(column) for column in columns) for row in rows],
    )


def _fresh_database(path: Path, schema_path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    return connection


def _build_canonical(path: Path, fixture: dict[str, Any]) -> None:
    with closing(_fresh_database(path, CANONICAL_SCHEMA)) as connection:
        with connection:
            for table in ("worlds", "nodes", "node_aliases", "edges", "evidence"):
                _insert_rows(connection, table, fixture.get(table, []))


def build_capability_connection(
    canonical_path: Path,
    selected_world: str,
    policy: dict[str, Any],
) -> sqlite3.Connection:
    canonical_uri = canonical_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(canonical_uri, uri=True)) as canonical:
        canonical.row_factory = sqlite3.Row
        canonical_rows = {
            table: [dict(row) for row in canonical.execute(f"SELECT * FROM {table}")]
            for table in ("nodes", "node_aliases", "edges", "evidence")
        }

    included_states = set(policy.get("include_states", ["active"]))
    denied_sensitivity = set(policy.get("deny_sensitivity", []))
    allowed_types = set(policy.get("allow_node_types", []))
    included_sources = set(policy.get("include_sources", []))

    eligible_evidence = [
        row for row in canonical_rows["evidence"]
        if not included_sources or row["source_kind"] in included_sources
    ]
    evidenced_nodes = {row["node_id"] for row in eligible_evidence if row.get("node_id")}
    nodes = [
        row for row in canonical_rows["nodes"]
        if row["world_id"] == selected_world
        and row["state"] in included_states
        and row["sensitivity"] not in denied_sensitivity
        and (not allowed_types or row["type"] in allowed_types)
        and row["node_id"] in evidenced_nodes
    ]
    node_ids = {row["node_id"] for row in nodes}
    aliases = [
        row for row in canonical_rows["node_aliases"] if row["node_id"] in node_ids
    ]
    edges = [
        row for row in canonical_rows["edges"]
        if row["world_id"] == selected_world
        and row["state"] in included_states
        and row["from_node_id"] in node_ids
        and row["to_node_id"] in node_ids
    ]
    edge_ids = {row["edge_id"] for row in edges}
    evidence = [
        row for row in eligible_evidence
        if (row.get("node_id") in node_ids)
        or (row.get("edge_id") in edge_ids)
    ]

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(CAPABILITY_SCHEMA.read_text(encoding="utf-8"))
        for table, rows in (
            ("nodes", nodes),
            ("node_aliases", aliases),
            ("edges", edges),
            ("evidence", evidence),
        ):
            _insert_rows(connection, table, rows)
        connection.commit()
        connection.execute("PRAGMA query_only = ON")
        return connection
    except Exception:
        connection.close()
        raise


def build_session(
    fixture_path: Path,
    policy_path: Path,
    selected_world: str,
    session_directory: Path,
    max_rows: int = 100,
    max_execution_ms: int = 1_000,
) -> Path:
    if max_rows <= 0 or max_execution_ms <= 0:
        raise ValueError("Query limits must be positive integers")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    policies = json.loads(policy_path.read_text(encoding="utf-8")).get("worlds", {})
    if selected_world not in policies:
        raise ValueError(f"World {selected_world!r} is not configured by the policy")
    fixture_worlds = {world["world_id"] for world in fixture.get("worlds", [])}
    if selected_world not in fixture_worlds:
        raise ValueError(f"World {selected_world!r} is not present in the fixture")

    session_directory = session_directory.resolve()
    canonical_path = session_directory / "canonical.sqlite3"
    session_path = session_directory / "session.json"
    _build_canonical(canonical_path, fixture)

    session_identifier = uuid.uuid4().hex
    session = {
        "sessionIdentifier": session_identifier,
        "selectedWorld": selected_world,
        "policyContract": policies[selected_world],
        "canonicalDatabase": str(canonical_path),
        "queryAuditLog": str(
            session_directory / f"query-audit-{session_identifier}.jsonl"
        ),
        "queryLimits": {
            "maxRows": max_rows,
            "maxExecutionMs": max_execution_ms,
        },
        "schemaGuidance": {
            "nodes": list(TABLE_COLUMNS["nodes"]),
            "node_aliases": list(TABLE_COLUMNS["node_aliases"]),
            "edges": list(TABLE_COLUMNS["edges"]),
            "evidence": list(TABLE_COLUMNS["evidence"]),
        },
    }
    session_path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return session_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--world", required=True)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=100)
    parser.add_argument("--max-execution-ms", type=int, default=1_000)
    arguments = parser.parse_args()
    session_path = build_session(
        arguments.fixture,
        arguments.policy,
        arguments.world,
        arguments.session_dir,
        arguments.max_rows,
        arguments.max_execution_ms,
    )
    session = json.loads(session_path.read_text(encoding="utf-8"))
    print(json.dumps({
        "selectedWorld": session["selectedWorld"],
        "sessionPath": str(session_path),
    }))


if __name__ == "__main__":
    main()
