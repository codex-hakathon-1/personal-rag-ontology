#!/usr/bin/env python3
"""Import Markdown Codex conversations into a canonical ontology graph."""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from import_records import CandidateEntity, ImportRecord


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = PLUGIN_ROOT / "schema" / "canonical.sql"
IMPORT_RECORD_SCHEMA = PLUGIN_ROOT / "schema" / "import_records.sql"
CLAIM_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(Decision|Plan|Topic)(?:\*\*)?\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
ROLE_PATTERN = re.compile(r"^#{1,6}\s+(User|Assistant)\s*$", re.IGNORECASE)
REPLACEMENT_PATTERN = re.compile(
    r"^\s*(?:This|That|The|It)\s+(decision|plan)\s+"
    r"(?:explicitly\s+)?replaces\s+[\"“'](.+?)[\"”']\.?\s*$",
    re.IGNORECASE,
)
KEY_LIKE_PATTERN = re.compile(
    r"(?i)\b((?:api[_-]?)?(?:key|token|secret|password|passwd|pwd)"
    r"[a-z0-9_-]*\s*[:=]\s*)([^\s\"'`,;]+)"
)
TOKEN_LIKE_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~-]{16,}"),
)


@dataclass(frozen=True)
class ExtractedEntity:
    type: str
    canonical_name: str
    line_number: int
    excerpt: str
    role: str | None


@dataclass(frozen=True)
class SupersessionStatement:
    type: str
    replacement_name: str
    replaced_name: str
    line_number: int
    excerpt: str
    role: str | None


@dataclass(frozen=True)
class CodexDocument:
    path: Path
    relative_path: str
    title: str
    occurred_at: str
    source_content_hash: str
    redacted_markdown: str
    entities: tuple[ExtractedEntity, ...]
    supersessions: tuple[SupersessionStatement, ...]
    redactions: dict[str, int]


@dataclass(frozen=True)
class RedactionRules:
    secret_paths: tuple[str, ...]


def _load_redaction_rules(path: Path | None) -> RedactionRules:
    if path is None:
        return RedactionRules(())
    document = json.loads(path.read_text(encoding="utf-8"))
    values = document.get("secret_paths", [])
    if not isinstance(values, list) or not all(
        isinstance(value, str) and value for value in values
    ):
        raise ValueError("secret_paths must be a list of non-empty strings")
    return RedactionRules(tuple(values))


def _redact(text: str, rules: RedactionRules) -> tuple[str, dict[str, int]]:
    counts = {
        "configured_secret_path": 0,
        "key_like_value": 0,
        "token_like_value": 0,
    }
    redacted = text
    for secret_path in sorted(rules.secret_paths, key=len, reverse=True):
        redacted, replacements = re.subn(
            re.escape(secret_path),
            "[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )
        counts["configured_secret_path"] += replacements

    def replace_key_like(match: re.Match[str]) -> str:
        counts["key_like_value"] += 1
        return f"{match.group(1)}[REDACTED]"

    redacted = KEY_LIKE_PATTERN.sub(replace_key_like, redacted)
    for pattern in TOKEN_LIKE_PATTERNS:
        redacted, replacements = pattern.subn("[REDACTED]", redacted)
        counts["token_like_value"] += replacements
    return redacted, counts


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _identifier(kind: str, *parts: str) -> str:
    return f"{kind}-{_digest(*parts)[:32]}"


def _fact_key(value: str) -> str:
    return value.strip().strip("\"'“”").rstrip(".!?").strip().casefold()


def _normalized_instant(value: str, path: Path) -> str:
    candidate = value.strip().strip('"\'')
    try:
        instant = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Invalid Codex log date in {path}: {value!r}") from error
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    metadata: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return metadata, index + 1
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip().lower()] = value.strip()
    return {}, 0


def _frontmatter_topics(value: str) -> tuple[str, ...]:
    candidate = value.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    return tuple(
        topic.strip().strip('"\'')
        for topic in candidate.split(",")
        if topic.strip().strip('"\'')
    )


