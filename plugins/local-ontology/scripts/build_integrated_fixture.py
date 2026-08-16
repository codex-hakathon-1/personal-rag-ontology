#!/usr/bin/env python3
"""Build one deterministic session from all supported Local Ontology sources."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from build_session import (
    CanonicalSource,
    build_capability_connection,
    build_session,
)
from import_browser_history import import_chromium_history
from import_codex_logs import import_codex_logs
from import_google_maps_takeout import import_google_maps_takeout


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = PLUGIN_ROOT / "examples"
CHROMIUM_FIXTURE = EXAMPLES / "chromium-history-fixture.sql"
CHROMIUM_PATTERNS = EXAMPLES / "chromium-sensitive-patterns.json"
CODEX_FIXTURE = EXAMPLES / "integrated-fixture" / "codex-logs"
TAKEOUT_FIXTURE = EXAMPLES / "google-maps-takeout-fixture"
POLICY = EXAMPLES / "integrated-policy.example.json"
GRAPH_OVERLAY = EXAMPLES / "integrated-fixture" / "graph-overlay.json"
WORLD_ID = "travel"


def _identifier(kind: str, *parts: str) -> str:
    payload = "\x1f".join((kind, *parts)).encode("utf-8")
    return f"{kind}-{hashlib.sha256(payload).hexdigest()[:24]}"


def _selected_node_id(
    connection: sqlite3.Connection,
    world_id: str,
    selector: dict[str, str],
) -> str:
    rows = connection.execute(
        "SELECT node_id FROM nodes "
        "WHERE world_id = ? AND type = ? AND canonical_name = ?",
        (world_id, selector["type"], selector["canonicalName"]),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError(
            "Integrated fixture selector must resolve to exactly one node: "
            f"{selector!r}"
        )
    return rows[0][0]


def _insert_fixture_evidence(
    connection: sqlite3.Connection,
    *,
    node_id: str | None = None,
    edge_id: str | None = None,
    source_ref: str,
    occurred_at: str,
    excerpt: str,
    content: dict[str, Any],
) -> None:
    owner_id = node_id or edge_id
    if owner_id is None or (node_id is not None and edge_id is not None):
        raise ValueError("Fixture evidence must belong to one node or one edge")
    connection.execute(
        """
        INSERT INTO evidence (
          evidence_id, node_id, edge_id, source_kind, source_ref,
          occurred_at, observed_at, excerpt, content_hash
        ) VALUES (?, ?, ?, 'fixture_graph', ?, ?, ?, ?, ?)
        """,
        (
            _identifier("fixture-evidence", owner_id),
            node_id,
            edge_id,
            source_ref,
            occurred_at,
            occurred_at,
            excerpt,
            hashlib.sha256(
                json.dumps(content, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        ),
    )


def apply_graph_overlay(
    canonical_path: Path,
    world_id: str,
    overlay_path: Path,
) -> None:
    """Add explicit fixture-only aliases, edges, and policy-boundary nodes."""

    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(canonical_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            for node in overlay["policyBoundaryNodes"]:
                node_world = node["worldId"]
                connection.execute(
                    "INSERT INTO worlds (world_id, name, description, enabled) "
                    "VALUES (?, ?, 'Integrated policy-boundary fixture', 1) "
                    "ON CONFLICT(world_id) DO NOTHING",
                    (node_world, node_world.replace("-", " ").title()),
                )
                node_id = _identifier(
                    "fixture-node", node_world, node["canonicalName"]
                )
                connection.execute(
                    """
                    INSERT INTO nodes (
                      node_id, world_id, type, canonical_name, summary, state,
                      sensitivity, valid_from, valid_to, last_seen_at,
                      superseded_by, created_at, updated_at
                    ) VALUES (?, ?, 'topic', ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?)
                    """,
                    (
                        node_id,
                        node_world,
                        node["canonicalName"],
                        node["canonicalName"],
                        node["state"],
                        node["sensitivity"],
                        node["occurredAt"],
                        node["occurredAt"],
                        node["occurredAt"],
                        node["occurredAt"],
                    ),
                )
                _insert_fixture_evidence(
                    connection,
                    node_id=node_id,
                    source_ref=node["sourceRef"],
                    occurred_at=node["occurredAt"],
                    excerpt=node["canonicalName"],
                    content=node,
                )
            for alias in overlay["aliases"]:
                node_id = _selected_node_id(connection, world_id, alias["node"])
                connection.execute(
                    "INSERT INTO node_aliases (alias, node_id, source, confidence) "
                    "VALUES (?, ?, 'fixture_graph', ?) "
                    "ON CONFLICT(alias, node_id) DO UPDATE SET "
                    "source = excluded.source, confidence = excluded.confidence",
                    (alias["alias"], node_id, alias["confidence"]),
                )
            for edge in overlay["edges"]:
                from_node_id = _selected_node_id(
                    connection, world_id, edge["from"]
                )
                to_node_id = _selected_node_id(connection, world_id, edge["to"])
                edge_id = _identifier(
                    "fixture-edge",
                    world_id,
                    from_node_id,
                    edge["relation"],
                    to_node_id,
                )
                connection.execute(
                    """
                    INSERT INTO edges (
                      edge_id, world_id, from_node_id, relation, to_node_id,
                      state, valid_from, valid_to, confidence, evidence_count,
                      created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'active', ?, NULL, ?, 1, ?, ?)
                    """,
                    (
                        edge_id,
                        world_id,
                        from_node_id,
                        edge["relation"],
                        to_node_id,
                        edge["occurredAt"],
                        edge["confidence"],
                        edge["occurredAt"],
                        edge["occurredAt"],
                    ),
                )
                _insert_fixture_evidence(
                    connection,
                    edge_id=edge_id,
                    source_ref=edge["sourceRef"],
                    occurred_at=edge["occurredAt"],
                    excerpt=edge["excerpt"],
                    content=edge,
                )


def build_integrated_fixture(
    session_directory: Path,
) -> dict[str, Any]:
    """Import all fixture sources and persist the selected-world capability."""

    session_directory = session_directory.resolve()
    session_directory.mkdir(parents=True, exist_ok=True)
    canonical_path = session_directory / "canonical.sqlite3"
    canonical_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as temporary_directory:
        history_path = Path(temporary_directory) / "History"
        with closing(sqlite3.connect(history_path)) as connection:
            with connection:
                connection.executescript(
                    CHROMIUM_FIXTURE.read_text(encoding="utf-8")
                )
        reports = {
            "browserHistory": import_chromium_history(
                history_path,
                canonical_path,
                WORLD_ID,
                CHROMIUM_PATTERNS,
            ),
            "codexLogs": import_codex_logs(
                CODEX_FIXTURE,
                canonical_path,
                WORLD_ID,
            ),
            "googleMapsTakeout": import_google_maps_takeout(
                TAKEOUT_FIXTURE,
                canonical_path,
                WORLD_ID,
            ),
        }
        apply_graph_overlay(canonical_path, WORLD_ID, GRAPH_OVERLAY)

    session_path = build_session(
        CanonicalSource(canonical_path),
        POLICY,
        WORLD_ID,
        session_directory,
    )
    session = json.loads(session_path.read_text(encoding="utf-8"))
    capability_path = session_directory / "capability.sqlite3"
    capability_path.unlink(missing_ok=True)
    with (
        closing(
            build_capability_connection(
                canonical_path,
                session["selectedWorld"],
                session["policyContract"],
            )
        ) as capability,
        closing(sqlite3.connect(capability_path)) as persisted_capability,
    ):
        capability.backup(persisted_capability)
    return {
        "capabilityDatabase": str(capability_path),
        "canonicalDatabase": str(canonical_path),
        "reports": reports,
        "selectedWorld": WORLD_ID,
        "sessionPath": str(session_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    arguments = parser.parse_args()
    print(
        json.dumps(
            build_integrated_fixture(arguments.session_dir),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
