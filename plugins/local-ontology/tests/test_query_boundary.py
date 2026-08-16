import json
import sqlite3
from pathlib import Path
import sys
import tempfile
import time
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from query_harness import QueryAuditContext, QueryRejected, query


class QueryBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("CREATE TABLE memories (value TEXT NOT NULL)")
        self.connection.execute("INSERT INTO memories VALUES ('allowed')")
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_system_objects_are_rejected(self):
        with self.assertRaisesRegex(QueryRejected, "prohibited database object"):
            query(self.connection, "SELECT name FROM sqlite_schema")

    def test_attached_databases_cannot_be_queried(self):
        self.connection.execute("ATTACH DATABASE ':memory:' AS canonical")
        self.connection.execute("CREATE TABLE canonical.secrets (value TEXT)")
        self.connection.execute("INSERT INTO canonical.secrets VALUES ('forbidden')")

        with self.assertRaisesRegex(QueryRejected, "prohibited database object"):
            query(self.connection, "SELECT value FROM canonical.secrets")

    def test_mutations_are_rejected_even_on_a_writable_connection(self):
        statements = {
            "insert": "INSERT INTO memories VALUES ('changed')",
            "with insert": (
                "WITH candidate(value) AS (VALUES ('changed')) "
                "INSERT INTO memories SELECT value FROM candidate"
            ),
            "update": "UPDATE memories SET value = 'changed'",
            "delete": "DELETE FROM memories",
            "replace": "REPLACE INTO memories VALUES ('changed')",
        }

        for operation, statement in statements.items():
            with self.subTest(operation=operation):
                with self.assertRaises(QueryRejected):
                    query(self.connection, statement)

        self.assertEqual(
            self.connection.execute("SELECT value FROM memories").fetchall(),
            [("allowed",)],
        )

    def test_schema_change_classes_are_rejected(self):
        statements = {
            "create table": "CREATE TABLE another (value TEXT)",
            "create index": "CREATE INDEX memories_value ON memories(value)",
            "create view": "CREATE VIEW memory_view AS SELECT * FROM memories",
            "create trigger": (
                "CREATE TRIGGER memory_trigger AFTER INSERT ON memories BEGIN "
                "DELETE FROM memories; END"
            ),
            "alter": "ALTER TABLE memories RENAME TO changed",
            "drop": "DROP TABLE memories",
            "vacuum": "VACUUM",
            "analyze": "ANALYZE",
            "reindex": "REINDEX",
        }

        for operation, statement in statements.items():
            with self.subTest(operation=operation):
                with self.assertRaises(QueryRejected):
                    query(self.connection, statement)

    def test_sqlite_capability_bypasses_are_rejected(self):
        self.connection.execute("CREATE TEMP TABLE temporary_memories (value TEXT)")
        statements = {
            "attach": "ATTACH DATABASE ':memory:' AS other",
            "detach": "DETACH DATABASE canonical",
            "pragma": "PRAGMA table_info(memories)",
            "pragma table function": "SELECT * FROM pragma_table_info('memories')",
            "extension loading": "SELECT load_extension('missing')",
            "begin": "BEGIN",
            "commit": "COMMIT",
            "rollback": "ROLLBACK",
            "savepoint": "SAVEPOINT model_query",
            "release": "RELEASE model_query",
            "multiple statements": "SELECT 1; SELECT 2",
            "temporary object": "SELECT value FROM temp.temporary_memories",
        }

        for operation, statement in statements.items():
            with self.subTest(operation=operation):
                with self.assertRaises(QueryRejected):
                    query(self.connection, statement)

    def test_extension_loading_is_rejected_when_sqlite_enables_it(self):
        self.connection.enable_load_extension(True)

        with self.assertRaisesRegex(QueryRejected, "prohibited SQL function"):
            query(self.connection, "SELECT load_extension('missing')")

    def test_read_only_queries_and_recursive_ctes_are_allowed(self):
        ordinary = query(
            self.connection,
            "-- a normal model-generated comment\nSELECT value FROM memories",
        )
        recursive = query(
            self.connection,
            """
            WITH RECURSIVE numbers(value) AS (
                SELECT 1
                UNION ALL
                SELECT value + 1 FROM numbers WHERE value < 3
            )
            SELECT value FROM numbers ORDER BY value
            """,
        )

        self.assertEqual(ordinary["rows"], [{"value": "allowed"}])
        self.assertEqual(
            recursive["rows"],
            [{"value": 1}, {"value": 2}, {"value": 3}],
        )

    def test_row_limit_reports_truncation(self):
        result = query(
            self.connection,
            """
            WITH candidates(value) AS (VALUES (1), (2), (3))
            SELECT value FROM candidates ORDER BY value
            """,
            max_rows=2,
        )

        self.assertEqual(result["rows"], [{"value": 1}, {"value": 2}])
        self.assertEqual(result["rowCount"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["maxRows"], 2)

    def test_execution_time_limit_interrupts_runaway_query(self):
        started = time.monotonic()

        with self.assertRaisesRegex(QueryRejected, "execution time limit"):
            query(
                self.connection,
                """
                WITH RECURSIVE forever(value) AS (
                    SELECT 1
                    UNION ALL
                    SELECT value + 1 FROM forever
                )
                SELECT sum(value) FROM forever
                """,
                max_execution_ms=5,
            )

        self.assertLess(time.monotonic() - started, 1)

    def test_every_attempt_writes_a_payload_free_audit_entry(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            audit_path = Path(temporary_directory) / "query-audit.jsonl"
            audit_context = QueryAuditContext(
                path=audit_path,
                session_identifier="session-123",
                world_identifier="travel",
            )

            result = query(
                self.connection,
                "SELECT value FROM memories",
                audit_context=audit_context,
            )
            with self.assertRaises(QueryRejected):
                query(
                    self.connection,
                    "DELETE FROM memories",
                    audit_context=audit_context,
                )

            entries = [
                json.loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]
            audit_text = audit_path.read_text(encoding="utf-8")

        self.assertEqual(result["rows"], [{"value": "allowed"}])
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            [entry["outcome"] for entry in entries],
            ["succeeded", "rejected"],
        )
        self.assertEqual([entry["rowCount"] for entry in entries], [1, 0])
        for entry in entries:
            self.assertEqual(entry["sessionIdentifier"], "session-123")
            self.assertEqual(entry["worldIdentifier"], "travel")
            self.assertGreaterEqual(entry["executionTimeMs"], 0)
            self.assertRegex(entry["sqlFingerprint"], r"^[0-9a-f]{64}$")
        self.assertNotIn("allowed", audit_text)
        self.assertNotIn("SELECT value", audit_text)
        self.assertNotIn("DELETE FROM", audit_text)


if __name__ == "__main__":
    unittest.main()
