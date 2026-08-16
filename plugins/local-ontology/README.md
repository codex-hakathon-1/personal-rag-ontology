# Local Ontology

**Personal memory that an LLM must earn with SQL—and cannot over-recall.**

Most personal-memory systems optimize for recall: retrieve similar text and inject it before the
model has established that it is relevant, current, or appropriate to the user's present role.
That over-recall failure mode can leak stale, superseded, sensitive, or wrong-world context into an
otherwise unrelated conversation.

Local Ontology optimizes for exclusion before recall. Imports build a canonical local SQLite graph,
but Codex never queries that graph. A session builder applies one explicit world policy and creates a
separate capability database containing only permitted rows. The model starts with schema and policy
instructions—not personal facts—and can issue ordinary read-only SQL only when a personal anchor
makes historical context useful.

```text
Chromium History ─┐
Codex Markdown ───┼─> canonical.sqlite3 ─> world policy ─> capability DB ─> read-only SQL
Maps Takeout ─────┘       never exposed          physical omission        model-facing
```

The falsifiable claim is simple: **policy changes the database the model can query, not merely the
instructions it is given.** A join, subquery, or recursive CTE cannot recover a row that is not in
the capability database.

## Five-minute reviewer proof

### Requirements and platform assumptions

- Python 3.11 or newer, including its standard-library `sqlite3` module with SQLite connection
  serialization support.
- No third-party Python packages, network service, API key, account, or external database.
- Windows, macOS, or Linux with a `python` executable on `PATH`. If the platform exposes only
  `python3`, use it for the fixture/test commands and change `.mcp.json`'s command before installing.
- Codex CLI is needed only to install the plugin. The fixture proof and tests run without Codex.
- Commands below are single-line and shell-neutral; PowerShell, Command Prompt, bash, and zsh can
  run them from the repository root.

From a clean checkout, validate the bundled marketplace by installing it with the current Codex CLI:

```text
codex plugin marketplace add .
codex plugin add local-ontology@personal
```

