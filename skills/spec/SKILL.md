---
name: spec
description: Use when the user says "write a spec" or "specify": turns a request or decision log into deliverables with checks.
license: MIT
---

# Spec

Spec turns a brainstorm decision log or a raw request into a written specification: deliverables, each
with one check that can fail and a named file scope. The user iterates the draft in batched rounds until
acceptance; only then is it written down and offered for commit.

## Input

Either the decision log from a brainstorm run (`../brainstorm/SKILL.md`) or a user's raw request. A raw
request with open interpretations goes to brainstorm first; spec starts from settled decisions, not from
ambiguity.

## Draft rules

1. Write the spec as a list of deliverables. Every deliverable pairs with one check that can fail — a
   shell command or test that exits non-zero when the deliverable is unmet.
2. A check that cannot fail is rewritten or dropped. If no failing state exists, the deliverable is not
   testable and gets rewritten.
3. Every deliverable names its file scope. A file not listed in any deliverable is out of scope for the
   whole spec.
4. One deliverable, one concern. Two deliverables sharing a file get merged, because no disjoint unit can
   own a shared file.
5. A command that names a value the user must look up goes to the user with that value inline, never a
   placeholder in angle or square brackets. A paste-in-place block that still holds one breaks the run
   after it edits system state, so the failed run and the rerun act on different inputs.
6. An open trade-off is a defect in the draft: send it back to brainstorm rather than encoding a coin
   flip.

## Iteration with the user

1. Show the whole draft once, numbered, so lines can be referenced.
2. The user edits in batched rounds: all change requests of one round fold into one revised draft, shown
   again in full.
3. Questions follow the same batching: one message, each question with a recommended answer, only
   questions only the user can answer.
4. The loop ends at acceptance, not at exhaustion: without the user's acceptance, nothing is written.

## Writing it down

On acceptance, write the spec to:

```
~/repos/memory/<project>/specs/YYYY-MM-DD-<slug>.md
```

- `<project>` is the code repo's name, not the checkout directory. `<slug>` is the spec title in
  kebab-case; the date is today.
- The file carries the spec as accepted, plus the decision log it derives from when one exists.
- Offer to commit the file to that logbook repository. No commit without the user's go.

Spec text the deliverer runs follows the same rule. When a deliverable validates work that ends in a
command block for the user, the spec writes the looked-up value into that block, not a placeholder.

## Handoff

Execution of an accepted spec goes to:

- `parallel` (`../parallel/SKILL.md`) when the deliverables split into one wave of disjoint-file units.
- `team` (`../team/SKILL.md`) when the work needs multiple rounds, critique of the split, or review gates.

State the recommendation in the acceptance message; the user picks.
