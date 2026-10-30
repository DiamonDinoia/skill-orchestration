Load this file when resolving models, lanes, web-verification nodes or a Sol round.

# Routing and models

Model routing facts live in skill `tiered-subagent-dispatch`, references/routing-mechanics.md. On conflict that skill wins. This file holds the manager rules that sit on top of those facts.

## Pin checks

The pinned reviewer model of the classification table is checked on the job's own runtime line. That is the completion header, the first report line, or the log's provider line. The check does not trust the report's own provider line. A route can substitute a model without an error. Substitution mechanics live in skill `tiered-subagent-dispatch`, references/routing-mechanics.md.
When a banner names one model and the body line names another, the manager relays both names to the user and trusts neither one.
When the runtime hides the model id, the report prints the launch line value with source `launch pin`. The manager compares it to the launch log.

## Web-verification nodes

The manager checks that analysis children on web-less models quote only the excerpt file of the fetch child. Any fact outside that file stays marked UNVERIFIED. Model web facts live in skill `tiered-subagent-dispatch`, references/routing-mechanics.md.

## Review-skill load and the Hermes one-shot

Only on Hermes load `ponytail-review` in a `hermes chat` one-shot with `-s ponytail:ponytail-review`.

## User route override

A user route override binds the named task only. The next task returns to the binding's route. The override takes effect at the next spawn. Do not steer a live child to change its model. Model resolution and pin behaviour live in skill `tiered-subagent-dispatch`, references/routing-mechanics.md.

## User model ban

A user model ban is session-scoped. It binds every task until the user lifts it.

## Numeric claims

A numeric claim that stays identical before and after the reported edit fails arithmetic. The manager checks the claimed values against the diff at the stated tip sha before it relays them.

## Dispatch waves

Each dispatch wave names the tier and the quota class of every lane in the report. A move to a paid or subscription model is a named escalation that needs the user's approval. A paid lane states its escalation reason.

## UI deliverables

A deliverable with rendered UI ships its screenshots through a vision check before the batch reports done.

## Rank table

On user request the manager shows the rank table and each tier's eligibility rules. It never reconstructs a rationale.
