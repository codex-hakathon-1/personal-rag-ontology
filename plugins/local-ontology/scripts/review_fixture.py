#!/usr/bin/env python3
"""Build the integrated fixture and print reviewer-verifiable query proofs."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Any

from build_integrated_fixture import build_integrated_fixture
from mcp_server import handle


HAPPY_PATH_SQL = """
WITH RECURSIVE neighborhood(node_id, depth, path) AS (
  SELECT DISTINCT n.node_id, 0, '|' || n.node_id || '|'
  FROM nodes AS n
  LEFT JOIN node_aliases AS a ON a.node_id = n.node_id
  WHERE lower(n.canonical_name) = lower('Kyoto market')
     OR lower(a.alias) = lower('Kyoto market')
  UNION ALL
  SELECT e.to_node_id, neighborhood.depth + 1,
         neighborhood.path || e.to_node_id || '|'
  FROM neighborhood
  JOIN edges AS e ON e.from_node_id = neighborhood.node_id
  WHERE neighborhood.depth < 2
    AND e.state = 'active'
    AND instr(neighborhood.path, '|' || e.to_node_id || '|') = 0
)
SELECT neighborhood.depth, n.canonical_name,
       v.source_kind, v.source_ref, v.occurred_at
FROM neighborhood
JOIN nodes AS n ON n.node_id = neighborhood.node_id
JOIN evidence AS v ON v.evidence_id = (
  SELECT candidate.evidence_id FROM evidence AS candidate
  WHERE candidate.node_id = n.node_id
  ORDER BY candidate.occurred_at DESC, candidate.evidence_id LIMIT 1
)
ORDER BY neighborhood.depth, n.canonical_name
""".strip()

ADVERSARIAL_SQL = """
SELECT n.canonical_name, n.world_id, n.state, n.sensitivity, v.source_ref
FROM nodes AS n
LEFT JOIN evidence AS v ON v.node_id = n.node_id
WHERE n.canonical_name LIKE 'Forbidden fixture:%'
   OR v.source_ref LIKE 'fixture://integrated/forbidden/%'
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
        raise RuntimeError(f"Reviewer query failed: {response!r}")
    return response["result"]["structuredContent"]


def build_review_proof(session_directory: Path) -> dict[str, Any]:
    fixture = build_integrated_fixture(session_directory)
    session = json.loads(Path(fixture["sessionPath"]).read_text(encoding="utf-8"))
    with (
        closing(sqlite3.connect(fixture["canonicalDatabase"])) as canonical,
        closing(sqlite3.connect(fixture["capabilityDatabase"])) as capability,
    ):
        source_kinds = [
            row[0]
            for row in canonical.execute(
                "SELECT DISTINCT source_kind FROM import_records "
                "ORDER BY source_kind"
            )
        ]
        forbidden_count = canonical.execute(
            "SELECT count(*) FROM nodes "
            "WHERE canonical_name LIKE 'Forbidden fixture:%'"
        ).fetchone()[0]
        return {
            "selectedWorld": session["selectedWorld"],
            "importedSourceKinds": source_kinds,
            "happyPath": _query_memory(session, capability, HAPPY_PATH_SQL),
            "forbiddenInCanonical": forbidden_count,
            "adversarial": _query_memory(
                session,
                capability,
                ADVERSARIAL_SQL,
            ),
            "sessionPath": fixture["sessionPath"],
            "canonicalDatabase": fixture["canonicalDatabase"],
            "capabilityDatabase": fixture["capabilityDatabase"],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    arguments = parser.parse_args()
    print(
        json.dumps(
            build_review_proof(arguments.session_dir),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
