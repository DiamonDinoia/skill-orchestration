# Delegation capability handoff

When a running child declares it cannot do one named sub-step, hand off just that sub-step to a model that has the capability. Keep the original child running; it owns the integration.

## Examples
- "Kimi has no web search": the original child writes local checks and routes the fetch sub-step through the fallback ladder (`hermes-dispatch-route pick research --needs web`). It reads the excerpts and continues. Same for a model that cannot read images and a UI layout review (a `pick vision` job).
- "opencode needs the provider-prefixed model id": the original child steers its opencode probe to use the prefixed id, not rebuild its whole probe plan.

## Rules
- Do not kill the original child. A capability gap is not a failure.
- Do not do the sub-step yourself. It hides what the original child can still do.
- Do not restart the whole job on a bigger model for a single missing capability.
- For a web or vision gap, never spawn a sibling child with a steer round-trip. Route the sub-step through the fallback ladder instead: a `hermes chat` job with the `pick` flags for that need.
- This is distinct from the manager skill's 'widened scope -> steer' rule, which covers new requirements a user adds. This covers capabilities the child's model lacks.
- The steering message names the exact sub-step, the missing capability, and how its result flows back: `Do step X locally. For step Y, launch a job with a model that has <capability>, feed it your findings, and use its result to continue.`
- A capability probe whose prompt is answerable from training memory proves nothing. The model answers without calling the tool. Use input that only the live tool can return, like an image generated on the spot or a page published after the training cutoff.