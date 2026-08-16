# 06 — Materialize lifecycle state and world policy

**What to build:** Let a user rebuild graph state and create a session database whose physical contents reflect the selected world's source, node-type, state, and sensitivity policy, including dormant and explicitly superseded memories.

**Blocked by:** 04 — Import Codex logs as decisions and plans.

**Status:** ready-for-agent

- [ ] A deterministic batch rebuild changes a stale plan from active to dormant according to configured age rules.
- [ ] Explicit replacement evidence changes the replaced fact to superseded, links it to its replacement, and does not treat ordinary recency as replacement.
- [ ] World policy can include sources and states and can restrict node types and denied sensitivity classes.
- [ ] Building a session capability database physically omits records from other worlds and every record denied by the selected policy, including connected edges and evidence.
- [ ] The selected world is explicit; the query surface cannot switch, widen, merge, or enumerate worlds.
- [ ] Rebuilding state and rebuilding a capability database from unchanged input produce deterministic results.
