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
