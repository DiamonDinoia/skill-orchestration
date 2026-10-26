# Routing selftest gates (per-check runner, reverse toggle)

Load before editing `references/flatiron-routing.json`, the router script or the tier tables.

The routing selftest (`scripts/selftest.py`) runs its `check_*` functions in one process and stops at the first failed assert. A failure early in `check_route` or `check_tiers` hides every check after it, so a before/after comparison of a routing change needs a per-check runner.

## Baseline first, then a per-check gate

1. Run `python3 scripts/selftest.py` on the UNEDITED files and save the exit code and the first failing line. This is the baseline.
2. `selftest.py` reads `references/flatiron-routing.json` itself (`check_tiers` loads it through `ROUTING_FILE`), so a json that disagrees with the router defaults fails on the baseline too. A failing baseline is a pre-existing failure: report it, do not let the edit brief revert the edit over it.
3. When the baseline is red, the plain selftest cannot gate the edit. Use the per-check runner below: it must print IDENTICAL PASS/FAIL lines for the unedited json and for the edited json. Any line that flips PASS to FAIL reverts the edit.

## Per-check runner (drop-in recipe)

`selftest.py` imports hermes-dispatch-route and hermes-adversarial-review by path from `~/.local/bin`, and `check_tiers` reads `ROUTING_FILE` from disk. A runner that compares two json variants swaps the variant into the real path before importing, calls each `check_*` in its own try/except, and restores the original content in a `finally`. Redirect stdout inside each call so the "selftest OK" print does not pollute the per-check table.

Skeleton:

```
import importlib.machinery, importlib.util, sys, traceback
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

SELFTEST = Path.home() / ".hermes/skills/autonomous-ai-agents/tiered-subagent-dispatch/scripts/selftest.py"
ROUTING  = Path.home() / ".hermes/skills/autonomous-ai-agents/tiered-subagent-dispatch/references/flatiron-routing.json"

def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod

def run_one(check_name, swap_json):
    orig = ROUTING.read_bytes()
    try:
        if swap_json:
            ROUTING.write_bytes(Path(swap_json).read_bytes())
        st = load("selftest", SELFTEST)
        buf = StringIO()
        with redirect_stdout(buf):
            getattr(st, check_name)()
        return ("PASS", "")
    except Exception:
        return ("FAIL", traceback.format_exc(limit=3).splitlines()[-1])
    finally:
        ROUTING.write_bytes(orig)

st = load("selftest", SELFTEST)
for c in [n for n in dir(st) if n.startswith("check_")]:
    b, b_err = run_one(c, sys.argv[1])   # baseline copy, or None
    e, e_err = run_one(c, sys.argv[2])   # edited copy
    print(c, f"baseline={b}", f"edited={e}", b_err or e_err)
```

Import selftest fresh per check: the module caches `ROUTING_FILE` content through the routing loader, and a stale import reuses the previous variant. The final `cmp` proof of "reverted" is byte equality with the baseline, not a claimed revert.

## Reverse-toggle evidence

When `check_tiers` fails on an assert such as `pick(tier="senior") == "claude-sonnet-9"`, name the field the assert reads (`tiers.senior.fallback`), then run `pick` in-process twice on scratch copies of the json: once with the field as-is, once with the value the assert expects. Report both outputs. The reverse toggle separates "the json is wrong" from "the selftest or router code is wrong" in one python invocation; without it, a fix lands on the wrong file.