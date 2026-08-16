# 03 — Import Chromium history with provenance

**What to build:** Let a user import Chromium-family browsing history into the local graph and query visited pages and topics with dates and source references, without modifying the live browser database or admitting sensitive URLs.

**Blocked by:** 01 — Prove the policy-bounded SQL path end to end.

**Status:** ready-for-agent

- [ ] A representative Chromium history fixture imports URL, title, visit time, host, and visit count into normalized records.
- [ ] Importing from a live-style locked database works through a temporary read-only copy and leaves the source database unchanged.
- [ ] Imported visits produce queryable web-page and topic candidates with stable source references, content hashes, and dated evidence.
- [ ] Re-importing the same history is idempotent and does not duplicate nodes, edges, or evidence.
- [ ] Configured sensitive URL patterns are excluded before graph construction and the import report identifies exclusions without exposing their sensitive values.
- [ ] An end-to-end test builds a capability database from the fixture and retrieves an allowed visited page with provenance.
