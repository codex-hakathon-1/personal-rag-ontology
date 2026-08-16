#!/usr/bin/env python3
"""Import Chromium-family History into a canonical Local Ontology graph."""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
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

from import_records import CandidateEntity, ImportRecord


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = PLUGIN_ROOT / "schema" / "canonical.sql"
BROWSER_RECORD_SCHEMA = PLUGIN_ROOT / "schema" / "browser_history.sql"
CHROMIUM_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ChromiumVisit:
    source_id: int
    occurred_at: str


@dataclass(frozen=True)
class ChromiumPage:
    source_id: int
    url: str
    title: str
    host: str
    visit_count: int
    last_visit_at: str
    visits: tuple[ChromiumVisit, ...]

    def import_records(self) -> tuple[ImportRecord, ...]:
        metadata = {
            "url": self.url,
            "title": self.title,
            "host": self.host,
            "visit_count": self.visit_count,
            "last_visit_at": self.last_visit_at,
        }
        candidates = (
            CandidateEntity("web_page", self.title),
            CandidateEntity("topic", self.host),
        )
        return tuple(
            ImportRecord(
                source_kind="browser_history",
                source_ref=self.url,
                occurred_at=visit.occurred_at,
                raw_text_or_metadata=metadata,
                candidate_entities=candidates,
                provenance={
                    "chromium_url_id": self.source_id,
                    "chromium_visit_id": visit.source_id,
                },
            )
            for visit in self.visits
        )


@dataclass(frozen=True)
class NodeCandidate:
    node_id: str
    world_id: str
    type: str
    canonical_name: str
    summary: str
    valid_from: str
    last_seen_at: str
    created_at: str
    updated_at: str


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


def _read_history_copy(history_path: Path) -> list[ChromiumPage]:
    with tempfile.TemporaryDirectory(prefix="local-ontology-chromium-") as root:
        copy_path = Path(root) / "History"
        shutil.copyfile(history_path, copy_path)
        wal_path = Path(f"{history_path}-wal")
        if wal_path.exists():
            shutil.copyfile(wal_path, Path(f"{copy_path}-wal"))
        uri = copy_path.resolve().as_uri() + "?mode=ro"
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
    grouped_rows: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped_rows[row["url_id"]].append(row)
    pages = []
    for page_rows in grouped_rows.values():
        first = page_rows[0]
        visits = tuple(
            ChromiumVisit(row["visit_id"], _chromium_time(row["visit_time"]))
            for row in page_rows
            if row["visit_id"] is not None
        )
        if not visits:
            visits = (ChromiumVisit(0, _chromium_time(first["last_visit_time"])),)
        pages.append(
            ChromiumPage(
                source_id=first["url_id"],
                url=first["url"],
                title=first["title"] or first["url"],
                host=(urlparse(first["url"]).hostname or "").lower(),
                visit_count=first["visit_count"],
                last_visit_at=_chromium_time(first["last_visit_time"]),
                visits=visits,
            )
        )
    return pages


