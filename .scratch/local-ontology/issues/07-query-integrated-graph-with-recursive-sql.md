# 07 — Query the integrated graph with recursive SQL

**What to build:** Let the model anchor on an entity named by the user and traverse a combined, policy-approved graph from all three import sources with recursive SQL, returning dated evidence while treating no match and no query as correct outcomes.

**Blocked by:** 02 — Harden the SQL execution boundary; 03 — Import Chromium history with provenance; 04 — Import Codex logs as decisions and plans; 05 — Import one explicit Google Maps Takeout format; 06 — Materialize lifecycle state and world policy.

**Status:** ready-for-agent

- [ ] One reproducible fixture run imports all three supported source kinds and builds a selected-world capability database.
- [ ] Alias and canonical-name matching can anchor a recursive common-table expression that returns an allowed two-hop neighborhood without looping on graph cycles.
- [ ] Returned facts include node or edge context plus source kind, source reference, and relevant dates so an answer can cite provenance and uncertainty.
- [ ] An adversarial read-only query cannot recover a record from another world, an excluded state, or a denied sensitivity class because that record is absent.
- [ ] An unmatched personal anchor returns no personal data, and a request without a personal anchor can complete without invoking the query tool.
- [ ] The plugin's operational guidance explains the available schema and graph traversal contract without preloading graph contents.
