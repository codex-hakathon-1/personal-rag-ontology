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
IMPORT_TAKEOUT = PLUGIN_ROOT / "scripts" / "import_google_maps_takeout.py"
BUILD_SESSION = PLUGIN_ROOT / "scripts" / "build_session.py"
MCP_SERVER = PLUGIN_ROOT / "scripts" / "mcp_server.py"
TAKEOUT_FIXTURE = (
    PLUGIN_ROOT / "examples" / "google-maps-takeout-fixture"
)
SAVED_PLACES_PATH = "Takeout/Maps (your places)/Saved Places.json"
POLICY = PLUGIN_ROOT / "examples" / "google-maps-policy.example.json"


class GoogleMapsTakeoutImportTest(unittest.TestCase):
    def test_saved_places_import_reports_records_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            canonical_path = Path(temporary_directory) / "canonical.sqlite3"

            first = self._import(TAKEOUT_FIXTURE, canonical_path)
            first_counts = self._table_counts(canonical_path)
            second = self._import(TAKEOUT_FIXTURE, canonical_path)
            second_counts = self._table_counts(canonical_path)

            with closing(sqlite3.connect(canonical_path)) as connection:
                places = connection.execute(
                    "SELECT canonical_name, summary, last_seen_at FROM nodes "
                    "WHERE type = 'place' ORDER BY canonical_name"
                ).fetchall()
                records = connection.execute(
                    "SELECT source_ref, occurred_at, raw_text_or_metadata, "
                    "candidate_entities, provenance, content_hash "
                    "FROM import_records "
                    "WHERE source_kind = 'google_maps_takeout' "
                    "ORDER BY occurred_at"
                ).fetchall()

            expected_report = {
                "archiveStatus": "supported",
                "format": "google_maps_saved_places_geojson_v1",
                "importedFiles": 1,
                "importedPlaces": 2,
                "malformedRecords": [
                    {
                        "path": SAVED_PLACES_PATH,
                        "recordIndex": 2,
                        "reason": (
                            "properties.Location.Business Name must be a "
                            "non-empty string"
                        ),
                    }
                ],
                "skippedPaths": [
                    {
                        "path": "Takeout/Chrome/BrowserHistory.json",
                        "reason": "unsupported_takeout_product",
                    },
                    {
                        "path": "Takeout/Maps (your places)/Reviews.json",
                        "reason": "unsupported_archive_path",
                    },
                ],
                "warnings": [
                    {
                        "path": SAVED_PLACES_PATH,
                        "recordIndex": 1,
                        "missingOptionalFields": ["properties.Location.Address"],
                    }
                ],
                "world": "travel",
            }
            self.assertEqual(first, expected_report)
            self.assertEqual(second, expected_report)
            self.assertEqual(first_counts, second_counts)
            self.assertEqual(
                first_counts,
                {"import_records": 2, "nodes": 2, "edges": 0, "evidence": 2},
            )
            self.assertEqual(
                places,
                [
                    (
                        "Nishiki Market",
                        "Saved Google Maps place at 2 Nakagyo Ward, Kyoto, Japan.",
                        "2025-03-12T08:15:00Z",
                    ),
                    (
                        "Philosopher's Path",
                        "Saved Google Maps place.",
                        "2025-03-13T09:30:00Z",
                    ),
                ],
            )
            self.assertEqual(len(records), 2)
            for (
                source_ref,
                occurred_at,
                raw_json,
                candidates_json,
                provenance_json,
                digest,
            ) in records:
                self.assertTrue(
                    source_ref.startswith("https://www.google.com/maps/place/")
                )
                self.assertRegex(occurred_at, r"^2025-03-\d{2}T")
                self.assertIn("geometry", json.loads(raw_json))
                self.assertEqual(
                    [candidate["type"] for candidate in json.loads(candidates_json)],
                    ["place"],
                )
                self.assertEqual(
                    json.loads(provenance_json)["archive_path"],
                    SAVED_PLACES_PATH,
                )
                self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", digest))

    def test_archive_without_supported_path_is_reported_and_not_misparsed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            takeout_path = root / "archive"
            unsupported_path = (
                takeout_path
                / "Takeout"
                / "Location History (Timeline)"
                / "Records.json"
            )
            unsupported_path.parent.mkdir(parents=True)
            unsupported_path.write_text(
                '{"locations": [{"latitudeE7": 350116000}]}\n',
                encoding="utf-8",
            )

            report = self._import(takeout_path, root / "canonical.sqlite3")

            self.assertEqual(report["archiveStatus"], "unsupported")
            self.assertEqual(report["importedFiles"], 0)
            self.assertEqual(report["importedPlaces"], 0)
            self.assertEqual(
                report["skippedPaths"],
                [
                    {
                        "path": (
                            "Takeout/Location History (Timeline)/Records.json"
                        ),
                        "reason": "unsupported_takeout_product",
                    },
                    {
                        "path": SAVED_PLACES_PATH,
                        "reason": "supported_archive_path_not_found",
                    },
                ],
            )
            self.assertEqual(
                self._table_counts(root / "canonical.sqlite3"),
                {
                    "import_records": 0,
                    "nodes": 0,
                    "edges": 0,
                    "evidence": 0,
                },
            )

    def test_imported_place_is_retrievable_with_takeout_provenance(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            canonical_path = root / "canonical.sqlite3"
            session_directory = root / "session"
            self._import(TAKEOUT_FIXTURE, canonical_path)

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
                                "SELECT n.canonical_name, n.summary, "
                                "e.source_kind, e.source_ref, e.occurred_at "
                                "FROM nodes AS n JOIN evidence AS e "
                                "ON e.node_id = n.node_id "
                                "WHERE n.type = 'place' "
                                "AND n.canonical_name = 'Nishiki Market'"
                            )
                        },
                    },
                },
            )

            self.assertEqual(
                response["result"]["structuredContent"]["rows"],
                [
                    {
                        "canonical_name": "Nishiki Market",
                        "summary": (
                            "Saved Google Maps place at "
                            "2 Nakagyo Ward, Kyoto, Japan."
                        ),
                        "source_kind": "google_maps_takeout",
                        "source_ref": (
                            "https://www.google.com/maps/place/"
                            "?q=place_id:fixture-nishiki"
                        ),
                        "occurred_at": "2025-03-12T08:15:00Z",
                    }
                ],
            )

    def _import(self, takeout_path, canonical_path):
        result = subprocess.run(
            [
                sys.executable,
                str(IMPORT_TAKEOUT),
                "--takeout",
                str(takeout_path),
                "--canonical",
                str(canonical_path),
                "--world",
                "travel",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

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

    @staticmethod
    def _table_counts(canonical_path):
        with closing(sqlite3.connect(canonical_path)) as connection:
            return {
                table: connection.execute(
                    f"SELECT count(*) FROM {table}"
                ).fetchone()[0]
                for table in ("import_records", "nodes", "edges", "evidence")
            }


if __name__ == "__main__":
    unittest.main()
