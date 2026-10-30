---
name: tiered-subagent-dispatch
description: "Use when dispatching tiered subagents in Hermes: flatiron-first ladder, tier picks, blind review, dispatch scripts."
version: 2.0.0
---

# Tiered subagent dispatch (Hermes binding)

This skill is the Hermes binding for delegation. The manager skill holds the core rules T1-T6, P1, D1 and R1. Cite them by the skill name `manager`. Never restate them here.

Standing preference of this user. On a delegation ask ("use kimi as a subagent", "delegate this") the parent on the configured default model takes no deliverable work. Rule R1 of skill `manager` bounds its commands to read-only state checks and `dag.py`; every edit, build and long job goes to a child. It writes briefs and dispatches subagents in parallel. One fresh verification child reruns the checks. One blind review closes the task. A PASS-WITH-NITS closes it too.

The routing and config rules below are Hermes only. For children that run in another harness, see `references/harness-skill-delivery.md`.

## Quota and provider rules

- Quota rule. A tier's fallback never lands on a paid Claude or OpenAI model unless the user named it. A paid model is a named escalation with the user's approval. Fallback rungs move only inside the quota-free pool.
- Provider fence. Every brief names its provider fence, for example "flatiron only; on any other provider stop and report". The first report line must satisfy the fence before work counts. See the report first line rule.

## Harness notes

- Hermes is the one harness that mixes providers. Flatiron work has no parallel cap. The only cap is `delegation.max_concurrent_children`.
- Skills reach a `hermes chat` child through `skills.auto_load` plus `-s <skill>`. A `delegate_task` child skips `auto_load`, so its goal names each skill and says to load it with `skill_view`.
- `delegate_task` cannot pass reasoning effort or extra skills. Reviews and principal work run as `hermes chat` jobs with the picked flags.

## Tiers and routing

The manager names a tier per deliverable. The tier sets the reasoning effort, the extra skills, the fallback order and, for intern and junior, the model pin. Tier names, never model names, go in a brief.

| Tier | Reasoning effort | Extra skills | Model pin |
|------|------------------|--------------|-----------|
| intern | low | none | cheapest healthy lane of the kind |
| junior | high | none | cheapest healthy lane of `code` |
| senior | high | brainstorm | none |
| principal | high | brainstorm, team, manager | none |

Rules that hold:

- Reasoning effort tops out at high. Max runs only when the user asks for it.
- A per-model effort override lives in the top-level `efforts` map of `references/flatiron-routing.json`, keyed by model. `sync` writes it from the rejection text. `pick` and `assign` clamp to it. A child that gets a refusal line reports the line and the effort it sent, and the manager reroutes the deliverable.
- Flatiron first. Every subagent goes to a flatiron model if any healthy one fits. A tier's fallback rung stays in the quota-free pool. Fable is excluded unless the user allows it for one named deliverable.
- Eligibility is a hard filter. A flatiron model serves a kind only when `references/flatiron-routing.json` names it in that kind's `routes` list, it is healthy and it passes `--needs`. The `floors` key is the capability cut line. A missing anchor entry fails closed. Mechanics: `references/routing-mechanics.md`.
- Spread parallel work over the whole eligible set. `assign` places each node on the eligible model with the fewest in-flight jobs. No model has a job cap. Never split one node for show.
- The model set comes from the gateway. A routing child runs `hermes-dispatch-route models` and `sync`. See `references/routing-mechanics.md`. Never hand-set a literal model id.
- Smoke tests and one-line checks run on the picked flatiron model, never on the default provider. `claude -p` and `codex exec` only when the check tests that tool's own config.

## Ladder (per deliverable)

1. Best eligible flatiron model for the task kind. A routing child runs `hermes-dispatch-route pick <kind> [--tier <tier>]`. The kinds are code, debug, frontend, research, prose, mechanical and vision. It returns `{provider, model, flags, reason, skipped}`. A `principal` pick is anchor-first from the kind's `floors`.
2. It fails (bad result after one corrective follow-up, crash, no progress). A routing child reruns `pick` with `--failed <every model that failed so far>`. It returns a flatiron model strictly stronger than every failed one.
3. No stronger flatiron model is healthy. The deliverable stops and reports `blocked`. The manager takes it to the user. A fallback to a paid model runs only when the user named that model.

