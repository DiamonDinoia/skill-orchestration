# Routing mechanics

Detail behind the tier and ladder rules in SKILL.md. Load before changing `references/flatiron-routing.json`, the router or a tier table, or before debugging a `pick` result. The routing facts here match `scripts/hermes-dispatch-route`. When prose and code disagree, fix the prose.

## Commands

`scripts/hermes-dispatch-route` is the router. Its commands:

- `status [--refresh]` prints flatiron health and the resolved latest Claude and OpenAI ids.
- `pick KIND [--tier TIER] [--failed MODEL,...] [--needs FEATURE,...] [--refresh] [--pin MODEL]` returns `{provider, model, reason, flags, skipped}`.
- `lanes KIND [--tier TIER] [--needs FEATURE,...] [--failed MODEL,...] [--pin MODEL]` returns one JSON line with every eligible flatiron lane.
- `assign NODE=KIND:TIER[:NEED,NEED] ...` returns one JSON entry per node.
- `latest opus|sonnet|sol|haiku` returns the bare model id of a family and resolves any context variant.
- `models [--refresh]` lists every gateway model with health, rank hint, kinds and new flags.
- `sync [--refresh]` writes discovered ids into the Hermes config.

KIND is code, debug, frontend, research, prose, mechanical or vision. TIER is intern, junior, senior, principal or super. A flatiron `pick` takes `--reasoning EFFORT`, clamped to the accepted values below. `-s SKILL` adds one tier skill to the flags of every pick. `--needs FEATURE` keeps only a model whose `features` entry has every named feature true. A model with no entry has no capabilities, and `pick vision` means `--needs vision`.

## Effort clamp

Each `reasoning_effort` a tier names is at most `high`. The top-level `efforts` map of `references/flatiron-routing.json` holds the accepted values per model. `sync` writes an entry from the gateway's rejection text. `pick` and `assign` clamp to the entry: a refused value becomes the highest accepted value at or below it; when none is at or below, the lowest accepted value and a warning naming the model. A lane-launcher brief repeats the accepted values of the models it may get and makes the launcher name every value it replaced. A replaced value means the `efforts` map misses that model: write the entry after the run. The reasoning effort applies only when the child runs on flatiron. A refusal line in a child's log means the manager reroutes the deliverable. Kimi-K3 accepts `low`, `high` and `max`. Qwen accepts `xhigh`, `medium` and `low`. Mistral accepts `none` and `high`.

## Gateway model set

The model set comes from the gateway, not from a list.

- A routing child runs `hermes-dispatch-route models [--refresh]`. It returns the model list with health, rank hint and the `features` columns.
- `sync` probes a new model for vision with 4 quadrant questions on two random 2x2 colour grids. Vision true needs 4 right answers of 4. False needs 2 clear wrong answers and no inconclusive reply. A refusal that names a colour is not an answer. A failed, empty, truncated or refused probe keeps the old entry. `sync` re-probes an entry older than 7 days. `sync` never probes web on flatiron.
- Web is false for every flatiron model. The provider rule sets it and `sync` never probes it. The Claude rungs and the sol model have web true.
- The 6-hourly `sync` ranker places a new or returning model in the `routes` lists. Placement obeys the anchor floor of the kind. Ranks are relative, so a new model renumbers the whole set and the ranker re-ranks the list.
- A model the gateway lists no more drops out of the rank map after 7 days. The drop also removes it from every `routes` list.
- After 3 rejected ranker attempts for one unranked set, `sync` stops calling the ranker until the set changes. Hand-rank from the reason in the sync log then. Each ranker run costs paid quota. The ranker-rejects state, the lock and the dated backups live in `~/.hermes/cache/dispatch-route/`.
- Known limit: no exclusion persists while the gateway lists a model. Sync re-ranks it and placement puts it back. A hand edit of the ranks or the `routes` lists is needed only after a rejected ranker run.
- The full `sync` with a vision probe or the ranker can take up to about 15 minutes, so it runs in cron. A `models --refresh` call takes about 5 s and runs before each dispatch batch.

## Eligibility and floors

A flatiron model is a ladder rung only when it is healthy and it passes `--needs`. The kind does not select the model. The kind `vision` maps to `--needs vision` and takes the ladder rungs with `features` vision true. The `routes` lists are the per-kind hint order for `sync` placement. The `floors` key is the capability cut line. Code, debug, research and frontend are floored with the anchor named in `floors`. A model the ranker places in a floored kind must rank at least as high as the anchor. Prose and mechanical have no floor. A missing anchor entry fails closed. A kind whose anchor is gone from the rank map fails closed too and takes no new model. `sync` logs a line that names the kind when it holds a new model back. Existing list members never move or drop because of placement.

## `pick` and `lanes`

