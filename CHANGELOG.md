# Changelog

## 2.3.2
- Dispatch: the pick follows the global rank map. Every task starts at the cheapest healthy local model with its needs and moves up the map, then to the paid ladder cheapest first. The kind and the tier set the filters and the effort, never the model.
- Dispatch: `--pin` gives pick, assign and lanes exactly the pinned model; `lanes --pin` adds the rungs above it. A paid discovery failure keeps fitting local rungs usable and drops the paid rungs with one warning.
- Docs: tests/test_docs.py rejects the three retired routing rules and fails loud when one comes back.
- Version fields are 2.3.2 in every manifest and skill.

## 2.3.1
- Dispatch: `--pin` resolves the provider from the id itself and obeys `--failed` and `--needs`; a malformed caller id exits non-zero, and an empty exact `features` entry wins over the family entry.
- Version fields are 2.3.1 in every manifest and skill.

## 2.3.0
- Dispatch: per-task routing fields (`pin_model`, `needs`) and multi-model recon in the manager brief.
- Manager: Sol is the permanent final reviewer; the tier-review ladder is dropped and a waiter-turn rule takes its place.
- Paid models run only through an explicit pin, after flatiron fails; they are never the default.
- Version fields are 2.3.0 in every manifest and skill.

## 2.2.2
- Routing: sync fallbacks stay in the quota-free pool (flatiron-only); unknown reasoning effort names warn and fall back instead of crashing.

## 2.2.1
- Routing: reasoning effort rounds down to the highest accepted level at or below the request; it never rises above it.

## 2.2.0
- The manager runs no commands; every manager command routes to a child, and waits go to the intern tier.
- `dag.py` defaults an untiered node to intern and escalates it to junior.
- `hermes-dispatch-route` defaults `pick` and `lanes` to the intern tier.
- `flatiron-routing.json`: prefer=cheapest tiers carry their lane model; `Qwen/Qwen3.8-27B-FP8` enters routes.code last, so the junior tier pins the cheapest code lane.
- Version fields are 2.2.0 in every manifest and skill.

## 2.1.0
- Install is agent-led: `INSTALL.md` detects the environment, asks one batched question round with detected defaults, shows the plan, waits for approval, acts, verifies and reports.
- The install links all six skills into OpenCode and Hermes. OpenCode keeps the link route even though its CLI has a `plugin` subcommand.
- No backups in the install. An occupied target stops the run and the report names the path.
- `install-opencode.sh` is gone; its missing sixth skill and missing `--help` go with it.
- Update and uninstall sections: `git pull` in the clone or the marketplace update; remove only links that resolve into the clone.
- Tests: `tests/test_docs.py` pins every install rule and fails when a rule is removed. `test/install.sh` walks the link steps in the container.
- Version fields are 2.1.0 in every manifest and skill.

## 2.0.0

- Round budget: one build, one review, at most one fix round, one re-check of the fixed findings only (rules T1-T6 in skill `manager`, SKILL.md). Then ship with documented limits or ask the user.
- Parallel fan-out starts every independent unit at once (rule P1). Quota-free children have no provider concurrency cap.
- Divide and conquer splits a unit until each leaf fits the cheapest tier that can pass its check (rule D1).
- The manager core is short and its references load on trigger. `AGENTS.md` and the rule copies carry only the core (fixes the 113 KB per-session load).
- `dag.py` adds `add` and `plan`, defaults a missing `tier` to `senior`, and reports every graph error at once.
- Tests: `test/test-dag.sh` covers the graph rules. `test/run.sh` runs it with the pi-extension tests and a generated-copy sync check.
- Script fixes in `tiered-subagent-dispatch`: the routing selftest, the lane assigner and the pin checks.
