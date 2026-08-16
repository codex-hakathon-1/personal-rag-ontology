import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SKILL = PLUGIN_ROOT / "skills" / "local-ontology" / "SKILL.md"
BUILD_INTEGRATED_FIXTURE = (
    PLUGIN_ROOT / "scripts" / "build_integrated_fixture.py"
)
SCRIPTS = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_session import build_capability_connection
from mcp_server import handle


class IntegratedGraphQueryTest(unittest.TestCase):
    def test_one_fixture_run_builds_a_three_source_capability_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            session = self._build_fixture(Path(temporary_directory))
            capability = build_capability_connection(
                Path(session["canonicalDatabase"]),
                session["selectedWorld"],
                session["policyContract"],
            )
            self.addCleanup(capability.close)

            source_kinds = capability.execute(
                "SELECT DISTINCT source_kind FROM evidence ORDER BY source_kind"
            ).fetchall()
            with closing(sqlite3.connect(session["canonicalDatabase"])) as canonical:
                imported_source_kinds = canonical.execute(
                    "SELECT DISTINCT source_kind FROM import_records "
                    "ORDER BY source_kind"
                ).fetchall()

            self.assertEqual(
                imported_source_kinds,
                [
                    ("browser_history",),
                    ("codex_logs",),
                    ("google_maps_takeout",),
                ],
            )
            self.assertTrue(set(imported_source_kinds).issubset(source_kinds))
            self.assertEqual(session["selectedWorld"], "travel")

    def test_alias_and_canonical_anchors_return_a_provenanced_two_hop_cycle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            session = self._build_fixture(Path(temporary_directory))
            capability = build_capability_connection(
                Path(session["canonicalDatabase"]),
                session["selectedWorld"],
                session["policyContract"],
            )
            self.addCleanup(capability.close)

            expectations = {
                "Kyoto market": [
                    (0, "Nishiki Market", "google_maps_takeout"),
                    (1, "Kyoto", "codex_logs"),
                    (2, "Kyoto itinerary", "browser_history"),
                ],
                "Kyoto itinerary": [
                    (0, "Kyoto itinerary", "browser_history"),
                    (1, "Nishiki Market", "google_maps_takeout"),
                    (2, "Kyoto", "codex_logs"),
                ],
            }
            for anchor, expected in expectations.items():
                with self.subTest(anchor=anchor):
                    rows = self._recursive_query(session, capability, anchor)
                    self.assertTrue(
                        set(expected).issubset({
                            (row["depth"], row["canonical_name"], row["source_kind"])
                            for row in rows
                        }),
                    )
                    self.assertEqual(
                        len({row["node_id"] for row in rows}),
                        len(rows),
                    )
                    self.assertTrue(all(row["source_ref"] for row in rows))
                    self.assertTrue(all(row["occurred_at"] for row in rows))

    def test_adversarial_read_cannot_recover_physically_omitted_records(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            session = self._build_fixture(Path(temporary_directory))
            with closing(sqlite3.connect(session["canonicalDatabase"])) as canonical:
                forbidden_canonical_names = canonical.execute(
                    "SELECT canonical_name FROM nodes "
                    "WHERE canonical_name LIKE 'Forbidden fixture:%' "
                    "ORDER BY canonical_name"
                ).fetchall()
            self.assertEqual(
                forbidden_canonical_names,
                [
                    ("Forbidden fixture: dormant",),
                    ("Forbidden fixture: other world",),
                    ("Forbidden fixture: secret",),
                ],
            )

            capability = build_capability_connection(
                Path(session["canonicalDatabase"]),
                session["selectedWorld"],
                session["policyContract"],
            )
            self.addCleanup(capability.close)
            response = handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "query_memory",
                        "arguments": {
                            "sql": (
                                "SELECT n.canonical_name, n.world_id, n.state, "
                                "n.sensitivity, v.source_ref "
                                "FROM nodes AS n LEFT JOIN evidence AS v "
                                "ON v.node_id = n.node_id "
                                "WHERE n.canonical_name LIKE 'Forbidden fixture:%' "
                                "OR v.source_ref LIKE "
                                "'fixture://integrated/forbidden/%'"
                            )
                        },
                    },
                },
                session,
                capability,
            )

            assert response is not None
            self.assertEqual(
                response["result"]["structuredContent"]["rows"],
                [],
            )

    def test_unmatched_personal_anchor_returns_no_personal_data(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            session = self._build_fixture(Path(temporary_directory))
            capability = build_capability_connection(
                Path(session["canonicalDatabase"]),
                session["selectedWorld"],
                session["policyContract"],
            )
            self.addCleanup(capability.close)

            rows = self._recursive_query(
                session,
                capability,
                "an entity that is absent from every fixture",
            )

            self.assertEqual(rows, [])

    def test_guidance_supports_no_query_and_explains_bounded_traversal(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            session = self._build_fixture(Path(temporary_directory))
            capability = build_capability_connection(
                Path(session["canonicalDatabase"]),
                session["selectedWorld"],
                session["policyContract"],
            )
            self.addCleanup(capability.close)

            response = handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                },
                session,
                capability,
            )

            assert response is not None
            instructions = response["result"]["instructions"].casefold()
            skill = PLUGIN_SKILL.read_text(encoding="utf-8").casefold()
            for guidance in (instructions, skill):
                self.assertIn("personal anchor", guidance)
                self.assertIn("no query is a normal outcome", guidance)
                self.assertIn("node_aliases", guidance)
                self.assertIn("two hops", guidance)
                self.assertIn("cycle", guidance)
                self.assertIn("source_kind", guidance)
                self.assertIn("source_ref", guidance)
                self.assertIn("occurred_at", guidance)
            for fixture_fact in (
                "nishiki market",
                "kyoto itinerary",
                "forbidden fixture",
            ):
                self.assertNotIn(fixture_fact, instructions)
                self.assertNotIn(fixture_fact, skill)
            self.assertFalse(Path(session["queryAuditLog"]).exists())

    @staticmethod
    def _build_fixture(root: Path) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                str(BUILD_INTEGRATED_FIXTURE),
                "--session-dir",
                str(root / "session"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        session_path = Path(json.loads(result.stdout)["sessionPath"])
        return json.loads(session_path.read_text(encoding="utf-8"))

    @staticmethod
    def _recursive_query(
        session: dict,
        capability: sqlite3.Connection,
        anchor: str,
    ) -> list[dict]:
        sql = f"""
            WITH RECURSIVE
            anchors(node_id) AS (
              SELECT DISTINCT n.node_id
              FROM nodes AS n
              LEFT JOIN node_aliases AS a ON a.node_id = n.node_id
              WHERE lower(n.canonical_name) = lower('{anchor}')
                 OR lower(a.alias) = lower('{anchor}')
            ),
            neighborhood(node_id, depth, path) AS (
              SELECT node_id, 0, '|' || node_id || '|'
              FROM anchors

              UNION ALL

              SELECT e.to_node_id,
                     neighborhood.depth + 1,
                     neighborhood.path || e.to_node_id || '|'
              FROM neighborhood
              JOIN edges AS e ON e.from_node_id = neighborhood.node_id
              WHERE neighborhood.depth < 2
                AND e.state = 'active'
                AND instr(
                      neighborhood.path,
                      '|' || e.to_node_id || '|'
                    ) = 0
            )
            SELECT neighborhood.node_id,
                   neighborhood.depth,
                   n.type AS node_type,
                   n.canonical_name,
                   v.source_kind,
                   v.source_ref,
                   v.occurred_at
            FROM neighborhood
            JOIN nodes AS n ON n.node_id = neighborhood.node_id
            JOIN evidence AS v ON v.evidence_id = (
              SELECT candidate.evidence_id
              FROM evidence AS candidate
              WHERE candidate.node_id = n.node_id
              ORDER BY candidate.occurred_at DESC, candidate.evidence_id
              LIMIT 1
            )
            ORDER BY neighborhood.depth, n.canonical_name, v.source_ref
        """
        response = handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "query_memory",
                    "arguments": {"sql": sql},
                },
            },
            session,
            capability,
        )
        assert response is not None
        return response["result"]["structuredContent"]["rows"]


if __name__ == "__main__":
    unittest.main()
