# No-network selftest harness

Recipe for proving that a test suite (selftest, test run) makes no network or CLI-tool calls. Use when a review finding says a test's stubs do not reach the code under test, or any time 'the test ran offline' must be proven rather than claimed.

The harness has two parts: a fake CLI per external tool, and dead proxy env vars.

1. Fresh dir per verification run: `$TMPDIR/<task>-harness/`. Never reuse a harness dir from an earlier run; a failed write in that run can leave a stale stub.
2. Per external tool the code can call (e.g. `gh`), write `bin/<tool>`:
   ```sh
   #!/bin/sh
   printf '%s\n' "$*" >> <harness>/gh.log
   exit 99
   ```
   `chmod +x` it.
3. Positive control BEFORE the real run: `env PATH=<harness>/bin:/usr/bin:/bin gh api probe; echo "exit=$?"` must print exit=99 and the log must hold the argv line. Then delete the log. A harness with no positive control proves nothing: the code can reach the real tool and the absence of log lines is uninformative.
4. Run the suite with the harness on PATH and all four proxy spellings dead-ended:
   ```
   env PATH=<harness>/bin:/usr/bin:/bin HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 python3 <suite> selftest; echo "exit=$?"
   ```
   The PASS condition is the suite's own marker line AND the fake-tool log file does not exist afterwards. Absent log = no stubbed tool was called. A passed suite WITH log lines means the stubs in the code do not intercept the real calls.
5. Mutations run under the same harness. One mutation per guard: remove the guard, the suite must FAIL (quote the first FAIL line), restore, confirm the tree is clean (`git diff --stat` empty) before the next mutation.
6. Instrumented live runs are the complement: wrap the subprocess/exec and http layers in Python, run against the real network, and record every method and argv. A read-only mode (dry-run) must record only GETs and read-only CLI subcommands.

Pitfalls:
- The stub naming trap: patching `import module as x` inside a `__main__` script creates a second module object, and patches land on the copy the code does not use. Patch through the function's `__globals__` or the module object the entry point actually runs in. The harness run proves the patch path works: with stubs bypassed, the fake tool's log fills.
- `126`-style exits from the fake tool (permission) mean `chmod +x` was skipped; `127` means PATH did not reach the harness. Both are harness failures, not suite results; rebuild and rerun.
- Keep the harness out of the repo; the blind review's diff must not include it.