# Agent process management

These are the rules the manager adds to every brief once children start launching their own children or long-running commands. They came out of a session where the manager's turn was killed mid-pipeline and several children detonated at once.

## Leftover state before redo

Any work an agent could have half-done deserves a step 0 before the redo. Inventory only the paths the redo will touch:

- `git status --short`, `git log --oneline -2` in each repo the redo will touch.
- `ls -la` of the scratch dir the previous run owned.
- `ps -p <pid>` for any background process the earlier run reported starting (a child exit kills its own `terminal(background=true)` children, but a nested `hermes chat` it launched directly may still run).
- See the steer entry in SKILL.md's Pitfalls for steer delivery timing. Reach the worker with a steer before it folds a user style decision. For an urgent reversal (drop a wrong lane), stop the child and re-dispatch with a fresh self-contained brief. Steering alone strands the in-flight call on the old course.
- Reuse whatever is found; escalate rather than discard partial work blindly.

A child that is interrupted, timed out, or killed may have committed part of a multi-deliverable fix. The redo brief names what it finds and what to keep.

Exit-code capture and the trailing-echo rule live in `references/report-evidence-pitfalls.md`. Use its capture form for every build, test and sweep run.

A background-process notice's Output preview is the tail of the last stdout write. A redirect to a log hides the real output for a `> log 2>&1` command. Its exit code follows the trailing-echo rule in `references/report-evidence-pitfalls.md`.

## A child owns its own background processes

`terminal(background=true)` processes started by a child die when the child exits and deliver no completion notice to the manager. A child that launches one must call `process_manage` action `wait` on its session id before it ends its turn; otherwise the work is invisible and the manager counts it as UNRUN. This also applies to nested `hermes chat` runs: the manager sees the outer child finish but never the inner review run.

## Never park the turn in a foreground sleep

`sleep 600` as a foreground terminal call pins the whole turn for the interval and costs more quota than the wait saves. All waiting is in background: `terminal(background=true)` for the worker and `process_manage` action `wait` to block on it. The manager's own turn ends right after dispatching.

## Trust the log file, not the notice

A background-process completion notice carries the stdout tail of the last command; for piped commands that can be the pipe's tail (empty or garbled), not the verdict. Rules:

- The notice never counts as evidence by itself. Before taking the next step, read the command's log file with read_file.
- The manager replies to each notice in one line: what step of which child it belongs to and who reads the log. The line also says why that exit code is not the verdict. Silence on alerts invites the user to ask whether something is hanging; a full re-report of the child wastes context.
- If the log is missing or truncated, report the step as unknown. Never infer a verdict from the notice alone.
- The notice `exit_code` field follows the trailing-echo rule in `references/report-evidence-pitfalls.md`.

## A rerun storm with edits between reruns is progress, not a loop

A stream of near-identical completion notices from one child (six probe reruns in a row) does not by itself mean the child is stuck. When the transcript shows edits between reruns, trust the two-check stop of SKILL.md's Monitor cadence rule and dispatch no child. Dispatch a cheap read-only inspector only for identical reruns with no edits. It compares edits between reruns, liveness of the tool processes (running / not running / unknown), and answers whether the child hangs. A build that failed and sits mid poll cycle reads as stale transcript, not as hung. The inspector names the poll cadence instead of declaring a hang.

## Stopping a stale job chain

User signals "too long", "kill", "wait / slow down" stop the running job before its deadline. First give the user what the stop leaves: commits, branch, leftover processes, what is left to do. Then stop and assess. A signal can be as plain as a number question or a capitalized "STOP". The manager restates it in one line, then stops the job chain.

A `delegate_task` stop arrives at the child's next iteration boundary, not its current tool call: an in-flight `hermes chat` session writes to a stopped brief after it. The follow-up that takes the job kills the child's `hermes chat` processes and Playwright children by `ps -eo pid,etime,args | grep -a -e 'hermes chat' -e playwright -e 'http.server'` before a snapshot: grep the args for the worktree, not the process name, and leave the user's own systemd units and the jobs of other batches alone.

The assess step is read-only. Snapshot (`git status --short`, `git log --oneline` from the last known-good tip, `git diff --stat`) and save an uncommitted diff to a scratch patch. Run the checks as they are. Map every open requirement to file:line plus the test that covers it as in / partial / missing. One assess report covers a whole stopped batch, not one per stopped child. The report has the ended state of the stopped job, not the new plan. On it the next dispatches run. The stop counts as assessed only when the report names a sha, gives test counts, and lists the leftover processes it killed.

## When a batch is interrupted en masse

A distributed kill (workflow abort, harness restart, or OOM) hits every child in the batch at once. Before restarting look for `git reset --soft`, `git rebase`, or `git merge` left in progress, and any worktrees the batch used; a worktree still on disk means the work survived. Re-dispatch with the same briefs and let each child's step 0 absorb it.

An interrupted turn is the same kill for its in-flight `delegate_task` children (`status=interrupted`, partial work in scratch). Take over with a fresh child whose first step is read-only state discovery of the paths the redo will touch. Never trust a partial output row as progress.