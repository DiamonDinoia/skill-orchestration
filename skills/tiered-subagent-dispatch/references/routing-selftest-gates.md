# Routing selftest gates (per-check runner, reverse toggle)

Load before editing `references/flatiron-routing.json`, the router script or the tier tables.

The routing selftest (`scripts/selftest.py`) runs its `check_*` functions in one process and stops at the first failed assert. A failure early in `check_route` or `check_tiers` hides every check after it. A red baseline therefore needs the per-check runner below.

## Baseline first, then a per-check gate

1. Run `python3 scripts/selftest.py` on the UNEDITED files and save the exit code and the first failing line. This is the baseline.
2. `selftest.py` reads `references/flatiron-routing.json` itself (`check_tiers` loads it through `ROUTING_FILE`), so a json that disagrees with the router defaults fails on the baseline too. A failing baseline is a pre-existing failure: report it, do not let the edit brief revert the edit over it.
3. When the baseline is red, the plain selftest cannot gate the edit. Use the per-check runner below: it must print IDENTICAL PASS/FAIL lines for the unedited json and for the edited json. Any line that flips PASS to FAIL reverts the edit.

## Per-check runner (drop-in recipe)

`selftest.py` imports `hermes-dispatch-route` and `hermes-adversarial-review` by path. It takes the copy next to `selftest.py` first and falls back to `~/.local/bin`. `check_tiers` reads the routing file the router resolves at import. A runner that compares two json variants works in a scratch dir. It copies `selftest.py`, its sibling tools and each variant there, and points `HERMES_DISPATCH_ROUTING_FILE` at the scratch variant before it loads `selftest`. The live routing file is never written.

Skeleton:

```
# Save as runner.py in the skill dir. Run: python3 runner.py UNEDITED.json EDITED.json
import importlib.machinery, importlib.util, os, shutil, sys, tempfile, traceback
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

SKILL = Path(__file__).resolve().parent
SELFTEST = SKILL / "scripts" / "selftest.py"
SCRATCH = Path(tempfile.mkdtemp(prefix="routing-gates-"))
TOOLS = ("hermes-dispatch-route", "hermes-adversarial-review")

def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod

def run_one(check_name, variant):
    # each run gets its own scratch copy of selftest, its sibling tools and the variant;
    # HERMES_DISPATCH_ROUTING_FILE points the router at the scratch copy, never at the live file
    d = Path(tempfile.mkdtemp(dir=SCRATCH))
    shutil.copy(SELFTEST, d / "selftest.py")
    for t in TOOLS:
        if (SELFTEST.parent / t).is_file():
            shutil.copy(SELFTEST.parent / t, d / t)
    shutil.copy(variant, d / "flatiron-routing.json")
    os.environ["HERMES_DISPATCH_ROUTING_FILE"] = str(d / "flatiron-routing.json")
    st = load("selftest", d / "selftest.py")
    buf = StringIO()
    try:
        with redirect_stdout(buf):
            getattr(st, check_name)()
        return ("PASS", "")
    except Exception:
        return ("FAIL", traceback.format_exc(limit=3).splitlines()[-1])

st = load("selftest", SELFTEST)
for c in [n for n in dir(st) if n.startswith("check_")]:
    b, b_err = run_one(c, Path(sys.argv[1]))   # unedited copy
    e, e_err = run_one(c, Path(sys.argv[2]))   # edited copy
    print(c, f"baseline={b}", f"edited={e}", b_err or e_err)
```

Load `selftest` fresh per run: a stale import reuses the previous variant. The proof that the runner left the live file alone is byte equality with a pre-run copy, not a claimed restore.

## Reverse-toggle evidence

Use the reverse toggle only for a claim that gates a fix. When `check_tiers` fails on an assert such as `pick(tier="senior") == "claude-sonnet-9"`, name the field the assert reads (`tiers.senior.fallback`), then run `pick` in-process twice on scratch copies of the json: once with the field as-is, once with the value the assert expects. Report both outputs. The reverse toggle separates "the json is wrong" from "the selftest or router code is wrong" in one python invocation; without it, a fix lands on the wrong file.
