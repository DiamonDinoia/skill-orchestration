---
name: spec
description: Use when the user says "write a spec" or "specify", or arrives from brainstorm with a decision log. Turns requests into deliverables with failing checks, iterated until accepted.
license: MIT
version: 2.1.0
---

# Spec

Spec turns a decision log or raw request into deliverables, each with one check that can fail and a file scope.

Core rules T1-T6, P1, D1 live in the manager skill and bind this skill. This skill never restates them.

## Input

A decision log from the brainstorm skill, or a raw request. Open interpretations go to the brainstorm skill first.

## Draft rules

1. List the deliverables, each with one check that can fail. Every check is a shell command that exits non-zero while the deliverable is unmet. Other skills cite this check shape.
2. Rewrite or drop a check that cannot fail, and the deliverable with no failing state.
3. Each deliverable names its file scope. Unlisted files are out of scope.
4. One deliverable, one concern. Merge deliverables that share a file. A disjoint unit cannot own one.
5. Commands needing a looked-up value go out with the value inline, never a placeholder. A leftover placeholder breaks the run after it edits system state.
6. Resolve looked-up values before the draft, not after acceptance. One cheap preflight job, such as the latest upstream release or tool availability, keeps a guessed version out of spec text the deliverers pin.
7. An open trade-off is a defect in the draft. Send it back to the brainstorm skill. Do not encode a coin flip.

## Questions before build

List every design question whose answer can delete or reshape work. Batch them in one message with a recommended answer each, before any build starts (T3). A question asked after a build is a spec defect.

## Iteration with the user

1. Show the full draft once, numbered for line reference.
2. Fold each round's requests into one revised draft, shown in full again.
3. Batch the questions per the question rules of the brainstorm skill.
4. A free-text answer that reframes an offered alternative, or that has a question mark, gets one question to make sure of the reading. Do this before the answer goes into the draft. After one confirmation, take the recommended reading and stop asking.
5. At most two revision rounds. Then ask once: accept or drop.
6. Nothing is written without acceptance.

## Writing it down

On acceptance, write to `~/repos/memory/<project>/specs/YYYY-MM-DD-<slug>.md`.

- `<project>` is the code repo name, not the checkout directory. `<slug>` is the kebab-case title. The date is today.
- The file carries the accepted spec plus the decision log when one exists.
- Offer to commit the spec in its memory repository at `~/repos/memory`. No commit without the user's go.

Spec text the deliverer runs follows draft rule 5 too.

## Handoff

Send an accepted spec to the parallel skill for one wave of disjoint-file units. Send it to the team skill for multiple rounds, split critique, or review gates. A unit too big for one leaf splits again before dispatch. State the recommendation in the acceptance message. The user picks.
