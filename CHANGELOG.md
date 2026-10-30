# Changelog

## 2.0.0

- Round budget: one build, one review, at most one fix round, one re-check of the fixed findings only (rules T1-T6 in skill `manager`, SKILL.md). Then ship with documented limits or ask the user.
- Parallel fan-out starts every independent unit at once (rule P1). Quota-free children have no provider concurrency cap.
- Divide and conquer splits a unit until each leaf fits the cheapest tier that can pass its check (rule D1).
- The manager core is short and its references load on trigger. `AGENTS.md` and the rule copies carry only the core (fixes the 113 KB per-session load).
- `dag.py` adds `add` and `plan`, defaults a missing `tier` to `senior`, and reports every graph error at once.
- Tests: `test/test-dag.sh` covers the graph rules. `test/run.sh` runs it with the pi-extension tests and a generated-copy sync check.
- Script fixes in `tiered-subagent-dispatch`: the routing selftest, the lane assigner and the pin checks.
