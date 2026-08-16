# Local Ontology

A local, policy-bounded memory graph that Codex queries with SQL only when context is needed.

This first runnable slice builds a canonical SQLite graph from a deterministic fixture. At MCP
session startup, it materializes a fresh in-memory capability database containing only records
allowed for the explicitly selected world. The query tool connects only to that database.

## Install the plugin

The repo includes a local marketplace entry. Validate the package with the current Codex
ingestion schema, or add this repository as a marketplace and install the plugin:

```powershell
codex plugin marketplace add .
codex plugin add local-ontology@personal
```

Restart Codex after installation. The bundled MCP server requires Python 3.11 or newer available
as `python` on `PATH`.

## Build a fixture session

From the repository root:

```powershell
python plugins/local-ontology/scripts/build_session.py `
  --fixture plugins/local-ontology/examples/demo-fixture/graph.json `
  --policy plugins/local-ontology/examples/policy.example.json `
  --world travel `
  --session-dir .local-ontology-session `
  --max-rows 100 `
  --max-execution-ms 1000
```

Set `LOCAL_ONTOLOGY_SESSION` to the emitted `sessionPath` before starting the bundled MCP server.
The server reads the canonical graph, applies the fixed world policy, and builds its private
in-memory capability database. Its initialization instructions contain only the operational
contract, schema guidance, selected world identifier, and policy contract. Fixture facts enter
model context only after an explicit `query_memory` SQL call.

## Build the integrated three-source fixture

One command imports the distributable Chromium, Codex Markdown, and Google Maps Takeout fixtures
into the `travel` world and writes a selected-world session:

```powershell
python plugins/local-ontology/scripts/build_integrated_fixture.py `
  --session-dir .local-ontology-integrated-session
```

The run prints its importer reports and `sessionPath` as JSON. The fixture's explicit
`graph-overlay.json` adds one alias and a small, cyclic set of cross-source edges so recursive SQL
can exercise canonical-name matching, alias matching, a two-hop bound, and a path-based cycle
guard. The overlay also adds wrong-world, dormant, and secret markers to the canonical database;
the integrated policy physically omits those markers from the capability database. Overlay-only
links use `fixture_graph` provenance so they cannot be mistaken for claims extracted from the
three supported source formats.

## Import Chromium history

Close the browser if its operating-system file permissions prevent copying its `History` file.
The importer never opens the source database with a SQLite connection: it copies the `History`
file and any live WAL companion into a temporary directory, opens only that copy in read-only
mode, and removes the copy afterward.

Configure URL exclusions as named regular expressions. Reports contain only each safe pattern
name and its match count; excluded URL and title values are not written to the graph or report.
See `examples/chromium-sensitive-patterns.json` for the format.

```powershell
python plugins/local-ontology/scripts/import_browser_history.py `
  --history "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\History" `
  --canonical .local-ontology\canonical.sqlite3 `
  --world travel `
  --sensitive-patterns `
    plugins/local-ontology/examples/chromium-sensitive-patterns.json

python plugins/local-ontology/scripts/build_session.py `
  --canonical .local-ontology\canonical.sqlite3 `
  --policy plugins/local-ontology/examples/chromium-policy.example.json `
  --world travel `
  --session-dir .local-ontology-session
```

Chromium `urls` and `visits` rows become aggregate `browser_history_records`, per-visit normalized
`import_records`, `web_page` and host-derived `topic` nodes, `about` edges, and dated evidence.
URLs remain source references; content bodies are not captured. Stable identifiers and content
hashes make unchanged re-imports idempotent. The supported fixture schema is documented by
`examples/chromium-history-fixture.sql`.

## Import Codex Markdown logs

Codex logs use UTF-8 Markdown with `title`, `date`, and optional `topics` frontmatter. The
deterministic MVP extractor recognizes `## User` and `## Assistant` message headings plus
`Decision:`, `Plan:`, and `Topic:` lines. Explicit forms such as `This replaces ...`,
`This decision replaces "..."`, and `Decision: New choice replaces "Old choice"` emit a
`supersedes` edge with `0.99` confidence and mark only the named older node as superseded. A newer
claim without that explicit language remains active. User and Assistant message bodies are also
retained as normalized, redacted conversation evidence.

```powershell
python plugins/local-ontology/scripts/import_codex_logs.py `
  --logs plugins/local-ontology/examples/codex-logs `
  --canonical .local-ontology\canonical.sqlite3 `
  --world personal `
  --secret-paths plugins/local-ontology/examples/codex-secret-paths.example.json

python plugins/local-ontology/scripts/build_session.py `
  --canonical .local-ontology\canonical.sqlite3 `
  --policy plugins/local-ontology/examples/policy.example.json `
  --world personal `
  --session-dir .local-ontology-session
```

The redaction pass runs before parsing or persistence. It replaces common token forms, values
assigned to key/token/secret/password-like names, and exact paths listed in the optional
`secret_paths` JSON file. This is conservative pattern matching, not a guarantee that every
possible secret will be recognized. Stored evidence uses stable `codex://<relative-path>#L<n>`
references and dated content hashes; re-importing a changed source reconciles its old graph rows
instead of duplicating them.