Escalate only the failing deliverables. Resolve "latest" ids live with `hermes-dispatch-route latest` only for a model the user named. A `vision` pick keeps only models with `features` vision true. In-process `delegate_task` children use `delegation.provider/model`, unless their tier carries a model pin. `sync` sets it to the highest-ranked healthy flatiron model. When none is healthy, `sync` keeps the pinned flatiron default and the report flags it. A mid-session model request of the user changes only new dispatches.

## Outcome ledger

- The manager alone appends one row per child outcome to `~/.hermes/cache/dispatch-route/outcomes.jsonl`. Fields: `ts`, `node`, `kind`, `tier`, `model`, `verdict`, `note`. A child-manager writes rows for its own leaves to the same ledger. A leaf child does not write the ledger.
- Before each batch a routing child reads the ledger tail and adds a leaders-per-kind summary to each brief. `pick`, `lanes` and `assign` skip a model for a kind when its last 3 rows for that kind all have a bad verdict. A bad verdict is `hung`, `fabricated`, `missed-defects` or a verdict that starts with `failed`. A hyphenated verdict counts as its stem.
- The ledger is per-host cache. Never commit it. Rotate it at 10k rows.

## Procedure

0. Baseline before any edit. A subagent records `git rev-parse HEAD` as BASE for repo work, or creates a snapshot for files outside git. One baseline at task start covers later scope growth. When scope grows, a subagent snapshots the new path inside the next work dispatch.
1. Routing selftest baseline before the first routing edit. Run `python3 scripts/selftest.py` on the unedited files and record the result. A failing edited run that matches the baseline is a pre-existing failure to report, never a reason to revert. When the baseline is red, gate the edit with the per-check runner of `references/routing-selftest-gates.md`.
   - A three-way doc disagreement between `references/flatiron-routing.json`, the router docstring and `selftest.py` gets one behaviour probe. Report and ask the user only if the probe is inconclusive. Then fix every stating source.
   - Reverse-toggle evidence (scratch copies only, never the live json) is required only for a routing claim that gates a fix.
2. Research. One intern research child per batch reports the paths and the pieces to reuse. It stops at the first reproduced cause. Read-only work such as "review PR N" is the same shape and produces no diff.
3. Brief. A subagent writes it to `$TMPDIR/<task>-brief.md`: goal, files in scope, one CHECK per deliverable that catches a defect, and one line naming skill `manager`, `references/child-rules.md`. A `diff` travels as `--stat` only. `[ESCALATE-TO-MANAGER]` marks items the child cannot do. The brief names the provider fence and the skills `ste`, `unslop`, `ponytail` plus the task skills. A missing skill installs inside the brief's first step. Put "do not create or edit skills or memory" in every brief. Keep briefs out of the repo. The reviewer must not see them.
4. Launch. A launcher subagent starts the work as a background Hermes process with the picked flags:
   ```
   hermes chat <flags from pick> --query-file <brief> -Q --yolo --max-turns 150 > <log> 2>&1
   ```
   It writes the flags to `<job>-flags.txt`. It stays alive until the notice arrives and returns the log path, the session id and the final report. The launcher keeps a per-model record of busy and warm instances and starts a warm one before a cold one. A job no launcher can wait out runs under a tracked supervisor the parent starts.
5. Wait on events. Arm `terminal(background=true, notify=true)`, or call `process_manage` action `wait`. Fixed intervals and `heartbeat=` scripts are not wait mechanisms. A `pgrep` name match is a read-only hint only. Inspect on a deadline event or when the user asks. The monitor relays a short status per event and the last status line before it exits. Every batch status message gives the log path and a `pgrep` watch command.
   - Once the code is done, stop the child and review the diff. Run one quick local check. Fold the edits. Then run the CI-version style checks and push the feature branch. Do this once per batch. Say which local checks were skipped.
   - A vanished child with no report is redispatched only when it left no committed evidence.
