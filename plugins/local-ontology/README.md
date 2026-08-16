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
  --session-dir .local-ontology-session
```

Set `LOCAL_ONTOLOGY_SESSION` to the emitted `sessionPath` before starting the bundled MCP server.
The server reads the canonical graph, applies the fixed world policy, and builds its private
in-memory capability database. Its initialization instructions contain only the operational
contract, schema guidance, selected world identifier, and policy contract. Fixture facts enter
model context only after an explicit `query_memory` SQL call.

## Test and validate

```powershell
python -m unittest discover -s plugins/local-ontology/tests -v
python C:/Users/<you>/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py `
  plugins/local-ontology
```

The implementation uses only Python's standard library and SQLite.
