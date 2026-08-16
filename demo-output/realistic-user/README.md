# Checked-in realistic user demo output

This directory is a generated, versioned demonstration snapshot. It contains
only the fictional data documented in
`plugins/local-ontology/examples/realistic-user-demo/`.

- `canonical.sqlite3`: full synthetic canonical graph, including three policy
  boundary records.
- `capability.sqlite3`: model-facing `work` graph after policy materialization;
  all three boundary records are physically absent.
- `session.json`: session and policy manifest used by the query boundary.
- `query-audit-*.jsonl`: payload-free audit records for the two demo queries.
- `demo-result.json`: import reports and provenance-bearing query results for
  `챗봇 분석` and `내 기억 시스템`.

Regenerate the snapshot from the repository root:

```text
python plugins/local-ontology/scripts/build_realistic_demo.py --session-dir demo-output/realistic-user
```
