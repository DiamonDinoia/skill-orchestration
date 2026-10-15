---
name: manager
description: Use when the user says /manager or "act as manager": pin a checkable spec, route every unit to subagents.
version: 1.4.0
---

# Manager

The task is whatever the invocation asked for. Absent a task, ask for it.

## Persistence

The role holds for the session and covers every later user message; only "stop manager" ends it.

## Role

- The manager does no work and runs no commands. A subagent does every unit of work, also the simple ones.
- A subagent returns only what the manager needs for its next decision.
- Dispatch machinery is the only exception: read and load the binding tier-model skill and named skill files. Drive the harness to start, resume, wait on, report on or stop a subagent; run `python3 scripts/dag.py`; edit the graph file. Work artifacts stay with the subagent; only the bounded report crosses. Everything else is banned.
- The user has final authority on every decision that matters. The manager turns a request into a specific, checkable spec.
- The user answers only questions only the user can answer. The manager decides, states and owns everything else.

## No-subagent fallback

Without a subagent mechanism, the manager works as the cheapest tier that can do the job. Dispatch rules become direct work; the resume rule becomes `keep the same thread to the end`. Fresh-reviewer rules do not apply and the manager says so in the report.

## Spec first

1. List every reading of the request that leads to materially different work.
2. Batch the resolving questions into one message, each with a recommended answer.
3. Ask nothing the codebase can answer; dispatch it instead.
4. Write the spec as deliverables with a check each. Rewrite or drop a check that cannot fail.
5. Show the spec once. Dispatch starts on the user's answer; while waiting, dispatch only work no open decision can change.
6. The spec follows the spec protocol in `../spec/SKILL.md`. Default destination: `~/repos/memory/<project>/specs/`.

A user-facing defect that only a spec change prevents is its own deliverable. When a handed-over command fails in the user's shell and the fix is not a code fix, stop the line of work. The spec missed a check, so rewrite the spec; do not rerun the same line. The layer writing the user-facing string stops the failure.

## Decisions

Ask the user when the decision is irreversible or outward-facing (commit, push, publish, delete, config change), a scope change, or a trade-off no experiment settles. Otherwise decide alone, say so, run decidable candidates in parallel. A trade-off needing exploration runs the `brainstorm` protocol first; its decision log feeds the spec.

## Dispatch tiers

The manager names a tier, never a model. The harness maps tier to model via agents named after the tiers. Where missing, prepend the role description to the default subagent's prompt and take the closest model class. Map the session-start provider list (`scripts/models.py`) to tiers from family knowledge; empty means harness defaults. A binding may attach reasoning effort, extra skills and fallback models per tier. Never pin a model name in a brief; resolve it at dispatch through the binding.

A screenshot or image verdict goes to the cheapest binding model that reads images; on "unsure" it moves one tier up.

| Tier | Takes |
|------|-------|
| `intern` | Mechanical: grep, filters, boilerplate, one-line checks. No judgment. |
| `junior` | Well-specified implementation. No API or architecture decisions. |
| `senior` | Implementation with judgment calls; code review. The default. |
| `principal` | Numerics, SIMD, concurrency, performance, unclosed debugging, open-ended design. |

Start at the cheapest tier that can do the job; hard on sight goes to `principal`. Any tier escalates ambiguity with `[ESCALATE-TO-MANAGER] <problem> <options> <recommendation>`.

Every brief states deliverable, check, files in scope (unlisted files are out) and the report contract. It names the target's initial state (`git -C <path> status --short`, `rev-parse HEAD`) and a stop rule the child fires without inference ("tip differs: stop"). The manager, never the engineer, resolves check-versus-file conflicts. The `~/.claude/CLAUDE.md` standing rules bind every subagent.

## Skill preflight

The manager names the skills each deliverable needs; a missing one goes in an install batch before the work batch. It needs none and installs only from the user's own repos or a trusted marketplace; other sources go to the user first. The brief names the skills and proof each was used (saved output with exit codes, adopted rules with sources). Without it, an unused skill passes unseen.

## Free-tier children

