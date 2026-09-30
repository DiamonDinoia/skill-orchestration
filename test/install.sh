#!/usr/bin/env bash
# Installs the plugin from /repo with the mechanism of each harness, then proves each one
# sees all five skills (manager, team, brainstorm, spec, parallel).
# Runs inside test/Dockerfile. Collects every result and fails at the end.
set -uo pipefail
repo=${1:-/repo}
fail=0
has() { [[ -f $1 ]] && grep -q "$2" "$1"; } # file, pattern
export -f has
check() { # name, command...
  local name=$1; shift
  if out=$("$@" 2>&1); then echo "PASS $name"; else echo "FAIL $name"; echo "$out" | tail -20; fail=1; fi
}

SKILLS="manager team brainstorm spec parallel"

# Every CLI answers its own --version before anything is gated on it.
for c in claude codex gemini opencode; do check "$c --version: $($c --version 2>&1 | head -1)" "$c" --version; done

# Skill format: agentskills.io name rule and the 1024-character description limit, per skill.
check "frontmatter name/description" python3 - "$repo" <<'EOF'
import re, sys
from pathlib import Path
repo = Path(sys.argv[1])
for want in ["manager", "team", "brainstorm", "spec", "parallel"]:
    text = (repo / "skills" / want / "SKILL.md").read_text()
    fm = text.split("---")[1]
    name = re.search(r"^name: (.+)$", fm, re.M).group(1).strip()
    desc = re.search(r"^description: (.+)$", fm, re.M).group(1).strip()
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64 and name == want, (want, name)
    assert 1 <= len(desc) <= 1024, (want, len(desc))
    print(f"name={name} description={len(desc)} chars")
EOF

on_disk5() { # prefix...
  local dir=$1
  for s in $SKILLS; do
    has "$dir/$s/SKILL.md" "^name: $s$" || { echo "missing/bad $dir/$s/SKILL.md"; return 1; }
  done
}
export -f on_disk5

# Claude Code: plugin marketplace.
check "claude plugin validate --strict" claude plugin validate "$repo" --strict
check "claude marketplace add" claude plugin marketplace add "$repo"
check "claude plugin install" claude plugin install orchestration@orchestration --scope user
check "claude all 5 skills on disk" bash -c \
  'root=$(dirname "$(find ~/.claude/plugins -path "*skills/manager/SKILL.md" | head -1)")/..; on_disk5 "$root/skills"'
check "claude plugin list shows orchestration" bash -c 'claude plugin list | grep -q "orchestration@orchestration"'

# Codex: plugin marketplace (reads .claude-plugin/marketplace.json) and the skills directory.
# A fresh CODEX_HOME per run: the control run shares the machine and must not see the main run's cache.
export CODEX_HOME=$(mktemp -d)
check "codex marketplace add" codex plugin marketplace add "$repo"
check "codex marketplace list shows orchestration" bash -c 'codex plugin marketplace list | grep -q orchestration'
check "codex plugin add" codex plugin add orchestration@orchestration
check "codex plugin cache has all 5 skills" bash -c \
  'root=$(dirname "$(find "$CODEX_HOME/plugins/cache" -path "*skills/manager/SKILL.md" | head -1)")/..; on_disk5 "$root/skills"'
# Codex prefers a native .codex-plugin/plugin.json when present: the cache path carries its version.
# The name assert is the control-run tripwire: TEAM_bad must not satisfy it.
check "codex reads .codex-plugin/plugin.json" python3 - "$repo" <<'EOF'
import json, os, re, sys
from pathlib import Path
home = Path(os.environ["CODEX_HOME"])
repo = Path(sys.argv[1])
codex_v = json.loads((repo / ".codex-plugin/plugin.json").read_text())["version"]
claude_v = json.loads((repo / ".claude-plugin/plugin.json").read_text())["version"]
assert codex_v == claude_v, (codex_v, claude_v)  # one release, two manifests
hit = list(home.glob("plugins/cache/*/*/" + codex_v))
assert hit, "codex did not install from the codex manifest version"
for want in ["manager", "team", "brainstorm", "spec", "parallel"]:
    skill = hit[0] / "skills" / want / "SKILL.md"
    assert skill.exists() and re.search(r"^name: " + want + r"\s*$", skill.read_text(), re.M), skill
print(f"codex native manifest won: {hit[0]}")
EOF

# Gemini CLI: extension.
check "gemini extension install" bash -c "yes | gemini extensions install '$repo' --consent"
check "gemini extensions list shows orchestration" bash -c 'gemini extensions list 2>&1 | grep -q orchestration'
check "gemini all 5 skills on disk" on_disk5 ~/.gemini/extensions/orchestration/skills

# By hand, as in the README, in a fresh home: link each skill dir.
manual=$(mktemp -d)
check "manual symlinks" bash -c \
  "mkdir -p '$manual/.claude/skills' && for s in $SKILLS; do ln -s '$repo/skills/'\$s '$manual/.claude/skills/'\$s; done"
check "manual skills on disk (all 5)" on_disk5 "$manual/.claude/skills"

# The opencode helper script links only opencode's own directories.
check "install-opencode.sh runs" bash "$repo/install-opencode.sh"
check "install-opencode.sh: 5 opencode skills" on_disk5 ~/.config/opencode/skills
check "install-opencode.sh: 5 commands + 4 tier agents" bash -c \
  'for c in manager team brainstorm spec parallel; do [ -e ~/.config/opencode/commands/$c.md ] || exit 1; done &&
   for t in intern junior senior principal; do [ -e ~/.config/opencode/agents/$t.md ] || exit 1; done'

# The parallel wave scheduler ships inside the plugin and self-tests from the installed copy.
waves=$(find ~/.claude/plugins -path "*skills/parallel/scripts/waves.py" | head -1)
check "installed waves.py found" test -f "$waves"
check "installed waves.py selftest" bash -c "python3 '$waves' --selftest | grep -x 'selftest: 5/5 PASS'"

# The model-discovery hook ships with the plugin: hook file, installed copy self-tests, and the
# no-credential session path prints the header (empty mapping) and exits 0, never crashing.
models=$(find ~/.claude/plugins -path "*scripts/models.py" | head -1)
check "hook manifest references models.py" has "$repo/hooks/hooks.json" "models.py"
check "installed models.py found" test -f "$models"
check "installed models.py selftest" bash -c "python3 '$models' --selftest | grep -x 'models selftest: 3/3 PASS'"
check "hook runs clean with no credentials" bash -c \
  'env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY ORCHESTRATION_MODELS_FIXTURE_FILE= \
   CLAUDE_PLUGIN_ROOT=$1 HOME=$(mktemp -d) python3 "$1/scripts/models.py" | grep -q "discovered at session start"' _ "$repo"

(( fail )) && echo "RESULT: FAIL" || echo "RESULT: PASS"
exit $fail
