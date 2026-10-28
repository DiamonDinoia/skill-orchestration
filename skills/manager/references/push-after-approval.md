# Push and clean up after an approved fix

Run only after explicit user approval and after the final review round passed on the exact tip to push. The approval message covers exactly the shas named in it; anything else (other branches, tags, force) stays out.

## Pre-checks

Each is a stop rule in the push brief, fired without inference:

- The review worktree's `rev-parse HEAD` equals the approved sha.
- `git ls-remote origin refs/heads/main` equals the tip the review ran against. A moved tip stops the push and reopens review on the new base.
- `git merge-base --is-ancestor <remote-tip> <approved-sha>` exits 0, so the push is a fast-forward.

## Push and verify

- `git push origin <approved-sha>:refs/heads/main`. No `--force`, no other branch, no tags.
- Verify by `ls-remote`: the remote main tip now prints the approved sha. A push exit 0 alone is not the proof.
- A commit message with `"Fix #N"` closes the issue on push. Check `gh issue view N --json state,stateReason`, retrying a couple of times over a minute. If it stays open, report that; never close the issue or comment on it without approval.

## PR route

When direct push to main is not approved, the approved sha lands through a branch and pull request:

- `git push origin <approved-sha>:refs/heads/<branch>`. Stop if the remote branch name already exists; never force.
- Open the PR with `gh pr create` against main; the body lists breaking changes and documented limits.
- Verify with `ls-remote`: the new remote branch prints the approved sha and `refs/heads/main` is unchanged.
- Merge only on explicit approval after `gh pr checks` passes. Match the repo's merge style: `git log --merges -5` on main shows whether history uses merge commits or squash, and the merge uses the matching `gh pr merge` mode with `--match-head-commit <approved-sha>` so a moved head stops the merge. Verify MERGED with `gh pr view --json state,mergeCommit`.
- Fast-forward the user's checkout onto the new main, then delete the merged local branch (`git branch -d`). The remote branch survives the merge unless the repo deletes on merge; list it and leave deletion to the user.
- A consumer repo pinned to the old sha by commit (a FetchContent `GIT_TAG`) keeps building after the merge. The pinned sha stays in main's history only for merge commits. A squash merge drops it, so the consumer's next pin target is the mergeCommit sha from `gh pr view --json mergeCommit`. Its API-update branch stays local; the pin bump is its own outward-facing step, not part of this landing.

## Local cleanup

Same brief, each item with its skip rule:

- Remove the scratch worktrees. If one is dirty, list its `status --short` and skip that one.
- Delete only the local branches the user named, with `git branch -D`. Record each branch's sha in the report first: the reflog plus that sha is the only way back.
- `git worktree prune`.
- Fetch origin, then fast-forward the user's checkout only when it sits on main and is clean (`git merge --ff-only origin/main`). Never stash, checkout, reset or restore in the user's checkout; report its state instead.
- Never delete remote branches without explicit approval. List the ones that exist.
- Delete leftover build artifacts (*.deb, *.buildinfo, *.changes) only inside the named scratch directories.
- Verify the cleanup by size, not by the delete-list: `du -sh` the task scratch dir and list the largest survivors. A keep-list of briefs and logs does not catch the multi-GB build directories review sandboxes leave behind; name those in the brief or delete them.

## Rewritten history the user named

Run only when the push message names the rewrite (a squash or a rebase onto a new base) and the branch. Main is never rewritten.

- Keep a backup ref of the pre-rewrite tip in the scratch worktree.
- Prove the rewritten tip holds the reviewed content: `git diff <pre-rewrite tip> <new tip>` empty. A rewrite that changes content goes back as a defect, it is not pushed.
- Build and run the checks on the rewritten tip. The reviewed shas no longer sit on the branch, so CI and any later reviewer see only the new tip.
- Capture the remote sha in the same turn: `git ls-remote origin refs/heads/<branch>`. Push with `git push --force-with-lease=refs/heads/<branch>:<remote-sha> origin HEAD:refs/heads/<branch>`. A plain `--force` overwrites work that landed between the checks, and a lease without the explicit expected sha trusts a stale local ref. A mismatch stops the push and reopens review on the new remote state.
- Verify by `ls-remote`. Never move or reset the user's own checkout; report its sha.

## Report

Pushed remote tip, issue state, deleted branches with their shas, removed worktrees, anything skipped with its reason.
