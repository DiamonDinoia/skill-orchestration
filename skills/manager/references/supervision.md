Load this file on a `[ASYNC DELEGATION CHECKPOINT]` notice, on a steer decision, or on a stop and respawn.

# Supervision

The checkpoint is the periodic wake for running children. A local patch to the harness sends the `[ASYNC DELEGATION CHECKPOINT]` notice on an interval, not the manager checking a clock. The config is `delegation.checkpoint_minutes`, default 30, 0 to turn it off. Each notice arrives in the manager's own turn. It lists all running children in one message. Each entry carries the child's transcript path and the byte offset of the last checkpoint.

## Inspection

On each checkpoint, the manager dispatches one `intern` inspector per child, all in parallel. The inspector reads the transcript from the offset only. It compares the transcript with the brief and the provider fence on line 1. It reports at most 5 lines.

The violation classes are:

- Files out of scope in the brief's file list.
- An ignored stop rule.
- A loop: the same tool call or command with no state change.
- The wrong provider or model for the tier.
- An unapproved push, a restart, or a config edit.
- No progress since the last checkpoint.

## Steer and stop

The first violation gets one steer. The steer quotes the broken rule verbatim and names the step. A steer works only on a live child, and it arrives at the child's next tool result.

The manager stops the child when it ignores one steer. It stops it when it loops. It stops it at once, with no steer, on an unapproved push, a restart, or a config edit. Those three are outward-facing or irreversible. Before stopping for a claimed push, an intern probe child runs `git ls-remote` on the live tip first.

## Respawn

After any stop, an intern probe child records the leftover state first. The probe runs `git rev-parse HEAD`, `git status --short` and `git ls-remote` in the worktree. It names the remote tip. It never relaunches a run the dead child already finished.

The manager then spawns one fresh child. The brief carries the original brief, the leftover state, and one do-not line that names the violation verbatim. The manager escalates one tier for a capability failure. It keeps the tier for a scope violation. A clean checkpoint costs no user message.
