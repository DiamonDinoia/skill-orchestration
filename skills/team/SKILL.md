---
name: team
description: "Multi-agent orchestration of one task in rounds: the manager splits, critics attack, engineers execute in worktrees, reviewers validate, and the manager merges and re-splits until deliverables pass."
disable-model-invocation: true
argument-hint: "[interview|plan|execute|review]"
version: 1.4.0
---

# Team

Team runs one task as rounds. The manager splits the task, critics attack the split, engineers execute subproblems in git worktrees, and reviewers validate and prune. The manager merges with user consent, re-splits what remains, and ends the run when every deliverable in the state file passes on the integration branch.

## Manager role

The invoking agent is the manager. When `../manager/SKILL.md` exists, its Role, Dispatch tiers, Free-tier children, Context budget, and Report contract rules also bind this run. Without that file, the Roles and harness mapping below stands alone. Inside a child run, the parent answers only from existing user instructions and escalates user-only decisions and consent requests.

## Triage

Run team only when the task has two or more independent subproblems and delegation saves context, latency, or verification cost. Skip Q&A, single commands, and single-file edits.

## Modes

| Argument | Run when |
|----------|----------|
| `interview` | no state file, no Deliverables section, or the user asks |
| `plan` | deliverables exist, no current split |
| `execute` | a split has open subproblems |
| `review` | all deliverables pass, or the user asks |

With no argument, pick the first matching row.

## Interview

Produce deliverables a reviewer can check without contacting the user.

1. Ask the user the smallest set of questions that makes every deliverable measurable.
2. Write the deliverables and the build-and-test command to the state file.
3. Run every check once. Fix environmental failures, or rewrite the deliverable.
4. If the state file lacks Dispatch preferences, decide concurrency and engineer dispatch, and record both. Both are reversible, so decide without asking the user.
5. Summarize the deliverables to the user. Interview ends there.

The interview can surface an open trade-off, such as a choice no experiment settles. When it does, run the `brainstorm` protocol first: recon by dispatch, enumerate interpretations, one batched question round, one recommended answer each. The decision log feeds the deliverables.

## Plan

1. Draft the split. Every subproblem carries owner role, file scope, check, and dependency list. An empty dependency list means the subproblem runs this round.
2. Draft the pool with one role per needed specialty. A role is a persona plus a scope.
3. Dispatch one critic per pool role with the Critic prompt below.
4. Fold the critique. Revise the split. Record accepted and rejected findings in the state file.
5. Repeat the critique at most once, and only when round one found structural problems: a missing subproblem, overlapping scopes, or a cyclic dependency.

Plan writes the state file only, never code, and ends when the split is recorded and no blocking finding remains.

## Execute

Run one round at a time.

1. Record the starting branch in Notes. If the Integration Branch and Checkout fields are empty, the run is top-level. Set Branch to `team/integration` and Checkout to the user's checkout path. Run `git -C "<integration checkout>" checkout <integration branch>`, adding `-b` when the branch is new. The step-10 merge never lands on another branch. Nested team runs are not supported, so an engineer never starts one.
2. Select subproblems whose dependencies are done.
3. Create one worktree per engineer, pinned to the current integration commit. `<repo>` names the repository directory.

```bash
BASE=$(git rev-parse <integration branch>)
git worktree add ../<repo>-team-<round>-<role> -b team/<round>-<role> "$BASE"
```

4. Dispatch engineers per the Dispatch preferences: `parallel` fans out, `one-at-a-time` serializes, `dispatched` uses subagents, `inline` makes the manager the engineer. Give each engineer the Engineer prompt below.
5. An engineer that emits `[ESCALATE-TO-MANAGER]` ends. Let the others finish. Resolve the escalation, then re-dispatch the subproblem (step 9) or return it to the pool.
6. The round ends when every engineer reports back. Record an engineer that ends without a report as a dropout in Rounds, and return the subproblem to the pool.
7. Dispatch one reviewer per worktree that reported, with the Reviewer prompt below. A worktree without a report gets no review, and re-dispatch or end-of-run cleanup removes it.
8. Apply verdicts. ACCEPT passes. On PRUNE, remove the listed edits in the worktree and re-run the check before the merge. On REJECT, record the failure and return the subproblem to the pool.
9. A re-dispatched subproblem removes its stale worktree and branch with `git worktree remove --force <previous worktree path>` and `git branch -D <previous branch name>`. Then it starts fresh per step 3 on branch `team/<round>-<role>-<attempt>`. `<attempt>` counts the dispatches of this subproblem this round and starts at 2.
10. After user consent for the round, run `git -C "<integration checkout>" rev-parse --abbrev-ref HEAD`. Stop unless it prints the integration branch. Rebase the engineer branch onto the integration branch inside the engineer worktree. Then:

