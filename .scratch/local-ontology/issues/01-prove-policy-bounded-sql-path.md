# 01 — Prove the policy-bounded SQL path end to end

**What to build:** Deliver the first runnable Local Ontology path: a user can install the minimal plugin, select a world, build a session capability database from a deterministic fixture, and use the query tool to retrieve an allowed fact with its provenance without receiving personal facts at startup.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The plugin package is accepted by the current Codex plugin validation or installation workflow and exposes the Local Ontology skill and query integration.
- [ ] Starting a fresh session exposes only the operational contract, schema guidance, selected world identifier, and policy contract; it exposes no fixture-derived personal facts, summaries, entity lists, or recency lists.
- [ ] A deterministic fixture can populate a canonical SQLite graph and build a fresh capability database for an explicitly selected world.
- [ ] The query tool accepts one ordinary read-only query and returns structured rows with source and date provenance plus truncation metadata.
- [ ] An end-to-end automated test proves that an allowed fixture fact is absent before querying and returned only after an explicit SQL query.