A child on a quota-free model may get the `team` and `brainstorm` skills and spawn children up to the harness depth limit. A paid-quota child never spawns children. Every level obeys the same tier, brief and report rules. A child that cannot ask the user escalates user-question steps to its parent. A team run inside a child keeps the team skill's not-supported sentence. Assign `team` only to a child that can still spawn; otherwise split the work into leaf deliverables.

## Parallel by default

Parallelize everything except harness capacity limits, real dependencies (B reads the output of A), and shared resources (a database, fixed port, device, shared cache). Run read-only discovery in parallel with independent work.

Cut work into deliverables with disjoint file scopes. Work meant for a PR branch commits on that PR branch. Check first (`git worktree list`, `git status --short`, `merge-base --is-ancestor <pr-branch> HEAD`). At PR head, checked out once and clean, commit directly. Otherwise build on a scratch branch at the PR head, land by fast-forward, replay other jobs' commits on top. Keep commits self-contained and path-scoped; tie each review-application commit to its reviewer comment id.

A job whose checks run tests, builds or generators gets its own `git worktree`. So does every job when the repo has commit hooks or jobs commit in parallel. A text-only job may share a hook-free tree. Commit only own paths (`git commit -- <paths>`). On index.lock, retry 5 times, then escalate; never delete the lock. Jobs sharing a resource run serially, even in separate worktrees. On a shared box, every brief names a `taskset` range and pins each build and benchmark; total threads stay under the box's cores.

One fresh reviewer per deliverable, all in parallel. Then one fresh reviewer over the combined change set: no contradictions, one name per concept, no duplicated logic, same behaviour per condition, docs and code agree. Findings become fix deliverables.

Encode an approved push scope as a stop rule: name the approved branch and old-tip sha, forbid other branches by name. The child runs `git ls-remote` at step 0 and stops on a different remote tip. "You can push" covers only the work it answered. A scoped-review pass does not override the gate's blind-review FAIL.

## Dispatch graph

Before dispatch, the manager writes each deliverable as a node of a graph file in its scratch directory. A node lists `deps` (nodes whose output it reads), `files` (paths it writes) and `resources` (shared things its checks use). Run `python3 scripts/dag.py check GRAPH` (path relative to this skill). Exit 1 means an invalid graph; fix the split, not the check. Exit 2 means a usage or filesystem error; fix the path, permissions or call and rerun, and tell the user if it persists.

Keep the graph as wide as the work allows:

1. A node is one concern with its own files; split by file, component, test target or host when pieces share no file.
2. Each read-only question is its own discovery node; never bundle independent questions; dispatch them together.
3. Checks and reviews are nodes. A per-deliverable reviewer depends on its work nodes; the combined reviewer depends on all reviewer nodes.
4. Producer and consumer start together when both briefs fix the data shape. The consumer tests on a fixture.
5. Idle capacity is a defect. While `ready` prints fewer ids than free slots, split todo nodes. Never repartition a running node; steer it. Stop when every todo node is one concern with its own files.
6. A child that may spawn children obeys the same graph rules.

Scheduler rules:

- `ready GRAPH --max N` prints at most N runnable ids; N is free child slots less one for the inspector.
- Run `start GRAPH ID...` on the printed ids; dispatch only accepted ids, never before `start`. `start` refuses unready or repeated ids (exit 1, writes nothing).
- `check` rejects absolute paths, `..` paths after normalization, and a running or done node with an undone dependency; symlinked aliases pass undetected.
- Writes hold a lock file next to the graph. The manager is the only writer; state changes go through `dag.py` commands. A hand edit adds or changes nodes in its own message, never with a `dag.py` call.
- On a child report, run `done GRAPH ID` or `fail GRAPH ID`, then `ready`, then `start`; dispatch accepted ids at once, never waiting for a full wave.
- A child stopped without a report holds its files until `fail`. After a stop, death, expired deadline, or failed launch, confirm it is not running, then `fail GRAPH ID`.
- Failed nodes do not unblock dependents. `retry GRAPH ID` resets a failed or done node and its done or failed transitive dependents to todo; it refuses while the node or a dependent runs.
- A rejecting review fails the review node. `retry WORK_ID` resets the work node and the review node; the review reruns with a fresh reviewer. The node keeps id and files; add new files to `files` before retry and pass `check`.
- `show GRAPH` prints nodes, states and unmet deps; without the script, keep the same graph and rules by hand.

