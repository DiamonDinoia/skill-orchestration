---
name: team
description: "Use when the user runs /team or asks for round-based multi-agent execution of one task. The manager splits, critics attack, engineers build in worktrees, reviewers check, the manager merges."
disable-model-invocation: true
argument-hint: "[interview|plan|execute|review]"
version: 2.0.0
---

# Team

Team runs one task as rounds. The manager splits the task, critics attack the split, engineers execute subproblems in git worktrees, and reviewers check the work. The manager merges with user consent and ends the run when every deliverable in the state file passes on the integration branch.

Core rules T1-T6, P1, D1 live in the manager skill and bind this skill. This skill never restates them.

## Manager role

The invoking agent is the manager. When the manager skill is installed, its report contract (skill `manager`, references/child-rules.md) binds this run too. Without it, the Roles and harness mapping below stands alone. Inside a child run, the parent answers only from existing user instructions and escalates user-only decisions and consent requests.

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

1. Ask the user the smallest set of questions that makes every deliverable measurable. Ask every design question whose answer can delete or reshape work in the same batch (T3).
2. Write the deliverables and the build-and-test command to the state file.
3. Run every check once. Fix environmental failures, or rewrite the deliverable.
4. If the state file lacks Dispatch preferences, decide the engineer dispatch and record it. It is reversible, so decide without asking the user.
5. Summarize the deliverables to the user. Interview ends there.

The interview can surface an open trade-off, such as a choice no experiment settles. When it does, run the brainstorm skill first (skill `brainstorm`, SKILL.md). The decision log feeds the deliverables. Later questions go to the run report; there is no second interview.

## Plan

1. Draft the split. Every subproblem carries owner role, file scope, check, and dependency list. One concern per subproblem. An empty dependency list means the subproblem runs this round.
2. Draft the pool with one role per needed specialty. A role is a persona plus a scope.
3. Dispatch one critic per pool role with the Critic prompt (references/prompts.md). One critique round answers.
4. Fold the critique. Revise the split. Record accepted and rejected findings in the state file.

Plan writes the state file only, never code, and ends when the split is recorded and no blocking finding remains.

## Execute

Dispatch each subproblem as soon as its dependencies are done. Rounds record state; they never hold back a ready subproblem.

1. Record the starting branch in Notes. If the Integration Branch and Checkout fields are empty, the run is top-level. Set Branch to `team/integration`. Create a dedicated integration worktree from the current commit and record its path in Checkout. The user's checkout never runs `git checkout`, `git stash`, `git restore` or `git reset`. The step-10 merge never lands on another branch. Nested team runs are not supported, so an engineer never starts one. Each worktree path names a fresh directory beside the repository.

```bash
BASE=$(git -C "<user checkout>" rev-parse HEAD)
git -C "<user checkout>" worktree add "<integration worktree path>" -b team/integration "$BASE"
```

2. Select subproblems whose dependencies are done.
3. Create one worktree per engineer, pinned to the current integration commit.

```bash
BASE=$(git rev-parse <integration branch>)
git worktree add "<engineer worktree path>" -b team/<round>-<role> "$BASE"
```

4. Dispatch every selected engineer at once: `dispatched` uses subagents, `inline` makes the manager the engineer. Give each engineer the Engineer prompt (references/prompts.md).
5. An engineer that emits `[ESCALATE-TO-MANAGER]` ends. Let the others finish. Resolve the escalation, then re-dispatch the subproblem (step 9) or return it to the pool.
6. The round ends when every engineer reports back. Record an engineer that ends without a report as a dropout in Rounds, and return the subproblem to the pool. A re-dispatch reruns only the checks the first attempt did not pass.
7. Dispatch one combined reviewer over the merged change set, with the Reviewer prompt (references/prompts.md). The reviewer reports BLOCKER and MAJOR findings only (T1). Per-worktree checks stay the workers' own checks, not reviews. Re-dispatch or end-of-run cleanup removes a worktree without a report.
8. Apply verdicts. ACCEPT passes. On PRUNE, remove the listed edits in the worktree and re-run the check before the merge. PRUNE covers correctness and out-of-scope edits only; log churn removals in Notes instead. On REJECT, record the failure and re-dispatch the subproblem once as a fix round. The re-check after that round covers the fixed findings only (T2).
9. A re-dispatched subproblem removes its stale worktree and branch with `git worktree remove --force <previous worktree path>` and `git branch -D <previous branch name>`. Then it starts fresh per step 3 on branch `team/<round>-<role>-<attempt>`. `<attempt>` counts the dispatches of this subproblem this round and starts at 2.
10. Under the run-level consent (Rules), run `git -C "<integration worktree>" rev-parse --abbrev-ref HEAD`. Stop unless it prints the integration branch. Rebase the engineer branch onto the integration branch inside the engineer worktree. Then:

