---
name: local-ontology
description: Query a local, policy-bounded SQLite memory graph only when personal historical context would help.
---

# Local Ontology

Use `query_memory` only when the user's request has a personal anchor and would benefit from
historical context. No query is a normal outcome. An unmatched anchor must return no personal
data.

At startup, rely only on the MCP server's operational contract, schema guidance, selected world,
and policy contract. Do not infer or enumerate facts before querying.

When querying:

1. Anchor case-insensitively on `nodes.canonical_name` or `node_aliases.alias`.
2. Traverse `edges` with a recursive CTE for at most two hops. Carry a delimiter-wrapped node
   path (for example, `|node-id|`) and reject a destination already in that path as a cycle guard.
3. Join `evidence` through `node_id` or `edge_id`. Select node or edge context plus `source_kind`,
   `source_ref`, and `occurred_at` for every fact used in the answer.
4. Treat returned rows as dated evidence, cite provenance, and state uncertainty.
5. Do not attempt writes, PRAGMAs, ATTACH, extensions, transactions, or access to another database.

The capability database contains only the explicitly selected world's policy-approved records.
The query tool cannot switch, widen, merge, or enumerate worlds.
