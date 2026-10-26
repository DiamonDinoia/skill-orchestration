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

## Local cleanup

Same brief, each item with its skip rule:

- Remove the scratch worktrees. If one is dirty, list its `status --short` and skip that one.
- Delete only the local branches the user named, with `git branch -D`. Record each branch's sha in the report first: the reflog plus that sha is the only way back.
- `git worktree prune`.
- Fetch origin, then fast-forward the user's checkout only when it sits on main and is clean (`git merge --ff-only origin/main`). Never stash, checkout, reset or restore in the user's checkout; report its state instead.
- Never delete remote branches without explicit approval. List the ones that exist.
- Delete leftover build artifacts (*.deb, *.buildinfo, *.changes) only inside the named scratch directories.

## Report

Pushed remote tip, issue state, deleted branches with their shas, removed worktrees, anything skipped with its reason.