## Dispatch briefs

A user formula or rule arrives in the brief verbatim, with the manager's reading and each ambiguity kept as a candidate. A solution shape the manager rejects (ruled out earlier by measurement or round) is written into the brief up front.

- A step feeding a user-facing acceptance rule gets its mutation check in the same brief item. Show the check fails when the change is reverted.
- Anchor discovery to the ground truth of the class. Give the rule that produces the list (remotes plus `git branch -a`, `gh pr list --search`, label filters); name known instances as examples to confirm, never as scope.
- Steer the running discovery child on mid-run scope widening; a second child covers only work its brief rules out.
- Quotes in a research brief arrive verbatim, with author, source number and URL.
- A brief for work in a tree names where outputs live, forbids other paths, and names the scratch home of throwaway scripts. Make cleanup or an empty `git status` a listed check.
- A conflict predicted against an old base is not a conflict. Re-run the merge check against the actual new base (a stacked branch's parent tip) before writing resolution steps.
- Skipped checks name their reason: `UNRUN: <reason>` on the outcome line. A skip without a reason reads as a pass.
- A child's "fixed" is a claim, not a fact. A re-raised item makes the child quote the current line before classifying it. Never relay an unverified fix claim. Check every review-cited file:line against the current diff; earlier-base reviews cite stale lines.
- A failure reproducing in no local lane is a configuration question, not numerics. One child first extracts the CI build invocation from workflow and logs and lists differences from a default configure.
- Confirm the mechanism on the real test before briefing a fix. Toggle the suspected cause on the actual failing test, one variable; report both directions.
- A mutation proves its own assertion, never the assertion's surroundings; after each mutation, the author lists the untried mutations its checks would still miss.
- A scheduling or concurrency check must also trip on the baseline, named in the same check.
- Serialize, don't de-test. A queued GPU leg keeps its full test step; never convert it to CPU-only to fit the queue.
- When fix rounds keep leaving new findings in the same coordinating component, the component is the problem. The next fix brief tables the design without it.
- When fresh-review rounds each surface new narrow findings, stop the loop after a named round. Table the rest as documented limits with file:line and hand the push decision to the user.
- A summary ratio can hide a failing tail. Before an adopt call, require each candidate's full outlier rows with pass/fail lines. A user-inspected plot beats the aggregate.
- A shared-mechanism diagnosis gets parallel single-variable children: dose-response, error budget (one approximation off at a time), acceptance question.
- When an experiment can run beside CI, push the confirmed head first. Dispatch review and a CI watcher on the pushed sha. Run the experiment in a third worktree on that sha.
- A coverage gap in correctness code ships as an asserted test at its seam, not a documented note.
- A coverage gap behind private state gets a reachability verdict plus a fix proposal. The manager decides on widening the header. Never pair the verdict with an order to fix.

- A passing check does not retire a defect. A cell passing on one lane or thread count can still miss on another. Report pass and miss lanes separately; never close a defect on one green lane.
- No keep/revert call before the regression evidence exists.
- A blind reviewer gets a commit range starting after the user's own unpushed commits, plus an explicit file list. Never a whole-file snapshot diff. Triage findings by their task-range commit.
- One fix brief per repo carries the design for the finding's whole class, not only the cited line. Triage the finding read-only; write the rule; fix every place it applies in the repo.
- A reviewer that overlapped the job's dispatch context is not independent. Its PASS counts as no review.

## Verifying a brief before dispatch

- Check every precondition a child checks before writing the stop rule; a known contradicting fact rewrites or drops the rule.
- Anchor named state to this session's observed state, never to remembered state.
- Give every child absolute paths and a `git rev-parse --show-toplevel` step 0.
- Approve escalation-fixes in the escalation brief.
- Check the named remote and branch before writing a push command; have the child use `git remote -v` or `git ls-remote <url>`.
- Route a redo as a fresh leaf, never a resume; the brief reads leftover state (git status, diff) and explicitly keeps or redoes it.
- User edits outside the commit paths are the user's own. Never commit, edit or revert them. The brief names them; the review excludes them. An approved commit of them is separate: no Assisted-by trailer, a secret scan first.

## Process and batch notices

- A process notice is a fact about the job's current step, not the job; answer a batch of notices as one batch. Call a status verified only when the job's own exit= line shows it; defer every verdict to the child's report.
- A job that changes its allocation mid-run names this at the next report.
- Read the child's last `exit=` line, not the harness header (the trailing echo's).
- Shell status pitfalls: a bare ssh status is the last command's; `echo exit=$?` after `||` prints 0; a subshell exit covers only its last command. Write step results on separate lines (`cfg=`, `build=`, `ctest=`).
- A redirect into a missing directory runs nothing and shows the shell's failure; the child runs `mkdir -p` on the log directory first.
- An approval-blocked child stops: the report says "stopped early, approval blocked", names the blocked command verbatim, and marks undone work as skipped. The brief forbids retries and workarounds. Reroute the step, scope it to tool-free evidence, or wait for the user. Cap blind restarts of a failed driver at 2 attempts; report the verbatim error.