```bash
git -C "<engineer worktree>" rebase <integration branch>
git -C "<integration worktree>" merge --ff-only <branch>
```

`<branch>` is the accepted branch, `team/<round>-<role>` or its `-<attempt>` variant after a retry. The manager resolves rebase conflicts inside the conflicted hunks only.
11. Update the state file: subproblem statuses, round verdicts, decisions.
12. If deliverables remain open, re-split from the remaining state (Plan). The run holds at most two rounds. Each subproblem takes at most one fix round and one re-check in the whole run (rule T2 in skill `manager`, SKILL.md). After that, hand the open deliverables to the user with options.
13. Mark every deliverable done when its check passes on the integration branch. The third failure of one subproblem escalates to the user.

## Review

Review audits. Review never edits the code or the branch.

1. Have fresh-context reviewers who did not write the work run every deliverable check from the state file.
2. List dead worktrees with `git worktree list` and unmerged branches with `git branch --no-merged <integration branch>`.
3. Compare the state file against the repo. The Status of every Split row must match its branch state.
4. Report BLOCKER and MAJOR findings (T1), then end with `REVIEW CLEAN` or the findings list.

## State file `.claude/team.md`

Keep the file self-contained so a fresh session continues from the file alone. The state file lives untracked at `.claude/team.md` in the user's checkout and never enters a branch. Only the manager edits it.

Every deliverable check is a shell command that exits non-zero while the deliverable is unmet. This is the check shape of the spec skill.

The manager updates Split Status cells, deliverable checkboxes, and Rounds appends mechanically. Everything else takes judgment. Round 0 records the critique of the split. Execution rounds start at 1. The file template is in references/state-file.md.

## Roles and harness mapping

| Role | Tier |
|------|------|
| Manager | session thread |
| Engineer | the cheapest tier that can pass its check: `intern`, `junior`, `senior`, `principal` |
| Critic | `senior` |
| Reviewer | one tier above the engineer |

Briefs name a tier, never a model. The manager skill states the model pinning rule once, and the harness resolves the model at dispatch. If a mapped role has no dispatchable child, the manager does the work inline and records the fallback in Notes. The manager never plays critic or reviewer on its own work. If no child can run those roles, it asks the user.

Cross-harness conventions outside this section: the slash invocations (`/team ...`), the `.claude/team.md` path, the frontmatter `description`, and the Claude-side key `disable-model-invocation`.

## Rules

- The standing rules file of the running harness binds every engineer. Claude Code uses `~/.claude/CLAUDE.md`.
- Critics and reviewers never edit the code or the branch. Engineers edit only their own worktree. The manager edits the state file, PRUNE removals, conflict resolutions, and, as an inline engineer, that engineer's worktree.
- A reviewer never reviews its own work. Every review uses fresh context. One reviewer per change set, no reviewer chains and no final reviewer (T5).
- Merges and `team/*` deletions need user consent. The manager asks once per execute run. The consent names the merge and deletion list it covers; items outside that list re-ask.
- Any agent may emit `[ESCALATE-TO-MANAGER] <problem> <options> <recommendation>`. The manager resolves and records the decision in Notes.
- While agents run, the manager advances other round work and never re-reads the agents' files.
- A failure is a REJECT verdict or a dropout. An escalation is not a failure. The second failure moves the subproblem up one tier (D1). The third failure of one subproblem escalates to the user.
- At cleanup, remove worktrees with `git worktree remove --force` and delete merged and failed `team/*` branches. Ask before deleting anything the run did not create. Keep the state file.
