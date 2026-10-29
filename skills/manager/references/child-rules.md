Load this file for child report rules.

# Child rules

A brief names this file in one line and holds only task-specific text. The child obeys the rules below on each task.

Shared rules:

- Line 1 of the report names the provider and model from the runtime of the child.
- End each command with `; echo "exit=$?"`.
- Do not edit installed skills or memory.
- Do not push without an approval from the user.

Report rules:

1. The report length follows the outcome. A clean result is one or two lines. The cap is 6 lines and 600 characters. For each check that fails, add one line, with a limit of 12.
2. Line 1 gives the provider and model, the outcome, and the one id that the manager uses: a sha, a URL or a path. The outcome is `done`, `blocked`, `partial`, or `UNRUN: <reason>`. A stopped task names its stopper: brief rule, user message, or harness.
3. The body holds the first error line of each check that fails. It holds open decisions with their options and a recommendation, and changes that the brief did not name, each flagged. Checks that pass count as one count line. A mutation check names `passed`, `failed-loud` or `silent-pass`. `failed-loud` means a contract check caught it. `silent-pass` means no check caught the defect. A revert with a clean tree is no result.
4. Write no boilerplate. Do not restate the brief or the goal. Do not copy the step-0 values that match. Do not list the files that hold the check output, add headings, or write empty `Skipped` or `Risk` lines. Do not add transcript paths, because the harness adds them.
5. The full report with commands, exit codes and decisive output goes to `report.md` in the `evidence` dir. The manager reads it only when a check does not succeed, when the user has a question, or to send proof to the user.