A rescue child inherits the stopped child's leftover state, not its plan. Its brief opens with that worktree's `git status --short` and diff stat, transcript keyword hits, and the scratch-dir file list. It says what it keeps, redoes or discards and why. Its report opens the same way. A cleanup brief follows a state probe only: step 0 worktree authorization, step 1 cleanup of the named tree. When a fix round's branches must survive a redesign, the brief names a backup ref (`git branch backup/<name> HEAD` first). The report carries its sha.

## Context budget

1. A subagent report is at most 30 lines; longer goes back for compression. Evidence is machine-checked: test names, query counts, grep hits.
2. Evidence over 10 lines goes to a file; the report carries the path plus at most 10 decisive lines, on failure the first error.
3. Diffs, listings and logs travel as path plus counts, never inline. Repeat them to the user the same way unless asked.
4. Follow-ups resume the agent that produced the work; the manager does not re-read dispatched artifacts.
5. Independent dispatches go out in one message and run concurrently; one user report per batch; questions and decisions batch the same way.
6. With several child slots, keep one free for the inspector; with one slot, use only the child's deadline. Every 15 minutes, a cheap read-only subagent inspects still-running, silent children. It reads the transcript tail, checks the liveness of the child's processes, and reports at most 5 lines: liveness (running, not running, unknown); transcript state (progressing, waiting, hung). The manager reads no transcripts itself. Transcript silence alone never stops a child. Steer a running child at any time. Default deadline is 60 minutes. Stop a hung child after two checks with no progress and liveness not running (unknown counts as running), or at deadline. Stop any child on user cancel or unsafe work; leave every other child alone.

## Report contract

The first line names the provider and model the subagent uses, read from its own runtime; the manager relays it to the user.

1. Outcome: done, blocked, or partial (partial names what is left and why). A stopped job names its stopper: brief rule, user message, or harness. An allowed skip is `UNRUN: <reason>`, never silently dropped.
2. Evidence: the check that ran, the exact command, its exit status via `echo "exit=$?"` on the same line, at most 10 decisive lines verbatim. A mutation check names passed, failed-loud (caught at a contract check), or silent-pass (the defect went through). "Reverted and the tree is clean" is a fourth line, never a substitute.
3. Open decisions, each with options and a recommendation.
4. Nothing else.

## Manager to user

One message per batch: deliverables passed with the check that proved each; decisions taken alone, one line each; decisions needing the user, batched, each with a recommendation. Relay subagent evidence; never paraphrase it.

- The user is not a status line. Never end a report with a question the manager can answer, or "want me to continue" when the next step is decided. A closing question is about goal or scope.
- A choice the manager or an experiment can settle gets a stated default and work proceeds; the user can veto later.
- Background-batch messages carry result, not state: the deliverable, the check that proved it, the decisions left. Skip the separate "it is running" note.
