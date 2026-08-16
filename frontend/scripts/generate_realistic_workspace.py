#!/usr/bin/env python3
"""Build the frontend demo workspace from the sanitized capability database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "demo-output" / "realistic-user" / "capability.sqlite3"
DEFAULT_OUTPUT = ROOT / "frontend" / "src" / "data" / "realistic-workspace.json"

PROJECT_RELATIONS = {
    "decided",
    "remembers_project",
    "researched_with",
    "tested_at",
    "worked_at",
}

SOURCE_META = {
    "browser_history": {
        "id": "src-browser",
        "name": "Browser history",
        "kind": "browser",
        "description": "Visited documentation and research pages from local browser history.",
    },
    "codex_logs": {
        "id": "src-codex",
        "name": "Codex conversations",
        "kind": "codex",
        "description": "Project topics, decisions, and plans extracted from local conversations.",
    },
    "fixture_graph": {
        "id": "src-manual",
        "name": "Curated graph overlay",
        "kind": "manual",
        "description": "Explicit relationships added by the deterministic demo fixture.",
    },
    "google_maps_takeout": {
        "id": "src-takeout",
        "name": "Google Maps Takeout",
        "kind": "takeout",
        "description": "Saved place context imported from a sanitized local Takeout export.",
    },
}

CATEGORY_BY_TYPE = {
    "decision": "Decision",
    "place": "Place",
    "plan": "Plan",
    "topic": "Topic",
    "web_page": "Research",
}

CATEGORY_ORDER = {
    "Decision": 0,
    "Plan": 1,
    "Research": 2,
    "Place": 3,
    "Topic": 4,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def rows(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(connection.execute(query, parameters))


def relation_value(node: sqlite3.Row, relation: str) -> str:
    summary = (node["summary"] or "").strip()
    if node["type"] in {"decision", "plan"}:
        return summary or node["canonical_name"]
    prefixes = {
        "place": "관련 장소",
        "web_page": "관련 리서치",
        "topic": "관련 주제",
    }
    prefix = prefixes.get(node["type"], relation.replace("_", " ").title())
    return f"{prefix}: {node['canonical_name']}"


def latest_evidence(connection: sqlite3.Connection, node_id: str) -> sqlite3.Row:
    evidence = connection.execute(
        """
        SELECT source_kind, source_ref, occurred_at, observed_at, excerpt
        FROM evidence
        WHERE node_id = ?
        ORDER BY COALESCE(occurred_at, observed_at) DESC, observed_at DESC, evidence_id
        LIMIT 1
        """,
        (node_id,),
    ).fetchone()
    if evidence is None:
        raise ValueError(f"Node {node_id} does not have provenance evidence")
    return evidence


def build_sources(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    stats = {
        row["source_kind"]: row
        for row in rows(
            connection,
            """
            SELECT source_kind, COUNT(*) AS item_count,
                   MAX(COALESCE(occurred_at, observed_at)) AS synced_at
            FROM evidence
            GROUP BY source_kind
            """,
        )
    }
    unknown = set(stats) - set(SOURCE_META)
    if unknown:
        raise ValueError(f"Unmapped evidence sources: {', '.join(sorted(unknown))}")

    result = []
    for source_kind in ("codex_logs", "browser_history", "google_maps_takeout", "fixture_graph"):
        if source_kind not in stats:
            continue
        meta = SOURCE_META[source_kind]
        result.append(
            {
                **meta,
                "itemCount": stats[source_kind]["item_count"],
                "lastSyncedAt": stats[source_kind]["synced_at"],
                "status": "connected",
            }
        )
    return result


def project_anchors(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in PROJECT_RELATIONS)
    return rows(
        connection,
        f"""
        SELECT DISTINCT n.*
        FROM nodes n
        JOIN edges e ON e.from_node_id = n.node_id AND e.state = 'active'
        WHERE n.type = 'topic' AND n.state = 'active'
          AND e.relation IN ({placeholders})
        ORDER BY n.last_seen_at DESC, n.canonical_name
        """,
        tuple(sorted(PROJECT_RELATIONS)),
    )


def conversation_for_project(connection: sqlite3.Connection, project_id: str) -> sqlite3.Row:
    conversation = connection.execute(
        """
        SELECT target.*
        FROM edges e
        JOIN nodes target ON target.node_id = e.to_node_id
        WHERE e.from_node_id = ? AND e.relation = 'mentioned_in'
          AND e.state = 'active' AND target.type = 'conversation'
        ORDER BY e.updated_at DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if conversation is None:
        raise ValueError(f"Project anchor {project_id} is not linked to a conversation")
    return conversation