## Import Google Maps Takeout Saved Places

The Google Maps importer intentionally supports one legacy Takeout layout only:

```text
<extracted-archive-root>/
└── Takeout/
    └── Maps (your places)/
        └── Saved Places.json
```

`Saved Places.json` must be a GeoJSON `FeatureCollection`. Each member must be a GeoJSON `Feature`
with Point or null geometry and requires `properties.Location.Business Name`, an
`https://www.google.com/maps/` URL in `properties.Google Maps URL`, and an RFC 3339
`properties.Published` timestamp. `properties.Location.Address` is optional. The distributable
fixture at
`examples/google-maps-takeout-fixture` is the exact supported contract. Google now documents
saved-list exports under the separate **Saved** Takeout product, so exports with a different
product name, CSV files, zip files, Timeline data, reviews, and other Maps layouts are not accepted
as this format. See Google's current
[saved-list export instructions](https://support.google.com/maps/answer/7280933) and
[general Takeout instructions](https://support.google.com/accounts/answer/3024190).

Pass the extracted archive root, not the `Takeout` directory or the original zip file:

```powershell
python plugins/local-ontology/scripts/import_google_maps_takeout.py `
  --takeout plugins/local-ontology/examples/google-maps-takeout-fixture `
  --canonical .local-ontology\canonical.sqlite3 `
  --world travel

python plugins/local-ontology/scripts/build_session.py `
  --canonical .local-ontology\canonical.sqlite3 `
  --policy plugins/local-ontology/examples/google-maps-policy.example.json `
  --world travel `
  --session-dir .local-ontology-session
```

Valid features become normalized `import_records`, `place` candidates, nodes, and dated evidence.
The full source feature remains in `raw_text_or_metadata`; extracted place claims remain separate
in `candidate_entities` and the graph. The Google Maps URL is the stable `source_ref`, and
`Published` becomes `occurred_at`. Re-imports update the same stable rows without duplicating them.
They do not treat an archive as a complete snapshot or delete prior records that are absent or
malformed in a later import.

The JSON report counts imported files and places. It reports each malformed feature by safe path,
record index, and reason; reports missing optional addresses as warnings; and classifies every
other file as `unsupported_archive_path` or `unsupported_takeout_product`. A directory without the
exact supported path returns `supported_archive_path_not_found` and imports nothing. Reports do
not include the contents of skipped or malformed records. Invalid JSON and unsupported top-level
GeoJSON shapes return `archiveErrors` in the report rather than being parsed as records.

## Rebuild lifecycle state and apply world policy

Lifecycle state is materialized in the canonical graph before a session reads it. Run the rebuild
with an explicit clock so the same graph, rules, and `--as-of` value always produce the same result:

```powershell
python plugins/local-ontology/scripts/rebuild_state.py `
  --canonical .local-ontology\canonical.sqlite3 `
  --rules plugins/local-ontology/examples/state-rules.example.json `
  --as-of 2026-08-16T00:00:00Z
```

`dormant_after_days` maps node types to inactivity thresholds measured from `last_seen_at`. The
rebuild moves configured non-superseded types between `active` and `dormant`. It materializes
`superseded` only when an active `supersedes` edge has stored evidence, choosing the newest explicit
replacement deterministically when more than one exists. A newer fact without that evidence never
replaces an older fact. Re-running unchanged input makes no further changes.

`build_session.py` requires one configured `--world`; the SQL tool has no world-selection input and
the capability schema has no `worlds` table. At MCP startup the capability builder copies only nodes
in that world which have an included evidence source, included state, allowed type, and sensitivity
outside `deny_sensitivity`. It then copies aliases from included sources, edges whose endpoints
remain and whose evidence includes an allowed source, and only the surviving evidence. Denied,
unevidenced, and other-world records are physically absent. Missing `include_sources` or
`allow_node_types` keys are unrestricted; an explicitly empty allowlist includes nothing.

## SQL safety boundary

The query harness accepts one `SELECT` or `WITH` statement, including recursive CTEs, against
the in-memory capability database. A SQLite authorizer rejects writes, schema changes,
transactions, database attachment, PRAGMAs, extension and file functions, temporary objects,
system objects, and reads from any attached database. A progress handler interrupts queries
that exceed `--max-execution-ms`, and the query runs in an isolated worker process that is
terminated at the same deadline; `--max-rows` bounds returned rows and the response reports
whether it was truncated.

Each session writes `query-audit-<session-id>.jsonl` beside `session.json`. Every successful or
rejected query attempt records a SHA-256 SQL fingerprint, elapsed milliseconds, returned row
count, truncation state, outcome, session identifier, and world identifier. The audit log stores
neither raw SQL nor result rows.

## Test and validate

```powershell
python -m unittest discover -s plugins/local-ontology/tests -v
python C:/Users/<you>/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py `
  plugins/local-ontology
```

The implementation uses only Python's standard library and SQLite.
