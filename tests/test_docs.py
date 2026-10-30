"""Doc pins for INSTALL.md and README.md: the install rules of INSTALL.md, the
README pointer, and the tokens the install must never bring back. One observed
negative per pin: each mutation removes one rule and the pin must fail loud.

Runs standalone (python3 tests/test_docs.py) and under pytest.
"""
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
INSTALL = REPO_ROOT / "INSTALL.md"

# The one mkdir INSTALL.md allows creates the parent folder of the link name.
MKDIR_CMD = 'mkdir -p "$(dirname "<link name>")"'

# The retired installer name. Built from fragments so this file does not hold it.
SCRIPT_NAME = "install-" "opencode" ".sh"

README_POINT = "Follow INSTALL.md in <clone>"
PLUGIN_COMMANDS = {
    "Claude Code": "claude plugin marketplace add",
    "Codex CLI": "codex plugin marketplace add",
    "Gemini CLI": "gemini extensions install",
}

# The hard rules and steps of INSTALL.md. One pin per rule. Each phrase must sit
# on one line of INSTALL.md: the mutation drops the lines that carry the phrases.
INSTALL_RULES = {
    "harness scope ask": ("Ask the user which harnesses to install for",
                          "The default is the harness that runs this agent"),
    "fork rule": ("Fork when the user wants to change skills", "no self-fork: use the clone"),
    "no secrets": ("Never ask for or echo a secret value", "Ask for provider names only",
                   "Never ask for a key value"),
    "plan approval": ("Show the plan to the user, then wait for the user to approve it.",),
    "plugin command gating": ("The agent runs a harness plugin command only after the user approves the plan.",
                              "Without approval the agent prints the commands"),
    "links approval": ("Skill-folder links need no approval beyond the plan",),
    "no backups": ("No backups in the install", "stop and name the path",
                   "Do not move, back up or delete it"),
    "failure rule": ("If a command in an act step exits non-zero, stop and report",
                      "Keep all paths as they are"),
    "detect probes": ("An absent result is an answer, not an error",
                      "A probe exit never stops the run"),
    "guarded probes": ("command -v gh >/dev/null", "command -v opencode >/dev/null",
                       "command -v hermes >/dev/null"),
    "provider names only": ("cut -d= -f1", "grep '_API_KEY$'"),
    "ordinary quotes": ("ordinary shell double quotes", "Do not add backslashes"),
    "restart hint": ("Tell the user to restart each installed harness",),
    "detect first": ("Record the results before asking anything",),
    "detect commands": ("command -v", "gh api user -q .login", "remote -v"),
    "one batched question": ("one batched question message",
                             "Write each question with the detected default"),
    "write gating": ("gates a write", "has no answer, stop"),
    "tier map deferred": ("tier-to-model stays a later manual edit of the routing file",
                          "flatiron-routing.json"),
    "plan contents": ("One row per link or command, with source path, target path and route",),
    "absolute source": ("Resolve the source in the clone with `realpath`",
                        "Keep the result as the absolute source"),
    "state test first": ("`test -L` before `readlink`",),
    "correct link stops": ("do no more for this link",),
    "mkdir parent-only": (MKDIR_CMD,),
    "link flags": ("ln -sTn",),
    "link resolves": ("`readlink -f` of the link name equals the absolute source",
                      "`test -e` of the link name exits 0"),
    "binary compile check": ("the source must compile",),
    "version line": ('"version": "2.1.0"',),
    "plugin list verify": ("`claude plugin list`", "`codex plugin list`", "`gemini extensions list`"),
    "update section": ("the marketplace update", "git pull in the clone"),
    "uninstall scope": ("Remove only the links that resolve into the clone", "Never delete the clone"),
    "plugin uninstall": ("claude plugin disable orchestration@orchestration",
                         "codex plugin remove orchestration@orchestration"),
    "pi openclaw": ("no verified install route for pi or openclaw", "print nothing to run"),
    "link paths": ("${XDG_CONFIG_HOME:-$HOME/.config}/opencode", "${HERMES_HOME:-$HOME/.hermes}/skills"),
    "six skills": ("Link all six skills",),
}

# Tokens the install must never bring back.
FORBIDDEN_TOKENS = {
    "no .bak-": (".bak-",),
    "no ln -sfn": ("ln -sfn",),
    "no rm -rf": ("rm -rf",),
    "no old install script": (SCRIPT_NAME,),
}

README_RULES = {
    "opencode plugin note": ("OpenCode has a `plugin` subcommand", "keeps the link route"),
    "version heading": ("## Version 2.1.0",),
}


def install_findings(text):
    """One finding per missing or broken INSTALL.md rule; empty when complete."""
    findings = []
    for rule, phrases in INSTALL_RULES.items():
        for phrase in phrases:
            if phrase not in text:
                findings.append(f"INSTALL.md misses the {rule} rule: {phrase}")
    for rule, tokens in FORBIDDEN_TOKENS.items():
        for token in tokens:
            if token in text:
                findings.append(f"INSTALL.md breaks the {rule} rule: it keeps the token {token!r}")
    if "mkdir" in text.replace(MKDIR_CMD, ""):
        findings.append("INSTALL.md breaks the mkdir parent-only rule: it runs `mkdir` outside the parent folder of the link name")
    return findings


