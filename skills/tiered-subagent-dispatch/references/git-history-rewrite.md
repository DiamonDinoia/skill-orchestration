# Git history rewrite: fixup, autosquash, moving branches

Rules for folding fixes into earlier commits, splitting or recomposing branch history, and moving branches after a rewrite. Load when a child does an amend, fixup+autosquash, interactive rebase, or any branch move that changes shas.

## Choosing the autosquash base (do not rewrite pushed commits)

Discovery first (squash asks): report the base from `git merge-base HEAD <upstream>/<default-branch>` with the commits-ahead count, then the shas and trailers of the range, then for EVERY remote whether refs/heads/<branch> exists (`git ls-remote`, empty means not pushed), then `gh pr list --head <branch> --state all`, then `git branch -r --contains HEAD` with `git diff` of HEAD against each containing branch. The containing-branch check is separate: a local branch can miss refs and PRs while its commits already sit on a remote branch under another name, and that remote branch can back the PR the local work belongs to.

## N-commit squash without checkout or reset

Without a working-tree change, an index touch, or leaving the branch: `git branch backup/<name> HEAD`; write the message file; `NEW=$(git commit-tree 'HEAD^{tree}' -p <base> -F <msgfile>)`; `git update-ref -m <reason> refs/heads/<branch> $NEW <old-tip-full-sha>`. Preferred over `git reset <base> && git commit` in a live shared tree: the old-value guard of update-ref aborts the move when the branch tip changed since the read. The guard watches only the named ref; it does not protect the index, stash or worktree (the recipe never touches them: commit-tree reads `HEAD^{tree}`, so their state stays exactly as it was), and a checked-out branch is never half-built. Message: one subject in the repo style; one bullet per change of substance, merged where commits overlap, in the writing style of the user's skills; dedup the trailers of all squashed commits; author = the configured user. No build or tests needed, but only once `git diff --quiet <backup> HEAD` exits 0 and both sides print the same `git diff --stat <base> --` tail line, which proves the tree byte-identical.

A `--fixup=<sha>` fold must anchor its rebase at the sh tip of what the user already pushed, not at an older commit the target line comes from. Only a commit below the pushed head needs a deeper base, and that commit is upstream/base-tree code you must not rewrite. Anchoring there rewrites commits a remote already has, so `git merge-base --is-ancestor <pushed-head> <new-tip>` fails and the push needs `--force-with-lease` on a branch the user saw.

Before the fixup, check `git merge-base --is-ancestor <target-sha> <pr-head>`. If the target is below the PR head (branch-introduced but already pushed), do not fold into it. Put the fix in a new commit on top instead. The branch then stays a fast-forward from the pushed head.

## Folding fixes into earlier local commits

It is a history rewrite: first `git branch backup/<name> HEAD`. Then use fixup + autosquash on the branch itself, not a manual checkout/apply/amend/cherry-pick chain: `git apply --check <patch>` for each patch, apply, `git add <paths>`, `git -c core.hooksPath=/dev/null commit --fixup=<target sha>`, then `GIT_SEQUENCE_EDITOR=true git -c core.hooksPath=/dev/null rebase -i --autosquash <base>`. The branch never leaves its name, so a failed step cannot leave `main` on a half-built detached state. A manual chain (`a && b; c`) keeps going after a failed step and does.

The one safe manual form: build the new commits in a detached scratch worktree (`git worktree add --detach $TMPDIR/<task>-fold <target>`, `git apply --index`, amend, `cherry-pick` the later commits), check `git diff <old tip> <new tip> --stat` there, run the review on that worktree, and only then move the branch. The rewritten tip does NOT descend from the old local tip, so `git merge --ff-only` always fails here; move it with `git reset --keep <new tip>` on the checked-out branch (or `git branch -f` when it is not checked out). The main branch does not move until the result is checked.

Gate the push on the move: `git reset --keep <new tip> && test "$(git rev-parse HEAD)" = <new tip> && git merge-base --is-ancestor origin/<branch> HEAD && git push origin <branch>`, all joined with `&&` in its own call. With `;` or a separate line, a failed move still pushes the OLD tip, and on a shared `main` that cannot be undone without a force push; the only repair is a new commit on top holding `git diff <pushed> <new tip>`. Finish with the one proof, `git diff backup/<name> HEAD --stat`, which must list only the intended patches. Patches from several children against the same commit apply together when their file sets are disjoint; check that with `--check` first.

A pre-commit hook that regenerates a version header on every commit fails the amend and leaves the header modified. Restore the header (`git checkout -- <file>`) and amend with `git -c core.hooksPath=/dev/null commit --amend --no-edit` so each commit keeps its own version. Say in the report that the hooks were skipped, and run them over the range before the push.

## Amend and force-push policy

Amend only commits no remote has. Before proposing an amend, run `git fetch` and `git branch -r --contains <sha>` for each target commit. Empty output means the amend is safe, and the push is a plain fast-forward (`git merge-base --is-ancestor origin/<branch> <branch>`). If a remote already has the commit, put the fix in a new commit. The user never force-pushes a shared `main`, so the `--force-with-lease` push is only for feature branches. Say in the amend proposal that the push stays a fast-forward.

A local branch whose upstream is `[gone]` after a squash merge still shows every commit as `+` in `git cherry`, because a squash changes the patch-ids. Prove it is merged with `git range-diff <old-base>..<branch> <squash-base>..origin/main` plus a tree diff of the files it touched, then delete it with `git branch -D` once the user agrees. Before the delete, switch the clone to `main` and `git merge --ff-only origin/main`, so the clone does not stay on a stale tip.

## Rewriting a reviewed branch

A finding that reverses an earlier round's fix is handled in `references/review-loop-rules.md` ("Which findings get fixed"). When a fix round changes constants a reviewer set on purpose, keep the numeric evidence in the commit message so the next reviewer sees the reason.
