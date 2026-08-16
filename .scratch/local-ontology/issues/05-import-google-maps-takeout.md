# 05 — Import one explicit Google Maps Takeout format

**What to build:** Let a user import one precisely documented Google Maps Takeout format into queryable place, trip, and event evidence while receiving a clear report for unsupported products or archive layouts.

**Blocked by:** 01 — Prove the policy-bounded SQL path end to end.

**Status:** ready-for-agent

- [ ] The importer supports one named Google Maps Timeline or Saved Places archive layout represented by a distributable fixture.
- [ ] Supported records produce normalized place, trip, or event candidates with stable source references and occurred-at dates.
- [ ] Re-importing the same archive is idempotent and preserves the distinction between raw source metadata and extracted claims.
- [ ] Missing optional fields and malformed records are reported without aborting valid records or silently inventing data.
- [ ] Unsupported Takeout products and paths are skipped with an explicit import report rather than being silently misparsed.
- [ ] An end-to-end test builds a capability database from the fixture and retrieves an allowed place or trip with provenance.
