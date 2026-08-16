---
name: local-ontology
description: Query a local, policy-bounded SQLite memory graph only when personal historical context would help.
---

# Local Ontology

Use `query_memory` only when the user's request has a personal anchor and would benefit from
historical context. No query is a normal outcome.

At startup, rely only on the MCP server's operational contract, schema guidance, selected world,
and policy contract. Do not infer or enumerate facts before querying.

When querying:

1. Write one ordinary read-only `SELECT` or `WITH` query against `nodes`, `node_aliases`, `edges`,
   and `evidence`.
2. Select `source_kind`, `source_ref`, and `occurred_at` for any fact used in the answer.
3. Treat returned rows as dated evidence, cite provenance, and state uncertainty.
4. Do not attempt writes, PRAGMAs, ATTACH, extensions, transactions, or access to another database.

The capability database contains only the explicitly selected world's policy-approved records.
The query tool cannot switch, widen, merge, or enumerate worlds.
