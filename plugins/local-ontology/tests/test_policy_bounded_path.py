import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
BUILD_SESSION = PLUGIN_ROOT / "scripts" / "build_session.py"
MCP_SERVER = PLUGIN_ROOT / "scripts" / "mcp_server.py"
FIXTURE = PLUGIN_ROOT / "examples" / "demo-fixture" / "graph.json"
POLICY = PLUGIN_ROOT / "examples" / "policy.example.json"
ALLOWED_FACT = "Booked a riverside ryokan for the Kyoto leg."


class PolicyBoundedSqlPathTest(unittest.TestCase):
    def test_fact_is_absent_at_startup_and_returned_only_by_explicit_sql(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            session_directory = Path(temporary_directory)
            build = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SESSION),
                    "--fixture",
                    str(FIXTURE),
                    "--policy",
                    str(POLICY),
                    "--world",
                    "travel",
                    "--session-dir",
                    str(session_directory),
                    "--max-rows",
                    "1",
                    "--max-execution-ms",
                    "250",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            build_result = json.loads(build.stdout)
            session_path = Path(build_result["sessionPath"])
            session = json.loads(session_path.read_text(encoding="utf-8"))

            self.assertEqual(build_result["selectedWorld"], "travel")
            self.assertNotIn(ALLOWED_FACT, build.stdout)

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

            initialize = self._request(
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
            serialized_startup = json.dumps(initialize, ensure_ascii=False)
            self.assertNotIn(ALLOWED_FACT, serialized_startup)
            self.assertIn("selected world is travel", serialized_startup)
            self.assertIn("nodes, edges, and evidence", serialized_startup)

            tools = self._request(
                server,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            self.assertEqual(
                [tool["name"] for tool in tools["result"]["tools"]],
                ["query_memory"],
            )

            query = self._request(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "query_memory",
                        "arguments": {
                            "sql": (
                                "SELECT n.canonical_name, n.summary, "
                                "e.source_kind, e.source_ref, e.occurred_at "
                                "FROM nodes AS n JOIN evidence AS e "
                                "ON e.node_id = n.node_id "
                                "WHERE n.canonical_name = 'Kyoto ryokan'"
                            )
                        },
                    },
                },
            )
            result = query["result"]["structuredContent"]

            self.assertEqual(
                result["rows"],
                [
                    {
                        "canonical_name": "Kyoto ryokan",
                        "summary": ALLOWED_FACT,
                        "source_kind": "codex_logs",
                        "source_ref": "fixture://travel/kyoto-plan.md#L12",
                        "occurred_at": "2025-03-18T09:30:00Z",
                    }
                ],
            )
            self.assertEqual(result["rowCount"], 1)
            self.assertFalse(result["truncated"])
            self.assertEqual(result["maxRows"], 1)

            canonical_path = session["canonicalDatabase"].replace("'", "''")
            attach = self._request(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "query_memory",
                        "arguments": {
                            "sql": (
                                f"ATTACH DATABASE '{canonical_path}' AS canonical"
                            )
                        },
                    },
                },
            )
            canonical_read = self._request(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "query_memory",
                        "arguments": {"sql": "SELECT * FROM canonical.nodes"},
                    },
                },
            )

            self.assertTrue(attach["result"]["isError"])
            self.assertTrue(canonical_read["result"]["isError"])

            audit_path = Path(session["queryAuditLog"])
            audit_text = audit_path.read_text(encoding="utf-8")
            audit_entries = [json.loads(line) for line in audit_text.splitlines()]
            self.assertEqual(len(audit_entries), 3)
            self.assertEqual(
                [entry["outcome"] for entry in audit_entries],
                ["succeeded", "rejected", "rejected"],
            )
            for entry in audit_entries:
                self.assertEqual(
                    entry["sessionIdentifier"], session["sessionIdentifier"]
                )
                self.assertEqual(entry["worldIdentifier"], "travel")
            self.assertNotIn(ALLOWED_FACT, audit_text)
            self.assertNotIn("ATTACH DATABASE", audit_text)
            self.assertEqual(
                session["queryLimits"],
                {"maxRows": 1, "maxExecutionMs": 250},
            )

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