def _markdown_paths(logs_path: Path) -> tuple[Path, tuple[Path, ...]]:
    resolved = logs_path.resolve()
    if resolved.is_file():
        if resolved.suffix.lower() not in {".md", ".markdown"}:
            raise ValueError(f"Codex log must be Markdown: {resolved}")
        return resolved.parent, (resolved,)
    if not resolved.is_dir():
        raise FileNotFoundError(f"Codex logs path does not exist: {resolved}")
    paths = tuple(
        sorted(
            path
            for path in resolved.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
        )
    )
    return resolved, paths


def _parse_document(
    path: Path,
    root: Path,
    redaction_rules: RedactionRules,
) -> CodexDocument:
    original = path.read_text(encoding="utf-8")
    redacted, redactions = _redact(original, redaction_rules)
    lines = redacted.splitlines()
    metadata, body_start = _parse_frontmatter(lines)
    title = metadata.get("title") or path.stem.replace("-", " ").title()
    date_value = metadata.get("date") or metadata.get("created_at")
    if not date_value:
        raise ValueError(f"Codex log requires a frontmatter date: {path}")
    occurred_at = _normalized_instant(date_value, path)
    entities: list[ExtractedEntity] = [
        ExtractedEntity("conversation", title, 1, title, None)
    ]
    topics_line = next(
        (
            index
            for index, line in enumerate(lines[:body_start], start=1)
            if line.lower().startswith("topics:")
        ),
        1,
    )
    entities.extend(
        ExtractedEntity("topic", topic, topics_line, topic, None)
        for topic in _frontmatter_topics(metadata.get("topics", ""))
    )
    role: str | None = None
    latest_claim: dict[str, ExtractedEntity] = {}
    supersessions: list[SupersessionStatement] = []
    for line_number, line in enumerate(lines[body_start:], start=body_start + 1):
        role_match = ROLE_PATTERN.match(line)
        if role_match:
            role = role_match.group(1).lower()
            continue
        claim_match = CLAIM_PATTERN.match(line)
        if claim_match:
            entity = ExtractedEntity(
                claim_match.group(1).lower(),
                claim_match.group(2).strip(),
                line_number,
                line.strip(),
                role,
            )
            entities.append(entity)
            if entity.type in {"decision", "plan"}:
                latest_claim[entity.type] = entity
            continue
        replacement_match = REPLACEMENT_PATTERN.match(line)
        if replacement_match:
            claim_type = replacement_match.group(1).lower()
            replacement = latest_claim.get(claim_type)
            if replacement is not None:
                supersessions.append(
                    SupersessionStatement(
                        claim_type,
                        replacement.canonical_name,
                        replacement_match.group(2).strip(),
                        line_number,
                        line.strip(),
                        role,
                    )
                )
    return CodexDocument(
        path=path,
        relative_path=path.relative_to(root).as_posix(),
        title=title,
        occurred_at=occurred_at,
        source_content_hash=hashlib.sha256(original.encode("utf-8")).hexdigest(),
        redacted_markdown=redacted,
        entities=tuple(entities),
        supersessions=tuple(supersessions),
        redactions=redactions,
    )