def _initialize_canonical(connection: sqlite3.Connection) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'worlds'"
    ).fetchone()
    if not exists:
        connection.executescript(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    connection.executescript(BROWSER_RECORD_SCHEMA.read_text(encoding="utf-8"))


def _upsert_node(connection: sqlite3.Connection, node: NodeCandidate) -> None:
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
        (
            node.node_id,
            node.world_id,
            node.type,
            node.canonical_name,
            node.summary,
            node.valid_from,
            node.last_seen_at,
            node.created_at,
            node.updated_at,
        ),
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


def _remove_excluded_page(
    connection: sqlite3.Connection,
    world_id: str,
    url: str,
) -> None:
    host = (urlparse(url).hostname or "").lower()
    page_id = _identifier("web-page", world_id, url)
    topic_id = _identifier("topic", world_id, host)
    edge_id = _identifier("edge", world_id, url, host)
    connection.execute(
        "DELETE FROM evidence WHERE source_ref = ? OR node_id = ? OR edge_id = ?",
        (url, page_id, edge_id),
    )
    connection.execute("DELETE FROM node_aliases WHERE node_id = ?", (page_id,))
    connection.execute("DELETE FROM edges WHERE edge_id = ?", (edge_id,))
    connection.execute(
        "DELETE FROM browser_history_records WHERE world_id = ? AND url = ?",
        (world_id, url),
    )
    connection.execute("DELETE FROM nodes WHERE node_id = ?", (page_id,))
    connection.execute(
        """
        DELETE FROM nodes
        WHERE node_id = ?
          AND NOT EXISTS (
            SELECT 1 FROM evidence WHERE evidence.node_id = nodes.node_id
          )
          AND NOT EXISTS (
            SELECT 1 FROM edges
            WHERE edges.from_node_id = nodes.node_id
               OR edges.to_node_id = nodes.node_id
          )
          AND NOT EXISTS (
            SELECT 1 FROM node_aliases
            WHERE node_aliases.node_id = nodes.node_id
          )
        """,
        (topic_id,),
    )


def import_chromium_history(
    history_path: Path,
    canonical_path: Path,
    world_id: str,
    sensitive_patterns_path: Path | None = None,
) -> dict[str, Any]:
    patterns = _load_patterns(sensitive_patterns_path)
    pages = _read_history_copy(history_path.resolve())
    exclusions = {name: 0 for name, _ in patterns}
    allowed_pages: list[ChromiumPage] = []
    excluded_pages_to_remove: list[ChromiumPage] = []
    excluded_pages = 0
    for page in pages:
        matched_name = next(
            (name for name, pattern in patterns if pattern.search(page.url)),
            None,
        )
        if matched_name is not None:
            exclusions[matched_name] += 1
            excluded_pages += 1
            excluded_pages_to_remove.append(page)
            continue
        allowed_pages.append(page)

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
            for page in excluded_pages_to_remove:
                _remove_excluded_page(connection, world_id, page.url)
            for page in allowed_pages:
                url = page.url
                title = page.title
                host = page.host
                first_visit = min(visit.occurred_at for visit in page.visits)
                last_visit = page.last_visit_at
                page_id = _identifier("web-page", world_id, url)
                topic_id = _identifier("topic", world_id, host)
                edge_id = _identifier("edge", world_id, url, host)
                record_hash = _digest(
                    world_id, url, title, host, str(page.visit_count), last_visit
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
                        page.visit_count,
                        last_visit,
                        record_hash,
                    ),
                )
                _upsert_node(
                    connection,
                    NodeCandidate(
                        node_id=page_id,
                        world_id=world_id,
                        type="web_page",
                        canonical_name=title,
                        summary=f"Visited {host} {page.visit_count} time(s).",
                        valid_from=first_visit,
                        last_seen_at=last_visit,
                        created_at=first_visit,
                        updated_at=last_visit,
                    ),
                )
                _upsert_node(
                    connection,
                    NodeCandidate(
                        node_id=topic_id,
                        world_id=world_id,
                        type="topic",
                        canonical_name=host,
                        summary=f"Chromium history topic candidate for {host}.",
                        valid_from=first_visit,
                        last_seen_at=last_visit,
                        created_at=first_visit,
                        updated_at=last_visit,
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
                        len(page.visits),
                        first_visit,
                        last_visit,
                    ),
                )
                for record in page.import_records():
                    excerpt = f"Visited {title} on {host}."
                    visit_key = str(record.provenance["chromium_visit_id"])
                    targets = (
                        ("page", page_id, None),
                        ("topic", topic_id, None),
                        ("edge", None, edge_id),
                    )
                    for target, node_id, target_edge_id in targets:
                        _upsert_evidence(
                            connection,
                            _identifier(
                                f"evidence-{target}", world_id, url, visit_key
                            ),
                            node_id,
                            target_edge_id,
                            record.source_ref,
                            record.occurred_at,
                            excerpt,
                            record.content_hash(),
                        )

    return {
        "excludedPages": excluded_pages,
        "exclusions": [
            {"pattern": name, "count": count}
            for name, count in exclusions.items()
            if count
        ],
        "importedPages": len(allowed_pages),
        "importedVisits": sum(len(page.visits) for page in allowed_pages),
        "topicCandidates": len({page.host for page in allowed_pages}),
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
