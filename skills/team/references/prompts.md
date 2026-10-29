# Prompt templates

Fill every `<...>` slot. Briefs name a tier, never a model.

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

Work only inside this worktree and stay in scope. Run the check. If the subproblem is too hard for your tier, split it or escalate.
Report per the report rules in skill `manager`, references/child-rules.md. They cover the changed paths and the check result.
Blocked: [ESCALATE-TO-MANAGER] <problem> <options> <recommendation>.
```

**Reviewer:**
```
Review work you did not write.

Worktree path: <path>
Diff: <pasted diff, or run `git -C <path> diff <base>..HEAD` when you have shell access>
Check: <check>

Run the check yourself. Read the diff. Report BLOCKER and MAJOR findings only. List out-of-scope edits with file:line. End with one verdict: ACCEPT, PRUNE <file:line list>, or REJECT <reason>.
No verdict possible: [ESCALATE-TO-MANAGER] <problem> <options> <recommendation>.
```
