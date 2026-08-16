import json
from contextlib import closing, contextmanager
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

from mcp_server import handle


class IntegratedGraphQueryTest(unittest.TestCase):
    def test_one_fixture_run_builds_a_three_source_capability_database(self):
        with self._fixture_session() as (session, capability):
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
            self.assertTrue(Path(session["capabilityDatabase"]).is_file())

    def test_alias_and_canonical_anchors_return_a_provenanced_two_hop_cycle(self):
        with self._fixture_session() as (session, capability):
            cycle_relations = capability.execute(
                "SELECT e.relation FROM edges AS e "
                "JOIN nodes AS source ON source.node_id = e.from_node_id "
                "JOIN nodes AS target ON target.node_id = e.to_node_id "
                "WHERE (source.canonical_name, target.canonical_name) IN "
                "(('Nishiki Market', 'Kyoto'), ('Kyoto', 'Nishiki Market')) "
                "ORDER BY e.relation"
            ).fetchall()
            self.assertEqual(cycle_relations, [("includes",), ("related_to",)])
            expectations = {
                "Kyoto market": [
                    (0, "Nishiki Market", "google_maps_takeout", None),
                    (1, "Kyoto", "codex_logs", "related_to"),
                    (
                        2,
                        "Kyoto itinerary",
                        "browser_history",
                        "researched_with",
                    ),
                ],
                "Kyoto itinerary": [
                    (0, "Kyoto itinerary", "browser_history", None),
                    (1, "Nishiki Market", "google_maps_takeout", "mentions"),
                    (2, "Kyoto", "codex_logs", "related_to"),
                ],
            }
            for anchor, expected in expectations.items():
                with self.subTest(anchor=anchor):
                    rows = self._recursive_query(session, capability, anchor)
                    self.assertTrue(
                        set(expected).issubset({
                            (
                                row["depth"],
                                row["canonical_name"],
                                row["node_source_kind"],
                                row["via_relation"],
                            )
                            for row in rows
                        }),
                    )
                    self.assertEqual(
                        len({row["node_id"] for row in rows}),
                        len(rows),
                    )
                    self.assertTrue(all(row["node_source_ref"] for row in rows))
                    self.assertTrue(all(row["node_occurred_at"] for row in rows))
                    traversed_rows = [row for row in rows if row["depth"] > 0]
                    self.assertTrue(
                        all(row["via_relation"] for row in traversed_rows)
                    )
                    self.assertTrue(
                        all(row["edge_source_kind"] for row in traversed_rows)
                    )
                    self.assertTrue(
                        all(row["edge_source_ref"] for row in traversed_rows)
                    )
                    self.assertTrue(
                        all(row["edge_occurred_at"] for row in traversed_rows)
                    )

    def test_adversarial_read_cannot_recover_physically_omitted_records(self):
        with self._fixture_session() as (session, capability):
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
        with self._fixture_session() as (session, capability):
            rows = self._recursive_query(
                session,
                capability,
                "an entity that is absent from every fixture",
            )

            self.assertEqual(rows, [])

    def test_guidance_supports_no_query_and_explains_bounded_traversal(self):
        with self._fixture_session() as (session, capability):
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
        fixture = json.loads(result.stdout)
        session_path = Path(fixture["sessionPath"])
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session["capabilityDatabase"] = fixture["capabilityDatabase"]
        return session

    @classmethod
    @contextmanager
    def _fixture_session(cls):
        with tempfile.TemporaryDirectory() as temporary_directory:
            session = cls._build_fixture(Path(temporary_directory))
            with closing(
                sqlite3.connect(session["capabilityDatabase"])
            ) as capability:
                yield session, capability

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
            neighborhood(node_id, depth, path, via_edge_id) AS (
              SELECT node_id, 0, '|' || node_id || '|', NULL
              FROM anchors

              UNION ALL

              SELECT e.to_node_id,
                     neighborhood.depth + 1,
                     neighborhood.path || e.to_node_id || '|',
                     e.edge_id
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
                   node_evidence.source_kind AS node_source_kind,
                   node_evidence.source_ref AS node_source_ref,
                   node_evidence.occurred_at AS node_occurred_at,
                   traversed.relation AS via_relation,
                   edge_evidence.source_kind AS edge_source_kind,
                   edge_evidence.source_ref AS edge_source_ref,
                   edge_evidence.occurred_at AS edge_occurred_at
            FROM neighborhood
            JOIN nodes AS n ON n.node_id = neighborhood.node_id
            JOIN evidence AS node_evidence ON node_evidence.evidence_id = (
              SELECT candidate.evidence_id
              FROM evidence AS candidate
              WHERE candidate.node_id = n.node_id
              ORDER BY candidate.occurred_at DESC, candidate.evidence_id
              LIMIT 1
            )
            LEFT JOIN edges AS traversed
              ON traversed.edge_id = neighborhood.via_edge_id
            LEFT JOIN evidence AS edge_evidence
              ON edge_evidence.evidence_id = (
                SELECT candidate.evidence_id
                FROM evidence AS candidate
                WHERE candidate.edge_id = traversed.edge_id
                ORDER BY candidate.occurred_at DESC, candidate.evidence_id
                LIMIT 1
              )
            ORDER BY neighborhood.depth,
                     n.canonical_name,
                     node_evidence.source_ref
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
