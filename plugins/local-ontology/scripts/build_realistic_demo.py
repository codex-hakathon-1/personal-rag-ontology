#!/usr/bin/env python3
"""Build and query the privacy-safe realistic synthetic user demo."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from build_integrated_fixture import apply_graph_overlay
from build_session import CanonicalSource, build_capability_connection, build_session
from import_browser_history import import_chromium_history
from import_codex_logs import import_codex_logs
from import_google_maps_takeout import import_google_maps_takeout
from mcp_server import handle


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PLUGIN_ROOT / "examples" / "realistic-user-demo"
CHROMIUM_FIXTURE = FIXTURE_ROOT / "chromium-history.sql"
CHROMIUM_PATTERNS = FIXTURE_ROOT / "chromium-sensitive-patterns.json"
CODEX_FIXTURE = FIXTURE_ROOT / "codex-logs"
TAKEOUT_FIXTURE = FIXTURE_ROOT / "google-maps-takeout"
POLICY = FIXTURE_ROOT / "policy.json"
GRAPH_OVERLAY = FIXTURE_ROOT / "graph-overlay.json"
PERSONA = FIXTURE_ROOT / "persona.json"
WORLD_ID = "work"
DEMO_ANCHORS = ("챗봇 분석", "내 기억 시스템")


def _anchor_query(anchor: str) -> str:
    literal = anchor.replace("'", "''")
    return f"""
WITH RECURSIVE neighborhood(node_id, depth, path, via_edge_id) AS (
  SELECT DISTINCT n.node_id, 0, '|' || n.node_id || '|', NULL
  FROM nodes AS n
  LEFT JOIN node_aliases AS a ON a.node_id = n.node_id
  WHERE lower(n.canonical_name) = lower('{literal}')
     OR lower(a.alias) = lower('{literal}')

  UNION ALL

  SELECT e.to_node_id, neighborhood.depth + 1,
         neighborhood.path || e.to_node_id || '|', e.edge_id
  FROM neighborhood
  JOIN edges AS e ON e.from_node_id = neighborhood.node_id
  WHERE neighborhood.depth < 2
    AND e.state = 'active'
    AND instr(neighborhood.path, '|' || e.to_node_id || '|') = 0
)
SELECT neighborhood.depth, n.type AS node_type, n.canonical_name,
       traversed.relation AS via_relation,
       node_evidence.source_kind AS node_source_kind,
       node_evidence.source_ref AS node_source_ref,
       node_evidence.occurred_at AS node_occurred_at,
       edge_evidence.source_kind AS edge_source_kind,
       edge_evidence.source_ref AS edge_source_ref,
       edge_evidence.occurred_at AS edge_occurred_at
FROM neighborhood
JOIN nodes AS n ON n.node_id = neighborhood.node_id
JOIN evidence AS node_evidence ON node_evidence.evidence_id = (
  SELECT candidate.evidence_id
  FROM evidence AS candidate
  WHERE candidate.node_id = n.node_id
  ORDER BY candidate.occurred_at DESC, candidate.evidence_id
  LIMIT 1
)
LEFT JOIN edges AS traversed ON traversed.edge_id = neighborhood.via_edge_id
LEFT JOIN evidence AS edge_evidence ON edge_evidence.evidence_id = (
  SELECT candidate.evidence_id
  FROM evidence AS candidate
  WHERE candidate.edge_id = traversed.edge_id
  ORDER BY candidate.occurred_at DESC, candidate.evidence_id
  LIMIT 1
)
ORDER BY neighborhood.depth, n.canonical_name
""".strip()


def _query_memory(
    session: dict[str, Any],
    capability: sqlite3.Connection,
    sql: str,
) -> dict[str, Any]:
    response = handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "query_memory",
                "arguments": {"sql": sql},
            },
        },
        session,
        capability,
    )
    if response is None or response.get("result", {}).get("isError"):
        raise RuntimeError(f"Realistic demo query failed: {response!r}")
    return response["result"]["structuredContent"]


def build_realistic_demo(session_directory: Path) -> dict[str, Any]:
    """Import every demo source and return ready-to-present query proofs."""

    session_directory = session_directory.resolve()
    session_directory.mkdir(parents=True, exist_ok=True)
    for audit_path in session_directory.glob("query-audit-*.jsonl"):
        audit_path.unlink()
    for generated_name in ("session.json", "demo-result.json"):
        (session_directory / generated_name).unlink(missing_ok=True)
    canonical_path = session_directory / "canonical.sqlite3"
    canonical_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as temporary_directory:
        history_path = Path(temporary_directory) / "History"
        with closing(sqlite3.connect(history_path)) as history:
            with history:
                history.executescript(CHROMIUM_FIXTURE.read_text(encoding="utf-8"))
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

    with (
        closing(sqlite3.connect(canonical_path)) as canonical,
        closing(sqlite3.connect(capability_path)) as capability,
    ):
        canonical_boundary_count = canonical.execute(
            "SELECT count(*) FROM nodes "
            "WHERE canonical_name LIKE '합성 경계 데이터:%'"
        ).fetchone()[0]
        capability_boundary_count = capability.execute(
            "SELECT count(*) FROM nodes "
            "WHERE canonical_name LIKE '합성 경계 데이터:%'"
        ).fetchone()[0]
        query_results = {
            anchor: _query_memory(session, capability, _anchor_query(anchor))
            for anchor in DEMO_ANCHORS
        }
        source_kinds = [
            row[0]
            for row in capability.execute(
                "SELECT DISTINCT source_kind FROM evidence ORDER BY source_kind"
            )
        ]

    return {
        "persona": json.loads(PERSONA.read_text(encoding="utf-8")),
        "selectedWorld": WORLD_ID,
        "sourceKinds": source_kinds,
        "reports": reports,
        "policyBoundary": {
            "canonicalRows": canonical_boundary_count,
            "capabilityRows": capability_boundary_count,
        },
        "queries": query_results,
        "sessionPath": str(session_path),
        "canonicalDatabase": str(canonical_path),
        "capabilityDatabase": str(capability_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    arguments = parser.parse_args()
    result = build_realistic_demo(arguments.session_dir)
    result_path = arguments.session_dir.resolve() / "demo-result.json"
    result["resultPath"] = str(result_path)
    rendered = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    result_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
