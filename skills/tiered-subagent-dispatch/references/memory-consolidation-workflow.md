# Agent memory and skill consolidation

Load for "consolidate/purge/compact my memories" asks, and for "same info in several harnesses" asks. Covers the agent memory stores and the skill library together: auto-loaded stores (Hermes MEMORY.md/USER.md, Claude CLAUDE.md and AGENTS-core.md, Codex and opencode AGENTS.md, Claude project memory indexes) are the hippocampus; the long-term repo and the SKILL.md bodies are the neocortex. Match placement and detail to replay strength; purge only what was superseded.

## Procedure

0. User decisions first: skills in scope or not, where a shared fact lives (once in `~/repos/memory`, pointer in the auto-loaded store), apply directly or approve first, local hosts only or also over ssh.
1. Baseline and inventory, all at once: git HEADs and dirty counts of dotfiles, memory repo and skill clones; `hermes-adversarial-review --snapshot-create`; byte and entry counts per store; duplicate detection (same skill name in 2+ places with different sha256). Beyond the obvious paths, probe `~/.hermes/memories/`, `~/.claude/CLAUDE.md`, `~/.claude/projects/*/memory/`, `~/.codex/` (memories AND *.sqlite), `~/.config/opencode/`, plus every symlink target. Other Hermes profiles (`~/.hermes/profiles/`): inventory, never edit. Snapshot every path that is not in git; backup tarballs on remote hosts.
2. Replay: mine the recent session logs (Hermes state.db sqlite read-only, Claude Code jsonl, Codex and opencode) for projects, corrections (verbatim, citing session id and date), facts agents re-discovered, and environment changes. Every replay claim carries a citation. Filter harness-injected text from real user turns; a raw hit count may double-count pasted brief text, and only hand-checked quotes count as real corrections.
3. Merge diverged repo copies BEFORE any edit. Fetch on both sides; the side that is behind does a `merge --ff-only`; a dirty path that overlaps an incoming change stops the job. Check stop rules against live state: `git rev-parse HEAD` must equal the one in the brief. Even an "obviously local" change went through origin here because other machines push to it.
4. Proposal: one verdict line per entry (keep | merge | move | purge | fix), each with evidence from the replay or the surviving id. Purge covers only superseded, contradicted, duplicate or stale task state. A durable fact with no recent use moves out of the auto-loaded store into `~/repos/memory` with a one-line pointer; that is the downscale step, and it deletes nothing.
5. Apply in parallel by file owner. Constraint: parallel children committing in one repo each commit only their own paths (`git commit -- <paths>`, retry index.lock up to 5 times, never delete it); the user's dirty files (named in the brief) are never touched, which also keeps the attribution review clean. No child pushes until every child has committed, and push waits for the review of step 6. Checks: assert per store (entry counts match the inventory, no duplicate facts across auto-loaded stores, moved facts exist at their new path, char budgets hold).
6. Review: fresh per-store reviewers plus one cross-store reviewer (no contradictions, no duplicates). Keep each verdict's evidence to rebut false findings.
7. Push and replicate, only after the review is clean: one push, then each remote pulls or re-runs its own update. Review comes before replication, as in `references/harness-audit-workflow.md`.

## Where a fact lives

- Every-session facts stay in the auto-loaded store, which carries a char budget (Hermes MEMORY.md and USER.md have hard limits, the dashboard turns yellow at 90%). Target <= 60% of the limit, not 90%: the first later add must fit without a new compaction round.
- A tested 30% shrink target is not always reachable: a file that is mostly machine-pinned text (a test-pinned frontmatter) or already at one-sentence density reports why and the reviewer accepts it. Set the target per file after the first ledger pass.
- User-dirty paths keep their local copies: an installed copy that sits in the user's uncommitted dotfiles changes stays put (with its staleness named in the report), and machines that load through symlinks into it keep the old version until the user commits.
- Project CLAUDE.md files are audited only: lines that duplicate or contradict global memory become findings in memories' own proposal.
- Verify a store's format by experiment on a toy change before bulk edits (the pluggable memory spec for Claude Code memory, the §-entry split and section char limits for Hermes). Assert the roundtrip in the check.

## Pitfalls

- A wrong fact found in an auto-loaded memory (e.g. a host identity line that names the wrong machine as "this host") is the highest-value finding; verify it with one live command (`hostname`, `nvidia-smi`) and fix it in the same pass.
- A dangling symlink into dotfiles (e.g. a harness memory file) is an environment bug with two defensible fixes; restore the target or remove the link, and name the callers first (config references).
- A rule a child copies into every brief ("do not push", "no memory edits") shows the real memory is the briefs, not the stores; recurring brief boilerplate is a candidate for the auto-loaded stores.
- Mid-run state changes happen: another agent can push to a shared repo mid-pass, or the user can delete a file mid-pass. A skill child that finds the target missing reports `skipped: user deleted`, not an invention.
- Session-log stores have finite retention (a state.db can start only weeks back): say the real window in the replay report; never imply full coverage.
- Third-party bulk skills (a large design-data install, several MiB per harness) are a disk and install matter, not a context-budget matter: leave them to a separate dedupe decision instead of compacting their content.
- After the pass, pending work items name the exact prerequisite commands in the report (e.g. a dotfiles pull plus a plugin update on a remote host), so a later session can finish them without rediscovery.