def _initialize_canonical(connection: sqlite3.Connection) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'worlds'"
    ).fetchone()
    if not exists:
        connection.executescript(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    connection.executescript(IMPORT_RECORD_SCHEMA.read_text(encoding="utf-8"))


def _remove_previous_document(
    connection: sqlite3.Connection,
    world_id: str,
    document: CodexDocument,
) -> None:
    source_prefix = f"codex://{document.relative_path}#"
    prefix_length = len(source_prefix)
    previous_node_ids = {
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT v.node_id
            FROM evidence AS v
            JOIN nodes AS n ON n.node_id = v.node_id
            WHERE n.world_id = ? AND v.source_kind = 'codex_logs'
              AND substr(v.source_ref, 1, ?) = ?
              AND v.node_id IS NOT NULL
            """,
            (world_id, prefix_length, source_prefix),
        )
    }
    previous_edge_ids = {
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT v.edge_id
            FROM evidence AS v
            JOIN edges AS e ON e.edge_id = v.edge_id
            WHERE e.world_id = ? AND v.source_kind = 'codex_logs'
              AND substr(v.source_ref, 1, ?) = ?
              AND v.edge_id IS NOT NULL
            """,
            (world_id, prefix_length, source_prefix),
        )
    }
    superseded_targets = connection.execute(
        f"""
        SELECT from_node_id, to_node_id
        FROM edges
        WHERE relation = 'supersedes' AND edge_id IN (
          {', '.join('?' for _ in previous_edge_ids) or "''"}
        )
        """,
        tuple(previous_edge_ids),
    ).fetchall()
    conversation_id = _identifier(
        "conversation",
        world_id,
        document.relative_path,
    )
    connection.execute(
        """
        DELETE FROM evidence
        WHERE source_kind = 'codex_logs'
          AND substr(source_ref, 1, ?) = ?
          AND (
            node_id IN (SELECT node_id FROM nodes WHERE world_id = ?)
            OR edge_id IN (SELECT edge_id FROM edges WHERE world_id = ?)
          )
        """,
        (prefix_length, source_prefix, world_id, world_id),
    )
    connection.execute(
        """
        DELETE FROM import_records
        WHERE world_id = ? AND source_kind = 'codex_logs'
          AND substr(source_ref, 1, ?) = ?
        """,
        (world_id, prefix_length, source_prefix),
    )
    connection.execute(
        "DELETE FROM edges WHERE world_id = ? AND relation = 'mentioned_in' "
        "AND to_node_id = ?",
        (world_id, conversation_id),
    )
    if previous_edge_ids:
        edge_placeholders = ", ".join("?" for _ in previous_edge_ids)
        connection.execute(
            f"DELETE FROM edges WHERE edge_id IN ({edge_placeholders})",
            tuple(previous_edge_ids),
        )
    for replacement_id, replaced_id in superseded_targets:
        still_superseded = connection.execute(
            """
            SELECT 1 FROM edges
            WHERE relation = 'supersedes' AND to_node_id = ? AND state = 'active'
            LIMIT 1
            """,
            (replaced_id,),
        ).fetchone()
        if still_superseded is None:
            connection.execute(
                """
                UPDATE nodes
                SET state = 'active', superseded_by = NULL
                WHERE node_id = ? AND superseded_by = ?
                """,
                (replaced_id, replacement_id),
            )
    for node_id in previous_node_ids:
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
            (node_id,),
        )


def _upsert_node(
    connection: sqlite3.Connection,
    node_id: str,
    world_id: str,
    entity: ExtractedEntity,
    occurred_at: str,
) -> None:
    summary = (
        f"Codex conversation: {entity.canonical_name}"
        if entity.type == "conversation"
        else entity.canonical_name
    )
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
            node_id,
            world_id,
            entity.type,
            entity.canonical_name,
            summary,
            occurred_at,
            occurred_at,
            occurred_at,
            occurred_at,
        ),
    )


def _entity_node_id(
    world_id: str,
    document: CodexDocument,
    entity: ExtractedEntity,
) -> str:
    if entity.type == "conversation":
        return _identifier("conversation", world_id, document.relative_path)
    identity = (
        _fact_key(entity.canonical_name)
        if entity.type in {"decision", "plan"}
        else entity.canonical_name.casefold()
    )
    return _identifier(
        entity.type,
        world_id,
        identity,
    )


def _record_for(
    document: CodexDocument,
    entity: ExtractedEntity,
    source_ref: str,
) -> ImportRecord:
    return ImportRecord(
        source_kind="codex_logs",
        source_ref=source_ref,
        occurred_at=document.occurred_at,
        raw_text_or_metadata={
            "role": entity.role,
            "text": entity.excerpt,
            "source_content_hash": document.source_content_hash,
        },
        candidate_entities=(
            CandidateEntity(entity.type, entity.canonical_name),
        ),
        provenance={
            "line": entity.line_number,
            "path": document.relative_path,
        },
    )


def _upsert_import_record(
    connection: sqlite3.Connection,
    world_id: str,
    record: ImportRecord,
    entity: ExtractedEntity,
) -> None:
    record_id = _identifier(
        "import-record",
        world_id,
        record.source_ref,
        entity.type,
        entity.canonical_name.casefold(),
    )
    connection.execute(
        """
        INSERT INTO import_records (
          record_id, world_id, source_kind, source_ref, occurred_at,
          raw_text_or_metadata, candidate_entities, provenance, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(record_id) DO UPDATE SET
          occurred_at = excluded.occurred_at,
          raw_text_or_metadata = excluded.raw_text_or_metadata,
          candidate_entities = excluded.candidate_entities,
          provenance = excluded.provenance,
          content_hash = excluded.content_hash
        """,
        (
            record_id,
            world_id,
            record.source_kind,
            record.source_ref,
            record.occurred_at,
            record.raw_metadata_json(),
            record.candidate_entities_json(),
            record.provenance_json(),
            record.content_hash(),
        ),
    )