- `pick` probes the gateway (60 s cache; `--refresh` forces) and returns the first eligible lane. Health and the served list are at most 60 s old at each dispatch. A recovered model rejoins with no edit.
- The tier floors the ladder and sets the effort and the skills. `tier_floor` maps tier to the floor model id (intern and junior Qwen3.8, senior and principal MiMo, super none). `paid_floor` maps tier to the paid family its paid rungs start at (intern and junior haiku, senior sonnet, principal and super opus). A null tier floor means no local rung, so that ladder starts at the paid floor. A missing or unknown tier takes the intern floor and haiku. The tier floor is `tier_floor[TIER]` first (its model must rank), then the legacy `tiers[TIER].min_rank`, then the intern floor. A `principal` tier pick is not the top rank. When the user asks for the top-ranked model instead, take it from the rank map, where a higher rank value means stronger. Never pick by `routes` list order, which encodes a preference, not strength.
- `pick KIND --tier TIER` returns the tier's floor model that has the task's needs. The pick order is the `rank` map of `references/flatiron-routing.json`, lowest rank first, from the tier floor up. When no healthy local model at or above the tier floor fits the needs, the local rungs move below the floor. The local rungs start at the strongest healthy local model there. Past the local rungs the order moves to the `paid_ladder` key at the tier's `paid_floor`, cheapest first. `--pin MODEL` returns MODEL. `lanes --pin MODEL` returns MODEL and the rungs above it. A pin overrides the local tier floor. A paid pin continues at the paid rungs after MODEL in `paid_ladder`. `assign --pin MODEL` returns MODEL for every node.
- `--failed` moves the pick to the next stronger healthy model on the ladder. Past the local ladder the pick moves to the `paid_ladder` key at the tier's paid floor, cheapest first. It prints one `blocked:` line with the available models and exits 3 only when no model fits. A paid model runs when the ladder moves to it. It also runs when the caller names it through `--pin MODEL` (delegate_task: `pin_model`), the family haiku|sonnet|opus|sol or an exact id. An exact id resolves to its provider against every model the routing file knows and every paid-family id, not only the latest per family. An unknown id is an error and exits non-zero; a pin never falls through to flatiron. A malformed caller id (`--pin` or `--failed`: whitespace, an argument suffix, a leading `-`, or a metadata key like `_doc`) exits non-zero and returns nothing: an id is one token of `[A-Za-z0-9./_-]`. The `--needs` check of a pin reads the exact `features` entry when the routing file has one, even when it is empty; the family entry applies only when the exact key is absent. A pinned model obeys `--failed` and `--needs`: an incompatible pin prints the `blocked:` line naming the model and the reason, exits 3, and never selects a substitute. The report flags every paid landing. Mistral carries `"ladder": false` and is pin-only.
- `lanes` lists every eligible flatiron lane. No free fit prints the same `blocked:` line and exits 3.

## `assign` and the in-flight scan

- `assign` prints one JSON entry per node: node, kind, tier, provider, model, flags, load, reason, fallback. Each node goes to the eligible model with the fewest in-flight jobs. The count rises by 1 per assignment in the batch. Ties break by pick order. The entry keeps the kind and tier eligibility filters of `pick`.
- There is no per-model job cap. The `capacity` map is gone: the router ignores a leftover `capacity` key in `references/flatiron-routing.json`. The old map gave Qwen 4 slots and let one lane ride a multi-slot model. Now the router spreads a batch by the in-flight count alone and never skips a model for load.
- The in-flight count is a live scan of `hermes chat --provider flatiron` processes. The scan matches the model argument in the forms `-m MODEL`, `--model MODEL` and `--model=MODEL`. There is no state file, so the count cannot go stale.
- The command re-reads health each batch. When no eligible model fits, one entry carries `"fallback": true` with no model and the `blocked:` line as its reason; the command prints that line and exits 3.
- A parallel wave of `hermes chat` lanes runs `assign`. When `assign` cannot fit the wave, pin `-m` per lane from `models --refresh`. This is the exception to the never-pin rule. Give adjacent lanes adjacent-rank entries from the healthy list with rank and ping. Keep the kind and tier eligibility filters there too, and quote the rank list in the dispatch note.
- One lane that stalls on `interrupted: waiting for model response` for many minutes can starve its siblings behind the same instance.

## Model pins

- A dispatch route with no per-task model slot silently drops the pin and runs the route's bound model. The completion lines show the substitution and no error. When the route cannot carry the pin, launch the job as a recorded background process with provider and model flags on the command line.
- Model and provider fix at process start. A running child cannot self-switch.
- A `hermes chat` launch whose `-m` model the resolved provider cannot serve falls back to the session default instead of erroring.

## User route override

The user can override the default dispatch route for one task. Resolve the exact name and any context variant once with `latest <family>`. Launch the task's later children as background `hermes chat` processes with `--yolo`, `--max-turns` and a query-file brief, with the resolved model pinned.

## Per-tier ladders, cap and ledger

The strength order is Qwen < GLM < MiMo < Kimi-K3 < Haiku < Sonnet < Opus. GLM sits between Qwen and MiMo only while flatiron serves it.

- intern and junior: Qwen, MiMo, Kimi-K3, then haiku, sonnet, opus.
- senior: MiMo, Kimi-K3, then sonnet, opus.
- principal: a MiMo team of 3, a Kimi-K3 team of 3, then one Opus child.
- super: an Opus team of 3 with no local rung. It runs only after principal fails.
- No child runs on a model stronger than the manager's own model. The same model is allowed. A pin above the cap returns the `blocked:` line. A capped ladder that runs out returns `blocked` and never climbs past the cap. Sol is exempt as the final reviewer and never writes code.
- The ledger drop counts only rows whose verdict is exactly `failed`. The verdicts `missed-defects`, `blocked`, `interrupted`, `hung` and `fabricated` never count.

## Routing ship's gate

A routing change ships with a live `pick <kind> --tier <tier>` for every affected tier, asserting the exact model and flags verbatim. Exit 0 alone passes on a reordered routes list that serves a wrong model. A tier invariant such as "the ladder order is the rank map above the tier floor" lives in the pick logic, never in list order alone. A later `sync` re-sorts by strength, so restoring a list order to recover a pick regresses at the next sync.
