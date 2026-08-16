#!/usr/bin/env python3
"""Minimal stdio MCP server exposing the policy-bounded SQL query tool."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

from build_session import build_capability_connection
from query_harness import QueryAuditContext, QueryRejected, query


PROTOCOL_VERSION = "2025-06-18"


def _load_session() -> dict[str, Any]:
    session_path = os.environ.get("LOCAL_ONTOLOGY_SESSION")
    if not session_path:
        raise RuntimeError(
            "LOCAL_ONTOLOGY_SESSION must point to a session.json built by build_session.py"
        )
    return json.loads(Path(session_path).read_text(encoding="utf-8"))


def _startup_instructions(session: dict[str, Any]) -> str:
    world = session["selectedWorld"]
    policy = json.dumps(session["policyContract"], sort_keys=True)
    schema = json.dumps(session["schemaGuidance"], sort_keys=True)
    return (
        "GLOBAL MEMORY\n"
        "- This is a read-only, policy-bounded personal-memory database.\n"
        "- Query only when the request has a personal anchor and benefits from "
        "historical context; no query is a normal outcome.\n"
        "- Use nodes, edges, and evidence; node_aliases provides alternate names.\n"
        "- Anchor on nodes.canonical_name or node_aliases.alias.\n"
        "- Traverse edges with a recursive CTE for at most two hops; carry a "
        "delimited node path and reject nodes already in it as a cycle guard.\n"
        "- Join evidence on node_id or edge_id and select source_kind, source_ref, "
        "and occurred_at for every fact used.\n"
        "- Treat results as dated evidence, cite provenance, and state uncertainty.\n"
        f"- The selected world is {world}; other worlds do not exist in this session.\n"
        f"- Policy contract: {policy}\n"
        f"- Schema guidance: {schema}\n"
        "- Do not attempt writes, PRAGMAs, ATTACH, extensions, or external access."
    )


def _tool_definition() -> dict[str, Any]:
    return {
        "name": "query_memory",
        "title": "Query Local Ontology",
        "description": (
            "Run one ordinary read-only SQL query against the selected world's "
            "capability database. Select evidence source_kind, source_ref, and "
            "occurred_at when retrieving facts so provenance is preserved."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A SELECT or WITH query."}
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "rows": {"type": "array", "items": {"type": "object"}},
                "rowCount": {"type": "integer"},
                "truncated": {"type": "boolean"},
                "maxRows": {"type": "integer"},
            },
            "required": ["rows", "rowCount", "truncated", "maxRows"],
        },
        "annotations": {"readOnlyHint": True},
    }


def _success(identifier: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": message},
    }


def handle(
    request: dict[str, Any],
    session: dict[str, Any],
    capability: sqlite3.Connection,
) -> dict[str, Any] | None:
    identifier = request.get("id")
    method = request.get("method")
    if method == "initialize":
        requested_version = request.get("params", {}).get("protocolVersion")
        return _success(identifier, {
            "protocolVersion": requested_version or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "local-ontology", "version": "0.1.0"},
            "instructions": _startup_instructions(session),
        })
    if method == "ping":
        return _success(identifier, {})
    if method == "tools/list":
        return _success(identifier, {"tools": [_tool_definition()]})
    if method == "tools/call":
        parameters = request.get("params", {})
        if parameters.get("name") != "query_memory":
            return _error(identifier, -32602, "Unknown tool")
        try:
            limits = session["queryLimits"]
            result = query(
                capability,
                parameters.get("arguments", {}).get("sql", ""),
                max_rows=limits["maxRows"],
                max_execution_ms=limits["maxExecutionMs"],
                audit_context=QueryAuditContext(
                    path=Path(session["queryAuditLog"]),
                    session_identifier=session["sessionIdentifier"],
                    world_identifier=session["selectedWorld"],
                ),
            )
        except QueryRejected as error:
            return _success(identifier, {
                "content": [{"type": "text", "text": str(error)}],
                "isError": True,
            })
        return _success(identifier, {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            "structuredContent": result,
            "isError": False,
        })
    if method and method.startswith("notifications/"):
        return None
    return _error(identifier, -32601, f"Method not found: {method}")


def main() -> None:
    try:
        session = _load_session()
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error

    capability = build_capability_connection(
        Path(session["canonicalDatabase"]),
        session["selectedWorld"],
        session["policyContract"],
    )
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                response = handle(request, session, capability)
            except (TypeError, ValueError) as error:
                response = _error(None, -32700, str(error))
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)
    finally:
        capability.close()


if __name__ == "__main__":
    main()