Restart the ChatGPT desktop app or start a new Codex CLI session so the installed skill and MCP tool
are discovered. The repository follows the current [OpenAI plugin package layout](https://developers.openai.com/plugins/build/plugins)
with `.codex-plugin/plugin.json`, `skills/`, and `.mcp.json` at the plugin root.

If the bundled `plugin-creator` system skill is installed, its ingestion-schema validator provides a
non-installing package check (replace `<you>` with the local user name):

```text
python C:/Users/<you>/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/local-ontology
```

Now build the graph, materialize the `travel` capability database, run the happy-path recursive SQL,
and run the adversarial SQL—all through one reproducible command:

```text
python plugins/local-ontology/scripts/review_fixture.py --session-dir .local-ontology-review
```

The JSON output proves all of the following without a live presentation:

- `importedSourceKinds` contains `browser_history`, `codex_logs`, and `google_maps_takeout`;
- `happyPath.rows` traverses from the alias `Kyoto market` to a two-hop neighborhood and gives every
  row a `source_kind`, `source_ref`, and `occurred_at`;
- `forbiddenInCanonical` is `3`, showing that the adversarial fixtures really were imported; and
- `adversarial.rows` is `[]`, showing that the model-facing database physically lacks them.

Finish by running the complete security, policy, importer, lifecycle, and recursive-query suite:

```text
python -m unittest discover -s plugins/local-ontology/tests -v
```

The generated `.local-ontology-review/` directory contains a canonical database, capability
database, session manifest, and payload-free query audit log. It is local runtime state, not part of
the plugin package. Delete it after review if it is no longer needed.

## Realistic synthetic user demo

For a richer presentation scenario, the repository also includes a privacy-safe fictional Korean
knowledge worker whose activity themes were generalized from owner-supplied local notes and AI
assistant logs. The source fixture contains browser visits, four Codex conversations, and three
fictional saved places; no raw conversation, real person name, private location, credential, or
absolute local path is copied into it.

```text
python plugins/local-ontology/scripts/build_realistic_demo.py --session-dir demo-output/realistic-user
```

The command materializes the `work` capability database and prints import counts, policy-boundary
counts, and provenance-bearing two-hop results for the aliases `챗봇 분석` and `내 기억 시스템`.
See [`examples/realistic-user-demo/README.md`](examples/realistic-user-demo/README.md) for the
fictional persona, source shapes, privacy transformations, and two additional presentation anchors.

## Happy path: direct recursive SQL

`review_fixture.py` submits this ordinary SQL to the same `query_memory` MCP boundary used by the
plugin. It anchors on a fixture alias, follows active edges for at most two hops, guards cycles with a
delimiter-wrapped path, and returns dated source provenance:

```sql
WITH RECURSIVE neighborhood(node_id, depth, path) AS (
  SELECT DISTINCT n.node_id, 0, '|' || n.node_id || '|'
  FROM nodes AS n
  LEFT JOIN node_aliases AS a ON a.node_id = n.node_id
  WHERE lower(n.canonical_name) = lower('Kyoto market')
     OR lower(a.alias) = lower('Kyoto market')
  UNION ALL
  SELECT e.to_node_id, neighborhood.depth + 1,
         neighborhood.path || e.to_node_id || '|'
  FROM neighborhood
  JOIN edges AS e ON e.from_node_id = neighborhood.node_id
  WHERE neighborhood.depth < 2
    AND e.state = 'active'
    AND instr(neighborhood.path, '|' || e.to_node_id || '|') = 0
)
SELECT neighborhood.depth, n.canonical_name,
       v.source_kind, v.source_ref, v.occurred_at
FROM neighborhood
JOIN nodes AS n ON n.node_id = neighborhood.node_id
JOIN evidence AS v ON v.evidence_id = (
  SELECT candidate.evidence_id FROM evidence AS candidate
  WHERE candidate.node_id = n.node_id
  ORDER BY candidate.occurred_at DESC, candidate.evidence_id LIMIT 1
)
ORDER BY neighborhood.depth, n.canonical_name;
```

The fixture result starts at `Nishiki Market`, reaches `Kyoto`, then reaches the browser-derived
`Kyoto itinerary` and Codex-log-derived `Kyoto research review`. Those rows demonstrate graph
traversal and provenance, not preloaded memory: the names enter model context only in the SQL result.

## Adversarial proof: forbidden means absent

The integrated fixture deliberately puts three markers in the canonical graph: one in another
world, one dormant, and one with denied `secret` sensitivity. The review command confirms those
three rows exist in the canonical database, then sends this query to `query_memory`:

```sql
SELECT n.canonical_name, n.world_id, n.state, n.sensitivity, v.source_ref
FROM nodes AS n
LEFT JOIN evidence AS v ON v.node_id = n.node_id
WHERE n.canonical_name LIKE 'Forbidden fixture:%'
   OR v.source_ref LIKE 'fixture://integrated/forbidden/%';
```

Expected model-facing result:

```json
{"rows": [], "rowCount": 0, "truncated": false, "maxRows": 100}
```

This is not a prompt-obedience demo. The capability builder omits denied nodes first, then aliases,
edges, and evidence that no longer have permitted owners or endpoints. The capability schema has no
`worlds` table, the query tool takes no world parameter, and the supplied connection cannot attach or
read the canonical database.

## Exactly supported import layouts

The MVP intentionally implements narrow, reproducible contracts. Anything outside this table is
unsupported; it should not be mistaken for broad browser, Codex export, or Google Takeout coverage.

| Importer | Exact accepted input | Included fixture | Explicitly unsupported |
| --- | --- | --- | --- |
| Chromium | One Chromium-family `History` SQLite file with `urls(id, url, title, visit_count, last_visit_time)` and `visits(id, url, visit_time)` tables; an adjacent live `History-wal` is copied when present. | `examples/chromium-history-fixture.sql` creates the exact schema. | Firefox/Safari databases, browser JSON/CSV exports, cookies, bookmarks, content bodies, and Chromium schema variants missing those columns. |
| Codex logs | One UTF-8 `.md`/`.markdown` file or a directory tree of them. Each file requires an ISO 8601 `date` or `created_at` frontmatter value; `title` (defaults to the filename) and `topics` are optional. The parser recognizes `## User`/`## Assistant` headings and `Decision:`, `Plan:`, or `Topic:` lines. | `examples/codex-logs/` and `examples/integrated-fixture/codex-logs/`. | JSON/JSONL transcripts, binary exports, Markdown without a frontmatter date, and general semantic extraction beyond the documented deterministic forms. Other file extensions are not inputs. |
| Google Maps | An extracted archive root containing exactly `Takeout/Maps (your places)/Saved Places.json`, where the file is a GeoJSON `FeatureCollection` of `Feature` records with the documented Location, Google Maps URL, and Published fields. | `examples/google-maps-takeout-fixture/`. | Zip files, Timeline, Reviews, Saved CSV, the newer separate `Saved` product layout, and every other Takeout product/path. The importer reports skipped products/paths and malformed records without copying their content into the report. |

### Import your own Chromium History

The importer copies the source and any live WAL companion to a temporary directory before opening
SQLite, then removes the copy. It does not modify the browser database. Close the browser only if
operating-system permissions prevent the initial file copy.

```text
python plugins/local-ontology/scripts/import_browser_history.py --history "C:/path/to/Profile/History" --canonical .local-ontology/canonical.sqlite3 --world travel --sensitive-patterns plugins/local-ontology/examples/chromium-sensitive-patterns.json
```

Named regular expressions exclude matching URL/title values before graph construction. Reports
contain only each safe pattern name and match count. URLs remain provenance references; page bodies
are not captured. Stable identifiers and hashes make unchanged re-imports idempotent.

### Import your own Codex Markdown logs

```text
python plugins/local-ontology/scripts/import_codex_logs.py --logs C:/path/to/markdown-logs --canonical .local-ontology/canonical.sqlite3 --world personal --secret-paths plugins/local-ontology/examples/codex-secret-paths.example.json
```

Redaction runs before parsing or persistence. It replaces documented token/key-like forms and exact
configured paths. Explicit replacement forms produce high-confidence supersession evidence; mere
recency does not. Evidence uses stable `codex://<relative-path>#L<n>` references and content hashes.

### Import the supported Google Maps Takeout layout

Pass the extracted archive root—not `Takeout/` and not the original zip:

```text
<archive-root>/
└── Takeout/
    └── Maps (your places)/
        └── Saved Places.json
```

```text
python plugins/local-ontology/scripts/import_google_maps_takeout.py --takeout C:/path/to/archive-root --canonical .local-ontology/canonical.sqlite3 --world travel
```

Each accepted GeoJSON `Feature` requires `properties.Location.Business Name`, an
`https://www.google.com/maps/` URL in `properties.Google Maps URL`, and an RFC 3339
`properties.Published`; a Point or null geometry is accepted and Address is optional. Reports name
safe paths, record indexes, and reasons for malformed/unsupported data without echoing record
contents.

## Lifecycle and policy materialization

Lifecycle state is written to the canonical graph before session construction. Given a fixed
`--as-of`, the rebuild deterministically marks stale configured types dormant and marks a fact
superseded only when an evidenced `supersedes` edge explicitly names it:

```text
python plugins/local-ontology/scripts/rebuild_state.py --canonical .local-ontology/canonical.sqlite3 --rules plugins/local-ontology/examples/state-rules.example.json --as-of 2026-08-16T00:00:00Z
```

`build_session.py` then requires one `--world` and applies `include_sources`, `include_states`,
`allow_node_types`, and `deny_sensitivity`. Missing source/type allowlists are unrestricted; an
explicitly empty allowlist includes nothing. Unchanged input produces deterministic state and
capability contents.

## SQL and audit boundary

The harness accepts one `SELECT` or `WITH` statement, including recursive CTEs. A SQLite authorizer
rejects writes, schema changes, transactions, `ATTACH`/`DETACH`, PRAGMAs, extension/file functions,
temporary/system objects, and reads from attached databases. Row and wall-clock limits are enforced
in an isolated worker process.

Every attempt appends a JSONL audit record containing a SHA-256 SQL fingerprint, elapsed time, row
count, truncation/outcome, session identifier, and world identifier. The audit contains neither raw
SQL nor result payloads.

## Privacy model and limitations

The implementation enforces these claims:

- import, graph construction, session materialization, and querying run locally by default;
- the supplied model-facing tool receives only the selected capability database, never the canonical
  database;
- other-world, excluded-state/type/source, and denied-sensitivity rows are physically absent;
- the supplied SQL path is read-only and resource-bounded; and
- queryable facts retain source/date provenance.

It does **not** claim any of the following:

- Raw source files, canonical databases, capability databases, session manifests, and audit logs are
  **not encrypted by this plugin**. Filesystem/device encryption and access control are the user's
  responsibility.
- Regex and configured-path redaction is **not perfect sensitive-data or secret detection**. Review
  source data and exclusion patterns before importing it.
- The boundary does **not prevent a model, prompt injection, user, or downstream process from
  exfiltrating or mishandling data that policy legitimately allowed the SQL query to return**.
- Local processing is not a claim about the behavior of the surrounding Codex host, model service,
  backups, sync software, or operating system.

Generated `*.db`, `*.sqlite`, `*.sqlite3`, session directories, and query-audit logs are ignored by
the plugin package, and the automated distribution test rejects any database file present in the
shipped plugin tree.

## Deliberate limits and roadmap

This MVP has no embeddings, similarity ranking, GUI, cloud sync, automatic world switching, or
autonomous actions. Entity extraction is deterministic and narrow; importer coverage is exactly the
table above. A future optional Screenpipe adapter could add continuous-capture records, but
Screenpipe is neither included nor required and would have to pass the same pre-query policy
materialization boundary.