6. Verify. A fresh verification child that did not write the code reads the log's final report. It runs `git diff`, reads the changed files and runs the checks. Verify only deliverables whose CHECK output is not already quoted with exit codes. One skill-quote probe per batch checks that the worker quoted each briefed skill. Measure column indices for layout claims before accepting them.
7. Follow-ups and spec changes. One follow-up round resumes the failed deliverables with `--resume <session_id>`. Report the rest. A spec change stops the child by the process rule, keeps only the child's own changes and resumes with a numbered `SPEC CHANGE` brief. Never kill by name. For a `delegate_task` child, patch the spec file then `steer`. A missed steer logs for the next brief. An escalation rung starts fresh and gets one self-contained brief.
   - Resume mechanics. `--resume <session_id>` reuses the producing session with the original launch flags. The resumed child already has the repo, brief and pitfalls in context, so a follow-up costs a fraction of a cold start. The resume repeats the saved flags and appends nothing job-shaping. A second occurrence of a pinned flag later in argv overrides the saved value and the resume then dies on the flag-mismatch check before any work starts. A course correction to a halted job resumes with a delta spec: a re-entry check that stops on a HEAD sha or status mismatch, the decision and its steps, then the original brief repeated below. `--resume` appends to the child's context, so the delta reads as the newer binding spec. Never substitute `--continue` for `--resume <id>` on a session launched with pinned flags. It resolves whatever session the directory holds and silently drops the pins, so the model shows as the harness default. A redo that discards the learned context launches fresh.
   - UI work ends with one vision verdict per deliverable. Skip before/after pairs for unchanged regions. Use neutral file names. Redesign asks follow `references/ui-redesign-options.md`.
8. Review. One combined reviewer per change set: Sol when the user configures one, else one principal-tier reviewer (rule T5 of skill `manager`). One review round, then at most one fix round and one re-check of the fixed findings only (rule T2). Reviewer output carries only BLOCKER and MAJOR (rule T1). Mechanics, verdicts and stop conditions: `references/review-loop-rules.md`. Load it before the first review run.
9. Parallel batches and fix rounds. Flatiron work is split and parallel by default. Cut the task into deliverables with disjoint file scopes and one worktree each. The dependency-graph scheduler and its check gate live in skill `manager`. Run the graph check and the idle-capacity split once per batch. Serialize only on a shared file, port, device or a real data dependency. Rules every lane shares go in one common preamble file. After the batch, `git show --stat` per new commit lists only that job's files. Fix-round split granularity follows the fix-split rule of skill `manager`. Merge and proof mechanics: `references/review-loop-rules.md`.
   - Producer and consumer pieces split by file owner. When their data shape is open, the producer's stub is its own node and both sides depend on it.
   - Any quota-free child may spawn children, per rule D1 of skill `manager`. A paid-quota child never spawns; it reports its split proposal upward. A one-shot leaf stays within `delegation.oneshot_max_children` and can spend both slots in one turn.
10. After a PASS: PR per repo, then merge when CI is green. Push the branch, `gh pr create`, then launch `scripts/merge-when-green.py <owner/repo> <pr>` as `terminal(background=true, notify=true>`. Repos that PASS go out at once. Hosted-runner incidents: `references/git-ci-pitfalls.md`. CI maintenance: `references/ci-maintenance.md`.
11. Report in proportion. One line per deliverable that passes. Expand only for failures and user decisions. The report contract and the first line rule live in skill `manager`, `references/child-rules.md`. Relay the review verdict with its path and name the escalated work.

## Standing rules