def candidates_for_project(
    connection: sqlite3.Connection,
    project_id: str,
    conversation_id: str,
) -> list[tuple[sqlite3.Row, str, float]]:
    candidates: dict[str, tuple[sqlite3.Row, str, float]] = {}

    direct = rows(
        connection,
        """
        SELECT target.*, e.relation, e.confidence
        FROM edges e
        JOIN nodes target ON target.node_id = e.to_node_id
        WHERE e.from_node_id = ? AND e.state = 'active'
          AND e.relation <> 'mentioned_in' AND target.state = 'active'
        """,
        (project_id,),
    )
    for node in direct:
        candidates[node["node_id"]] = (node, node["relation"], node["confidence"])

    conversation_peers = rows(
        connection,
        """
        SELECT source.*, e.relation, e.confidence
        FROM edges e
        JOIN nodes source ON source.node_id = e.from_node_id
        WHERE e.to_node_id = ? AND e.relation = 'mentioned_in'
          AND e.state = 'active' AND source.state = 'active'
          AND source.node_id <> ?
        """,
        (conversation_id, project_id),
    )
    for node in conversation_peers:
        existing = candidates.get(node["node_id"])
        if existing is None or node["confidence"] > existing[2]:
            candidates[node["node_id"]] = (node, node["relation"], node["confidence"])

    return sorted(
        candidates.values(),
        key=lambda item: (
            CATEGORY_ORDER.get(CATEGORY_BY_TYPE.get(item[0]["type"], "Topic"), 99),
            item[0]["canonical_name"],
        ),
    )


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    for key in ("sources", "attributes", "projects", "projectAttributes"):
        if not snapshot[key]:
            raise ValueError(f"Generated workspace has no {key}")

    source_ids = {source["id"] for source in snapshot["sources"]}
    attribute_ids = {attribute["id"] for attribute in snapshot["attributes"]}
    project_ids = {project["id"] for project in snapshot["projects"]}
    if len(source_ids) != len(snapshot["sources"]):
        raise ValueError("Duplicate source IDs in generated workspace")
    if len(attribute_ids) != len(snapshot["attributes"]):
        raise ValueError("Duplicate attribute IDs in generated workspace")
    if len(project_ids) != len(snapshot["projects"]):
        raise ValueError("Duplicate project IDs in generated workspace")

    for attribute in snapshot["attributes"]:
        if attribute["sourceId"] not in source_ids:
            raise ValueError(f"Unknown source for attribute {attribute['id']}")
    for relation in snapshot["projectAttributes"]:
        if relation["projectId"] not in project_ids or relation["attributeId"] not in attribute_ids:
            raise ValueError("Generated project relation has a dangling reference")


def build_workspace(connection: sqlite3.Connection) -> dict[str, Any]:
    projects: list[dict[str, Any]] = []
    attributes_by_id: dict[str, dict[str, Any]] = {}
    project_attributes: list[dict[str, Any]] = []

    for anchor in project_anchors(connection):
        conversation = conversation_for_project(connection, anchor["node_id"])
        project_id = f"project-{anchor['node_id']}"
        projects.append(
            {
                "id": project_id,
                "name": anchor["canonical_name"],
                "description": f"{conversation['canonical_name']}에서 수집한 결정, 계획, 리서치와 장소 맥락.",
                "status": "active",
                "memoryStatus": "added",
                "updatedAt": anchor["last_seen_at"] or anchor["updated_at"],
            }
        )

        for node, relation, confidence in candidates_for_project(
            connection, anchor["node_id"], conversation["node_id"]
        ):
            evidence = latest_evidence(connection, node["node_id"])
            source_id = SOURCE_META[evidence["source_kind"]]["id"]
            observed_at = evidence["occurred_at"] or evidence["observed_at"]
            state = "added" if confidence >= 0.9 else "suggested"
            attributes_by_id.setdefault(
                node["node_id"],
                {
                    "id": node["node_id"],
                    "title": node["canonical_name"],
                    "value": relation_value(node, relation),
                    "category": CATEGORY_BY_TYPE.get(node["type"], "Topic"),
                    "sourceId": source_id,
                    "confidence": confidence,
                    "status": "kept" if confidence >= 0.9 else "suggested",
                    "excerpt": (evidence["excerpt"] or node["summary"] or node["canonical_name"]).strip(),
                    "sourceRef": evidence["source_ref"],
                    "observedAt": observed_at,
                    "updatedAt": node["updated_at"],
                },
            )
            project_attributes.append(
                {
                    "projectId": project_id,
                    "attributeId": node["node_id"],
                    "status": state,
                    "valueStatus": state,
                    "sourceStatus": state,
                    "confidenceStatus": "added" if confidence == 1.0 else "suggested",
                    "suggestedAt": observed_at,
                }
            )

    attributes = sorted(
        attributes_by_id.values(),
        key=lambda item: (CATEGORY_ORDER.get(item["category"], 99), item["title"]),
    )
    snapshot = {
        "sources": build_sources(connection),
        "attributes": attributes,
        "projects": projects,
        "projectAttributes": project_attributes,
    }
    validate_snapshot(snapshot)
    return snapshot


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    if not input_path.is_file():
        raise SystemExit(f"Capability database not found: {input_path}")

    connection = sqlite3.connect(f"file:{input_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        snapshot = build_workspace(connection)
    finally:
        connection.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Generated {len(snapshot['projects'])} projects, "
        f"{len(snapshot['attributes'])} attributes, and "
        f"{len(snapshot['sources'])} sources at {output_path}"
    )


if __name__ == "__main__":
    main()
