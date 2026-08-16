# 04 — Import Codex logs as decisions and plans

**What to build:** Let a user import Markdown Codex conversations as queryable conversations, decisions, plans, and evidence while conservatively redacting secrets and distinguishing explicit replacement statements from mere recency.

**Blocked by:** 01 — Prove the policy-bounded SQL path end to end.

**Status:** ready-for-agent

- [ ] Representative Markdown log fixtures produce normalized conversation, decision, plan, topic, and evidence records with stable provenance.
- [ ] Token-like values, key-like values, and configured secret paths are redacted before persistence and never appear in queryable excerpts.
- [ ] A direct statement that one decision or plan replaces another emits high-confidence supersession evidence.
- [ ] A newer statement without explicit replacement language does not mark an older fact as superseded.
- [ ] Re-importing unchanged logs is idempotent and changed content is distinguishable by its content hash.
- [ ] An end-to-end test retrieves an allowed decision or plan with its conversation source and date.
