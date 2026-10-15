---
name: parallel
description: Use when the user says "run in parallel" or holds an approved spec with units on disjoint files. Runs one concurrent wave, re-splits leftovers.
license: MIT
version: 1.4.0
---

# Parallel

Run an approved spec as one concurrent wave of units on disjoint file sets. No spec, no wave.

## Split rule

If two units name one file, merge them and re-check. Unowned files are gaps, not freedom to touch.

## Unit definition

- Deliverable: one statement, checkable on its own.
- Check: a command exiting nonzero while the deliverable is unmet.
- File scope: exactly the disjoint set.
- Tier: `intern`, `junior`, `senior` (default) or `principal`, cheapest that meets the check. Mechanical to intern, well-specified to junior, judgment to senior, hard-on-sight to principal.

## Dispatch and report

Dispatch all units in one concurrent message. Each prompt carries the unit definition verbatim plus the report contract. During the wave, prepare integration; read no unit output.

Report contract (30 lines max):

1. Outcome: done, blocked, or partial; partial names what is left and why.
2. Evidence: check command, exit status, up to 10 decisive lines verbatim; longer output goes to a file, report its path.
3. Open decisions, each with options and a recommendation.

## Integration

1. Rerun every check on the integrated tree. A unit passing alone but failing integrated shared a file; merge the scopes, redo the split.
2. Re-split failed or blocked units into the next wave. A failure surviving re-split goes to the user with options; never retry silently.
3. End when every deliverable passes integrated, or the user stops it.

## Computing waves

For multiple units, write `plan.json`, one entry per unit: `name`, `files`, optional `depends`, `cost` (intern 1, junior 2, senior 3, principal 4). Then run:

    python3 scripts/waves.py plan.json

relative to this skill. Nonzero exit means overlap, cycle, or bad input; fix the split, not the plan. Dispatch waves in order, concurrently within each; senior/principal take `(critical)` units.
