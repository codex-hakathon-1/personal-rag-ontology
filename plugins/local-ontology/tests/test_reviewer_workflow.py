import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REVIEW_FIXTURE = PLUGIN_ROOT / "scripts" / "review_fixture.py"


class ReviewerWorkflowTest(unittest.TestCase):
    def test_one_command_proves_imports_query_provenance_and_policy_boundary(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(REVIEW_FIXTURE),
                    "--session-dir",
                    str(Path(temporary_directory) / "session"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        proof = json.loads(result.stdout)
        self.assertEqual(proof["selectedWorld"], "travel")
        self.assertEqual(
            proof["importedSourceKinds"],
            ["browser_history", "codex_logs", "google_maps_takeout"],
        )
        self.assertEqual(
            [
                (row["depth"], row["canonical_name"])
                for row in proof["happyPath"]["rows"]
            ],
            [
                (0, "Nishiki Market"),
                (1, "Kyoto"),
                (2, "Kyoto itinerary"),
                (2, "Kyoto research review"),
            ],
        )
        self.assertTrue(
            all(
                row["source_kind"]
                and row["source_ref"]
                and row["occurred_at"]
                for row in proof["happyPath"]["rows"]
            )
        )
        self.assertEqual(proof["forbiddenInCanonical"], 3)
        self.assertEqual(proof["adversarial"]["rows"], [])

    def test_distributed_plugin_contains_no_generated_database(self):
        database_suffixes = {".db", ".sqlite", ".sqlite3"}
        packaged_databases = [
            path.relative_to(PLUGIN_ROOT).as_posix()
            for path in PLUGIN_ROOT.rglob("*")
            if path.is_file() and path.suffix.casefold() in database_suffixes
        ]

        self.assertEqual(packaged_databases, [])


if __name__ == "__main__":
    unittest.main()
