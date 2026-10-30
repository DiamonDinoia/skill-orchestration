# Install

An agent follows these steps to install the orchestration skills of this repository. The agent detects
the environment, asks one question round, shows a plan, acts after approval, verifies, and reports.

## Hard rules

1. Ask the user which harnesses to install for. The default is the harness that runs this agent.
2. Fork when the user wants to change skills. When the `gh` user owns this repository, there is
   no self-fork: use the clone.
3. Never ask for or echo a secret value. Ask for provider names only. Never ask for a key value.
4. Show the plan to the user, then wait for the user to approve it. The agent runs a harness plugin command only after the user approves the plan.
   Without approval the agent prints the commands for the user. Skill-folder links need no approval beyond the plan.
5. No backups in the install. If a target path holds anything but the correct link, stop and name the path.
   Do not move, back up or delete it.
6. If a command in an act step exits non-zero, stop and report. Keep all paths as they are.
7. Enclose each path argument in ordinary shell double quotes. Do not add backslashes.
8. Tell the user to restart each installed harness at the end.

## Steps

### 1. Detect

Name the harness that runs this agent, and tell the user. Record the results before asking anything.
Each command below is a probe. An absent result is an answer, not an error.
A probe exit never stops the run. Rule 6 covers the act steps only.
Run these commands:

```sh
for c in hermes claude codex gemini opencode pi openclaw; do command -v "$c" || true; done
for d in "$HOME/.claude" "$HOME/.codex" "${XDG_CONFIG_HOME:-$HOME/.config}/opencode" "${HERMES_HOME:-$HOME/.hermes}"; do test -d "$d" && echo "$d" || true; done
command -v gh >/dev/null && gh api user -q .login || true
test -d "<clone>" && git -C "<clone>" remote -v || true
for f in ".claude-plugin/plugin.json" ".codex-plugin/plugin.json" "gemini-extension.json"; do test -e "<clone>/$f" && echo "$f" || true; done
env | cut -d= -f1 | grep '_API_KEY$' || true
command -v opencode >/dev/null && opencode auth list || true
command -v hermes >/dev/null && hermes config get providers || true
```

The provider lines carry names only, never a key value.

### 2. Ask

Ask the user in one batched question message. Put every question in that one message.
Write each question with the detected default. Questions 1 to 5 and 8 to 10 gate a write.
If a question whose answer gates a write has no answer, stop.

1. Which harnesses get the install? Default: only the harness that runs this agent.
2. Which skills? Default: all six (manager, team, brainstorm, spec, parallel, tiered-subagent-dispatch).
3. Which route per harness? Default: the plugin route for Claude Code, Codex CLI and Gemini CLI;
   links for OpenCode and Hermes.
4. Where does the clone live? Default: the detected clone, else $HOME/.cache/opencode-skills/skill-orchestration.
5. Fork or upstream clone? Default: fork when the user wants to change skills. When the gh user
   owns this repository, there is no self-fork: use the clone.
6. How does the user want updates? Default: the marketplace update on plugin routes, git pull in
   the clone on link routes.
7. Which model providers are configured? Ask for the detected provider names, never a key value.
   Default: the detected names, else the harness defaults. The tier-to-model map is not a question:
   tier-to-model stays a later manual edit of the routing file
   skills/tiered-subagent-dispatch/references/flatiron-routing.json.
8. Hermes: which profile, and should skills.auto_load gain the skill names? Default: the active
   profile, no skills.auto_load change.
9. OpenCode: also link the five command shims and the four tier agents? Default: yes, all three groups.
10. Hermes: also link hermes-dispatch-route into $HOME/.local/bin? Default: yes for Hermes users.

### 3. Plan

Show the plan before any write. One row per link or command, with source path, target path and route.
Name every file the run creates or replaces. Show the exact commands of the plugin routes.
Wait for the user to approve the plan.

### 4. Act

First make the clone the answers name. When the user forked, clone the fork. When the user keeps
upstream, clone https://github.com/DiamonDinoia/skill-orchestration. When the `gh` user owns the
repository, use the clone and skip the fork step.