def install_file_findings(root):
    """Check INSTALL.md under root. A missing file is one finding."""
    path = Path(root) / "INSTALL.md"
    if not path.is_file():
        return ["INSTALL.md is missing"]
    return install_findings(path.read_text())


def readme_findings(text):
    findings = []
    if README_POINT not in text:
        findings.append("README does not point to INSTALL.md")
    for harness, command in PLUGIN_COMMANDS.items():
        if harness not in text:
            findings.append(f"README misses the {harness} row")
        if command not in text:
            findings.append(f"README misses the {harness} command: {command}")
    for rule, phrases in README_RULES.items():
        for phrase in phrases:
            if phrase not in text:
                findings.append(f"README misses the {rule} rule: {phrase}")
    return findings


def script_absence_findings(root):
    """The retired installer name must stay out of README, INSTALL.md, test and tests."""
    root = Path(root)
    targets = [root / "README.md", root / "INSTALL.md"]
    for folder in ("test", "tests"):
        if (root / folder).is_dir():
            targets += [p for p in (root / folder).rglob("*") if p.is_file()]
    findings = []
    for path in targets:
        if path.is_file() and SCRIPT_NAME in path.read_text(errors="ignore"):
            findings.append(f"{path.relative_to(root)} keeps the old install script name")
    return findings


def drop_lines(text, *needles):
    lines = text.splitlines(keepends=True)
    kept = [ln for ln in lines if not any(n in ln for n in needles)]
    assert kept != lines, f"no line matched {needles}"
    return "".join(kept)


def insert_token(token):
    return lambda root, t: t.replace("# Install\n", f"# Install\n\n{token}\n", 1)


def build_mutations():
    """One entry per pin: name, file, checker, mutator that removes the rule."""
    mutations = [
        ("INSTALL.md exists", None, install_file_findings, lambda root, t: root),
        ("README points to INSTALL.md", "README.md", readme_findings,
         lambda root, t: t.replace(README_POINT, "")),
        ("old install script absent", "README.md", script_absence_findings,
         lambda root, t: t.replace("# orchestration", f"# orchestration\n{SCRIPT_NAME}")),
    ]
    for rule, phrases in INSTALL_RULES.items():
        mutations.append((rule, "INSTALL.md", install_findings,
                          lambda root, t, ph=phrases: drop_lines(t, *ph)))
    for rule, tokens in FORBIDDEN_TOKENS.items():
        mutations.append((rule, "INSTALL.md", install_findings, insert_token(tokens[0])))
    for rule, phrases in README_RULES.items():
        mutations.append((rule, "README.md", readme_findings,
                          lambda root, t, ph=phrases: drop_lines(t, *ph)))
    return mutations


def test_install_pins_pass_on_the_repo_files():
    assert install_file_findings(REPO_ROOT) == [], install_file_findings(REPO_ROOT)
    assert readme_findings(README.read_text()) == [], readme_findings(README.read_text())
    assert script_absence_findings(REPO_ROOT) == [], script_absence_findings(REPO_ROOT)


def test_install_pins_fail_when_the_rule_is_removed(tmp_path):
    """One observed negative per pin. The line records the observation."""
    for name, rel, check, mutate in build_mutations():
        root = Path(tmp_path) / re.sub(r"[^A-Za-z0-9-]", "-", name)
        root.mkdir(exist_ok=True)
        if rel is None:
            findings = check(root)
        else:
            original = (REPO_ROOT / rel).read_text()
            mutated = mutate(root, original)
            assert mutated != original, f"the {name} mutation did nothing"
            (root / rel).write_text(mutated)
            findings = check(root) if check is script_absence_findings else check(mutated)
        state = "failed-loud" if findings else "SILENT PASS"
        print(f"mutation: {name} removed -> {state}: {findings}")
        assert findings, f"the {name} pin must fail when its rule is removed"
        if rel == "INSTALL.md":
            assert any(f"the {name} rule" in f for f in findings), f"the {name} pin did not fire"


def main():
    tmp = Path(tempfile.mkdtemp(prefix="doc-pins-"))
    mutations = build_mutations()
    pins = len(INSTALL_RULES) + len(FORBIDDEN_TOKENS) + len(README_RULES) + 2
    print(f"pins: {pins} (install rules {len(INSTALL_RULES)}, forbidden {len(FORBIDDEN_TOKENS)}, "
          f"readme rules {len(README_RULES)}, pointer + script absence 2)")
    test_install_pins_pass_on_the_repo_files()
    test_install_pins_fail_when_the_rule_is_removed(tmp)
    print(f"mutations: {len(mutations)}/{len(mutations)} failed loud")
    return 0


if __name__ == "__main__":
    sys.exit(main())
