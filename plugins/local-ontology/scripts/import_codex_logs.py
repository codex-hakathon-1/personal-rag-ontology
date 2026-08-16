#!/usr/bin/env python3
"""Import Markdown Codex conversations into a canonical ontology graph."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from codex_log_parser import (
    CodexDocument,
    EntityType,
    ExtractedEntity,
    SourceEvidence,
    SupersessionStatement,
    load_redaction_rules,
    markdown_paths,
    parse_document,
)
from import_records import CandidateEntity, ImportRecord


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = PLUGIN_ROOT / "schema" / "canonical.sql"
IMPORT_RECORD_SCHEMA = PLUGIN_ROOT / "schema" / "import_records.sql"


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _identifier(kind: str, *parts: str) -> str:
    return f"{kind}-{_digest(*parts)[:32]}"


def _fact_key(value: str) -> str:
    return value.strip().strip("\"'“”").rstrip(".!?").strip().casefold()


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
    previous_node_ids.update(
        node_id
        for endpoints in superseded_targets
        for node_id in endpoints
    )
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
    for _, replaced_id in superseded_targets:
        remaining_replacement = connection.execute(
            """
            SELECT from_node_id FROM edges
            WHERE relation = 'supersedes' AND to_node_id = ? AND state = 'active'
            ORDER BY valid_from DESC, edge_id DESC
            LIMIT 1
            """,
            (replaced_id,),
        ).fetchone()
        if remaining_replacement is None:
            connection.execute(
                """
                UPDATE nodes
                SET state = 'active', superseded_by = NULL
                WHERE node_id = ?
                """,
                (replaced_id,),
            )
        else:
            connection.execute(
                """
                UPDATE nodes
                SET state = 'superseded', superseded_by = ?
                WHERE node_id = ?
                """,
                (remaining_replacement[0], replaced_id),
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
        if entity.type is EntityType.CONVERSATION
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
            entity.type.value,
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
    if entity.type is EntityType.CONVERSATION:
        return _identifier("conversation", world_id, document.relative_path)
    identity = (
        _fact_key(entity.canonical_name)
        if entity.type in {EntityType.DECISION, EntityType.PLAN}
        else entity.canonical_name.casefold()
    )
    return _identifier(
        entity.type.value,
        world_id,
        identity,
    )


def _codex_import_record(
    document: CodexDocument,
    source_ref: str,
    source: SourceEvidence,
    candidate_entities: tuple[CandidateEntity, ...],
    *,
    kind: str | None = None,
    signal: str | None = None,
) -> ImportRecord:
    metadata = {
        "role": source.role,
        "text": source.text,
        "source_content_hash": document.source_content_hash,
    }
    if kind is not None:
        metadata["kind"] = kind
    provenance = {
        "line": source.line_number,
        "path": document.relative_path,
    }
    if source.role is not None:
        provenance["role"] = source.role
    if signal is not None:
        provenance["signal"] = signal
    return ImportRecord(
        source_kind="codex_logs",
        source_ref=source_ref,
        occurred_at=document.occurred_at,
        raw_text_or_metadata=metadata,
        candidate_entities=candidate_entities,
        provenance=provenance,
    )


def _record_for(
    document: CodexDocument,
    entity: ExtractedEntity,
    source_ref: str,
) -> ImportRecord:
    return _codex_import_record(
        document,
        source_ref,
        entity.source,
        (CandidateEntity(entity.type.value, entity.canonical_name),),
    )


def _record_for_message(
    document: CodexDocument,
    message: SourceEvidence,
) -> ImportRecord:
    source_ref = f"codex://{document.relative_path}#L{message.line_number}"
    return _codex_import_record(
        document,
        source_ref,
        message,
        (
            CandidateEntity(EntityType.CONVERSATION.value, document.title),
        ),
        kind="message",
    )


def _upsert_import_record(
    connection: sqlite3.Connection,
    world_id: str,
    record: ImportRecord,
    *identity_parts: str,
) -> None:
    record_id = _identifier(
        "import-record",
        world_id,
        record.source_ref,
        *identity_parts,
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


def _upsert_evidence_row(
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
        ) VALUES (?, ?, ?, 'codex_logs', ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_id) DO UPDATE SET
          node_id = excluded.node_id,
          edge_id = excluded.edge_id,
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


def _upsert_entity_evidence(
    connection: sqlite3.Connection,
    world_id: str,
    node_id: str,
    record: ImportRecord,
    entity: ExtractedEntity,
) -> None:
    _upsert_evidence_row(
        connection,
        _identifier(
            "evidence",
            world_id,
            record.source_ref,
            entity.type.value,
            entity.canonical_name.casefold(),
        ),
        node_id,
        None,
        record.source_ref,
        record.occurred_at,
        entity.source.text,
        record.content_hash(),
    )


def _upsert_membership_edge(
    connection: sqlite3.Connection,
    world_id: str,
    node_id: str,
    conversation_id: str,
    record: ImportRecord,
    entity: ExtractedEntity,
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
            record.occurred_at,
            record.occurred_at,
            record.occurred_at,
        ),
    )
    _upsert_evidence_row(
        connection,
        _identifier(
            "evidence",
            world_id,
            record.source_ref,
            "mentioned_in",
            node_id,
            conversation_id,
        ),
        None,
        edge_id,
        record.source_ref,
        record.occurred_at,
        entity.source.text,
        record.content_hash(),
    )


def _upsert_supersession(
    connection: sqlite3.Connection,
    world_id: str,
    document: CodexDocument,
    statement: SupersessionStatement,
) -> bool:
    replacement_id = _identifier(
        statement.type.value,
        world_id,
        _fact_key(statement.replacement_name),
    )
    replaced_id = _identifier(
        statement.type.value,
        world_id,
        _fact_key(statement.replaced_name),
    )
    replacement_present = connection.execute(
        "SELECT 1 FROM nodes WHERE node_id = ?",
        (replacement_id,),
    ).fetchone()
    if replacement_present is None:
        return False
    replaced_present = connection.execute(
        "SELECT 1 FROM nodes WHERE node_id = ?",
        (replaced_id,),
    ).fetchone()
    if replaced_present is None:
        _upsert_node(
            connection,
            replaced_id,
            world_id,
            ExtractedEntity(
                statement.type,
                statement.replaced_name,
                statement.source,
            ),
            document.occurred_at,
        )
    edge_id = _identifier(
        "edge",
        world_id,
        replacement_id,
        "supersedes",
        replaced_id,
    )
    source_ref = (
        f"codex://{document.relative_path}#L{statement.source.line_number}"
    )
    record = _codex_import_record(
        document,
        source_ref,
        statement.source,
        (
            CandidateEntity(statement.type.value, statement.replacement_name),
            CandidateEntity(statement.type.value, statement.replaced_name),
        ),
        signal="explicit_replacement",
    )
    _upsert_import_record(
        connection,
        world_id,
        record,
        "supersedes",
        statement.type.value,
        statement.replacement_name.casefold(),
        statement.replaced_name.casefold(),
    )
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
    _upsert_evidence_row(
        connection,
        _identifier("evidence", world_id, source_ref, "supersedes"),
        None,
        edge_id,
        source_ref,
        document.occurred_at,
        statement.source.text,
        record.content_hash(),
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
    root, paths = markdown_paths(logs_path)
    redaction_rules = load_redaction_rules(secret_paths_path)
    documents = tuple(
        sorted(
            (parse_document(path, root, redaction_rules) for path in paths),
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
                        if entity.type is EntityType.CONVERSATION
                        else (
                            f"codex://{document.relative_path}"
                            f"#L{entity.source.line_number}"
                        )
                    )
                    record = _record_for(document, entity, source_ref)
                    _upsert_node(
                        connection,
                        node_id,
                        world_id,
                        entity,
                        document.occurred_at,
                    )
                    _upsert_import_record(
                        connection,
                        world_id,
                        record,
                        entity.type.value,
                        entity.canonical_name.casefold(),
                    )
                    _upsert_entity_evidence(
                        connection,
                        world_id,
                        node_id,
                        record,
                        entity,
                    )
                    if entity.type is not EntityType.CONVERSATION:
                        _upsert_membership_edge(
                            connection,
                            world_id,
                            node_id,
                            conversation_id,
                            record,
                            entity,
                        )
                for message in document.messages:
                    record = _record_for_message(document, message)
                    _upsert_import_record(
                        connection,
                        world_id,
                        record,
                        "message",
                        message.role or "unknown",
                    )
                    _upsert_evidence_row(
                        connection,
                        _identifier(
                            "evidence",
                            world_id,
                            record.source_ref,
                            "message",
                            message.role or "unknown",
                        ),
                        conversation_id,
                        None,
                        record.source_ref,
                        record.occurred_at,
                        message.text,
                        record.content_hash(),
                    )
            resolved_supersessions = sum(
                _upsert_supersession(connection, world_id, document, statement)
                for document in documents
                for statement in document.supersessions
            )
    return {
        "importedConversations": len(documents),
        "importedDecisions": sum(
            entity.type is EntityType.DECISION
            for document in documents
            for entity in document.entities
        ),
        "importedPlans": sum(
            entity.type is EntityType.PLAN
            for document in documents
            for entity in document.entities
        ),
        "importedMessages": sum(
            len(document.messages) for document in documents
        ),
        "topicCandidates": len(
            {
                entity.canonical_name.casefold()
                for document in documents
                for entity in document.entities
                if entity.type is EntityType.TOPIC
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
