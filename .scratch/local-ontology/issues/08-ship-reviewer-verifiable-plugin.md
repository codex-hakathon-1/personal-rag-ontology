# 08 — Ship a reviewer-verifiable plugin

**What to build:** Deliver a cleanly installable hackathon submission whose README and reproducible fixtures let a reviewer verify the policy boundary, direct SQL, provenance, and three local import paths without a live presentation.

**Blocked by:** 07 — Query the integrated graph with recursive SQL.

**Status:** ready-for-agent

- [ ] A clean checkout can install or validate the plugin, build the fixture graph, create a capability database, run the example query, and execute the automated test suite using documented commands.
- [ ] The README opens with the product thesis and explains the over-recall failure mode and capability-database boundary before presenting feature details.
- [ ] The README includes a concise happy-path recursive SQL example and an adversarial example proving that forbidden rows are physically absent.
- [ ] The README names the exact supported input layout for each importer, shows the fixture workflow, and clearly reports unsupported source coverage.
- [ ] Privacy claims are limited to enforced behavior and explicitly disclaim raw-source encryption, perfect sensitive-data detection, and protection against exfiltration of legitimately queried data.
- [ ] Runtime dependencies and platform assumptions are explicit, packaging contains no fixture-generated personal database, and all required security, policy, importer, lifecycle, and recursive-query tests pass.