```bash
git -C "<engineer worktree>" rebase <integration branch>
git -C "<integration checkout>" merge --ff-only <branch>
```

`<branch>` is the accepted branch, `team/<round>-<role>` or its `-<attempt>` variant after a retry. The manager resolves rebase conflicts inside the conflicted hunks only.
11. Update the state file: subproblem statuses, round verdicts, decisions.
12. If deliverables remain open, re-split from the remaining state (Plan, including its critique pass) and start the next round.
13. Dispatch a fresh reviewer with the Final reviewer prompt below. On ALL GREEN, mark every deliverable done and end `/team execute`. A failure reopens that deliverable and returns the run to step 12. The third failure of one deliverable escalates to the user.

## Review

Review audits. Review never edits.

1. Have fresh-context reviewers who did not write the work run every deliverable check from the state file.
2. List dead worktrees with `git worktree list` and unmerged branches with `git branch --no-merged <integration branch>`.
3. Compare the state file against the repo. The Status of every Split row must match its branch state.
4. Report ranked findings, then end with `REVIEW CLEAN` or the findings list.

## State file `.claude/team.md`

Keep the file self-contained so a fresh session continues from the file alone. The state file lives untracked at `.claude/team.md` in the user's checkout and never enters a branch. Only the manager edits it.

Every deliverable check is a shell command that exits non-zero on failure. This contract is the single definition. No other section repeats it.

The manager updates Split Status cells, deliverable checkboxes, and Rounds appends mechanically. Everything else takes judgment. Round 0 records the critique of the split. Execution rounds start at 1.

```markdown
### Goal
What, why, the expected end state.

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

If a mapped subagent type is not dispatchable, the manager does the work inline and records the fallback in Notes. The manager never plays critic or reviewer on its own work. If no subagent can run those roles, it asks the user.

Cross-harness conventions outside this section: the slash invocations (`/team ...`), the `.claude/team.md` path, the frontmatter `description`, and the Claude-side key `disable-model-invocation`.

## Rules

- The standing rules in `~/.claude/CLAUDE.md` bind every engineer.
- Critics and reviewers never edit. Engineers edit only their own worktree. The manager edits the state file, PRUNE removals, conflict resolutions, and, as an inline engineer, that engineer's worktree.
- A reviewer never reviews its own work. Every review uses fresh context.
- Merges and `team/*` deletions need user consent. The manager asks once per execute run, and the answer covers the whole run, including end-of-run cleanup.
- Any agent may emit `[ESCALATE-TO-MANAGER] <problem> <options> <recommendation>`. The manager resolves and records the decision in Notes.
- While agents run, the manager advances other round work and never re-reads the agents' files.
- A failure is a REJECT verdict or a dropout. An escalation is not a failure. The third failure of one subproblem escalates to the user.
- After step 13, check out the starting branch before cleanup. At cleanup, remove worktrees with `git worktree remove --force` and delete merged and failed `team/*` branches. Ask before deleting anything the run did not create. Keep the state file.

## Prompt templates

**Critic:**
```
Attack this split as the <role> critic. Answer: what is missing, what is redundant, what overlaps, what is mis-sized, what dependency is unstated.

Goal: <goal>
Deliverables: <deliverables>
Split: <split table>
Pool: <pool table>

List findings with the subproblem numbers each touches. If you find nothing, say SPLIT CLEAN.
Cannot judge a point: [ESCALATE-TO-MANAGER] <problem> <options> <recommendation>.
```

**Engineer:**
```
Execute this bounded subproblem. You are the only writer in this worktree.

Subproblem: <subproblem>
Worktree path: <path>
Scope: <files you own>
Check: <check>
Base commit: <sha>

Work only inside this worktree and stay in scope. Run the check and report changed paths plus its result.
Blocked: [ESCALATE-TO-MANAGER] <problem> <options> <recommendation>.
```

**Reviewer:**
```
Review work you did not write.

Worktree path: <path>
Diff: <pasted diff, or run `git -C <path> diff <base>..HEAD` when you have shell access>
Check: <check>

Run the check yourself. Read the diff. List out-of-scope edits with file:line. End with one verdict: ACCEPT, PRUNE <file:line list>, or REJECT <reason>.
No verdict possible: [ESCALATE-TO-MANAGER] <problem> <options> <recommendation>.
```

**Final reviewer:**
```
Verify the finished run.

Deliverables: <deliverable list>
Verification: <build-and-test command>
Checkout: <path of the run's integration checkout>

Run every deliverable check. Run the Verification command. Report ALL GREEN or the failing items.
```
