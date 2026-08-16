import hashlib
import json
import os
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
IMPORT_HISTORY = PLUGIN_ROOT / "scripts" / "import_browser_history.py"
BUILD_SESSION = PLUGIN_ROOT / "scripts" / "build_session.py"
MCP_SERVER = PLUGIN_ROOT / "scripts" / "mcp_server.py"
HISTORY_FIXTURE = PLUGIN_ROOT / "examples" / "chromium-history-fixture.sql"
SENSITIVE_PATTERNS = (
    PLUGIN_ROOT / "examples" / "chromium-sensitive-patterns.json"
)
POLICY = PLUGIN_ROOT / "examples" / "chromium-policy.example.json"
SENSITIVE_URL = "https://bank.example.com/account?token=fixture-secret"


class ChromiumHistoryImportTest(unittest.TestCase):
    def test_fixture_imports_normalized_records_and_graph_idempotently(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            history_path = root / "History"
            canonical_path = root / "canonical.sqlite3"
            self._create_history(history_path)

            first = self._import(history_path, canonical_path)
            first_counts = self._table_counts(canonical_path)
            first_record_hashes = self._record_hashes(canonical_path)
            second = self._import(history_path, canonical_path)
            second_counts = self._table_counts(canonical_path)
            second_record_hashes = self._record_hashes(canonical_path)

            with closing(sqlite3.connect(canonical_path)) as connection:
                records = connection.execute(
                    "SELECT url, title, host, visit_count, last_visit_at "
                    "FROM browser_history_records ORDER BY url"
                ).fetchall()
                candidates = connection.execute(
                    "SELECT type, canonical_name FROM nodes "
                    "ORDER BY type, canonical_name"
                ).fetchall()
                node_evidence = connection.execute(
                    "SELECT n.type, e.source_ref, e.occurred_at, e.content_hash "
                    "FROM nodes AS n JOIN evidence AS e ON e.node_id = n.node_id "
                    "ORDER BY n.type, e.occurred_at"
                ).fetchall()
                graph_dump = "\n".join(connection.iterdump())

            expected_report = {
                "excludedPages": 1,
                "exclusions": [
                    {"pattern": "account-credentials", "count": 1}
                ],
                "importedPages": 2,
                "importedVisits": 3,
                "topicCandidates": 2,
                "world": "travel",
            }
            self.assertEqual(first, expected_report)
            self.assertEqual(second, expected_report)
            self.assertEqual(
                records,
                [
                    (
                        "https://platform.openai.com/docs/guides",
                        "OpenAI API guides",
                        "platform.openai.com",
                        2,
                        "2025-08-02T11:30:00Z",
                    ),
                    (
                        "https://travel.example.org/kyoto-itinerary",
                        "Kyoto itinerary",
                        "travel.example.org",
                        1,
                        "2025-08-03T12:00:00Z",
                    ),
                ],
            )
            self.assertEqual(first_record_hashes, second_record_hashes)
            self.assertTrue(
                all(
                    re.fullmatch(r"[0-9a-f]{64}", value)
                    for value in second_record_hashes
                )
            )
            self.assertEqual(
                candidates,
                [
                    ("topic", "platform.openai.com"),
                    ("topic", "travel.example.org"),
                    ("web_page", "Kyoto itinerary"),
                    ("web_page", "OpenAI API guides"),
                ],
            )
            self.assertEqual(
                {row[0] for row in node_evidence},
                {"topic", "web_page"},
            )
            self.assertTrue(
                all(row[1].startswith("https://") for row in node_evidence)
            )
            self.assertTrue(all(row[2].endswith("Z") for row in node_evidence))
            self.assertTrue(
                all(re.fullmatch(r"[0-9a-f]{64}", row[3]) for row in node_evidence)
            )
            self.assertEqual(first_counts, second_counts)
            self.assertEqual(
                first_counts,
                {
                    "browser_history_records": 2,
                    "nodes": 4,
                    "edges": 2,
                    "evidence": 9,
                },
            )
            self.assertNotIn(SENSITIVE_URL, json.dumps(first))
            self.assertNotIn(SENSITIVE_URL, graph_dump)

    def test_locked_source_import_uses_a_copy_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            history_path = root / "History"
            canonical_path = root / "canonical.sqlite3"
            self._create_history(history_path)
            before = hashlib.sha256(history_path.read_bytes()).hexdigest()

            with closing(sqlite3.connect(history_path)) as lock:
                lock.execute("BEGIN EXCLUSIVE")
                report = self._import(history_path, canonical_path)

            after = hashlib.sha256(history_path.read_bytes()).hexdigest()
            self.assertEqual(report["importedPages"], 2)
            self.assertEqual(after, before)

    def test_imported_page_is_retrievable_through_session_query(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            history_path = root / "History"
            canonical_path = root / "canonical.sqlite3"
            session_directory = root / "session"
            self._create_history(history_path)
            self._import(history_path, canonical_path)

            build = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SESSION),
                    "--canonical",
                    str(canonical_path),
                    "--policy",
                    str(POLICY),
                    "--world",
                    "travel",
                    "--session-dir",
                    str(session_directory),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            session_path = Path(json.loads(build.stdout)["sessionPath"])
            environment = os.environ.copy()
            environment["LOCAL_ONTOLOGY_SESSION"] = str(session_path)
            server = subprocess.Popen(
                [sys.executable, str(MCP_SERVER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            self.addCleanup(self._stop_server, server)
            self._request(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "e2e-test", "version": "1.0.0"},
                    },
                },
            )
            response = self._request(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "query_memory",
                        "arguments": {
                            "sql": (
                                "SELECT n.canonical_name, e.source_ref, "
                                "e.occurred_at, e.content_hash "
                                "FROM nodes AS n JOIN evidence AS e "
                                "ON e.node_id = n.node_id "
                                "WHERE n.type = 'web_page' "
                                "AND n.canonical_name = 'Kyoto itinerary'"
                            )
                        },
                    },
                },
            )

            rows = response["result"]["structuredContent"]["rows"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(
                {key: rows[0][key] for key in (
                    "canonical_name", "source_ref", "occurred_at"
                )},
                {
                    "canonical_name": "Kyoto itinerary",
                    "source_ref": (
                        "https://travel.example.org/kyoto-itinerary"
                    ),
                    "occurred_at": "2025-08-03T12:00:00Z",
                },
            )
            self.assertRegex(rows[0]["content_hash"], r"^[0-9a-f]{64}$")

    def _import(self, history_path, canonical_path):
        result = subprocess.run(
            [
                sys.executable,
                str(IMPORT_HISTORY),
                "--history",
                str(history_path),
                "--canonical",
                str(canonical_path),
                "--world",
                "travel",
                "--sensitive-patterns",
                str(SENSITIVE_PATTERNS),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertNotIn(SENSITIVE_URL, result.stdout)
        self.assertNotIn(SENSITIVE_URL, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def _create_history(path):
        with closing(sqlite3.connect(path)) as connection:
            with connection:
                connection.executescript(
                    HISTORY_FIXTURE.read_text(encoding="utf-8")
                )

    @staticmethod
    def _table_counts(path):
        with closing(sqlite3.connect(path)) as connection:
            return {
                table: connection.execute(
                    f"SELECT count(*) FROM {table}"
                ).fetchone()[0]
                for table in (
                    "browser_history_records", "nodes", "edges", "evidence"
                )
            }

    @staticmethod
    def _record_hashes(path):
        with closing(sqlite3.connect(path)) as connection:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT content_hash FROM browser_history_records ORDER BY url"
                )
            ]

    @staticmethod
    def _request(server, request):
        assert server.stdin is not None
        assert server.stdout is not None
        server.stdin.write(json.dumps(request) + "\n")
        server.stdin.flush()
        response = server.stdout.readline()
        if not response:
            stderr = server.stderr.read() if server.stderr else ""
            raise AssertionError(f"MCP server closed without a response: {stderr}")
        return json.loads(response)

    @staticmethod
    def _stop_server(server):
        if server.poll() is None:
            server.terminate()
            server.wait(timeout=5)
        for stream in (server.stdin, server.stdout, server.stderr):
            if stream is not None:
                stream.close()


if __name__ == "__main__":
    unittest.main()
