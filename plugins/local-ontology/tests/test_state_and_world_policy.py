import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = PLUGIN_ROOT / "schema" / "canonical.sql"
REBUILD_STATE = PLUGIN_ROOT / "scripts" / "rebuild_state.py"
SCRIPTS = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_session import build_capability_connection


class StateAndWorldPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.canonical_path = self.root / "canonical.sqlite3"
        with closing(sqlite3.connect(self.canonical_path)) as connection:
            with connection:
                connection.executescript(
                    CANONICAL_SCHEMA.read_text(encoding="utf-8")
                )
                connection.execute(
                    "INSERT INTO worlds VALUES (?, ?, ?, ?)",
                    ("travel", "Travel", "Travel memories", 1),
                )
                connection.execute(
                    "INSERT INTO worlds VALUES (?, ?, ?, ?)",
                    ("personal", "Personal", "Personal memories", 1),
                )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def add_node(
        self,
        node_id,
        *,
        node_type="plan",
        state="active",
        sensitivity="normal",
        last_seen_at="2025-01-01T00:00:00Z",
        world_id="travel",
    ):
        with closing(sqlite3.connect(self.canonical_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO nodes (
                      node_id, world_id, type, canonical_name, summary, state,
                      sensitivity, valid_from, valid_to, last_seen_at,
                      superseded_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?)
                    """,
                    (
                        node_id,
                        world_id,
                        node_type,
                        node_id,
                        node_id,
                        state,
                        sensitivity,
                        last_seen_at,
                        last_seen_at,
                        last_seen_at,
                        last_seen_at,
                    ),
                )

    def add_evidence(
        self,
        evidence_id,
        *,
        node_id=None,
        edge_id=None,
        source_kind="codex_logs",
    ):
        with closing(sqlite3.connect(self.canonical_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO evidence VALUES (
                      ?, ?, ?, ?, ?, '2025-01-01T00:00:00Z',
                      '2025-01-01T00:00:00Z', ?, ?
                    )
                    """,
                    (
                        evidence_id,
                        node_id,
                        edge_id,
                        source_kind,
                        f"{source_kind}://{evidence_id}",
                        evidence_id,
                        f"hash-{evidence_id}",
                    ),
                )

    def add_edge(self, edge_id, from_node_id, to_node_id, *, source_kind):
        with closing(sqlite3.connect(self.canonical_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO edges VALUES (
                      ?, 'travel', ?, 'related_to', ?, 'active',
                      '2025-01-01T00:00:00Z', NULL, 1.0, 1,
                      '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'
                    )
                    """,
                    (edge_id, from_node_id, to_node_id),
                )
        self.add_evidence(
            f"evidence-{edge_id}",
            edge_id=edge_id,
            source_kind=source_kind,
        )

    def test_rebuild_marks_only_plans_older_than_configured_age_as_dormant(self):
        self.add_node("stale-plan", last_seen_at="2025-01-01T00:00:00Z")
        self.add_node("recent-plan", last_seen_at="2025-04-15T00:00:00Z")
        rules_path = self.root / "state-rules.json"
        rules_path.write_text(
            json.dumps({"dormant_after_days": {"plan": 90}}),
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(REBUILD_STATE),
                "--canonical",
                str(self.canonical_path),
                "--rules",
                str(rules_path),
                "--as-of",
                "2025-05-01T00:00:00Z",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        with closing(sqlite3.connect(self.canonical_path)) as connection:
            states = dict(connection.execute("SELECT node_id, state FROM nodes"))

        self.assertEqual(
            states,
            {"stale-plan": "dormant", "recent-plan": "active"},
        )

    def test_rebuild_supersedes_only_the_fact_named_by_replacement_evidence(self):
        self.add_node("old-plan", last_seen_at="2025-01-01T00:00:00Z")
        self.add_node("replacement-plan", last_seen_at="2025-03-01T00:00:00Z")
        self.add_node("merely-newer-plan", last_seen_at="2025-04-01T00:00:00Z")
        with closing(sqlite3.connect(self.canonical_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO edges (
                      edge_id, world_id, from_node_id, relation, to_node_id,
                      state, valid_from, valid_to, confidence, evidence_count,
                      created_at, updated_at
                    ) VALUES (
                      'replacement-edge', 'travel', 'replacement-plan',
                      'supersedes', 'old-plan', 'active',
                      '2025-03-01T00:00:00Z', NULL, 0.99, 1,
                      '2025-03-01T00:00:00Z', '2025-03-01T00:00:00Z'
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO evidence VALUES (
                      'replacement-evidence', NULL, 'replacement-edge',
                      'codex_logs', 'codex://plans.md#L12',
                      '2025-03-01T00:00:00Z', '2025-03-01T00:00:00Z',
                      'Replacement plan replaces old plan.', 'replacement-hash'
                    )
                    """
                )
        rules_path = self.root / "state-rules.json"
        rules_path.write_text("{}", encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                str(REBUILD_STATE),
                "--canonical",
                str(self.canonical_path),
                "--rules",
                str(rules_path),
                "--as-of",
                "2025-05-01T00:00:00Z",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        with closing(sqlite3.connect(self.canonical_path)) as connection:
            rows = connection.execute(
                "SELECT node_id, state, superseded_by FROM nodes ORDER BY node_id"
            ).fetchall()

        self.assertEqual(
            rows,
            [
                ("merely-newer-plan", "active", None),
                ("old-plan", "superseded", "replacement-plan"),
                ("replacement-plan", "active", None),
            ],
        )

    def test_capability_database_physically_applies_the_complete_world_policy(self):
        nodes = (
            ("allowed-active", {}),
            ("allowed-dormant", {"state": "dormant"}),
            ("allowed-superseded", {"state": "superseded"}),
            ("denied-type", {"node_type": "place"}),
            ("denied-sensitivity", {"sensitivity": "secret"}),
            ("denied-source", {}),
            ("other-world", {"world_id": "personal"}),
        )
        for node_id, options in nodes:
            self.add_node(node_id, **options)
            source = "browser_history" if node_id == "denied-source" else "codex_logs"
            self.add_evidence(
                f"evidence-{node_id}",
                node_id=node_id,
                source_kind=source,
            )
        self.add_edge(
            "allowed-edge",
            "allowed-active",
            "allowed-dormant",
            source_kind="codex_logs",
        )
        self.add_edge(
            "denied-endpoint-edge",
            "allowed-active",
            "denied-type",
            source_kind="codex_logs",
        )
        self.add_edge(
            "denied-source-edge",
            "allowed-active",
            "allowed-dormant",
            source_kind="browser_history",
        )
        policy = {
            "include_sources": ["codex_logs"],
            "allow_node_types": ["plan"],
            "include_states": ["active", "dormant", "superseded"],
            "deny_sensitivity": ["secret", "identity"],
        }

        capability = build_capability_connection(
            self.canonical_path,
            "travel",
            policy,
        )
        self.addCleanup(capability.close)

        self.assertEqual(
            capability.execute("SELECT node_id FROM nodes ORDER BY node_id").fetchall(),
            [
                ("allowed-active",),
                ("allowed-dormant",),
                ("allowed-superseded",),
            ],
        )
        self.assertEqual(
            capability.execute("SELECT DISTINCT world_id FROM nodes").fetchall(),
            [("travel",)],
        )
        with self.assertRaisesRegex(sqlite3.OperationalError, "no such table: worlds"):
            capability.execute("SELECT * FROM worlds").fetchall()
        self.assertEqual(
            capability.execute("SELECT edge_id FROM edges ORDER BY edge_id").fetchall(),
            [("allowed-edge",)],
        )
        self.assertEqual(
            capability.execute(
                "SELECT evidence_id FROM evidence ORDER BY evidence_id"
            ).fetchall(),
            [
                ("evidence-allowed-active",),
                ("evidence-allowed-dormant",),
                ("evidence-allowed-edge",),
                ("evidence-allowed-superseded",),
            ],
        )

    def test_unchanged_rebuilds_have_deterministic_state_and_capability_contents(self):
        self.add_node("stale-plan", last_seen_at="2025-01-01T00:00:00Z")
        self.add_evidence("evidence-stale-plan", node_id="stale-plan")
        rules_path = self.root / "state-rules.json"
        rules_path.write_text(
            json.dumps({"dormant_after_days": {"plan": 30}}),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(REBUILD_STATE),
            "--canonical",
            str(self.canonical_path),
            "--rules",
            str(rules_path),
            "--as-of",
            "2025-05-01T00:00:00Z",
        ]

        first = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        with closing(sqlite3.connect(self.canonical_path)) as connection:
            state_after_first = connection.execute(
                "SELECT state, superseded_by, updated_at FROM nodes WHERE node_id = ?",
                ("stale-plan",),
            ).fetchone()
        second = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        with closing(sqlite3.connect(self.canonical_path)) as connection:
            state_after_second = connection.execute(
                "SELECT state, superseded_by, updated_at FROM nodes WHERE node_id = ?",
                ("stale-plan",),
            ).fetchone()

        policy = {
            "include_sources": ["codex_logs"],
            "allow_node_types": ["plan"],
            "include_states": ["dormant"],
            "deny_sensitivity": ["secret"],
        }
        first_capability = build_capability_connection(
            self.canonical_path, "travel", policy
        )
        second_capability = build_capability_connection(
            self.canonical_path, "travel", policy
        )
        self.addCleanup(first_capability.close)
        self.addCleanup(second_capability.close)

        self.assertEqual(
            json.loads(first.stdout),
            {
                "changedToActive": 0,
                "changedToDormant": 1,
                "changedToSuperseded": 0,
            },
        )
        self.assertEqual(
            json.loads(second.stdout),
            {
                "changedToActive": 0,
                "changedToDormant": 0,
                "changedToSuperseded": 0,
            },
        )
        self.assertEqual(state_after_first, state_after_second)
        self.assertEqual(first_capability.serialize(), second_capability.serialize())

    def test_explicitly_empty_policy_allowlists_do_not_widen_access(self):
        self.add_node("plan")
        self.add_evidence("evidence-plan", node_id="plan")

        for policy in (
            {"include_sources": [], "include_states": ["active"]},
            {"allow_node_types": [], "include_states": ["active"]},
        ):
            with self.subTest(policy=policy):
                capability = build_capability_connection(
                    self.canonical_path,
                    "travel",
                    policy,
                )
                try:
                    count = capability.execute(
                        "SELECT count(*) FROM nodes"
                    ).fetchone()[0]
                finally:
                    capability.close()

                self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
