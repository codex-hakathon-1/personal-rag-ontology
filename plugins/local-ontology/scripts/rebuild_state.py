#!/usr/bin/env python3
"""Deterministically materialize lifecycle state in a canonical graph."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Lifecycle timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _dormancy_rules(rules: dict[str, Any]) -> dict[str, int]:
    configured = rules.get("dormant_after_days", {})
    if not isinstance(configured, dict):
        raise ValueError("dormant_after_days must be an object")
    normalized: dict[str, int] = {}
    for node_type, days in configured.items():
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("Dormancy rule node types must be non-empty strings")
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            raise ValueError("Dormancy thresholds must be non-negative integers")
        normalized[node_type] = days
    return normalized


def rebuild_state(
    canonical_path: Path,
    rules: dict[str, Any],
    as_of: str,
) -> dict[str, int]:
    """Apply configured age rules using an explicit deterministic clock."""
    reference_time = _timestamp(as_of)
    dormant_after_days = _dormancy_rules(rules)
    changed_to_active = 0
    changed_to_dormant = 0
    changed_to_superseded = 0

    with closing(sqlite3.connect(canonical_path)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            replacement_rows = connection.execute(
                """
                SELECT DISTINCT
                  edge.to_node_id AS replaced_id,
                  edge.from_node_id AS replacement_id,
                  edge.valid_from,
                  edge.edge_id
                FROM edges AS edge
                JOIN nodes AS replacement
                  ON replacement.node_id = edge.from_node_id
                 AND replacement.world_id = edge.world_id
                JOIN nodes AS replaced
                  ON replaced.node_id = edge.to_node_id
                 AND replaced.world_id = edge.world_id
                WHERE edge.relation = 'supersedes'
                  AND edge.state = 'active'
                  AND EXISTS (
                    SELECT 1 FROM evidence
                    WHERE evidence.edge_id = edge.edge_id
                  )
                ORDER BY
                  edge.to_node_id,
                  COALESCE(edge.valid_from, '') DESC,
                  edge.edge_id
                """
            ).fetchall()
            replacements: dict[str, str] = {}
            for row in replacement_rows:
                replacements.setdefault(row["replaced_id"], row["replacement_id"])

            rows = connection.execute(
                """
                SELECT node_id, type, state, last_seen_at
                FROM nodes
                WHERE state != 'superseded'
                ORDER BY node_id
                """
            ).fetchall()
            for row in rows:
                if row["node_id"] in replacements:
                    continue
                threshold = dormant_after_days.get(row["type"])
                if threshold is None or row["last_seen_at"] is None:
                    continue
                last_seen_at = _timestamp(row["last_seen_at"])
                desired_state = (
                    "dormant"
                    if last_seen_at < reference_time - timedelta(days=threshold)
                    else "active"
                )
                if row["state"] == desired_state:
                    continue
                connection.execute(
                    """
                    UPDATE nodes
                    SET state = ?, superseded_by = NULL, updated_at = ?
                    WHERE node_id = ?
                    """,
                    (desired_state, as_of, row["node_id"]),
                )
                if desired_state == "dormant":
                    changed_to_dormant += 1
                else:
                    changed_to_active += 1

            for replaced_id, replacement_id in replacements.items():
                current = connection.execute(
                    "SELECT state, superseded_by FROM nodes WHERE node_id = ?",
                    (replaced_id,),
                ).fetchone()
                if (
                    current["state"] == "superseded"
                    and current["superseded_by"] == replacement_id
                ):
                    continue
                connection.execute(
                    """
                    UPDATE nodes
                    SET state = 'superseded', superseded_by = ?, updated_at = ?
                    WHERE node_id = ?
                    """,
                    (replacement_id, as_of, replaced_id),
                )
                changed_to_superseded += 1

    return {
        "changedToActive": changed_to_active,
        "changedToDormant": changed_to_dormant,
        "changedToSuperseded": changed_to_superseded,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    arguments = parser.parse_args()
    rules = json.loads(arguments.rules.read_text(encoding="utf-8"))
    report = rebuild_state(arguments.canonical, rules, arguments.as_of)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
