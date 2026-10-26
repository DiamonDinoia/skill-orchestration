# CI maintenance for this user's repos

## User rules for "update CI to the latest versions"

- Actions go to the latest release by tag. Keep the repo's own convention: when the repo pins tags, never pin a sha.
- Languages go to the latest stable release (Python, Node). Toolchains pin the current stable line, not a trunk/dev line (LLVM: `CURRENT_LLVM_STABLE` in apt.llvm.org `llvm.sh`).
- Runners pin a versioned image (`ubuntu-24.04`, `macos-15`, `windows-2022`), never `*-latest`. A `-latest` label moves to a new OS on GitHub's date and can break a distro-specific repo (apt.llvm.org `noble` packages on a newer Ubuntu). Pick the version that the repo's apt sources and sibling repos already use.
- pre-commit hooks: when the new rev reformats tracked files, make two commits. First apply the hooks at the OLD revs (format only, no hand edits). Then bump the revs and commit their rewrites with the bump. Check `pre-commit run --all-files` exits 0 twice in a row.
- One PR per repo, merged by `scripts/merge-when-green.py` when CI is green.

## Publishing from CI

- Publish a build from the job that tested it: a final job in the same workflow with `needs:` on every test job and `if:` on push to main. A separate scheduled workflow that checks CI on one commit and checks out another can publish untested code.
- Do not put a `concurrency:` group on a publish job. GitHub keeps one pending run and cancels the rest, so some tested commits never publish. Unique versions plus `skip-existing` make serialisation unnecessary.
- PyPI/TestPyPI trusted publishing matches on owner, repo, workflow FILE name and environment. Moving the publish step to another workflow file needs a new publisher, which only the user can add. Name the exact fields before the merge. Until it exists, the job fails with `invalid-publisher`; after the user adds it, rerun only the failed job (`gh run rerun <id> --failed`).
- A dev version stamp must sort above every version already on the index, or `pip install --pre` keeps the old build. Read the newest first: `curl -H 'Accept: application/vnd.pypi.simple.v1+json' https://test.pypi.org/simple/<pkg>/`. The `/pypi/<pkg>/json` endpoint lags minutes behind an upload. A composite stamp (committer time `%Y%m%d%H%M` UTC plus a zero-padded run number) keeps the order; a bare run number sorts below dated builds.
- A `workflow_run` follow-up (coverage audit) runs only after a successful CI run. A red publish job blocks it, so fix the publisher before waiting for the follow-up PR.

## Releases

- Use the repo's own workflows (`Bump Version`, then `Release`, each `-f dry_run=false` only after a dry run or a user go-ahead). Each step waits for the one before it; stop on the first failure so nothing is half-published. Check the result on the index, not only the workflow conclusion.
- Cut a release only when `main` has user-visible changes since the last tag (`gh api repos/<o>/<r>/compare/<tag>...main -q .ahead_by`, then read the subjects). Repos with no release history get none unless the user asks.

## Validating installer and conda PRs

- A PR whose deliverable is an installer script (conda env file, install script) is not done until the script ran once outside CI. Validate it rootless in a container: `podman run --rm --network=host -v <clone>:/ws:rw -w /ws -e HOME=/ws -e CONDA_ENVS_PATH=/ws/.conda/envs -e CONDA_PKGS_DIRS=/ws/.conda/pkgs docker.io/condaforge/miniforge3:latest sh -c 'bash python/<pkg>/conda-install.sh'`. Redirect the run's own output, never through a pipe; keep the solve cache inside scratch via CONDA_ENV/PKGS_DIRS so reruns cost nothing.
- The check a script passes must match how the docs tell the user to call it (bash vs sh). A script that works under bash but is invoked as `sh script.sh` prints `[[: not found` from conda's activate.d hooks and can pass anyway; note the bash assumption in the docs where the recipe lives.
- A dependency pin must match the comment it documents. A comment that says "cupy 14 needs the targets layout" next to an unpinned `cupy-cuda12x` line is not load-bearing; pin a floor at or below the lowest version the claim names so the solver cannot drift under it.
- When the audit finds the PR body's CI description stale (CI moved from one workflow file to another mid-PR), the fix is a one-line body edit naming the real CI, not a rewrite of both files.