- **The manager takes no deliverable work.** Rule R1 of skill `manager` bounds its commands to read-only state checks and `dag.py`. No routing lookup, no `hermes-dispatch-route` call, no review run. Every check outside that list is a unit of work for a subagent. Routing bootstrap: the first `delegate_task` of a task goes to a routing subagent, which returns the healthy models from the last `sync`. At most 4 routing retries per task, then report `blocked` and take it to the user. Only routing-control dispatches run before routing is fresh.
- **Never change user settings.** Theme, skin, TUI widgets, `model.default` and the provider choice stay unchanged, unless the user asks for that exact change. The expected change is the `delegation.*` write of `sync`. An installer brief copies each config file it can touch before the run and restores changes outside the task's keys after. One combined drift-audit and restore job handles a reported config change.
- **Process rule.** Start long work only through `terminal(background=true, notify=true)` or `delegate_task`. Stop only with `process_manage` action `kill` or `delegate_task` action `stop`. Never kill by name. `pgrep` is a read-only hint.
- **File delete and move rule.** Before a delete or move, check for live links (symlink, hard link, config reference). Update the link first or keep the file.
- **Branch delete rule.** Before a delete, record the tip sha of each branch and the remote URL. Put them in a restore file under the task scratch dir. A delete with no recorded sha cannot be undone.
- **Shared repo rule.** Never run `git stash`, `checkout`, `restore` or `reset` in a shared repo. Those commands can remove work in progress.
- **Brainstorm decisions rule.** Every brief tells the child to load `brainstorm` with `skill_view`. It uses it for each decision with more than one live option and returns the decision log. It decides alone only when the choice is reversible and inside the brief. Otherwise it returns `[ESCALATE-TO-MANAGER]`. At most one manager round and one batched user question per task settle what remains.
- **Monitor cadence rule.** Hermes ends a stalled async child after 450 s idle and a child stalled in one tool after 1200 s. Inspect on an event, never on a clock. Transcript silence alone never stops a child. Two checks in a row with no progress and no liveness stop a hung child. A brief without a deadline carries a 60-minute default deadline. Steering lands at the child's next tool result. Never leave a child in a sleep poll.
- **Report first line rule.** The provider and model rule lives in skill `manager`, `references/child-rules.md`. For a `delegate_task` child give the `Model:` line of the output header. For a `hermes chat` job give the launcher's `-flags.txt` content.
- **Child visibility rule.** In-process `delegate_task` children show live in the TUI. A background `hermes chat -Q` job is invisible there, so the log-and-watch rule of step 5 stays mandatory in every batch status message.
- **Removing a tool: official path first.** A read-only child writes the documented uninstall sequence with what each step leaves behind. The purge job runs those commands, then the installer's own uninstall, then edits by hand only the leftovers. A tool that serves the subagents' own route is removed last. Detail: `references/dispatch-ops-pitfalls.md`.
- **Mid-task model exclusion.** An exclusion covers every route to the model: `delegation.model`, the tier pins and the fallback lists. Re-route this task's deliveries to the next eligible model and state the re-route. Check each completion header's Model line once per batch. Flag a result that landed on an excluded model instead of rerunning it.
- **Web research split.** A step that needs web search or web fetch runs `hermes-dispatch-route pick research --needs web`. That job is fetch-only: verbatim excerpts with URLs to a scratch file. A flatiron child then reads the file and does the analysis. Mark unopened facts UNVERIFIED and relay the mark unchanged.
- **Flatiron outages are temporary.** A model dying mid-run is an outage, not a quality failure. Probe gateway health once per batch with `models --refresh`. Wait at most 30 minutes for flatiron to come back. Still down: ask the user before any work runs on a paid provider. A retry that failed only because flatiron was down is not an escalation. Flag every fallback landing in the report.
- **Fast mode once the work is small.** Cut a final fix round into parallel deliverables in one batch. Doc-only deliverables get no build. Code changes rebuild only their own targets and run each rebuilt binary in full. Build detail for C++: `references/cpp-build-test-pitfalls.md`. The report names what was not run and why.
- **Builds run at the lowest priority.** Every build brief says: run with `nice -n 19 ionice -c 3 <cmd>`. Launch the `hermes chat` child under `nice -n 19` too. A control subagent can renice running children in place.
- **Test small first, then expand.** Start with the smallest batch that can answer the question. Exactly one named expansion per deliverable when the small batch is inconclusive. A full sweep is never the first step.
- **Cheap first, escalate on failure.** Rule D1 of skill `manager` is the split rule. Each parent splits until each leaf fits the cheapest tier that can pass its check. A leaf moves up one tier only after it fails its check, with `pick --failed` and `dag.py fail` plus `dag.py escalate`. A `principal` leaf that does not succeed goes to the parent manager. A repetition-stall crash is a crash of the author: salvage the leftover diff and route the rescue to the next rung. Edits that restructure a shared function across whole regions route one tier up from the start. A pin model caught fabricating a report starts the next report-bearing deliverable of that task one tier up.
- **Unanswered questions do not block.** Proceed on the recommended option for reversible work and say so in the report. Prepare a backup branch at the verified alternative only when the work is not reversible. Never push on an unanswered outward-facing question; the push gate of skill `manager` applies.
- **Issue sweeps split per issue, not per repo.** One read-only discovery child lists the open work. Each fixable issue is its own lane in its own worktree, with the issue body quoted verbatim and one mutation-check test. Skip the triage child when the report already names one cause.

