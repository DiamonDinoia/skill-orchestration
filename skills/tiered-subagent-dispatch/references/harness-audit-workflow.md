# Harness config review and consolidation

Load for "review/audit my harness setup" asks (Hermes, Claude Code, Codex, opencode).

Order the work so nothing depends on a child that has not reported yet:

1. Baseline first: snapshot (`hermes-adversarial-review --snapshot-create`) plus git HEADs of dotfiles, memory repo, owned skill clones, hermes-agent. While it runs, dispatch the rest of discovery together: the context-text inventory, the skills/plugins audit, the package dry-run (READ-ONLY; list outdated + upgrade commands, run nothing), the conversation mine, and any external skill-repo survey. From the conversation mine, write each filter you had to add into the next brief (e.g. harness-written IDE-context headers, manager-written briefs in user-role rows) so the next child does not rediscover them.

2. Package upgrades second; they take a config-file copy, upgrade, and a diff-back check. Put each plugin/marketplace update in its own child after the CLI updates: version checks on stale registries (`version` field in a tag's own manifest, not the tag name) come before any `update` command.

3. Rule-text consolidation third; description shortening is its own child because it holds the SKILL.md files that a rule-prose child also edits, so scope them apart by section (descriptions child touches only frontmatter, prose child touches no SKILL.md).

4. Remote replication LAST, after the local review passes; the remotes pull dotfiles and re-run each harness's update commands themselves, they never need the local diffs carried over. Pitfalls this class hits:

Pitfalls this class hits:

- Hermes skill shadowing: two copies of one name (hub + `skills/local/`, tap + local) make `hermes chat -s <name>` fail at resolution with `Ambiguous skill name`. Fix is `mv` the loser to `~/.hermes/.attic/` (never delete; a confessed duplicate may hold user edits). Probe afterwards: `hermes skills list` name count == 1, a `-s <name>` PONG chat.
- Hermes refuses to start a session when two skills share a name (`Ambiguous skill name manager`), and the `hermes` wrapper passes `-s manager` on every interactive launch. A tap or URL install of an owned skill next to an old `~/.hermes/skills/local/<name>` copy causes it. Hermes also scans `~/.hermes/skills/.attic`, so move old copies to `~/.hermes/.attic/` (outside `skills/`). Every install brief's CHECK runs `hermes chat -s <name> -q 'reply PONG' -Q` and one plain `hermes skills list` call; the child reads its output and counts the lines with the exact name <name>, and the count must be 1.

- Tool that can crash at exit: gate the check on a marker line (`*_PASS`), never the exit code.

- Harnesses that keep their own old-version caches (codex `~/.codex/plugins/cache/<mp>/<name>/.orphaned_at`): `find` those marker files and remove only the marked orphans; never guess from mtimes.

- A "stale version" report can be the REGISTRY's string, not the install's: when a plugin manager reports an old version but only a newer one exists on disk, fix the registry entry, or the report keeps lying after every update.

- `--force` does not beat the install scanner: Hermes skills-guard `dangerous` blocks `--force` too; the fix is rewording the source repo (pin package versions, name the installer, no `sudo`), a new release, then update. This is per release, not a whitelist.

- A child whose report says "file written, identical content, no commit needed" while the file-mutation verifier flags a refused overwrite: trust the verifier, not the report; record the sha from the earlier turn.

- an upgrade child that finds the target version already at latest exits `up_to_date` with no work. That is a pass, not a finding.

- Claude Code `SubagentStart` hooks: the 10000-character limit (bundle constant `1e4`, function `Rde`) applies to the `additionalContext` string only, not the JSON envelope. Above it the subagent sees a 2000-character preview. Reject review findings that count the envelope; cite the bundle code.

- This rule is skill-orchestration-repo-only, never generalise it. `skill-orchestration` keeps the manager rules in many generated copies (`AGENTS.md`, `.agents/rules`, `.clinerules`, `.cursor/rules`, `.kiro`, `.windsurf` and others), built from `skills/manager/SKILL.md` by `scripts/build-rules.sh`. A brief for manager text edits only `SKILL.md`, then runs the generator; never hand-edit a copy. Its check diffs each copy against `SKILL.md` from the changed section to EOF, found with `rg --hidden -g '!.git' -l '<heading>'` (plain `rg` skips the dot-dirs). A hand fix to two copies left seven stale and failed a full review round.

- Public owned-skill text names no machine-specific standing skills (ste, unslop, ponytail). It says "the standing skills that the harness config names go to every child"; the names live in this skill. A public rule that names them without a source fails review as an unresolvable dependency.

- A skill probe or relay through `opencode run` needs the provider-prefixed model id (`<provider-prefix>/<org>/<model>`); a bare `<org>/<model>` is rejected. Put the prefixed id in opencode briefs, and check that the child's opencode probe really ran before trusting its yes/no.

## Owned skills (github.com/DiamonDinoia/skill-*)

Every harness installs them from its marketplace (Hermes `hermes skills install`/`tap`, Claude/Codex plugin marketplaces, opencode's installer). An agent or the curator may edit an installed copy of a skill. Every edit goes upstream into the clone in `~/repos/skills/<repo>` before the next release. One review covers the whole release batch. Never symlink a harness install into a clone. A change to an owned skill (including one found as a local edit in an installed copy) goes into the clone. The batch's review passes first. Then the change is pushed and released with a version bump in every manifest, and the installs are updated. Machine-specific text (home paths, provider/model names, flatiron, the Hermes binding) stays out of the public repo; it lives in the tiered-subagent-dispatch skill. Before replacing a local copy, diff it against the repo and upstream its general content first. Before a release, diff the installed copy against the clone tip: the Hermes background-review curator can edit the installed copy after the port (ledger `~/.hermes/skills/.curator_ledger.jsonl`), and a clone-based release silently drops those hunks. Port each kept hunk with a coverage check that accounts for every added line as carried or consciously listed as dropped. A reworded hunk needs no coverage check. Reword harness-specific names (this harness's tool and config names) to neutral terms and skip hunks holding private data. The curator keeps editing while the port runs, so record the installed sha at port start and re-diff right before tagging.

Before tagging an owned-skill release, run Hermes' install scanner on the skill dir: `cd ~/.hermes/hermes-agent && python3 -c "from tools.skills_guard import scan_skill; from pathlib import Path; r=scan_skill(Path('<wt>/skills/<name>'), source='skills-sh/DiamonDinoia/<repo>/<name>'); print(r.verdict, r.findings)"`. The release brief's CHECK requires a verdict that is not `dangerous`. The scanner matches words, not intent: a warning such as "never use sudo" or "never run `curl | sh`" and an unpinned `pip install <pkg>` each count as the act. A `dangerous` verdict blocks `hermes skills install/update` with no override (`--force` and the trusted-repo list do not apply), so the fix is rewording ("never with root rights", name the installer by URL, pin `<pkg>==<version>`) and a new release.

An owned-skill release ends only when every harness install on every host shows the new version. One job per host updates Claude Code, Codex, opencode and Hermes and reports a host x harness table. Its check reads the installed files (a new reference file present, a new term in SKILL.md), not the update command's exit code. When the job reports an "install was wiped/replaced" claim, a subagent does the read-back (`head` the installed SKILL.md, `.hub/lock.json`) before the manager relays it.

Edits to an owned skill repo happen in a git worktree on a branch (`git -C <clone> worktree add "$TMPDIR/<repo>-wt-<topic>" -b wt/<topic> main`), one per job. Merge into `main` and push only after the review passes, then remove the worktree. Before a private repo goes public, a job scans the FULL history (`git log -p --all`, not just HEAD) for home paths, provider/model names, tokens and keys, and the manager shows the hits to the user before `gh repo edit --visibility public`.

A new tool integration in a skill (a linter, a docs lookup) starts with a prototype job that edits no repo: it works in scratch, in containers (podman, non-root user), and leaves a rebuild script plus a short recipe of only the commands that worked. The skill job's brief then reads that recipe. Tool installs the skill prescribes ask the user first and stay in user space (`uv tool install`, else `pip install --user`), never sudo.
