# orchestration

Five skills that share one pipeline: brainstorm explores a decision, spec pins it down,
parallel and team execute it, and manager is the persistent role the others build on.
Each harness maps the four dispatch tiers (`intern`/`junior`/`senior`/`principal`) to its
own models; the skills name a tier, never a model.

| Skill | Does |
|---|---|
| `brainstorm` | Recon by dispatch → interpretations → one batched question round with recommendations → decision log |
| `spec` | Turns decisions into deliverables, each with a check that can fail; accepted specs land in `memory/<project>/specs/` |
| `parallel` | Executes a spec as disjoint-file dispatch units; `scripts/waves.py` (stdlib `graphlib`) computes waves and the critical path |
| `team` | Multi-agent rounds (triage/plan/execute/review) in worktrees; the invoking agent assumes the manager role |
| `manager` | Persistent orchestration role: spec first, tiered dispatch, hard context budget |

At session start the Claude Code hook runs `scripts/models.py`: it fetches the available model
list from the already-configured provider (Anthropic or OpenAI API key, else the opencode
registry), prints it into context, and the agent tiers the models itself — the only classifier
that tracks new releases. Unconfigured or failed queries print an empty list (harness defaults)
and never block the session; discoveries cache 24h in `~/.cache/orchestration/`. Codex and the
rule-only harnesses have no session hook and keep their own defaults.

## Install

| Harness | Command |
|---|---|
| Claude Code | `claude plugin marketplace add DiamonDinoia/skill-orchestration && claude plugin install orchestration@orchestration --scope user` |
| Codex CLI | `codex plugin marketplace add DiamonDinoia/skill-orchestration`, then `codex plugin add orchestration@orchestration` |
| Gemini CLI | `gemini extensions install https://github.com/DiamonDinoia/skill-orchestration --consent` |
| opencode (by hand, scripted) | `git clone https://github.com/DiamonDinoia/skill-orchestration && ./skill-orchestration/install-opencode.sh` |
| by hand | `git clone https://github.com/DiamonDinoia/skill-orchestration && for s in manager team brainstorm spec parallel; do ln -s "$PWD/skill-orchestration/skills/$s" ~/.claude/skills/$s; done` |

The three harnesses with a native manifest carry one in this repository: `.claude-plugin/` for
Claude Code, `.codex-plugin/` for Codex, and `gemini-extension.json` for Gemini CLI. opencode has
no plugin system — `install-opencode.sh` links the five skills, the five command shims and the
tier agents from a checkout; anything else: symlink by hand (last row).

Rule-only harnesses (Cursor rules, Cline, Windsurf, Kiro, Qoder, Grok, Devin, ...) receive the
manager rule copy — the four other skills orchestrate subagents, which those harnesses lack.
Edit `skills/manager/SKILL.md` and run `scripts/build-rules.sh` to regenerate every rule copy.

Claude Code: in `/plugin`, enable auto-update for the `orchestration` marketplace.
`claude plugin disable orchestration@orchestration` stops the skills. `claude plugin update
orchestration@orchestration` pulls the new release.

Restart the harness after installing. `/manager <task>` starts the role; "stop manager" ends it.
The other four skills trigger on their descriptions or by name (`/team`, `/brainstorm`, ...).

## Validation

`test/run.sh` builds a container with each harness, installs the plugin with each mechanism and
checks that each harness finds all five skills. A copy with an invalid skill name must fail on
the name check. It also runs `skills/parallel/scripts/waves.py --selftest` from the installed copy.

```sh
test/run.sh   # podman, or: test/run.sh docker
```

## License

MIT.
