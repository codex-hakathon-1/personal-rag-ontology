#!/usr/bin/env python3
"""Import one explicit Google Maps Takeout Saved Places GeoJSON layout."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import urlparse

from import_records import CandidateEntity, ImportRecord


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = PLUGIN_ROOT / "schema" / "canonical.sql"
IMPORT_RECORD_SCHEMA = PLUGIN_ROOT / "schema" / "import_records.sql"
SUPPORTED_PATH = Path("Takeout") / "Maps (your places)" / "Saved Places.json"
SOURCE_KIND = "google_maps_takeout"
FORMAT_NAME = "google_maps_saved_places_geojson_v1"
RFC_3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2})$"
)


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _identifier(kind: str, *parts: str) -> str:
    return f"{kind}-{_digest(*parts)[:32]}"


def _initialize_canonical(connection: sqlite3.Connection) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'worlds'"
    ).fetchone()
    if not exists:
        connection.executescript(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    connection.executescript(IMPORT_RECORD_SCHEMA.read_text(encoding="utf-8"))


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not RFC_3339_PATTERN.fullmatch(value):
        raise ValueError("properties.Published must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            "properties.Published must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise ValueError("properties.Published must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _google_maps_url(value: Any) -> str:
    url = _non_empty_string(value, "properties.Google Maps URL")
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.google.com"
        or not parsed.path.startswith("/maps/")
    ):
        raise ValueError(
            "properties.Google Maps URL must be an "
            "https://www.google.com/maps/ URL"
        )
    return url


def _record_from_feature(
    feature: Any,
    archive_path: str,
    record_index: int,
) -> tuple[ImportRecord, str, list[str]]:
    if not isinstance(feature, dict):
        raise ValueError("feature must be an object")
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("properties must be an object")
    location = properties.get("Location")
    if not isinstance(location, dict):
        raise ValueError("properties.Location must be an object")
    name = _non_empty_string(
        location.get("Business Name"),
        "properties.Location.Business Name",
    )
    source_ref = _google_maps_url(properties.get("Google Maps URL"))
    occurred_at = _timestamp(properties.get("Published"))
    missing_optional_fields = []
    address = location.get("Address")
    if not isinstance(address, str) or not address.strip():
        missing_optional_fields.append("properties.Location.Address")
        summary = "Saved Google Maps place."
    else:
        summary = f"Saved Google Maps place at {address.strip()}."
    return (
        ImportRecord(
            source_kind=SOURCE_KIND,
            source_ref=source_ref,
            occurred_at=occurred_at,
            raw_text_or_metadata=feature,
            candidate_entities=(CandidateEntity("place", name),),
            provenance={
                "archive_path": archive_path,
                "record_index": record_index,
            },
        ),
        summary,
        missing_optional_fields,
    )


def _upsert_record(
    connection: sqlite3.Connection,
    world_id: str,
    record: ImportRecord,
    summary: str,
) -> None:
    place = record.candidate_entities[0]
    node_id = _identifier("place", world_id, SOURCE_KIND, record.source_ref)
    record_id = _identifier("import-record", world_id, SOURCE_KIND, record.source_ref)
    evidence_id = _identifier("evidence", world_id, SOURCE_KIND, record.source_ref)
    connection.execute(
        """
        INSERT INTO nodes (
          node_id, world_id, type, canonical_name, summary, state,
          sensitivity, valid_from, valid_to, last_seen_at, superseded_by,
          created_at, updated_at
        ) VALUES (?, ?, 'place', ?, ?, 'active', 'normal', ?, NULL, ?, NULL, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
          canonical_name = excluded.canonical_name,
          summary = excluded.summary,
          valid_from = excluded.valid_from,
          last_seen_at = excluded.last_seen_at,
          updated_at = excluded.updated_at
        """,
        (
            node_id,
            world_id,
            place.canonical_name,
            summary,
            record.occurred_at,
            record.occurred_at,
            record.occurred_at,
            record.occurred_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO import_records (
          record_id, world_id, source_kind, source_ref, occurred_at,
          raw_text_or_metadata, candidate_entities, provenance, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(record_id) DO UPDATE SET
          occurred_at = excluded.occurred_at,
          raw_text_or_metadata = excluded.raw_text_or_metadata,
          candidate_entities = excluded.candidate_entities,
          provenance = excluded.provenance,
          content_hash = excluded.content_hash
        """,
        (
            record_id,
            world_id,
            SOURCE_KIND,
            record.source_ref,
            record.occurred_at,
            record.raw_metadata_json(),
            record.candidate_entities_json(),
            record.provenance_json(),
            record.content_hash(),
        ),
    )
    connection.execute(
        """
        INSERT INTO evidence (
          evidence_id, node_id, edge_id, source_kind, source_ref,
          occurred_at, observed_at, excerpt, content_hash
        ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_id) DO UPDATE SET
          node_id = excluded.node_id,
          source_ref = excluded.source_ref,
          occurred_at = excluded.occurred_at,
          observed_at = excluded.observed_at,
          excerpt = excluded.excerpt,
          content_hash = excluded.content_hash
        """,
        (
            evidence_id,
            node_id,
            SOURCE_KIND,
            record.source_ref,
            record.occurred_at,
            record.occurred_at,
            summary,
            record.content_hash(),
        ),
    )


