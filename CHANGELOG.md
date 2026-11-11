# Changelog

## 2.3.5
- Rules: a web search or web fetch step runs on a Haiku child. The child writes verbatim excerpts with their URLs to a scratch file and does no analysis. A flatiron child reads that file and does the analysis.
- Dispatch: the `sync` ranker runs on the resolved Haiku id. It is the one documented exception to the web research split: one Haiku child both searches and ranks. With no live Haiku id the ranker does not run.
- Landing: after a PASS the run pushes the branch, makes its CI green, then fast-forwards the default branch to the branch tip. No pull request. The branch is deleted after the default-branch CI is green.
- Docs: `tests/test_docs.py` pins the ranker exception sentence in the Web research split bullet.
- Version fields are 2.3.5 in every manifest and skill.

## 2.3.4
- Dispatch: `tier_floor` and `paid_floor` set each tier's local floor and paid floor. A null local floor starts the ladder at the paid floor.
- Dispatch: when no healthy local model at or above the tier floor fits, the local rungs start at the strongest healthy local model below it.
- Dispatch: only the ledger verdict `failed` counts toward the drop. The verdicts missed-defects, blocked and interrupted never count.
- Dispatch: the router drops every rung stronger than the caller model. A pin above the cap and an exhausted capped ladder return blocked. Sol is exempt as a reviewer.
- Tiers: `super` is an Opus team and runs only after principal fails. `dag.py` escalates a failed principal node to super.
- Teams: principal and super run as teams of 3 children, marked by `team_size` in `lanes` and `assign`. The manager skill holds the dispatch rule.
- Health: when the 60 s probe sees the served list change, the router ranks the new ids at once. `lanes` and `assign` gain `--refresh`.
- Dispatch: the ledger drop reads the last 3 counted rows of one kind, not a lifetime count. A later success clears the drop.
- Dispatch: auto-sync diagnostics go to stderr; the stdout of `pick`, `lanes` and `assign` holds only the JSON result.
- Dispatch: discovery and auto-sync run before the ladder reads the routing config, so one dispatch sees a newly ranked model.
- Health: a new model joins the rank map only after its features probe succeeds. A failed probe leaves it out and retries next cycle; the selftest rejects a rank with no features entry.
- Dispatch: the caller cap compares paid families in the one strength order Qwen < GLM < MiMo < Kimi-K3 < Haiku < Sonnet < Opus, never in the enabled `paid_ladder` order.
- Tiers: principal carries skills brainstorm, agent-comms, team and manager. The SKILL.md and routing-mechanics.md tables and the built-in defaults match the data.
- Documented limits: core `ROUTE_KEYS` drops the plugin's `team_size` route key. Team dispatch is a manager rule driven by router `lanes` and `assign` output, so `team_size` there is what matters.
- Version fields are 2.3.4 in every manifest and skill.

## 2.3.3
- Dispatch: a pin overrides the local tier floor. `lanes --pin MODEL` and the plugin `pin_model` chain continue at every healthy fitting local rung above MODEL, then the paid rungs from the tier's paid floor; a paid pin continues at the paid rungs after MODEL in `paid_ladder` order. `pick --pin` and `assign --pin` stay exactly MODEL.
- Dispatch: the tier floor is `tier_floor[TIER]` first (its model must rank), then the legacy `tiers[TIER].min_rank`, then the intern floor; a missing or unknown tier takes the intern floor directly.

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
