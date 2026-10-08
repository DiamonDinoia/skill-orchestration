---
name: brainstorm
description: Use when the user says "brainstorm" or "help me decide": settle open design decisions into a decision log first.
license: MIT
---

# Brainstorm

Brainstorm settles open decisions before any spec exists. The brainstormer explores interpretations by
dispatch, asks the user one batched round of questions, and records what was chosen and what was rejected
with reasons. It never edits code; the decisions fold into a spec afterwards.

## When to use

- The request names an intent, not a shape: "add search", "make it pluggable", "speed it up somehow".
- Several materially different designs all fit the request and no running experiment picks one.
- The user carries a trade-off they cannot yet decide (API shape, storage, protocol, dependencies).

Not for: a request with one reading (go straight to spec), or a question the codebase can answer (that is
recon; dispatch it and take the answer).

## The loop

1. Recon by dispatch. Every fact the codebase can answer goes to subagents; the brainstormer's own context
   never reads the tree directly. Independent recon dispatches go out in one message.
2. Enumerate the interpretations. From the recon, list every reading of the request that leads to
   materially different work. Each reading gets one line: what it means, what it costs, what it closes.
3. One batched question round. Distil the readings into the smallest set of questions only the user can
   answer and ask them all in a single message. Question rules below.
4. Fold the answers. Each answer selects an interpretation; the unchosen readings are recorded as rejected
   with the reason (the user's words where given, inferred cost or risk otherwise).
5. Record the decision log. Loop back to step 2 only for decisions the answers newly opened; otherwise
   exit.

## Recon and context budget

- Recon runs on subagents only. A recon report is at most 30 lines; longer goes back for compression.
- A child that cannot dispatch recon subagents requests recon from its parent instead.
- Evidence longer than 10 lines goes to a file; the report carries the path plus the decisive lines.
- The brainstormer never loads raw logs, listings or diffs into its own context.

## Question rules

- Ask only what only the user can answer: priorities, taste, external constraints. Anything readable or
  measurable in the codebase is recon, never a question.
- Inside a child, the parent takes the user's role as a communication proxy: it answers only from existing user instructions and escalates user-only decisions and consent requests to the user.
- Every question carries a recommended answer.
- All questions go in one message. A second round exists only when an answer opened a genuinely new
  interpretation; it is not a licence for trickle questions.

## Scope rule

Brainstorm produces decisions, never artifacts: no implementation, no code edits, no spec writing. An urge
to prototype is a signal the decision is already settled — record it and exit.

## Decision log

The deliverable is a markdown table, one row per settled decision:

| decision | chosen | rejected alternatives | why |
|----------|--------|-----------------------|-----|
| <decision> | <chosen option> | <rejected options> | <reason in one line> |

A row with an empty "why" is not settled; send it back through the loop.

## Exit

Exit when the interpretations are exhausted — every live reading is either chosen or rejected — or the
user says go. Hand off to the spec protocol in `../spec/SKILL.md`, carrying the decision log as its input.
