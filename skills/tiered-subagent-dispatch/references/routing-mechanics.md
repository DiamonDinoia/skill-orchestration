# Routing mechanics

Detail behind the tier and ladder rules in SKILL.md. Load before changing `references/flatiron-routing.json`, the router or a tier table, or before debugging a `pick` result. The routing facts here match `scripts/hermes-dispatch-route`. When prose and code disagree, fix the prose.

## Effort clamp

Each `reasoning_effort` a tier names is at most `high`. The top-level `efforts` map of `references/flatiron-routing.json` holds the accepted values per model. `sync` writes an entry from the gateway's rejection text. `pick` and `assign` clamp to the entry: a refused value becomes the nearest accepted value at or above it, else the highest accepted value. A lane-launcher brief repeats the accepted values of the models it may get and makes the launcher name every value it replaced. A replaced value means the `efforts` map misses that model: write the entry after the run. The reasoning effort applies only when the child runs on flatiron. A refusal line in a child's log means the manager reroutes the deliverable.

## Gateway model set

The model set comes from the gateway, not from a list.

- A routing child runs `hermes-dispatch-route models [--refresh]`. It returns the model list with health, rank hint and the `features` columns.
- `sync` probes a new model for vision with 4 quadrant questions on two random 2x2 colour grids. Vision true needs 4 right answers of 4. False needs 2 clear wrong answers and no inconclusive reply. A refusal that names a colour is not an answer. A failed, empty, truncated or refused probe keeps the old entry. `sync` re-probes an entry older than 7 days. `sync` never probes web on flatiron.
- The 6-hourly `sync` ranker places a new or returning model in the `routes` lists. Placement obeys the anchor floor of the kind. Ranks are relative, so a new model renumbers the whole set and the ranker re-ranks the list.
- A model the gateway lists no more drops out of the rank map after 7 days. The drop also removes it from every `routes` list.
- After 3 rejected ranker attempts for one unranked set, `sync` stops calling the ranker until the set changes. Hand-rank from the reason in the sync log then. Each ranker run costs paid quota. The ranker-rejects state, the lock and the dated backups live in `~/.hermes/cache/dispatch-route/`.
- Known limit: no exclusion persists while the gateway lists a model. Sync re-ranks it and placement puts it back. A hand edit of the ranks or the `routes` lists is needed only after a rejected ranker run.
- The full `sync` with a vision probe or the ranker can take up to about 15 minutes, so it runs in cron. A `models --refresh` call takes about 5 s and runs before each dispatch batch.

## Eligibility and floors

A flatiron model is eligible for a kind with a `routes` list only if that list names it. It must be healthy and pass `--needs`. The kind `vision` takes every healthy model with `features` vision true. The `floors` key is the capability cut line. Code, debug, research and frontend are floored with the anchor named in `floors`. A model the ranker places in a floored kind must rank at least as high as the anchor. Prose and mechanical have no floor. A missing anchor entry fails closed. A kind whose anchor is gone from the rank map fails closed too and takes no new model. `sync` logs a line that names the kind when it holds a new model back. Existing list members never move or drop because of placement.

## `pick` and `lanes`

- `pick KIND [--tier TIER]` probes the gateway (60 s cache; `--refresh` forces) and returns `{provider, model, flags, reason, skipped}`.
- A `principal` tier takes only the top 3 rank values of the listed models. Its pick leads with the kind's `floors` anchor. It is not the top rank. When the user asks for the top-ranked model instead, take it from the rank map, where a higher rank value means stronger. Never pick by `routes` list order, which encodes a preference, not strength.
- `pick KIND --tier TIER` returns the cheapest healthy model in the `routes` list of KIND, except for the mechanical kind and the intern tier, which take the cheapest lane of the kind. The tier pins come from `flatiron_lanes`, lowest rank value first.
- `--failed M,...` restricts the pick to models strictly stronger than every failed one. When no such model is healthy, `pick` returns the next rung of the tier's fallback list in the routing file. The quota rule of SKILL.md gates that rung: stop and ask the user before it runs.
- `lanes KIND` lists every eligible flatiron lane plus one `{fallback: true}` entry when none fits.

## `assign` and the in-flight scan

- `assign NODE=KIND:TIER[:NEED,NEED] ...` prints one JSON entry per node: node, kind, tier, provider, model, flags, load, reason, fallback. Each node goes to the eligible model with the fewest in-flight jobs. Ties break by pick order. The count rises by 1 per assignment in the batch. There is no job cap: a model takes every parallel job that fits its eligibility.
- The in-flight count is a live scan of `hermes chat --provider flatiron` processes. The scan matches the model argument in the forms `-m MODEL`, `--model MODEL` and `--model=MODEL`. There is no state file, so the count cannot go stale.
- The command re-reads health each batch. When no eligible model fits, one entry carries `"fallback": true` with the rung `pick` would return.

## Routing ship's gate

A routing change ships with a live `pick <kind> --tier <tier>` for every affected tier, asserting the exact model and flags verbatim. Exit 0 alone passes on a reordered routes list that serves a wrong model. A tier invariant such as "the anchor holds the principal pick" lives in the pick logic, never in list order alone. A later `sync` re-sorts by strength, so restoring a list order to recover a pick regresses at the next sync.
