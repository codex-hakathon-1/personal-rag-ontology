import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
IMPORT_CODEX_LOGS = PLUGIN_ROOT / "scripts" / "import_codex_logs.py"
BUILD_SESSION = PLUGIN_ROOT / "scripts" / "build_session.py"
MCP_SERVER = PLUGIN_ROOT / "scripts" / "mcp_server.py"
LOG_FIXTURES = PLUGIN_ROOT / "examples" / "codex-logs"
POLICY = PLUGIN_ROOT / "examples" / "policy.example.json"


class CodexLogsImportTest(unittest.TestCase):
    def test_markdown_logs_create_normalized_graph_with_stable_provenance(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            canonical_path = Path(temporary_directory) / "canonical.sqlite3"

            report = self._import(LOG_FIXTURES, canonical_path)

            with closing(sqlite3.connect(canonical_path)) as connection:
                node_types = dict(
                    connection.execute(
                        "SELECT type, count(*) FROM nodes GROUP BY type"
                    )
                )
                normalized_types = {
                    entity["type"]
                    for row in connection.execute(
                        "SELECT candidate_entities FROM import_records"
                    )
                    for entity in json.loads(row[0])
                }
                normalized_messages = connection.execute(
                    "SELECT count(*) FROM import_records "
                    "WHERE json_extract(raw_text_or_metadata, '$.kind') = 'message'"
                ).fetchone()[0]
                provenance = connection.execute(
                    "SELECT source_ref, occurred_at, content_hash "
                    "FROM evidence WHERE source_kind = 'codex_logs' "
                    "ORDER BY source_ref"
                ).fetchall()

            self.assertEqual(report["importedConversations"], 3)
            self.assertEqual(report["importedMessages"], 6)
            self.assertEqual(normalized_messages, 6)
            self.assertEqual(node_types["conversation"], 3)
            self.assertGreaterEqual(node_types["decision"], 3)
            self.assertGreaterEqual(node_types["plan"], 3)
            self.assertGreaterEqual(node_types["topic"], 3)
            self.assertEqual(
                normalized_types,
                {"conversation", "decision", "plan", "topic"},
            )
            self.assertTrue(provenance)
            for source_ref, occurred_at, content_hash in provenance:
                self.assertRegex(
                    source_ref,
                    r"^codex://[^#]+(?:#document|#L\d+)$",
                )
                self.assertRegex(occurred_at, r"^2025-03-\d{2}T")
                self.assertRegex(content_hash, r"^[0-9a-f]{64}$")

    def test_secrets_are_redacted_before_any_content_is_persisted(self):
        token = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
        key_value = "ultra-secret-database-password"
        quoted_key_value = "quoted-secret-value"
        password_value = "correct horse battery staple"
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturevalue"
        secret_path = r"C:\Users\dev\.ssh\id_ed25519"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            logs_path = root / "logs"
            logs_path.mkdir()
            (logs_path / "secret-review.md").write_text(
                "\n".join(
                    [
                        "---",
                        "title: Secret review",
                        "date: 2025-03-21T08:00:00Z",
                        "topics: [security]",
                        "---",
                        "",
                        "## User",
                        "",
                        f"The temporary token is {token}.",
                        "",
                        "## Assistant",
                        "",
                        (
                            f'Decision: Set API_KEY="{quoted_key_value}" and '
                            f'password: "{password_value}" locally.'
                        ),
                        "",
                        (
                            f"Plan: Use DATABASE_PASSWORD={key_value}, then read "
                            f"{secret_path}; auth proof: {jwt}."
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            secret_paths = root / "secret-paths.json"
            secret_paths.write_text(
                json.dumps({"secret_paths": [secret_path]}),
                encoding="utf-8",
            )
            canonical_path = root / "canonical.sqlite3"

            report = self._import(
                logs_path,
                canonical_path,
                "--secret-paths",
                str(secret_paths),
            )

            with closing(sqlite3.connect(canonical_path)) as connection:
                database_dump = "\n".join(connection.iterdump())
                excerpts = "\n".join(
                    row[0] or ""
                    for row in connection.execute("SELECT excerpt FROM evidence")
                )
            for secret in (
                token,
                key_value,
                quoted_key_value,
                password_value,
                jwt,
                secret_path,
            ):
                self.assertNotIn(secret, database_dump)
                self.assertNotIn(secret, excerpts)
            self.assertGreaterEqual(database_dump.count("[REDACTED]"), 2)
            self.assertEqual(report["redactions"]["configured_secret_path"], 1)
            self.assertGreaterEqual(report["redactions"]["key_like_value"], 3)
            self.assertGreaterEqual(report["redactions"]["token_like_value"], 2)

    def test_only_explicit_replacement_creates_supersession_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            canonical_path = Path(temporary_directory) / "canonical.sqlite3"

            self._import(LOG_FIXTURES, canonical_path)

            with closing(sqlite3.connect(canonical_path)) as connection:
                connection.row_factory = sqlite3.Row
                old_decision = connection.execute(
                    "SELECT node_id, state, superseded_by FROM nodes "
                    "WHERE type = 'decision' "
                    "AND canonical_name = 'Store memories in JSON files.'"
                ).fetchone()
                replacement = connection.execute(
                    "SELECT node_id, state FROM nodes "
                    "WHERE type = 'decision' "
                    "AND canonical_name = 'Store memories in SQLite.'"
                ).fetchone()
                newer_decision = connection.execute(
                    "SELECT node_id, state, superseded_by FROM nodes "
                    "WHERE type = 'decision' "
                    "AND canonical_name = 'Keep Markdown fixtures deterministic.'"
                ).fetchone()
                supersession = connection.execute(
                    "SELECT e.from_node_id, e.to_node_id, e.confidence, "
                    "v.source_ref, v.excerpt "
                    "FROM edges AS e JOIN evidence AS v ON v.edge_id = e.edge_id "
                    "WHERE e.relation = 'supersedes'"
                ).fetchall()

            self.assertEqual(old_decision["state"], "superseded")
            self.assertEqual(old_decision["superseded_by"], replacement["node_id"])
            self.assertEqual(replacement["state"], "active")
            self.assertEqual(newer_decision["state"], "active")
            self.assertIsNone(newer_decision["superseded_by"])
            self.assertEqual(len(supersession), 1)
            self.assertEqual(
                (supersession[0]["from_node_id"], supersession[0]["to_node_id"]),
                (replacement["node_id"], old_decision["node_id"]),
            )
            self.assertGreaterEqual(supersession[0]["confidence"], 0.95)
            self.assertRegex(supersession[0]["source_ref"], r"#L\d+$")
            self.assertIn("replaces", supersession[0]["excerpt"])

    def test_inline_replacement_materializes_a_named_older_plan(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            log_path = root / "plan.md"
            log_path.write_text(
                "\n".join(
                    [
                        "---",
                        "title: Release plan",
                        "date: 2025-04-01T10:00:00Z",
                        "---",
                        "",
                        "## Assistant",
                        "",
                        'Plan: Ship the beta replaces "Ship the alpha".',
                    ]
                ),
                encoding="utf-8",
            )
            canonical_path = root / "canonical.sqlite3"

            report = self._import(log_path, canonical_path)

            with closing(sqlite3.connect(canonical_path)) as connection:
                plans = connection.execute(
                    "SELECT canonical_name, state FROM nodes "
                    "WHERE type = 'plan' ORDER BY canonical_name"
                ).fetchall()
                edge_count = connection.execute(
                    "SELECT count(*) FROM edges WHERE relation = 'supersedes'"
                ).fetchone()[0]
            self.assertEqual(
                plans,
                [("Ship the alpha", "superseded"), ("Ship the beta", "active")],
            )
            self.assertEqual(edge_count, 1)
            self.assertEqual(report["explicitSupersessions"], 1)

            log_path.write_text(
                log_path.read_text(encoding="utf-8").replace(
                    'Plan: Ship the beta replaces "Ship the alpha".',
                    "Plan: Ship the beta.",
                ),
                encoding="utf-8",
            )
            self._import(log_path, canonical_path)
            with closing(sqlite3.connect(canonical_path)) as connection:
                remaining_plans = connection.execute(
                    "SELECT canonical_name, state FROM nodes WHERE type = 'plan'"
                ).fetchall()
                remaining_edges = connection.execute(
                    "SELECT count(*) FROM edges WHERE relation = 'supersedes'"
                ).fetchone()[0]
            self.assertEqual(remaining_plans, [("Ship the beta.", "active")])
            self.assertEqual(remaining_edges, 0)

    def test_reimport_is_idempotent_and_changed_content_updates_hashes(self):
        source = LOG_FIXTURES / "2025-03-20-review.md"
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            logs_path = root / "logs"
            logs_path.mkdir()
            log_path = logs_path / source.name
            original = source.read_text(encoding="utf-8")
            log_path.write_text(original, encoding="utf-8")
            canonical_path = root / "canonical.sqlite3"

            self._import(logs_path, canonical_path)
            first_counts, first_hashes = self._counts_and_hashes(canonical_path)
            self._import(logs_path, canonical_path)
            second_counts, second_hashes = self._counts_and_hashes(canonical_path)

            log_path.write_text(
                original.replace(
                    "Plan: Add an end-to-end retrieval test next.",
                    "Plan: Add an end-to-end provenance test next.",
                ),
                encoding="utf-8",
            )
            self._import(logs_path, canonical_path)
            changed_counts, changed_hashes = self._counts_and_hashes(canonical_path)

            self.assertEqual(second_counts, first_counts)
            self.assertEqual(second_hashes, first_hashes)
            self.assertEqual(changed_counts, first_counts)
            self.assertNotEqual(changed_hashes, first_hashes)

    def test_allowed_decision_is_retrieved_with_conversation_source_and_date(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            canonical_path = root / "canonical.sqlite3"
            session_directory = root / "session"
            self._import(LOG_FIXTURES, canonical_path)
            build = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SESSION),
                    "--canonical",
                    str(canonical_path),
                    "--policy",
                    str(POLICY),
                    "--world",
                    "personal",
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
                                "SELECT d.canonical_name AS decision, "
                                "c.canonical_name AS conversation, "
                                "v.source_ref, v.occurred_at "
                                "FROM nodes AS d "
                                "JOIN edges AS link ON link.from_node_id = d.node_id "
                                "AND link.relation = 'mentioned_in' "
                                "JOIN nodes AS c ON c.node_id = link.to_node_id "
                                "JOIN evidence AS v ON v.node_id = d.node_id "
                                "WHERE d.type = 'decision' "
                                "AND d.canonical_name = 'Store memories in SQLite.'"
                            )
                        },
                    },
                },
            )

            rows = response["result"]["structuredContent"]["rows"]
            self.assertEqual(
                rows,
                [
                    {
                        "decision": "Store memories in SQLite.",
                        "conversation": "SQLite migration",
                        "source_ref": "codex://2025-03-15-sqlite.md#L13",
                        "occurred_at": "2025-03-15T14:30:00Z",
                    }
                ],
            )

    def _import(self, logs_path, canonical_path, *extra_arguments):
        result = subprocess.run(
            [
                sys.executable,
                str(IMPORT_CODEX_LOGS),
                "--logs",
                str(logs_path),
                "--canonical",
                str(canonical_path),
                "--world",
                "personal",
                *extra_arguments,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    @staticmethod
    def _counts_and_hashes(canonical_path):
        with closing(sqlite3.connect(canonical_path)) as connection:
            counts = {
                table: connection.execute(
                    f"SELECT count(*) FROM {table}"
                ).fetchone()[0]
                for table in ("nodes", "edges", "evidence", "import_records")
            }
            hashes = connection.execute(
                "SELECT source_ref, content_hash FROM evidence ORDER BY source_ref"
            ).fetchall()
        return counts, hashes

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