def _upsert_evidence(
    connection: sqlite3.Connection,
    world_id: str,
    node_id: str,
    record: ImportRecord,
    entity: ExtractedEntity,
) -> None:
    connection.execute(
        """
        INSERT INTO evidence (
          evidence_id, node_id, edge_id, source_kind, source_ref,
          occurred_at, observed_at, excerpt, content_hash
        ) VALUES (?, ?, NULL, 'codex_logs', ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_id) DO UPDATE SET
          node_id = excluded.node_id,
          occurred_at = excluded.occurred_at,
          observed_at = excluded.observed_at,
          excerpt = excluded.excerpt,
          content_hash = excluded.content_hash
        """,
        (
            _identifier(
                "evidence",
                world_id,
                record.source_ref,
                entity.type,
                entity.canonical_name.casefold(),
            ),
            node_id,
            record.source_ref,
            record.occurred_at,
            record.occurred_at,
            entity.excerpt,
            record.content_hash(),
        ),
    )


def _upsert_membership_edge(
    connection: sqlite3.Connection,
    world_id: str,
    node_id: str,
    conversation_id: str,
    occurred_at: str,
) -> None:
    edge_id = _identifier("edge", world_id, node_id, "mentioned_in", conversation_id)
    connection.execute(
        """
        INSERT INTO edges (
          edge_id, world_id, from_node_id, relation, to_node_id, state,
          valid_from, valid_to, confidence, evidence_count, created_at, updated_at
        ) VALUES (?, ?, ?, 'mentioned_in', ?, 'active', ?, NULL, 1.0, 1, ?, ?)
        ON CONFLICT(edge_id) DO UPDATE SET
          evidence_count = excluded.evidence_count,
          updated_at = max(edges.updated_at, excluded.updated_at)
        """,
        (
            edge_id,
            world_id,
            node_id,
            conversation_id,
            occurred_at,
            occurred_at,
            occurred_at,
        ),
    )