def import_google_maps_takeout(
    takeout_path: Path,
    canonical_path: Path,
    world_id: str,
) -> dict[str, Any]:
    takeout_path = takeout_path.resolve()
    supported_file = takeout_path / SUPPORTED_PATH
    archive_path = SUPPORTED_PATH.as_posix()
    skipped_paths = []
    if takeout_path.is_dir():
        files = sorted(
            item for item in takeout_path.rglob("*") if item.is_file()
        )
        for path in files:
            relative_path = path.relative_to(takeout_path)
            if relative_path == SUPPORTED_PATH:
                continue
            relative_text = relative_path.as_posix()
            maps_prefix = "Takeout/Maps (your places)/"
            reason = (
                "unsupported_archive_path"
                if relative_text.startswith(maps_prefix)
                else "unsupported_takeout_product"
            )
            skipped_paths.append({"path": relative_text, "reason": reason})

    records: list[tuple[ImportRecord, str]] = []
    archive_errors = []
    malformed_records = []
    warnings = []
    imported_files = 0
    if supported_file.is_file():
        try:
            document = json.loads(supported_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            archive_errors.append({"path": archive_path, "reason": "invalid_json"})
        else:
            if (
                not isinstance(document, dict)
                or document.get("type") != "FeatureCollection"
            ):
                archive_errors.append(
                    {
                        "path": archive_path,
                        "reason": "expected_geojson_feature_collection",
                    }
                )
            elif not isinstance(document.get("features"), list):
                archive_errors.append(
                    {"path": archive_path, "reason": "features_must_be_array"}
                )
            else:
                imported_files = 1
                for index, feature in enumerate(document["features"]):
                    try:
                        record, summary, missing_optional_fields = (
                            _record_from_feature(feature, archive_path, index)
                        )
                    except ValueError as error:
                        malformed_records.append(
                            {
                                "path": archive_path,
                                "recordIndex": index,
                                "reason": str(error),
                            }
                        )
                        continue
                    records.append((record, summary))
                    if missing_optional_fields:
                        warnings.append(
                            {
                                "path": archive_path,
                                "recordIndex": index,
                                "missingOptionalFields": missing_optional_fields,
                            }
                        )
    elif takeout_path.exists():
        skipped_paths.append(
            {"path": archive_path, "reason": "supported_archive_path_not_found"}
        )
    else:
        raise FileNotFoundError(f"Takeout path does not exist: {takeout_path}")

    canonical_path = canonical_path.resolve()
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(canonical_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _initialize_canonical(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO worlds (world_id, name, description, enabled)
                VALUES (?, ?, 'Imported Google Maps Takeout saved places', 1)
                ON CONFLICT(world_id) DO NOTHING
                """,
                (world_id, world_id.replace("-", " ").title()),
            )
            for record, summary in records:
                _upsert_record(connection, world_id, record, summary)

    return {
        "archiveErrors": archive_errors,
        "archiveStatus": "supported" if imported_files else "unsupported",
        "format": FORMAT_NAME,
        "importedFiles": imported_files,
        "importedPlaces": len(records),
        "malformedRecords": malformed_records,
        "skippedPaths": skipped_paths,
        "warnings": warnings,
        "world": world_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--takeout", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--world", required=True)
    arguments = parser.parse_args()
    report = import_google_maps_takeout(
        arguments.takeout,
        arguments.canonical,
        arguments.world,
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
