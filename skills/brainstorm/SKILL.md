---
name: brainstorm
description: Use when the user says "brainstorm", "help me decide" or "think this through", or brings a vague design intent. Conversation-only; output is a decision log.
license: MIT
version: 1.4.0
---

# Brainstorm

Settle open design decisions before any spec exists. Explore interpretations by dispatch, ask one batched question round, record what the user chose and rejected. Never edit code.

## When to use

- The request names an intent, not a shape, such as "add search".
- Several materially different designs fit and no running experiment picks one.
- The user cannot yet decide a trade-off, such as API shape or storage.

A request with one reading goes straight to spec. A question the codebase can answer is recon.

## The loop

1. Recon by dispatch. Send independent dispatches in one message.
2. Enumerate the interpretations. Give each reading one line: what it means, costs, closes.
3. Ask one batched question round. Obey the question rules.
4. Fold the answers. Each answer selects a reading. Record the rejected ones with the reason.
5. Record the decision log. Loop to step 2 only for decisions the answers newly opened.

## Recon budget

- Recon runs on subagents only. Cap each report at 30 lines.
- A child that cannot dispatch subagents asks its parent for recon.
- Evidence over 10 lines goes to a file. Report the path and the decisive lines.
- The brainstormer never reads raw logs, listings or diffs itself.

## Question rules

- Ask only what the user alone can answer. Priorities, taste, constraints.
- Anything readable or measurable in the codebase is recon, not a question.
- A parent proxies the user for its child from existing instructions and escalates user-only decisions.
- Every question carries a recommended answer.
- Ask a second round only if an answer opened a new interpretation.

## Scope

Produce decisions, not artifacts. No code edits, no spec writing. An urge to prototype means the decision is settled. Record it and exit.

## Decision log

The deliverable is a markdown table with one row for each settled decision:

| decision | chosen | rejected alternatives | why |
|----------|--------|-----------------------|-----|
| <decision> | <chosen option> | <rejected options> | <reason in one line> |

An empty "why" is not settled. Send the row back through the loop.

## Exit

Exit when every reading is chosen or rejected, or the user says go. Hand off to the spec protocol in `../spec/SKILL.md` with the decision log.