def _upsert_supersession(
    connection: sqlite3.Connection,
    world_id: str,
    document: CodexDocument,
    statement: SupersessionStatement,
) -> bool:
    replacement_id = _identifier(
        statement.type,
        world_id,
        _fact_key(statement.replacement_name),
    )
    replaced_id = _identifier(
        statement.type,
        world_id,
        _fact_key(statement.replaced_name),
    )
    present = connection.execute(
        "SELECT node_id FROM nodes WHERE node_id IN (?, ?)",
        (replacement_id, replaced_id),
    ).fetchall()
    if {row[0] for row in present} != {replacement_id, replaced_id}:
        return False
    edge_id = _identifier(
        "edge",
        world_id,
        replacement_id,
        "supersedes",
        replaced_id,
    )
    source_ref = f"codex://{document.relative_path}#L{statement.line_number}"
    record = ImportRecord(
        source_kind="codex_logs",
        source_ref=source_ref,
        occurred_at=document.occurred_at,
        raw_text_or_metadata={
            "role": statement.role,
            "text": statement.excerpt,
            "source_content_hash": document.source_content_hash,
        },
        candidate_entities=(
            CandidateEntity(statement.type, statement.replacement_name),
            CandidateEntity(statement.type, statement.replaced_name),
        ),
        provenance={
            "line": statement.line_number,
            "path": document.relative_path,
            "signal": "explicit_replacement",
        },
    )
    record_identity = ExtractedEntity(
        statement.type,
        f"{statement.replacement_name}\x1f{statement.replaced_name}",
        statement.line_number,
        statement.excerpt,
        statement.role,
    )
    _upsert_import_record(connection, world_id, record, record_identity)
    connection.execute(
        """
        INSERT INTO edges (
          edge_id, world_id, from_node_id, relation, to_node_id, state,
          valid_from, valid_to, confidence, evidence_count, created_at, updated_at
        ) VALUES (?, ?, ?, 'supersedes', ?, 'active', ?, NULL, 0.99, 1, ?, ?)
        ON CONFLICT(edge_id) DO UPDATE SET
          state = 'active',
          confidence = 0.99,
          evidence_count = 1,
          updated_at = excluded.updated_at
        """,
        (
            edge_id,
            world_id,
            replacement_id,
            replaced_id,
            document.occurred_at,
            document.occurred_at,
            document.occurred_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO evidence (
          evidence_id, node_id, edge_id, source_kind, source_ref,
          occurred_at, observed_at, excerpt, content_hash
        ) VALUES (?, NULL, ?, 'codex_logs', ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_id) DO UPDATE SET
          edge_id = excluded.edge_id,
          occurred_at = excluded.occurred_at,
          observed_at = excluded.observed_at,
          excerpt = excluded.excerpt,
          content_hash = excluded.content_hash
        """,
        (
            _identifier("evidence", world_id, source_ref, "supersedes"),
            edge_id,
            source_ref,
            document.occurred_at,
            document.occurred_at,
            statement.excerpt,
            record.content_hash(),
        ),
    )
    connection.execute(
        """
        UPDATE nodes
        SET state = 'superseded', superseded_by = ?, updated_at = ?
        WHERE node_id = ?
        """,
        (replacement_id, document.occurred_at, replaced_id),
    )
    return True


def import_codex_logs(
    logs_path: Path,
    canonical_path: Path,
    world_id: str,
    secret_paths_path: Path | None = None,
) -> dict[str, Any]:
    root, paths = _markdown_paths(logs_path)
    redaction_rules = _load_redaction_rules(secret_paths_path)
    documents = tuple(
        sorted(
            (_parse_document(path, root, redaction_rules) for path in paths),
            key=lambda document: (document.occurred_at, document.relative_path),
        )
    )
    canonical_path = canonical_path.resolve()
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(canonical_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _initialize_canonical(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO worlds (world_id, name, description, enabled)
                VALUES (?, ?, 'Imported Markdown Codex conversations', 1)
                ON CONFLICT(world_id) DO NOTHING
                """,
                (world_id, world_id.replace("-", " ").title()),
            )
            for document in documents:
                _remove_previous_document(connection, world_id, document)
                conversation = document.entities[0]
                conversation_id = _entity_node_id(world_id, document, conversation)
                for entity in document.entities:
                    node_id = _entity_node_id(world_id, document, entity)
                    source_ref = (
                        f"codex://{document.relative_path}#document"
                        if entity.type == "conversation"
                        else f"codex://{document.relative_path}#L{entity.line_number}"
                    )
                    record = _record_for(document, entity, source_ref)
                    _upsert_node(
                        connection,
                        node_id,
                        world_id,
                        entity,
                        document.occurred_at,
                    )
                    _upsert_import_record(connection, world_id, record, entity)
                    _upsert_evidence(
                        connection,
                        world_id,
                        node_id,
                        record,
                        entity,
                    )
                    if entity.type != "conversation":
                        _upsert_membership_edge(
                            connection,
                            world_id,
                            node_id,
                            conversation_id,
                            document.occurred_at,
                        )
            resolved_supersessions = sum(
                _upsert_supersession(connection, world_id, document, statement)
                for document in documents
                for statement in document.supersessions
            )
    return {
        "importedConversations": len(documents),
        "importedDecisions": sum(
            entity.type == "decision"
            for document in documents
            for entity in document.entities
        ),
        "importedPlans": sum(
            entity.type == "plan"
            for document in documents
            for entity in document.entities
        ),
        "topicCandidates": len(
            {
                entity.canonical_name.casefold()
                for document in documents
                for entity in document.entities
                if entity.type == "topic"
            }
        ),
        "redactions": {
            category: sum(
                document.redactions[category] for document in documents
            )
            for category in (
                "configured_secret_path",
                "key_like_value",
                "token_like_value",
            )
        },
        "explicitSupersessions": resolved_supersessions,
        "world": world_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--world", required=True)
    parser.add_argument("--secret-paths", type=Path)
    arguments = parser.parse_args()
    report = import_codex_logs(
        arguments.logs,
        arguments.canonical,
        arguments.world,
        arguments.secret_paths,
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
