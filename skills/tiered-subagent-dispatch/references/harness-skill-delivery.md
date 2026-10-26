# How skills reach a child, per harness (for the step 0b preflight)

Check the mechanism of the harness the child runs in, then prove it with the worker's first-reply quote (step 5b).

| Harness | Standing skills (ste, unslop) | Ponytail | Task skills | Notes |
|---|---|---|---|---|
| Hermes `hermes chat` | `skills.auto_load` in config.yaml | plugin `~/.hermes/plugins/ponytail` (`pre_llm_call` hook) does the injection; ponytail is not a skill | `-s <skill>`, repeatable | Leave the `ponytail` auto_load entry in place: it is harmless, and removing it is churn that every review flags. `delegate_task` children skip auto_load: the goal names each skill and says to load it with `skill_view` |
| Claude Code | SubagentStart hook `~/.claude/hooks/subagent-ste-unslop.sh` (`hookSpecificOutput.additionalContext`) | the ponytail Claude plugin has its own SubagentStart hook (`ponytail-subagent.js`); the ste/unslop hook must not inject it again | marketplace plugins (`<name>@<name>` in installed_plugins.json) | Claude Code passes additionalContext whole up to 10000 chars; above that it saves the text to disk and the subagent sees only a 2000-char preview. The hook gives each skill its own share of 10000, cuts each part at the last whole line, keeps each source optional, and strips frontmatter only when line 1 is `---`. Read every skill from its installed SKILL.md; a hard-coded digest drifts |
| Codex | `~/.codex/hooks.json` calls the dotfiles script `~/.codex/hooks/read-ste.sh`: it reads the newest `~/.codex/plugins/cache/ste/ste/<ver>/skills/ste/SKILL.md` that exists (`sort -V -r`), else `~/.codex/skills/ste/SKILL.md`, else prints one stderr line and exits 0 | plugin config | Codex plugin marketplace (`codex plugin list`) | Keep hook commands as plain script paths: an inline `$(...)` lookup breaks `check-ai-sync`'s hook-path check, and an empty lookup turns into a relative path that reads a `skills/ste/SKILL.md` from the cwd. A plugin skill plus a `~/.codex/skills` copy of the same name is a duplicate. A private marketplace repo on a host without `gh` needs the ssh remote (`git@github.com:`) |
| opencode | `~/.config/opencode/skills/` | npm plugin under `~/.config/opencode/node_modules/`; its pinned dep must be installed there (`npm install` in `~/.config/opencode`), else the plugin wrapper loads nothing | same skills dir | model ids must be provider-prefixed (`kimi-k3/moonshotai/Kimi-K3`). The 2.x CLI ships as npm `@opencode/cli` (`opencode-ai` stops at 1.18.x); a dotfiles config written for 2.x does not start on 1.18 |

Before a hook or config change that enforces a harness limit, find the real number in the installed CLI (docs, or `rg` in its bundle) and cite it in the code comment. A guessed limit cut both skills for nothing and cost two review rounds.

## Updating owned-skill installs

Owned skills (`DiamonDinoia/skill-*`) come from each harness's marketplace, never from a symlink into `~/repos/skills`.

- Hermes: `hermes skills update <name>`, or `hermes skills install DiamonDinoia/<repo>/<skill> --force --yes`. A pinned skills.sh install command reinstalls the old text.
- Claude Code / Codex: update the plugin from its marketplace, then check the version in the plugin list.
- opencode: the installer cache `~/.cache/opencode-skills/<repo>` must be a real `git clone`; update with `git -C <cache> pull && <cache>/install-opencode.sh`. A hand-copied cache cannot update; move it to the attic and clone again instead of adding installer options.

Installed Hermes copies carry `metadata: github-*` frontmatter added by the installer: that is install metadata, not
a local change, so it is never upstreamed.