Claude Code, Codex CLI and Gemini CLI use the plugin route. The agent runs these commands only
after the user approves the plan:

```sh
claude plugin marketplace add DiamonDinoia/skill-orchestration
claude plugin install orchestration@orchestration --scope user
codex plugin marketplace add DiamonDinoia/skill-orchestration
codex plugin add orchestration@orchestration
gemini extensions install https://github.com/DiamonDinoia/skill-orchestration --consent
```

When the user forked, replace DiamonDinoia in these commands with the fork owner.

OpenCode and Hermes use the link route. Link all six skills. The link names come from this table.

| Harness | Group | Link name | Source |
|---|---|---|---|
| OpenCode | skills | `${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/<skill>` | `<clone>/skills/<skill>` |
| OpenCode | commands | `${XDG_CONFIG_HOME:-$HOME/.config}/opencode/commands/<name>.md` | `<clone>/.opencode/command/<name>.md` |
| OpenCode | agents | `${XDG_CONFIG_HOME:-$HOME/.config}/opencode/agents/<tier>.md` | `<clone>/.opencode/agents/<tier>.md` |
| Hermes | skills | `${HERMES_HOME:-$HOME/.hermes}/skills/<skill>` | `<clone>/skills/<skill>` |
| Hermes | binary | `$HOME/.local/bin/hermes-dispatch-route` | `<clone>/skills/tiered-subagent-dispatch/scripts/hermes-dispatch-route` |

`<skill>` runs over manager, team, brainstorm, spec, parallel, tiered-subagent-dispatch. `<name>`
runs over manager, team, brainstorm, spec, parallel. `<tier>` runs over intern, junior, senior,
principal. The binary row needs a yes to question 10.

For each link in the plan, run these steps in order.

1. Resolve the source in the clone with `realpath`. Keep the result as the absolute source.
   Check: the result starts with `/`.
2. Test the link name with `test -L` before `readlink`. If `test -L` exits 0, print `readlink -f`
   of the link name. If the result equals the absolute source and `test -e` of the link name
   exits 0, the link is correct: do no more for this link.
3. If anything else is at the link name, stop and tell the user the path. Do not move, back up or
   delete it.
4. If nothing is at the link name (`test -e` and `test -L` both exit non-zero), make the parent
   folder of the link name when it is absent: `mkdir -p "$(dirname "<link name>")"`. If that
   command exits non-zero, stop and report. Check: `test -d` of the parent folder exits 0.
5. Make the link: `ln -sTn "<absolute source>" "<link name>"`. If that command exits non-zero,
   stop and report.

For the binary row, run one check before the link steps: the source must compile.
`python3 -c 'import sys; compile(open(sys.argv[1]).read(), sys.argv[1], "exec")' "<absolute source>"`.
If that command exits non-zero, stop and report.

### 5. Verify

For each link in the plan, `readlink -f` of the link name equals the absolute source and `test -e` of the link name exits 0.
For plugin routes the list output shows `orchestration`: `claude plugin list`, `codex plugin list`, `gemini extensions list`.
Check the version line: `grep -h '"version"' "<clone>/.claude-plugin/plugin.json" "<clone>/.codex-plugin/plugin.json" "<clone>/gemini-extension.json"` prints `"version": "2.1.0"` and nothing else.

### 6. Report

Report each check result. Tell the user to restart each installed harness. Name every harness the
report covers.

## Update

To update a plugin route, run the marketplace update of the harness. To update a link route, run
git pull in the clone, then run the verify step again. Never pin an old install command as the
update path.

## Uninstall

Remove only the links that resolve into the clone. For each link name in the plan, if `readlink -f`
of the link name is inside the clone, `rm "<link name>"`. Never delete the clone. Never delete a
path the run did not create.

For plugin routes, run the remove command of the harness: `claude plugin disable orchestration@orchestration`, `codex plugin remove orchestration@orchestration`.
For Gemini CLI, run `gemini extensions --help` and use its remove command.

## pi and openclaw

This repository has no verified install route for pi or openclaw. Say so and print nothing to run.
