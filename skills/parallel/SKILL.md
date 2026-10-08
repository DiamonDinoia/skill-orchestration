---
name: parallel
description: Use when the user says "run in parallel": parallel-execute an approved spec whose units touch disjoint files.
license: MIT
---

# Parallel

Parallel executes an approved spec or plan as one concurrent wave of independent units. Each unit owns a
disjoint file set, carries one deliverable with a check, and is staffed by tier. Leftovers after
integration feed the next wave.

## Input

An approved spec or plan — from the spec protocol, from the user, or from a team split. No spec, no wave:
an underspecified request goes back; it is not split here.

## Split rule

Split only along disjoint file sets. A file named in two units means the split is wrong: merge those units
and re-check disjointness. Directory-level scopes are disjoint only when no file can fall in both. A file
no unit owns is a gap in the split, not freedom to touch.

## Unit definition

Every unit carries:

- Deliverable: one statement, checkable on its own.
- Check: a command that exits non-zero while the deliverable is unmet.
- File scope: exactly the disjoint set above; a file not listed is out of scope.
- Tier: `intern`, `junior`, `senior` or `principal` — the manager skill's tiers. Intern takes mechanical,
  junior the well-specified, senior (the default) anything with judgment calls, principal the hard-on-sight
  work. The cheapest tier that can meet the check takes it.

## Dispatch

One message, all units dispatched concurrently. Every dispatch prompt states the unit definition verbatim
plus the report contract below. While the wave runs, prepare integration; read nothing the units write.

## Report contract (per unit, ≤30 lines)

1. Outcome: done, blocked, or partial — partial names what is left and why.
2. Evidence: the check that ran, the exact command, its exit status, at most 10 decisive lines verbatim.
   Longer evidence goes to a file; the report carries the path.
3. Open decisions, each with options and a recommendation.
4. Nothing else.

## Integration and next wave

1. Rerun every unit's check on the integrated tree. A unit that passed alone and fails integrated collided
   with the split rule: find the shared file, merge the units' scopes, redo the split.
2. A failed or blocked unit re-splits into the next wave under the same rules. A failure that survives a
   re-split goes to the user with options; never retry silently.
3. The run ends when every deliverable passes on the integrated tree, or the user stops it.

## Computing waves

A spec with more than one unit gets a `plan.json`: one entry per unit with `name`, `files`, optional
`depends` on unit names, and `cost` from the tier — intern 1, junior 2, senior 3, principal 4. Then run:

    python3 scripts/waves.py plan.json

relative to this skill. A nonzero exit means the split is wrong — overlap, cycle or bad input — so fix
the split, not the plan. Dispatch the printed waves concurrently, wave after wave; put senior/principal
on the `(critical)` units.