## References (load on trigger)

- `references/review-loop-rules.md`. Review rounds, verdicts, fix-round mechanics, push gates, stop conditions. Load before the first review run.
- `references/routing-mechanics.md`. Effort clamp, gateway model-set lifecycle, `assign` scan, lanes. Load before changing routing files or debugging a pick.
- `references/routing-selftest-gates.md`. Selftest baseline, per-check runner, reverse toggle. Load before any routing edit.
- `references/flatiron-routing.json`. Ranks, routes lists, floors, efforts. The data the router reads.
- `references/dispatch-ops-pitfalls.md`. Watch loops, background handoffs, worktree paths, shell aliases, skill edits. Load before dispatching a tricky batch.
- `references/report-evidence-pitfalls.md`. Report evidence, exit codes, state salvage. Load before accepting a child report.
- `references/agent-process-management.md`. Start, wait, stop and redo mechanics. Load when a child stalls or restarts.
- `references/delegate-orchestration.md`. Brief contracts and report verification. Load when writing a multi-child brief.
- `references/delegation-capability-handoff.md`. Web and vision gaps inside a child. Load when a child lacks a capability.
- `references/verification-pass-pitfalls.md`. Verification and blind-review pitfalls. Load before a verification round.
- `references/hermes-runtime-pitfalls.md`. Gateway health, provider deaths, resume compaction, config rewrites. Load on a runtime fault.
- `references/git-ci-pitfalls.md` and `references/git-history-rewrite.md`. Rebase, CI and branch-shape pitfalls. Load before a rebase, force-push or CI fix.
- `references/ci-maintenance.md`. CI version bumps, runner pinning, publishing auth, releases.
- `references/cpp-build-test-pitfalls.md`. C++ build, numeric and timing pitfalls. Load before a C++ fix round.
- `references/mutation-testing-pitfalls.md`. Mutation and test-double pitfalls.
- `references/numeric-heuristics.md`. Tolerance and bound tuning. Load before a child tunes a numerical bound.
- `references/no-network-selftest-harness.md`. Offline selftest harnesses.
- `references/live-tui-job-briefs.md`. TUI and statusline job briefs, vision audits. Load for UI inspect-and-fix loops.
- `references/ui-redesign-options.md`. Redesign and simplification asks.
- `references/harness-audit-workflow.md`. Harness config review and owned-skill rules. Load for "review my harness setup" asks.
- `references/memory-consolidation-workflow.md`. Memory and skill consolidation. Load for "consolidate my memories" asks.
- `references/harness-skill-delivery.md`. Skill delivery in other harnesses. Load for a foreign-harness child.
- `references/kimi-review-block.md`. Review brief block for a principal-tier review.
