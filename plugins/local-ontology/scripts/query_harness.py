#!/usr/bin/env python3
"""Execute one ordinary read-only SQL query against a capability database."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Literal


class QueryRejected(ValueError):
    """Raised when SQL is outside the read-only MVP query contract."""


AuditOutcome = Literal["failed", "rejected", "succeeded"]


@dataclass(frozen=True)
class QueryAuditContext:
    """Identity and destination for payload-free query audit entries."""

    path: Path
    session_identifier: str
    world_identifier: str

    def record(
        self,
        sql: object,
        execution_time_ms: float,
        row_count: int,
        outcome: AuditOutcome,
        truncated: bool,
    ) -> None:
        fingerprint_source = (
            sql if isinstance(sql, str) else f"<invalid:{type(sql).__name__}>"
        )
        entry = {
            "sqlFingerprint": hashlib.sha256(
                fingerprint_source.encode("utf-8")
            ).hexdigest(),
            "executionTimeMs": round(execution_time_ms, 3),
            "rowCount": row_count,
            "sessionIdentifier": self.session_identifier,
            "worldIdentifier": self.world_identifier,
            "outcome": outcome,
            "truncated": truncated,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as audit_file:
                audit_file.write(json.dumps(entry, sort_keys=True) + "\n")
        except OSError as error:
            raise QueryRejected("The query audit entry could not be recorded") from error


_READ_ONLY_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_RECURSIVE,
        sqlite3.SQLITE_SELECT,
    }
)
_PROHIBITED_FUNCTIONS = frozenset(
    {"fts3_tokenizer", "load_extension", "readfile", "writefile"}
)
_LEADING_SQL = re.compile(
    r"(?:\s|--[^\r\n]*(?:\r?\n|$)|/\*.*?\*/)*([A-Za-z]+)",
    re.DOTALL,
)


def _is_prohibited_object(table: str | None, database: str | None) -> bool:
    normalized_table = (table or "").lower()
    normalized_database = (database or "").lower()
    return (
        normalized_database not in {"", "main"}
        or normalized_table.startswith("sqlite_")
        or normalized_table.startswith("pragma_")
    )


def _first_keyword(sql: str) -> str | None:
    match = _LEADING_SQL.match(sql)
    return match.group(1).lower() if match else None


def _execute_query(
    connection: sqlite3.Connection,
    sql: str,
    max_rows: int = 100,
    max_execution_ms: int = 1_000,
) -> dict[str, Any]:
    if not isinstance(sql, str):
        raise QueryRejected("SQL must be a string")
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or max_rows <= 0:
        raise QueryRejected("Row limit must be a positive integer")
    if (
        not isinstance(max_execution_ms, int)
        or isinstance(max_execution_ms, bool)
        or max_execution_ms <= 0
    ):
        raise QueryRejected("Execution time limit must be a positive integer")

    statement = sql.strip()
    if _first_keyword(statement) not in {"select", "with"}:
        raise QueryRejected("Only one SELECT or WITH statement is allowed")

    rejection_reason: str | None = None
    deadline = time.monotonic() + (max_execution_ms / 1_000)
    execution_timed_out = False

    def authorize(
        action: int,
        argument_one: str | None,
        argument_two: str | None,
        database: str | None,
        _trigger: str | None,
    ) -> int:
        nonlocal rejection_reason
        if action not in _READ_ONLY_ACTIONS:
            rejection_reason = "A prohibited SQL operation was rejected"
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (
            argument_two or argument_one or ""
        ).lower() in _PROHIBITED_FUNCTIONS:
            rejection_reason = "Use of a prohibited SQL function is not allowed"
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and _is_prohibited_object(
            argument_one, database
        ):
            rejection_reason = "Access to a prohibited database object is not allowed"
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def enforce_deadline() -> int:
        nonlocal execution_timed_out
        execution_timed_out = time.monotonic() >= deadline
        return 1 if execution_timed_out else 0

    previous_row_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    connection.set_authorizer(authorize)
    connection.set_progress_handler(enforce_deadline, 100)
    try:
        cursor = connection.execute(statement)
        fetched = cursor.fetchmany(max_rows + 1)
        if time.monotonic() >= deadline:
            execution_timed_out = True
            raise sqlite3.OperationalError("query execution time limit exceeded")
        truncated = len(fetched) > max_rows
        rows = [dict(row) for row in fetched[:max_rows]]
        return {
            "rows": rows,
            "rowCount": len(rows),
            "truncated": truncated,
            "maxRows": max_rows,
        }
    except sqlite3.Error as error:
        if execution_timed_out:
            rejection_reason = (
                f"Query exceeded the {max_execution_ms} ms execution time limit"
            )
        raise QueryRejected(rejection_reason or str(error)) from error
    finally:
        connection.set_progress_handler(None, 0)
        connection.set_authorizer(None)
        connection.row_factory = previous_row_factory


def query(
    connection: sqlite3.Connection,
    sql: str,
    max_rows: int = 100,
    max_execution_ms: int = 1_000,
    *,
    audit_context: QueryAuditContext,
) -> dict[str, Any]:
    """Run one bounded read-only statement and record the attempt."""

    started = time.monotonic()
    row_count = 0
    truncated = False
    outcome: AuditOutcome = "failed"
    try:
        result = _execute_query(connection, sql, max_rows, max_execution_ms)
        row_count = result["rowCount"]
        truncated = result["truncated"]
        outcome = "succeeded"
        return result
    except QueryRejected:
        outcome = "rejected"
        raise
    finally:
        audit_context.record(
            sql=sql,
            execution_time_ms=(time.monotonic() - started) * 1_000,
            row_count=row_count,
            outcome=outcome,
            truncated=truncated,
        )
