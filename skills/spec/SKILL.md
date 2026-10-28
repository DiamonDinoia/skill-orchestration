---
name: spec
description: Use when the user says "write a spec" or "specify", or arrives from brainstorm with a decision log. Turns requests into deliverables with failing checks, iterated until accepted.
license: MIT
version: 1.4.0
---

# Spec

Spec turns a decision log or raw request into deliverables, each with one check that can fail and a file scope.

## Input

A brainstorm decision log (`../brainstorm/SKILL.md`) or a raw request. Open interpretations go to brainstorm first.

## Draft rules

1. List the deliverables, each with one check that can fail, a command or test exiting non-zero when unmet.
2. Rewrite or drop a check that cannot fail, and the deliverable with no failing state.
3. Each deliverable names its file scope. Unlisted files are out of scope.
4. One deliverable, one concern. Merge deliverables that share a file. A disjoint unit cannot own one.
5. Commands needing a looked-up value go out with the value inline, never a placeholder. A leftover placeholder breaks the run after it edits system state.
6. Resolve looked-up values before the draft, not after acceptance: one cheap preflight job (latest upstream release, tool availability) keeps a guessed version out of spec text the deliverers pin.
7. An open trade-off is a defect in the draft. Send it back to brainstorm. Do not encode a coin flip.

## Iteration with the user

1. Show the full draft once, numbered for line reference.
2. Fold each round's requests into one revised draft, shown in full again.
3. Batch questions likewise, each with a recommended answer, and only those the user alone can answer.
4. A free-text answer that reframes an offered alternative, or that has a question mark, gets one question to make sure of the reading. Do this before the answer goes into the draft. An assumed reading of such an answer bakes a guess into accepted spec text.
5. The loop ends at acceptance. Nothing is written without it.

## Writing it down

On acceptance, write to `~/repos/memory/<project>/specs/YYYY-MM-DD-<slug>.md`.

- `<project>` is the code repo name, not the checkout directory. `<slug>` is the kebab-case title. The date is today.
- The file carries the accepted spec plus the decision log when one exists.
- Offer to commit to the logbook repository. No commit without the user's go.

Spec text the deliverer runs follows draft rule 5 too.

## Handoff

Send an accepted spec to `parallel` (`../parallel/SKILL.md`) for one wave of disjoint-file units, or `team` (`../team/SKILL.md`) for multiple rounds, split critique, or review gates. State the recommendation in the acceptance message. The user picks.
