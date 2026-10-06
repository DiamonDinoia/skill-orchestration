---
name: team
description: Iterative multi-agent orchestration for one task, run as rounds. The manager splits the task, critics attack the split, engineers execute in worktrees, reviewers validate, and the manager merges and re-splits until every deliverable passes.
disable-model-invocation: true
argument-hint: "[interview|plan|execute|review]"
---

# Team

Team runs one task as rounds. The manager splits the task into subproblems. Critics attack the split before any work starts. Engineers execute subproblems, each in its own git worktree. Reviewers validate and prune the work. The manager merges with consent. The manager re-splits what remains. The loop ends when every deliverable in the run's state file passes on the integration branch.

## Manager role

The invoking agent assumes the manager role for the run. Where `../manager/SKILL.md` is present, its Role, Dispatch tiers, Free-tier children, Context budget and Report contract rules bind this run too. Where that file is absent (standalone install), the Roles and harness mapping below stands alone. Inside a child, the parent takes the user's role as a communication proxy: it answers only from existing user instructions and escalates user-only decisions and consent requests to the user.

## Triage

Run team only when the task has two or more independent subproblems and delegation saves context, latency, or verification cost. Skip for Q&A, single commands, and single-file edits.

## Modes

The first invocation argument selects the mode.

| Argument | Mode | Run when |
|----------|------|----------|
| `interview` | Interview | no state file, or the user asks |
| `plan` | Plan | deliverables exist, no current split |
| `execute` | Execute | a split has open subproblems |
| `review` | Review | all deliverables pass, or the user asks |

With no argument, read the state file and decide in this order: no state file, or no Deliverables section in it, runs Interview. An open subproblem in the split runs Execute. Every deliverable passing runs Review. Anything else runs Plan.

Invocations: `/team interview`, `/team plan`, `/team execute`, `/team review`, `/team`.

## Interview

Produce deliverables a reviewer can check without contacting the user. Invocation: `/team interview`.

1. Ask the user the smallest set of questions that makes every deliverable measurable.
2. Write the deliverables and the build-and-test command into the state file. The State-file section defines the check format.
3. Run every check once. A check that errors for environmental reasons gets fixed, or the deliverable gets rewritten.
4. If the state file has no Dispatch preferences, decide concurrency (parallel or one-at-a-time) and engineer dispatch (dispatched or manager-inline) and record both in the state file. Both are reversible, so the manager decides them instead of asking the user.
5. Summarize the deliverables to the user. Interview ends after the summary.

Open trade-offs that surface through interview questions — multiple live interpretations, or a trade-off no experiment settles — run the brainstorm protocol of the `brainstorm` skill first: recon by dispatch, enumerate the interpretations, one batched question round carrying a recommended answer each. The decision log feeds the deliverables.

## Plan

Invocation: `/team plan`.

1. Draft the split. Every subproblem carries: owner role, file scope, check, dependency list. An empty dependency list means the subproblem runs in the current round.
2. Draft the pool. One role per needed specialty. A role is a persona plus a scope.
3. Dispatch one critic per pool role. The prompt names the role as the critic's lens. Every critic answers: what is missing, what is redundant, what overlaps, what is mis-sized, what dependency is unstated.
4. Fold the critique. Revise the split. Record accepted and rejected findings in the state file.
5. Repeat the critique at most once more, and only when the first round found structural problems: a missing subproblem, overlapping scopes, or a cyclic dependency.

Plan writes the state file only. Plan writes no code. Plan ends when the split is recorded and no blocking finding remains.

## Execute

Run one round at a time. Invocation: `/team execute`.

1. Record the starting branch in Notes. Read the state file's Integration branch and Integration checkout fields. If they are empty, the run is top-level: record the branch as `team/integration` and the checkout as the path of the user's checkout. Check out the integration branch in the recorded integration checkout, whether the branch exists or is new: `git -C "<integration checkout>" checkout <integration branch>`, or `git -C "<integration checkout>" checkout -b <integration branch>` when it does not exist. The merge of step 10 never ends up on another branch, such as `main`. A team run inside another team run is not supported yet, so an engineer in a team run does not start its own team run.
2. Select subproblems whose dependencies are done.
3. Create one worktree per engineer, pinned to the current integration commit:

