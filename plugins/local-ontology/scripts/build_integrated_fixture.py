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

from build_session import CanonicalSource, build_session
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


def _apply_graph_overlay(canonical_path: Path, world_id: str) -> None:
    overlay = json.loads(GRAPH_OVERLAY.read_text(encoding="utf-8"))
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
                evidence_id = _identifier("fixture-evidence", node_id)
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
                connection.execute(
                    """
                    INSERT INTO evidence (
                      evidence_id, node_id, edge_id, source_kind, source_ref,
                      occurred_at, observed_at, excerpt, content_hash
                    ) VALUES (?, ?, NULL, 'fixture_graph', ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        node_id,
                        node["sourceRef"],
                        node["occurredAt"],
                        node["occurredAt"],
                        node["canonicalName"],
                        hashlib.sha256(
                            json.dumps(node, sort_keys=True).encode("utf-8")
                        ).hexdigest(),
                    ),
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
                evidence_id = _identifier("fixture-evidence", edge_id)
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
                connection.execute(
                    """
                    INSERT INTO evidence (
                      evidence_id, node_id, edge_id, source_kind, source_ref,
                      occurred_at, observed_at, excerpt, content_hash
                    ) VALUES (?, NULL, ?, 'fixture_graph', ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        edge_id,
                        edge["sourceRef"],
                        edge["occurredAt"],
                        edge["occurredAt"],
                        edge["excerpt"],
                        hashlib.sha256(
                            json.dumps(edge, sort_keys=True).encode("utf-8")
                        ).hexdigest(),
                    ),
                )


def build_integrated_fixture(
    session_directory: Path,
    world_id: str = "travel",
) -> dict[str, Any]:
    """Import all supported fixture sources and build one capability session."""

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
                world_id,
                CHROMIUM_PATTERNS,
            ),
            "codexLogs": import_codex_logs(
                CODEX_FIXTURE,
                canonical_path,
                world_id,
            ),
            "googleMapsTakeout": import_google_maps_takeout(
                TAKEOUT_FIXTURE,
                canonical_path,
                world_id,
            ),
        }
        _apply_graph_overlay(canonical_path, world_id)

    session_path = build_session(
        CanonicalSource(canonical_path),
        POLICY,
        world_id,
        session_directory,
    )
    return {
        "canonicalDatabase": str(canonical_path),
        "reports": reports,
        "selectedWorld": world_id,
        "sessionPath": str(session_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--world", default="travel")
    arguments = parser.parse_args()
    print(
        json.dumps(
            build_integrated_fixture(arguments.session_dir, arguments.world),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
