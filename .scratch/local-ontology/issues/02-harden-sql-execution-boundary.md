# 02 — Harden the SQL execution boundary

**What to build:** Let the model use expressive read-only SQLite while making prohibited database capabilities fail predictably, bounding resource use, and recording a payload-free audit trail for every attempted query.

**Blocked by:** 01 — Prove the policy-bounded SQL path end to end.

**Status:** ready-for-agent

- [ ] Ordinary read-only queries and common-table expressions run successfully against the session capability database.
- [ ] Every mutation and schema-change class is rejected, including insert, update, delete, replace, create, alter, drop, and vacuum operations.
- [ ] Attach, detach, pragma, extension loading, transaction control, multiple statements, and access to prohibited temporary or system objects are rejected by automated bypass tests.
- [ ] Query execution enforces configured time and row limits and reports whether a result was truncated.
- [ ] Each attempt records a SQL fingerprint, execution time, row count, session identifier, and world identifier without retaining the full result payload.
- [ ] The supplied query path cannot open or query the canonical database.
