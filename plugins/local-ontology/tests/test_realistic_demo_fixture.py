import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PLUGIN_ROOT / "examples" / "realistic-user-demo"
BUILD_DEMO = PLUGIN_ROOT / "scripts" / "build_realistic_demo.py"


class RealisticDemoFixtureTest(unittest.TestCase):
    def test_demo_builds_all_sources_and_returns_provenanced_queries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_DEMO),
                    "--session-dir",
                    str(Path(temporary_directory) / "session"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            demo = json.loads(result.stdout)
            result_path = Path(demo["resultPath"])
            self.assertTrue(result_path.is_file())
            self.assertEqual(
                json.loads(result_path.read_text(encoding="utf-8")),
                demo,
            )

        self.assertTrue(demo["persona"]["fictional"])
        self.assertFalse(demo["persona"]["privacy"]["rawDataCopied"])
        self.assertEqual(demo["selectedWorld"], "work")
        self.assertEqual(
            demo["sourceKinds"],
            [
                "browser_history",
                "codex_logs",
                "fixture_graph",
                "google_maps_takeout",
            ],
        )
        self.assertEqual(demo["reports"]["browserHistory"]["importedPages"], 7)
        self.assertEqual(demo["reports"]["browserHistory"]["excludedPages"], 1)
        self.assertEqual(demo["reports"]["codexLogs"]["importedConversations"], 4)
        self.assertEqual(
            demo["reports"]["googleMapsTakeout"]["importedPlaces"],
            3,
        )
        self.assertEqual(
            demo["policyBoundary"],
            {"canonicalRows": 3, "capabilityRows": 0},
        )

        chatbot_rows = demo["queries"]["챗봇 분석"]["rows"]
        chatbot_names = {row["canonical_name"] for row in chatbot_rows}
        self.assertTrue(
            {
                "사회적 챗봇 성과 분석",
                "관찰 기간은 설치 다음 날부터 28일로 정한다.",
                "pandas DataFrame.merge documentation",
                "서울 데이터랩",
            }.issubset(chatbot_names)
        )
        ontology_rows = demo["queries"]["내 기억 시스템"]["rows"]
        ontology_names = {row["canonical_name"] for row in ontology_rows}
        self.assertTrue(
            {
                "개인용 로컬 온톨로지",
                "SQLite WITH and recursive CTE documentation",
                "성수 데모 워크라운지",
                "사회적 챗봇 성과 분석",
            }.issubset(ontology_names)
        )
        for rows in (chatbot_rows, ontology_rows):
            self.assertTrue(all(row["node_source_kind"] for row in rows))
            self.assertTrue(all(row["node_source_ref"] for row in rows))
            self.assertTrue(all(row["node_occurred_at"] for row in rows))

    def test_fixture_does_not_copy_local_identifiers_or_paths(self):
        fixture_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in FIXTURE_ROOT.rglob("*")
            if path.is_file()
        ).casefold()
        for forbidden in (
            "jae04",
            "d:\\.jae",
            "c:\\users\\",
            "\\.claude\\",
            "\\.codex\\",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, fixture_text)


if __name__ == "__main__":
    unittest.main()
