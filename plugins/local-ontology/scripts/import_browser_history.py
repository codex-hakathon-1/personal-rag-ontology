#!/usr/bin/env python3
"""Import Chromium-family History into a canonical Local Ontology graph."""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any
from urllib.parse import urlparse


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = PLUGIN_ROOT / "schema" / "canonical.sql"
CHROMIUM_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)

BROWSER_RECORD_SCHEMA = """
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
"""


def _digest(*parts: str) -> str:
    value = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _identifier(kind: str, *parts: str) -> str:
    return f"{kind}-{_digest(*parts)[:32]}"


def _chromium_time(value: int) -> str:
    instant = CHROMIUM_EPOCH + timedelta(microseconds=value)
    return instant.isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_patterns(path: Path | None) -> list[tuple[str, re.Pattern[str]]]:
    if path is None:
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    patterns = []
    names = set()
    for entry in document.get("patterns", []):
        name = entry["name"]
        if name in names:
            raise ValueError(f"Sensitive pattern names must be unique: {name!r}")
        names.add(name)
        patterns.append((name, re.compile(entry["regex"], re.IGNORECASE)))
    return patterns


def _read_history_copy(history_path: Path) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="local-ontology-chromium-") as root:
        copy_path = Path(root) / "History"
        shutil.copyfile(history_path, copy_path)
        uri = copy_path.resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT u.id AS url_id, u.url, u.title, u.visit_count,
                       u.last_visit_time, v.id AS visit_id,
                       v.visit_time
                FROM urls AS u
                LEFT JOIN visits AS v ON v.url = u.id
                ORDER BY u.id, v.visit_time, v.id
                """
            ).fetchall()
            return [dict(row) for row in rows]


def _initialize_canonical(connection: sqlite3.Connection) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'worlds'"
    ).fetchone()
    if not exists:
        connection.executescript(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    else:
        connection.executescript(BROWSER_RECORD_SCHEMA)


def _upsert_node(connection: sqlite3.Connection, row: tuple[Any, ...]) -> None:
    connection.execute(
        """
        INSERT INTO nodes (
          node_id, world_id, type, canonical_name, summary, state,
          sensitivity, valid_from, valid_to, last_seen_at, superseded_by,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'active', 'normal', ?, NULL, ?, NULL, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
          canonical_name = excluded.canonical_name,
          summary = excluded.summary,
          valid_from = min(nodes.valid_from, excluded.valid_from),
          last_seen_at = max(nodes.last_seen_at, excluded.last_seen_at),
          updated_at = max(nodes.updated_at, excluded.updated_at)
        """,
        row,
    )


def _upsert_evidence(
    connection: sqlite3.Connection,
    evidence_id: str,
    node_id: str | None,
    edge_id: str | None,
    source_ref: str,
    occurred_at: str,
    excerpt: str,
    content_hash: str,
) -> None:
    connection.execute(
        """
        INSERT INTO evidence (
          evidence_id, node_id, edge_id, source_kind, source_ref,
          occurred_at, observed_at, excerpt, content_hash
        ) VALUES (?, ?, ?, 'browser_history', ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_id) DO UPDATE SET
          node_id = excluded.node_id,
          edge_id = excluded.edge_id,
          source_ref = excluded.source_ref,
          occurred_at = excluded.occurred_at,
          observed_at = excluded.observed_at,
          excerpt = excluded.excerpt,
          content_hash = excluded.content_hash
        """,
        (
            evidence_id,
            node_id,
            edge_id,
            source_ref,
            occurred_at,
            occurred_at,
            excerpt,
            content_hash,
        ),
    )


def import_chromium_history(
    history_path: Path,
    canonical_path: Path,
    world_id: str,
    sensitive_patterns_path: Path | None = None,
) -> dict[str, Any]:
    patterns = _load_patterns(sensitive_patterns_path)
    source_rows = _read_history_copy(history_path.resolve())
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        grouped[row["url_id"]].append(row)

    exclusions = {name: 0 for name, _ in patterns}
    allowed: list[dict[str, Any]] = []
    excluded_pages = 0
    for rows in grouped.values():
        page = rows[0]
        matched_name = next(
            (name for name, pattern in patterns if pattern.search(page["url"])),
            None,
        )
        if matched_name is not None:
            exclusions[matched_name] += 1
            excluded_pages += 1
            continue
        page["visits"] = [
            {"id": row["visit_id"], "time": row["visit_time"]}
            for row in rows
            if row["visit_id"] is not None
        ]
        if not page["visits"]:
            page["visits"] = [{"id": 0, "time": page["last_visit_time"]}]
        page["host"] = (urlparse(page["url"]).hostname or "").lower()
        allowed.append(page)

    canonical_path = canonical_path.resolve()
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(canonical_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _initialize_canonical(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO worlds (world_id, name, description, enabled)
                VALUES (?, ?, 'Imported Chromium browsing history', 1)
                ON CONFLICT(world_id) DO NOTHING
                """,
                (world_id, world_id.replace("-", " ").title()),
            )
            for page in allowed:
                url = page["url"]
                title = page["title"] or url
                host = page["host"]
                visit_times = [_chromium_time(visit["time"]) for visit in page["visits"]]
                first_visit = min(visit_times)
                last_visit = _chromium_time(page["last_visit_time"])
                page_id = _identifier("web-page", world_id, url)
                topic_id = _identifier("topic", world_id, host)
                edge_id = _identifier("edge", world_id, url, host)
                record_hash = _digest(
                    world_id, url, title, host, str(page["visit_count"]), last_visit
                )
                connection.execute(
                    """
                    INSERT INTO browser_history_records (
                      record_id, world_id, source_ref, url, title, host,
                      visit_count, last_visit_at, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id) DO UPDATE SET
                      source_ref = excluded.source_ref,
                      title = excluded.title,
                      host = excluded.host,
                      visit_count = excluded.visit_count,
                      last_visit_at = excluded.last_visit_at,
                      content_hash = excluded.content_hash
                    """,
                    (
                        _identifier("browser-record", world_id, url),
                        world_id,
                        url,
                        url,
                        title,
                        host,
                        page["visit_count"],
                        last_visit,
                        record_hash,
                    ),
                )
                _upsert_node(
                    connection,
                    (
                        page_id,
                        world_id,
                        "web_page",
                        title,
                        f"Visited {host} {page['visit_count']} time(s).",
                        first_visit,
                        last_visit,
                        first_visit,
                        last_visit,
                    ),
                )
                _upsert_node(
                    connection,
                    (
                        topic_id,
                        world_id,
                        "topic",
                        host,
                        f"Chromium history topic candidate for {host}.",
                        first_visit,
                        last_visit,
                        first_visit,
                        last_visit,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO edges (
                      edge_id, world_id, from_node_id, relation, to_node_id,
                      state, valid_from, valid_to, confidence, evidence_count,
                      created_at, updated_at
                    ) VALUES (?, ?, ?, 'about', ?, 'active', ?, NULL, 1.0, ?, ?, ?)
                    ON CONFLICT(edge_id) DO UPDATE SET
                      evidence_count = excluded.evidence_count,
                      valid_from = min(edges.valid_from, excluded.valid_from),
                      updated_at = max(edges.updated_at, excluded.updated_at)
                    """,
                    (
                        edge_id,
                        world_id,
                        page_id,
                        topic_id,
                        first_visit,
                        len(page["visits"]),
                        first_visit,
                        last_visit,
                    ),
                )
                for visit in page["visits"]:
                    occurred_at = _chromium_time(visit["time"])
                    content_hash = _digest(
                        url,
                        title,
                        host,
                        str(page["visit_count"]),
                        occurred_at,
                    )
                    excerpt = f"Visited {title} on {host}."
                    visit_key = str(visit["id"])
                    _upsert_evidence(
                        connection,
                        _identifier("evidence-page", world_id, url, visit_key),
                        page_id,
                        None,
                        url,
                        occurred_at,
                        excerpt,
                        content_hash,
                    )
                    _upsert_evidence(
                        connection,
                        _identifier("evidence-topic", world_id, url, visit_key),
                        topic_id,
                        None,
                        url,
                        occurred_at,
                        excerpt,
                        content_hash,
                    )
                    _upsert_evidence(
                        connection,
                        _identifier("evidence-edge", world_id, url, visit_key),
                        None,
                        edge_id,
                        url,
                        occurred_at,
                        excerpt,
                        content_hash,
                    )

    return {
        "excludedPages": excluded_pages,
        "exclusions": [
            {"pattern": name, "count": count}
            for name, count in exclusions.items()
            if count
        ],
        "importedPages": len(allowed),
        "importedVisits": sum(len(page["visits"]) for page in allowed),
        "topicCandidates": len({page["host"] for page in allowed}),
        "world": world_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--world", required=True)
    parser.add_argument("--sensitive-patterns", type=Path)
    arguments = parser.parse_args()
    report = import_chromium_history(
        arguments.history,
        arguments.canonical,
        arguments.world,
        arguments.sensitive_patterns,
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