```bash
BASE=$(git rev-parse <integration branch>)
git worktree add ../<repo>-team-<round>-<role> -b team/<round>-<role> "$BASE"
```

`<repo>` names the repository directory. One engineer writes in one worktree. No two engineers share a worktree, so no write conflicts occur.

4. Dispatch engineers per the Dispatch preferences: `parallel` fans out, `one-at-a-time` serializes, `dispatched` uses subagents, `inline` makes the manager the engineer. Every engineer gets: the subproblem, the worktree path, the scope, the check, the base commit, and the sentence "You are the only writer in this worktree."
5. If an engineer emits `[ESCALATE-TO-MANAGER]`, that engineer ends. Let the others finish. The manager resolves the escalation and re-dispatches the subproblem (step 9) or returns it to the pool.
6. The round ends when every dispatched engineer reports back. While it runs, advance other round work: prepare reviewer prompts, update the Split table. An engineer that ends without a report is a dropout. Record the dropout in Rounds and return the subproblem to the pool.
7. Dispatch one reviewer per worktree that produced a report, with the Reviewer prompt template. A reviewer never reviews work it wrote. Worktrees without a report get no review; re-dispatch or end-of-run cleanup removes them.
8. Apply verdicts. ACCEPT passes. PRUNE: the manager removes the listed edits in the worktree and re-runs the check before the merge. REJECT: record the failure and return the subproblem to the pool.
9. A re-dispatched subproblem first removes the stale worktree and branch: `git worktree remove --force <previous worktree path>`, then `git branch -D <previous branch name>`. Then it gets a fresh worktree per step 3 and a new branch `team/<round>-<role>-<attempt>`; `<attempt>` counts the dispatches of that subproblem in the current round and starts at 2.
10. Rebase the engineer's branch onto the run's integration branch, then fast-forward the integration branch onto it, after user consent for the round. Rebase inside the engineer's worktree, where the branch is checked out. Merge inside the recorded integration checkout, which has the integration branch checked out. Before the merge, check the integration checkout is on the integration branch with `git -C "<integration checkout>" rev-parse --abbrev-ref HEAD`; if it is not, stop. Then:

```bash
git -C "<engineer worktree>" rebase <integration branch>
git -C "<integration checkout>" merge --ff-only <branch>
```

`<branch>` is the accepted branch: `team/<round>-<role>`, or `team/<round>-<role>-<attempt>` after a retry. The manager resolves conflicts during the rebase inside the conflicted hunks only.
11. Update the state file: subproblem statuses, round verdicts, decisions.
12. If deliverables remain open, re-split from the remaining state (Plan, including its critique pass) and start the next round.
13. Dispatch a fresh reviewer with the deliverables, the Verification command, and the run's integration checkout path. The reviewer runs every deliverable check plus the build-and-test command. All green marks every deliverable done in the state file and ends `/team execute`. Any failure reopens that deliverable and returns the run to step 12. A deliverable fails at most twice here; the third failure escalates to the user.

## Review

Review audits. Review never edits. Invocation: `/team review`.

1. Dispatch fresh-context reviewers that did not write the work.
2. Run every deliverable check from the state file. Never trust a checked box.
3. List dead worktrees with `git worktree list` and unmerged branches with `git branch --no-merged <integration branch>`.
4. Compare the state file against the repo. Every Split row's Status must match its branch state.
5. Report ranked findings, then end with `REVIEW CLEAN` or the findings list. `/team review` ends there.

## State file `.claude/team.md`

Keep the file self-contained. A fresh session continues from the file alone. The state file is an untracked file at `.claude/team.md` in the user's checkout. It never enters a branch. Only the manager edits it.

Every deliverable check is a shell command that exits non-zero on failure. This contract is the single definition; no other section repeats it.

The manager updates these fields mechanically: Split Status cells, deliverable checkboxes, Rounds appends. Everything else takes judgment.

Rounds are numbered. Round 0 records the critique of the split. Execution rounds start at 1.

