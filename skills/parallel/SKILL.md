---
name: parallel
description: Use when the user holds an approved spec with units on disjoint files. A bare "run in parallel" request goes to spec first. Runs every wave of the spec in one run.
license: MIT
version: 2.0.0
---

# Parallel

Run an approved spec as waves of units on disjoint file sets. No spec, no wave.

Core rules T1-T6, P1, D1 live in the manager skill and bind this skill. This skill never restates them.

## Split rule

If two units name one file, merge them and re-check. Unowned files are gaps, not freedom to touch.

## Unit definition

- Deliverable: one statement, checkable on its own.
- Check: a shell command that exits non-zero while the deliverable is unmet. This is the check shape of the spec skill.
- File scope: exactly the disjoint set.
- Tier: `intern`, `junior`, `senior` or `principal`. Start at the cheapest tier that can do the unit. Mechanical to intern, well-specified to junior, judgment to senior, hard-on-sight to principal. Split a unit until its check passes at that tier. A failed check escalates one tier (D1).

## Dispatch and report

Dispatch one wave per message, concurrently within each wave. Start each wave when every dependency of its units is done. Each prompt carries the unit definition verbatim plus the report contract. During the wave, prepare integration; read no unit output.

Report contract: each report obeys the report rules in skill `manager`, references/child-rules.md. The outcome is `done`, `blocked`, `partial`, or `UNRUN: <reason>`. Partial names what is left and why.

## Integration

1. Rerun every check on the integrated tree. Integration feedback rule: a unit that passes alone but fails integrated shared a file. Merge the scopes and redo the split, one re-split pass at most, then report the leftovers.
2. On a failure, escalate one tier for a capability failure and re-split for a scope problem. Never do both. A failure that survives both goes to the user with options; never retry silently.
3. End when every deliverable passes integrated, or the user stops it.
4. Parallel runs no review of its own. The caller runs the T2 review after integration.

## Computing waves

Compute the waves with `python3 scripts/waves.py plan.json` from this skill directory. The plan shape, one example and the exit codes live in skill `parallel`, references/waves.md. Senior and principal take `(critical)` units.
