# orchestration

Six skills share one split-execute-review pipeline. Per-skill scope: `brainstorm` decides, `spec`
pins the decision, `parallel` runs one wave of disjoint-file units, `team` runs rounds in worktrees,
and `manager` owns the dispatch graph and the shared review contract (rules T1-T6, P1, D1, R1 in
skill `manager`, SKILL.md). `tiered-subagent-dispatch` runs the delegation ladder in Hermes.
Each harness maps the four dispatch tiers (`intern`/`junior`/`senior`/`principal`) to its
own models; the skills name a tier, never a model.

| Skill | Does |
|---|---|
| `brainstorm` | Recon by dispatch → interpretations → one batched question round with recommendations → decision log |
| `spec` | Turns decisions into deliverables, each with a check that can fail; accepted specs land in `~/repos/memory/<project>/specs/` |
| `parallel` | Executes a spec as disjoint-file dispatch units; `scripts/waves.py` (stdlib `graphlib`) computes waves and the critical path |
| `team` | Multi-agent rounds (triage/plan/execute/review) in worktrees; the invoking agent assumes the manager role |
| `manager` | Persistent orchestration role: spec first, tiered dispatch, hard context budget |
| `tiered-subagent-dispatch` | Delegation in Hermes: best flatiron model, Sonnet, Opus, then blind review |

At session start the Claude Code hook runs `scripts/models.py`: it fetches the available model
list from the already-configured provider (Anthropic or OpenAI API key, else the opencode
registry), prints it into context, and the agent tiers the models itself — the only classifier
that tracks new releases. Unconfigured or failed queries print an empty list (harness defaults)
and never block the session; discoveries cache 24h in `~/.cache/orchestration/`. Codex and the
rule-only harnesses have no session hook and keep their own defaults.

## Install

Tell your agent: Follow INSTALL.md in <clone>

The agent detects the environment, asks one batched question round with detected defaults, shows
the plan, acts after approval, verifies and reports. The plugin routes also work by hand:

| Harness | Command |
|---|---|
| Claude Code | `claude plugin marketplace add DiamonDinoia/skill-orchestration && claude plugin install orchestration@orchestration --scope user` |
| Codex CLI | `codex plugin marketplace add DiamonDinoia/skill-orchestration`, then `codex plugin add orchestration@orchestration` |
| Gemini CLI | `gemini extensions install https://github.com/DiamonDinoia/skill-orchestration --consent` |

The three harnesses with a native manifest carry one in this repository: `.claude-plugin/` for
Claude Code, `.codex-plugin/` for Codex, and `gemini-extension.json` for Gemini CLI.
OpenCode has a `plugin` subcommand, but this repository keeps the link route for it:
`INSTALL.md` links the six skills, the five command shims and the four tier agents into
`${XDG_CONFIG_HOME:-$HOME/.config}/opencode/`. Hermes takes links into `${HERMES_HOME:-$HOME/.hermes}/skills`.
`tiered-subagent-dispatch` runs the delegation ladder in Hermes and links wherever the user asks.

Rule-only harnesses (Cursor rules, Cline, Windsurf, Kiro, Qoder, Grok, Devin, ...) receive the
manager rule copy. The other skills orchestrate subagents, which those harnesses lack.
Edit `skills/manager/SKILL.md` and run `scripts/build-rules.sh` to regenerate every rule copy.

Claude Code: in `/plugin`, enable auto-update for the `orchestration` marketplace.
`claude plugin disable orchestration@orchestration` stops the skills. `claude plugin update
orchestration@orchestration` pulls the new release.

Restart the harness after installing. `/manager <task>` starts the role; "stop manager" ends it.
The other skills trigger on their descriptions or by name (`/brainstorm`, `/spec`, `/parallel`).
`team` triggers by name only (`/team`).

## Validation

`test/run.sh` builds a container with each harness, installs the plugin with each mechanism and
checks that each harness finds all five generic skills. A copy with an invalid skill name must fail on
the name check. It also runs `skills/parallel/scripts/waves.py --selftest` from the installed copy.

```sh
test/run.sh   # podman, or: test/run.sh docker
```

## Version 2.1.0

Install is agent-led: `INSTALL.md` detects the environment, asks one batched question round with
detected defaults, shows the plan, waits for approval, acts, verifies and reports. Every loop ends
after one review, one fix round and one re-check of the fixed findings (rules T1-T6 in skill
`manager`, SKILL.md). Parallel fan-out starts every independent unit at once (P1). Divide and
conquer splits work into leaves for the cheap tiers (D1). The manager core is short and its
references load on trigger, so `AGENTS.md` carries only the core. `dag.py` adds `add` and `plan`.
`CHANGELOG.md` lists every change.

## License

MIT.