```markdown
### Goal
One paragraph: what, why, the expected end state.

### Deliverables
- [ ] D1: <statement>; check: <shell command, non-zero exit on failure>

### Dispatch preferences
- Concurrency: parallel | one-at-a-time
- Engineers: dispatched | inline

### Integration
- Branch: team/integration
- Checkout: <path of the integration checkout>

### Pool
| Role | Specialty |
|------|-----------|

### Split
| # | Subproblem | Role | Scope | Check | Depends on | Status |
|---|------------|------|-------|-------|------------|--------|

### Rounds
| Round | Event | Accepted findings | Rejected findings |
|-------|-------|-------------------|-------------------|

### Verification
Build and test: <shell command, non-zero exit on failure>

### Notes
Decisions, escalation resolutions, review findings.
```

## Roles and harness mapping

| Role | Claude Code | opencode |
|------|-------------|----------|
| Manager | session thread | session thread |
| Engineer | `sonnet-engineer` | `team-engineer` or `general`, else manager inline |
| Critic | `sonnet-engineer` | `explore` |
| Reviewer | fresh `sonnet-engineer` | `team-reviewer` or `explore` |

If the mapped subagent type is not dispatchable in the session, the manager does that work inline and records the fallback in Notes. The manager never plays critic or reviewer on its own work; if no subagent can run those roles, the manager asks the user.

Sanctioned dual-harness conventions outside this section: the slash invocations (`/team ...`), the `.claude/team.md` path, the frontmatter `description`, and the Claude-side frontmatter key `disable-model-invocation`.

## Rules

- The standing rules in `~/.claude/CLAUDE.md` bind every engineer.
- Critics never edit. Reviewers never edit. Engineers edit only their own worktree. The manager edits the state file, PRUNE removals, conflict resolutions, and, when running as an inline engineer, that engineer's worktree.
- A reviewer never validates its own output. Every review uses fresh context.
- Merges and `team/*` deletions need user consent. The manager asks at the start of each execute run, and the answer covers every merge and `team/*` deletion of the run, including end-of-run cleanup.
- Any agent may emit `[ESCALATE-TO-MANAGER] <problem> <options> <recommendation>`. The manager resolves and records the decision in Notes.
- After dispatching agents, the manager advances other round work rather than blocking on results, and does not re-read the agents' files while they run.
- A failure is a REJECT verdict or a dropout; an escalation is not a failure. The third failure of one subproblem escalates to the user.
- Execute records the starting branch in Notes and checks it out again after step 13, before end-of-run cleanup.
- At the end of a run: remove worktrees with `git worktree remove --force`, delete merged and failed `team/*` branches, ask before deleting anything the run did not create, and keep the state file.

## Prompt templates

**Critic:**
```
Attack this split as the <role> critic. Answer five questions: what is missing, what is redundant, what overlaps, what is mis-sized, what dependency is unstated.

Goal: <goal>
Deliverables: <deliverables>
Split: <split table>
Pool: <pool table>

Return findings as a list. Every finding names the subproblem numbers it touches. If you find nothing, say SPLIT CLEAN.
If you cannot judge a point, return [ESCALATE-TO-MANAGER] <problem> <options> <recommendation>.
```

**Engineer:**
```
Execute this bounded subproblem.

Subproblem: <subproblem>
Worktree path: <path>
Scope: <files you own>
Check: <check>
Base commit: <sha>

Work only inside the worktree at <path>. Meet the check, run it, and report changed paths plus the check result. Stay inside scope.
If blocked, return [ESCALATE-TO-MANAGER] <problem> <options> <recommendation>.
```

**Reviewer:**
```
Review work you did not write.

Worktree path: <path>
Diff: <pasted diff, or run `git -C <path> diff <base>..HEAD` when you have shell access>
Check: <check>

Run the check yourself. Read the diff. List out-of-scope edits with file:line. End with one verdict: ACCEPT, PRUNE <file:line list>, or REJECT <reason>.
If you cannot reach a verdict, return [ESCALATE-TO-MANAGER] <problem> <options> <recommendation>.
```

**Final reviewer:**
```
Verify the finished run.

Deliverables: <deliverable list>
Verification: <build-and-test command>
Checkout: <path of the run's integration checkout>

Run every deliverable check. Run the Verification command. Report ALL GREEN or the failing items.
```
