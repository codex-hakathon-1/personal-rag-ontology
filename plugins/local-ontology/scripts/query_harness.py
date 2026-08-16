#!/usr/bin/env python3
"""Execute one ordinary read-only SQL query against a capability database."""

from __future__ import annotations

import sqlite3
from typing import Any


class QueryRejected(ValueError):
    """Raised when SQL is outside the read-only MVP query contract."""


def query(connection: sqlite3.Connection, sql: str, max_rows: int = 100) -> dict[str, Any]:
    statement = sql.strip()
    if not statement or not statement.lower().startswith(("select", "with")):
        raise QueryRejected("Only one SELECT or WITH statement is allowed")

    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(statement)
        fetched = cursor.fetchmany(max_rows + 1)
        truncated = len(fetched) > max_rows
        rows = [dict(row) for row in fetched[:max_rows]]
        return {
            "rows": rows,
            "rowCount": len(rows),
            "truncated": truncated,
            "maxRows": max_rows,
        }
    except sqlite3.Error as error:
        raise QueryRejected(str(error)) from error
