#!/usr/bin/env python3
"""Offline self-check for hermes-dispatch-route and hermes-adversarial-review. No network, no models.
Run: python3 scripts/selftest.py"""
import contextlib, fcntl, importlib.machinery, importlib.util, io, json, os, subprocess, sys, tempfile, time, types
from pathlib import Path

BIN = Path.home() / ".local" / "bin"
# Every check runs against an empty ledger: a path that never exists. The live outcomes ledger
# demotes real model ids and would make a check depend on the host's run history.
NO_LEDGER = "/nonexistent/hermes-selftest/ledger.jsonl"
# Staged runs: HERMES_DISPATCH_BIN names a dir holding a candidate router; absent tools fall to BIN.
STAGE = Path(os.environ.get("HERMES_DISPATCH_BIN") or BIN)


def tool_path(name):
    # the copy next to this file is the release copy under test: a checkout run tests its own tree
    here = Path(__file__).resolve().parent / name
    return here if here.is_file() else (STAGE / name if (STAGE / name).is_file() else BIN / name)


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(tool_path(name)))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def check_route():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    r.routing = lambda: {"rank": {"a/Top": 4, "b/Mid": 3}, "routes": {"code": ["a/Top", "b/Mid"]},
                         "paid_ladder": ["haiku", "sonnet", "opus"]}
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    pick = lambda failed=(): r.pick("code", "senior", list(failed), False)
    model = lambda failed=(): pick(failed)["model"]
    health(a_Top=True, b_Mid=True);   assert model() == "b/Mid"                         # the ladder starts at the lowest rank
    health(a_Top=False, b_Mid=True);  assert model() == "b/Mid"                         # the unhealthy strong rung is skipped
    health(a_Top=True, b_Mid=False);  assert model() == "a/Top"                         # the unhealthy cheap rung is skipped
    health(a_Top=False, b_Mid=False)                                                   # no local rung -> the paid rungs
    assert model() == "claude-haiku-9", pick()                                          # paid cheapest first
    assert [x["model"] for x in r.lanes("code", "senior", [], [])] == ["claude-haiku-9", "claude-sonnet-9", "claude-opus-9"]
    assert model(["claude-haiku-9"]) == "claude-sonnet-9"                               # a failed rung is skipped, never retried
    assert model(["claude-haiku-9", "claude-sonnet-9", "claude-opus-9"]) is None        # every rung failed -> blocked
    assert pick(["claude-haiku-9", "claude-sonnet-9", "claude-opus-9"])["reason"].startswith("blocked:")
    health(a_Top=True, b_Mid=True);   assert model() == "b/Mid"                         # recovered -> back to the cheap rung
    health(n_New=True);               assert model() == "claude-haiku-9"               # an unranked model is no rung
    assert "n/New" not in str(pick())
    health(a_Top=True, b_Mid=True)
    assert model(["b/Mid"]) == "a/Top"                                                  # --failed skips the rung
    assert model(["b/Mid", "a/Top"]) == "claude-haiku-9"                                # local rungs gone -> paid


def check_tiers():
    """The tier floors the ladder: the tier_floor model of a tier is its first rung and paid_floor
    starts its paid rungs. A missing or unknown tier takes the intern floor. A null tier floor
    (super) has no local rung. Need-wins: a need the floor models lack starts at the strongest
    fitting local model below the floor. A failed floor model opens the same exception. A
    ladder-false model is never a rung and stays pinnable."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = json.loads(r.ROUTING_FILE.read_text())  # the real tier table, so a bad edit to it fails here
    tf = cfg["tier_floor"]                        # the real floor ids, tested here verbatim
    QWEN, GLM, MIMO, KIMI = "Qwen/Qwen3.8-27B-FP8", "zai-org/GLM-5.3", "XiaomiMiMo/MiMo-V2.6-Pro-MOPD", "moonshotai/Kimi-K3"
    assert tf == {"intern": QWEN, "junior": QWEN, "senior": MIMO, "principal": MIMO, "super": None}, tf
    assert cfg["paid_floor"] == {"intern": "haiku", "junior": "haiku", "senior": "sonnet",
                                 "principal": "opus", "super": "opus"}, cfg["paid_floor"]
    assert cfg["tiers"]["super"] == {"reasoning_effort": "high", "skills": ["brainstorm", "agent-comms"],
                                     "fallback": ["opus"]}, cfg["tiers"]["super"]
    MIST = "mistralai/Mistral-Medium-3.5-128B"
    cfg["rank"] = {QWEN: 3, GLM: 4, MIMO: 5, KIMI: 6, MIST: 1}   # the shipped scale: qwen weakest
    cfg["routes"] = {"code": [QWEN, GLM, MIMO, KIMI]}
    cfg["features"] = {m: {"vision": False, "web": False} for m in cfg["rank"]}
    cfg["features"][QWEN] = {"vision": True, "web": False}       # only qwen fits vision below every floor
    cfg["features"][MIST] = {"vision": False, "web": False, "ladder": False}
    cfg["paid_ladder"] = ["haiku", "sonnet", "opus"]
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    paid = ["claude-haiku-9", "claude-sonnet-9", "claude-opus-9"]
    lanes = lambda tier, failed=(), needs=(): [x["model"] for x in r.lanes("code", tier, list(failed), list(needs))]
    names = lambda tier: [m for _p, m, _t in r.ladder([], [], tier)]
    pick = lambda kind="code", tier="senior", failed=(), pin=None, needs=(): r.pick(kind, tier, list(failed), False, list(needs), pin)
    health(**{QWEN: True, GLM: True, MIMO: True, KIMI: True, MIST: True})          # every local healthy
    assert lanes("intern") == [QWEN, GLM, MIMO, KIMI] + paid, lanes("intern")            # floor = weakest local
    assert names(None) == names("intern"), "a missing tier takes the intern floor"
    assert names("lead") == names("intern"), "an unknown tier takes the intern floor"
    assert lanes("junior") == [QWEN, GLM, MIMO, KIMI] + paid, lanes("junior")            # junior floor is qwen
    assert lanes("senior") == [MIMO, KIMI] + paid[1:], lanes("senior")                   # senior starts at MiMo
    assert lanes("principal") == [MIMO, KIMI] + paid[2:], lanes("principal")             # principal starts at MiMo
    assert lanes("super") == paid[2:], lanes("super")                                    # a null floor: paid only
    assert MIST not in str(lanes("intern")) + str(lanes("principal")), "ladder false is never a rung"
    assert lanes("senior", needs=["vision"]) == [QWEN] + paid[1:], "need-wins drops below the floor"
    assert lanes("senior", failed=[MIMO, KIMI]) == [GLM] + paid[1:], "a failed floor opens the exception"
    assert lanes("principal", failed=[KIMI]) == [MIMO] + paid[2:], "principal paid floor is opus"
    assert lanes("intern", failed=[QWEN, GLM, MIMO, KIMI]) == paid, "every local failed -> intern paid floor"
    assert pick(tier="principal", pin=MIST)["model"] == MIST, "a ladder-false model stays pinnable"
    f = pick(tier="principal")["flags"]                                                   # flatiron pick: effort and skills
    assert "--reasoning high" in f and "-s brainstorm -s agent-comms -s team -s manager" in f, f
    f = pick(tier="intern")["flags"]
    assert "-s " not in f and "--reasoning low" in f, f
    f = pick(tier="super")["flags"]                                                       # super: opus team, no effort
    assert "--reasoning" not in f and "-s brainstorm -s agent-comms" in f, f
    health(**{QWEN: False, GLM: False, MIMO: False, KIMI: False, MIST: False})    # all flatiron down
    assert lanes("intern") == paid and lanes("senior") == paid[1:] and lanes("principal") == paid[2:]
    f = pick(tier="principal", pin="opus")["flags"]                                       # explicit pin: skills, no effort
    assert "--reasoning" not in f and "-s manager" in f, f


def check_effort_clamp():
    """The efforts map clamps --reasoning to what each flatiron model accepts: the highest
    accepted value at or below the tier effort. pick, lanes and assign agree on the value."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    jpath = STAGE / "flatiron-routing.json"                       # staged runs judge the staged json
    cfg = json.loads((jpath if jpath.is_file() else r.ROUTING_FILE).read_text())
    QWEN, MIST = "Qwen/Qwen3.8-27B-FP8", "mistralai/Mistral-Medium-3.5-128B"
    assert set(cfg.get("efforts") or {}) >= {QWEN, MIST}, cfg.get("efforts")   # both limited models listed
    r.routing = lambda: cfg
    r.inflight_counts = lambda: {}

    def efforts_of(model, tier, pin=False):
        cfg["rank"], cfg["routes"] = {model: 5}, {"code": [model]}
        r.flatiron_status = lambda *a: {model: {"ok": True}}
        p = model if pin else None          # a ladder-false model runs only as a pin
        outs = [r.pick("code", tier, [], False, pin=p), r.lanes("code", tier, [], [], p)[0],
                r.assign([("n1", "code", tier, [])], p)[0]]
        return [o["flags"].split("--reasoning ", 1)[1].split()[0] for o in outs]

    assert efforts_of(QWEN, "senior") == ["medium"] * 3               # high -> medium
    assert efforts_of(QWEN, "principal") == ["medium"] * 3            # principal high -> medium
    assert efforts_of(MIST, "intern", pin=True) == ["none"] * 3       # low -> none (pin only: ladder false)
    assert efforts_of(MIST, "principal", pin=True) == ["high"] * 3    # principal high -> high
    jv = cfg["tiers"]["junior"]["reasoning_effort"]                    # the json value, not a live pin
    assert efforts_of("n/Unlisted", "junior") == [jv] * 3              # no entry: the tier value stays


def check_effort_round_down():
    """Round down: a rejected effort takes the highest accepted level at or below the request;
    only an all-above accepted set falls to the lowest, with a warning naming model and level."""
    r = load("hermes-dispatch-route")
    cfg = {"efforts": {"m/Down": ["xhigh", "medium", "low"], "m/Xhigh": ["xhigh"]}}
    assert r._effort("m/Down", "high", cfg) == "medium"
    assert r._effort("m/Down", "low", cfg) == "low"
    assert r._effort("m/Down", "medium", cfg) == "medium"
    assert r._effort("m/None", "high", cfg) == "high"
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        got = r._effort("m/Xhigh", "high", cfg)
    assert got == "xhigh", got
    assert "m/Xhigh" in buf.getvalue() and "xhigh" in buf.getvalue(), buf.getvalue()


def check_effort_unknown_names():
    """An effort name outside the scale warns with the valid list and never raises. The scale
    holds every Hermes name, and every value of the shipped efforts map."""
    r = load("hermes-dispatch-route")

    def run(m, effort, accepted):
        r._WARNED_EFFORTS.clear()                                                # each case sees its own warning
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            got = r._effort(m, effort, {"efforts": {m: accepted}})
        return got, buf.getvalue()
    valid = "valid: " + ", ".join(r._EFFORT_SCALE)
    assert run("m/A", "ultra", ["xhigh", "medium", "low"]) == ("xhigh", "")     # a Hermes name rounds down
    got, err = run("m/B", "bogus", ["xhigh", "medium", "low"])
    assert got == "medium" and err == f"warning: unknown reasoning effort 'bogus'; {valid}; using medium\n", (got, err)
    got, err = run("m/C", "high", ["bogus", "low"])
    assert got == "low" and err.count("'bogus'") == 1 and valid in err, (got, err)
    got, err = run("m/D", "high", ["bogus"])
    assert got == "high" and err.count("'bogus'") == 1 and valid in err, (got, err)
    jpath = STAGE / "flatiron-routing.json"                                      # staged runs judge the staged json
    cfg = json.loads((jpath if jpath.is_file() else r.ROUTING_FILE).read_text())
    for m, acc in (cfg.get("efforts") or {}).items():
        if m != "_doc":
            assert set(acc) <= set(r._EFFORT_SCALE), (m, acc)


def check_lanes():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = json.loads(r.ROUTING_FILE.read_text())  # the real tier table, so a bad edit to it fails here
    cfg["rank"] = {"a/Top": 5, "b/Mid": 4, "c/Lo": 3, "d/NoVis": 2, "e/Down": 1}
    cfg["routes"] = {"code": ["a/Top", "b/Mid", "c/Lo", "d/NoVis", "e/Down"]}
    cfg["features"] = {"a/Top": {"vision": True, "web": False}, "b/Mid": {"vision": True, "web": False},
                       "c/Lo": {"vision": False, "web": False}, "d/NoVis": {"vision": False, "web": False},
                       "haiku": {"vision": True, "web": True}, "sonnet": {"vision": True, "web": True},
                       "opus": {"vision": True, "web": True}}
    cfg["paid_ladder"] = ["haiku", "sonnet", "opus"]
    cfg["tier_floor"] = {t: "e/Down" for t in ("intern", "junior", "senior", "principal")}   # every floor at the weakest
    cfg["paid_floor"] = {t: "haiku" for t in ("intern", "junior", "senior", "principal")}
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    lanes = lambda kind="code", tier="senior", failed=(), needs=(), pin=None: r.lanes(kind, tier, list(failed), list(needs), pin)
    pick = lambda kind="code", tier="senior", failed=(), needs=(): r.pick(kind, tier, list(failed), False, list(needs))
    paid = ["claude-haiku-9", "claude-sonnet-9", "claude-opus-9"]
    health(a_Top=True, b_Mid=True, c_Lo=True, d_NoVis=True, e_Down=False)          # one unhealthy model
    out = lanes()
    assert [x["model"] for x in out] == ["d/NoVis", "c/Lo", "b/Mid", "a/Top"] + paid, out  # ascending rank, then paid
    assert [x["rank"] for x in out] == [2, 3, 4, 5, None, None, None], out
    assert "e/Down" not in str(out), out                                             # unhealthy model absent
    health(a_Top=True, b_Mid=True, c_Lo=True, d_NoVis=False, e_Down=False)          # 3 healthy -> exactly 3 local lanes
    out = lanes()
    assert [x["model"] for x in out] == ["c/Lo", "b/Mid", "a/Top"] + paid, out
    first = pick()                                                                  # lanes[0] equals pick for the same args
    assert first["model"] == out[0]["model"] and first["flags"] == out[0]["flags"] \
        and first["provider"] == out[0]["provider"], (first, out[0])
    health(a_Top=True, b_Mid=True, c_Lo=True, d_NoVis=True, e_Down=False)
    assert [x["model"] for x in lanes(needs=["vision"])] == ["b/Mid", "a/Top"] + paid, "vision need must drop c/Lo and d/NoVis"
    assert [x["model"] for x in lanes(kind="vision")] == ["b/Mid", "a/Top"] + paid, "kind vision == --needs vision"
    assert [x["model"] for x in lanes(tier="principal")] == [x["model"] for x in lanes(tier="intern")], "equal floors give equal rungs"
    cfg["tier_floor"]["principal"] = "b/Mid"                                        # the floor picks the first rung
    assert [x["model"] for x in lanes(tier="principal")] == ["b/Mid", "a/Top"] + paid, lanes(tier="principal")
    cfg["tier_floor"]["principal"] = "e/Down"
    f = lanes(tier="principal")[0]["flags"]                                         # the tier's effort and skills, like pick's
    assert "--reasoning high" in f and "-s brainstorm -s agent-comms -s team -s manager" in f, f
    health(a_Top=False, b_Mid=False, c_Lo=False, d_NoVis=False, e_Down=False)      # all flatiron down
    assert [x["model"] for x in lanes()] == paid, lanes()                           # the paid rungs serve
    got = pick()
    assert got["model"] == "claude-haiku-9" and got["provider"] != "flatiron", got
    assert [x["model"] for x in lanes(kind="code", tier="senior", pin="sonnet")] == paid[1:], lanes("code", "senior", pin="sonnet")   # pin, then up the ladder


def check_needs():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"a/Top": 4, "b/Mid": 3}, "routes": {"code": ["a/Top", "b/Mid"]},
           "paid_ladder": ["haiku", "sonnet", "opus"],
           "features": {"a/Top": {"vision": True, "web": False}, "b/Mid": {"vision": False, "web": True},
                        "haiku": {"vision": True, "web": True}, "sonnet": {"vision": True, "web": True},
                        "opus": {"vision": True, "web": True}}}
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    pick = lambda kind="code", tier="senior", failed=(), needs=(): r.pick(kind, tier, list(failed), False, list(needs))
    health(a_Top=True, b_Mid=True)
    assert pick(needs=["web"])["model"] == "b/Mid"                                     # --needs web: the cheap web rung
    assert pick(needs=["vision"])["model"] == "a/Top"                                  # --needs vision: the only local fit
    assert pick("vision")["model"] == "a/Top"                                          # kind vision == --needs vision
    assert pick(needs=["vision", "web"])["model"] == "claude-haiku-9"                  # no local fit -> the paid rungs serve
    health(a_Top=True, b_Mid=True, n_Noentry=True)
    assert pick(needs=["web"])["model"] == "b/Mid"                                     # missing entry = no features
    assert "n/Noentry" not in str(pick(needs=["web"])), "an unranked model is no rung"
    cfg["features"]["haiku"] = {"vision": False, "web": False}
    cfg["features"]["sonnet"] = {"vision": False, "web": False}
    cfg["features"]["opus"] = {"vision": False, "web": False}
    got = pick(needs=["vision", "web"])
    assert got["provider"] is None and got["reason"].startswith("blocked:"), got       # no rung of any kind fits
    assert "failed" not in got["reason"], got                                          # none failed: no "( failed)"


def check_default_features():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"a/Top": 4}, "routes": {"code": ["a/Top"]}}       # a routing json with no features map
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {"a/Top": {"ok": False}}
    assert r.pick("code", "senior", [], False)["model"] == "claude-haiku-9"            # built-in Claude entries make the rungs fit
    got = r.pick("code", "senior", [], False, ["telepathy"])                           # no rung of any kind: the blocked line
    line = got["reason"]
    assert got["model"] is None and line.startswith("blocked:"), got
    assert "claude-sonnet-9 (vision=true, web=true)" in line, line                     # built-in Claude entries give the rungs their features
    cfg["features"] = {"haiku": {"vision": False, "web": False}}      # a loaded entry wins, missing keys keep the built-ins
    line = r.pick("code", "senior", [], False, ["telepathy"])["reason"]
    assert "claude-haiku-9 (vision=false, web=false)" in line, line
    assert "claude-sonnet-9 (vision=true, web=true)" in line, line


def check_probe_fallback():
    r = load("hermes-dispatch-route")
    r.routing = lambda: {"rank": {"a/Top": 4, "b/Mid": 3}, "routes": {}}
    r.save_section = lambda *a: None

    # /models raises a timeout -> ONE call, then ranked models probed directly; unranked ones absent
    calls = [0]
    def slow_list(path, body=None, timeout=60):
        calls[0] += 1
        raise TimeoutError("timed out")
    r._req = slow_list
    r.probe_one = lambda m: (m, {"ok": True, "latency_s": 0.2, "error": None})
    h = r.flatiron_status(refresh=True)
    assert calls[0] == 1, calls
    assert h["a/Top"]["ok"] is True and h["b/Mid"]["ok"] is True, h
    assert set(h) == set(r.routing()["rank"]), h

    # /models fails and every chat probe fails -> all down (gateway really down)
    r.probe_one = lambda m: (m, {"ok": False, "latency_s": 25.0, "error": "timed out"})
    h = r.flatiron_status(refresh=True)
    assert all(not v["ok"] for v in h.values()) and set(h) == {"a/Top", "b/Mid"}, h

    # /models returns an empty list -> same direct-probe fallback
    r._req = lambda *a, **k: {"data": []}
    r.probe_one = lambda m: (m, {"ok": True, "latency_s": 0.1, "error": None})
    h = r.flatiron_status(refresh=True)
    assert h["a/Top"]["ok"] is True, h


def check_sync_features():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        today = time.strftime("%Y-%m-%d")
        rj = Path(d, "routing.json")
        rj.write_text(json.dumps({"rank": {"a/Old": 1}, "routes": {}, "tiers": {},
                                  "features": {"a/Old": {"vision": True, "web": False, "probed": today},
                                               "s/Stale": {"vision": False, "web": False, "probed": "2026-10-01"},
                                               "s/Fresh": {"vision": True, "web": False, "probed": today},
                                               "s/Bad": {"vision": False, "web": False, "probed": "2026-10-01"}}}))
        r.ROUTING_FILE = rj
        r.SIDECAR_DIR = Path(d, "cache", "dispatch-route")   # the real shape: sidecars off the json dir
        listed = ["a/Old", "n/New", "s/Stale", "s/Fresh", "s/Bad", "t/Time", "d/Down"]
        health = {m: {"ok": m != "d/Down"} for m in listed}
        calls = []
        def fake_vision(model):
            calls.append(model)
            if model in ("s/Bad", "t/Time"):
                raise TimeoutError("host down")
            return model != "n/New"     # n/New has no vision, the rest do
        r._vision_probe = fake_vision
        r.sync_features(health, listed)
        feats = json.loads(rj.read_text())["features"]
        assert feats["n/New"] == {"vision": False, "web": False, "probed": today}, feats   # new healthy model gets an entry
        assert feats["s/Stale"] == {"vision": True, "web": False, "probed": today}, feats  # stale entry re-probed
        assert feats["s/Fresh"] == {"vision": True, "web": False, "probed": today}, feats
        assert "s/Fresh" not in calls and "a/Old" not in calls, calls                      # fresh entries not re-probed
        assert feats["s/Bad"] == {"vision": False, "web": False, "probed": "2026-10-01"}, feats  # failed re-probe keeps old entry
        assert "t/Time" not in feats and "d/Down" not in feats, feats                      # failed probe and unhealthy get none
        assert all(e["web"] is False for e in feats.values()), feats                       # flatiron web=False by provider rule
        assert set(calls) == {"n/New", "s/Stale", "s/Bad", "t/Time"}, calls
        # second run: only the stale survivors and the never-probed model are probed (record the
        # calls, the swallowed-AssertionError guard proved nothing)
        calls.clear()
        r._vision_probe = lambda model: calls.append(model) or True
        r.sync_features(health, listed)
        assert set(calls) == {"s/Bad", "t/Time"}, calls            # the expected retry set

        # M1: a mid-run edit of the json: sync aborts instead of writing a stale read over it
        edi = {"rank": {"a/Old": 1}, "routes": {"code": ["a/Old"]}, "tiers": {}, "features": {}}

        def edit_and_probe(model):
            rj.write_text(json.dumps(edi))     # an installed-copy editor writes while the probes run
            return True

        r._vision_probe = edit_and_probe
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r.sync_features({**health, "e/New2": {"ok": True}}, listed + ["e/New2"])
        assert "routing json changed during sync, not published" in buf.getvalue(), buf.getvalue()
        assert json.loads(rj.read_text()) == edi, "the mid-run edit must not be overwritten"


def check_sync_rank():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        rj = Path(d, "routing.json")
        base = {"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {},
                "features": {"a/Top": {"vision": True, "web": True}, "n/New": {"vision": False, "web": False}, "x/Z": {"vision": False, "web": False}, "w/New": {"vision": False, "web": False}}, "tiers": {}}
        rj.write_text(json.dumps(base))
        r.ROUTING_FILE = rj
        side = Path(d, "cache", "dispatch-route")   # the real shape: sidecars off the json dir
        r.SIDECAR_DIR = side
        health = {"a/Top": {"ok": True}, "b/Mid": {"ok": True}, "n/New": {"ok": True}, "x/Z": {"ok": True}}
        latest = {"opus": "claude-opus-9"}
        # no new model for the given listing: the ranker never runs (count calls: sync_rank swallows raises)
        calls = []
        r._run_ranker = lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("ranker ran"))
        r.sync_rank(latest, health, ["a/Top", "b/Mid"])
        assert calls == [] and json.loads(rj.read_text())["rank"] == base["rank"], calls
        # an order that drops a model is rejected; the json is untouched
        # (_selftest_ok is stubbed true so only the validation guard can stop the write)
        r._selftest_ok = lambda *_: True
        r._run_ranker = lambda *a, **k: {"a/Top": 2, "n/New": 1}
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        assert json.loads(rj.read_text()) == base
        # a valid order is accepted: the gate sees a scratch CANDIDATE while the live json is still
        # the previous text, the old json is backed up by name with the exact previous content
        before = rj.read_text()
        seen = []
        r._selftest_ok = lambda cand: seen.append((rj.read_text(), Path(cand).read_text())) or True
        r._run_ranker = lambda *a, **k: {"a/Top": 3, "n/New": 2, "b/Mid": 1}
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        got = json.loads(rj.read_text())
        assert got["rank"] == {"a/Top": 3, "n/New": 2, "b/Mid": 1}, got
        assert seen and seen[0][0] == before, "the live json must still be the old text at gate time"
        assert json.loads(seen[0][1])["rank"] == {"a/Top": 3, "n/New": 2, "b/Mid": 1}, "the gate must see the candidate order"
        backups = sorted(side.glob("routing.json.20??-??-??*"))
        assert len(backups) == 1 and backups[0].read_text() == before, [p.name for p in Path(d).iterdir()]
        # a selftest failure on the new order leaves the live json byte for byte and no candidate
        old = rj.read_text()
        r._selftest_ok = lambda *_: False
        r._run_ranker = lambda *a, **k: {"a/Top": 4, "x/Z": 2, "b/Mid": 1, "n/New": 3}
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New", "x/Z"])
        assert rj.read_text() == old and not list(Path(d).glob("routing.json.candidate*")), os.listdir(d)
        # F2: a ranked model the gateway lists no more drops out after 7 days (old sidecar date) and
        # heals when re-listed; the drop rides the same gated publish
        r._selftest_ok = lambda *_: True
        base2 = json.loads(rj.read_text())
        base2["rank"]["r/Gone"] = 9
        rj.write_text(json.dumps(base2))
        (side / "routing.json.last-listed").write_text(json.dumps({"r/Gone": "2020-01-01", "a/Top": "2020-01-01"}))
        r.sync_rank(latest, health, ["a/Top", "b/Mid"])       # nothing unranked: the drop publishes alone
        rank_now = json.loads(rj.read_text())["rank"]
        assert "r/Gone" not in rank_now, rank_now             # absent 7+ days -> dropped
        assert "a/Top" in rank_now and "b/Mid" in rank_now, rank_now
        seen2 = json.loads((side / "routing.json.last-listed").read_text())
        assert seen2["a/Top"] == time.strftime("%Y-%m-%d"), seen2  # re-listed: the clock resets

        # m1: a rejected publication keeps the retirement clock, the next sync retries the drop
        base3 = json.loads(rj.read_text())
        base3["rank"]["r/Gone"] = 9
        rj.write_text(json.dumps(base3))
        (side / (rj.name + ".last-listed")).write_text(json.dumps({"r/Gone": "2020-01-01", "a/Top": "2020-01-01"}))
        r._selftest_ok = lambda *_: False
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        assert "r/Gone" in json.loads(rj.read_text())["rank"], "a rejected publish must not drop the model"
        kept = json.loads((side / (rj.name + ".last-listed")).read_text())
        assert kept.get("r/Gone") == "2020-01-01", kept          # the clock is not restarted at today
        r._selftest_ok = lambda *_: True
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])  # the drop retries and lands
        assert "r/Gone" not in json.loads(rj.read_text())["rank"]

        # M1: a mid-run edit of the json aborts the publish: no write, no backup, no budget burn
        edi = json.loads(rj.read_text())
        edi["rank"] = {"z/Edited": 9}

        def rank_edit(*a, **k):
            rj.write_text(json.dumps(edi))       # an installed-copy editor writes while the ranker runs
            return {"a/Top": 3, "b/Mid": 1, "n/New": 2, "w/New": 4}

        r._selftest_ok = lambda *_: (_ for _ in ()).throw(AssertionError("publish ran after a mid-run edit"))
        (side / (rj.name + ".ranker-rejects")).unlink(missing_ok=True)
        r._run_ranker = rank_edit
        nbackup = len(list(side.glob(rj.name + ".20??-??-??*")))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New", "w/New"])
        assert "routing json changed during sync, not published" in buf.getvalue(), buf.getvalue()
        assert json.loads(rj.read_text()) == edi, "the mid-run edit must not be overwritten"
        assert len(list(side.glob(rj.name + ".20??-??-??*"))) == nbackup, "a stale abort writes no backup"
        assert not (side / (rj.name + ".ranker-rejects")).exists(), "a stale abort must not burn ranker budget"


def check_sync_rank_gates():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        sub = Path(d, "sub"); (sub / "refs").mkdir(parents=True); (sub / "scripts").mkdir()
        (sub / "scripts" / "selftest.py").write_text("")    # gate path must exist for the timeout below
        rj = sub / "refs" / "routing.json"
        raw = json.dumps({"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {},
                                  "features": {"n/New": {"vision": False, "web": False}, "y/New2": {"vision": False, "web": False}, "z/New3": {"vision": False, "web": False}}, "tiers": {}}) + "\n"
        rj.write_text(raw)
        r.ROUTING_FILE = rj
        side = Path(d, "cache", "dispatch-route")   # the real shape: sidecars off the json dir
        r.SIDECAR_DIR = side
        health = {m: {"ok": True} for m in ("a/Top", "b/Mid", "n/New", "y/New2", "z/New3")}
        latest = {"opus": "claude-opus-9"}
        calls = []
        def counted(order):    # a fresh budget per case, so every case must reach the ranker
            def _(*a, **k):
                calls.append(1)
                return order
            return _
        st_state = side / (rj.name + ".ranker-rejects")

        # a selftest gate timeout leaves the old json byte for byte (the gate fails closed)
        r._run_ranker = counted({"a/Top": 3, "b/Mid": 1, "n/New": 2})
        r.subprocess = types.SimpleNamespace(
            TimeoutExpired=subprocess.TimeoutExpired,
            run=lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("selftest", 120)))
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        assert rj.read_bytes() == raw.encode(), "a gate timeout must leave the old json"
        assert len(calls) == 1, calls

        # a gate that raises OSError fails closed the same way: untouched json + counted attempt
        r.subprocess = types.SimpleNamespace(
            TimeoutExpired=subprocess.TimeoutExpired,
            run=lambda *a, **k: (_ for _ in ()).throw(OSError("selftest python missing")))
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        assert rj.read_bytes() == raw.encode(), "a gate OSError must leave the old json"
        assert len(calls) == 2, calls
        assert json.loads(st_state.read_text())["attempts"] == 2, st_state.read_text()
        r.subprocess = subprocess

        # a string rank and a true rank are rejected and the json is unchanged
        r._selftest_ok = lambda *_: True
        st_state.unlink(missing_ok=True)                    # fresh budget: this case must rank
        r._run_ranker = counted({"a/Top": 3, "b/Mid": "1", "n/New": 2})
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        assert rj.read_bytes() == raw.encode(), "a string rank must be rejected"
        assert len(calls) == 3, calls
        st_state.unlink(missing_ok=True)                    # fresh budget: this case must rank too
        r._run_ranker = counted({"a/Top": 3, "b/Mid": True, "n/New": 2})
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        assert rj.read_bytes() == raw.encode(), "true must not pass as rank 1"
        assert len(calls) == 4, calls

        # 3 rejected runs stop the retries; a changed unranked set resets the count
        st_state.unlink(missing_ok=True)
        def rejecter(*a, **k):
            calls.append(1)
            return {"a/Top": 3, "b/Mid": 1}                 # drops n/New and y/New2 -> rejected
        r._run_ranker = rejecter
        lst = ["a/Top", "b/Mid", "n/New", "y/New2"]
        for _ in range(3):
            r.sync_rank(latest, health, lst)
        assert len(calls) == 7 and rj.read_bytes() == raw.encode(), calls
        r.sync_rank(latest, health, lst)                    # 4th sync: no ranker call
        assert len(calls) == 7, f"ranker ran on the 4th sync: {len(calls)}"
        r.sync_rank(latest, health, lst + ["z/New3"])       # new unranked set -> new budget
        assert len(calls) == 8, f"changed unranked set must reset the count: {len(calls)}"


def check_sync_rank_gate_crash():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        rj = Path(d, "routing.json")
        raw = json.dumps({"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {},
                                  "features": {"n/New": {"vision": False, "web": False}}, "tiers": {}}) + "\n"
        rj.write_text(raw)
        r.ROUTING_FILE = rj
        side = Path(d, "cache", "dispatch-route")   # the real shape: sidecars off the json dir
        r.SIDECAR_DIR = side
        health = {m: {"ok": True} for m in ("a/Top", "b/Mid", "n/New")}
        latest = {"opus": "claude-opus-9"}
        # a valid order, then the gate itself raises after it saw the candidate: the live json must
        # stay byte for byte and one attempt is counted (no exception leaves sync_rank)
        r._run_ranker = lambda *a, **k: {"a/Top": 3, "b/Mid": 1, "n/New": 2}
        r._selftest_ok = lambda *_: (_ for _ in ()).throw(RuntimeError("gate crashed"))
        r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        assert rj.read_bytes() == raw.encode(), "a raising gate must restore the old json"
        st_state = side / (rj.name + ".ranker-rejects")
        assert json.loads(st_state.read_text())["attempts"] == 1, st_state.read_text()
        assert not list(rj.parent.glob(rj.name + ".candidate*")), os.listdir(rj.parent)   # no candidate leaks
        # m2: a failed atomic write leaves no temp file behind
        adir = rj.parent / "adir"
        adir.mkdir()
        raised = False
        try:
            r._write_file_atomic(adir, "x")                     # the replace onto a directory fails
        except OSError:
            raised = True
        assert raised, "the replace onto a directory must fail"
        assert not [p.name for p in rj.parent.iterdir() if p.name.startswith("adir.")], os.listdir(rj.parent)


def check_sync_rank_budget():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        rj = Path(d, "routing.json")
        raw = json.dumps({"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {},
                                  "features": {"n/New": {"vision": False, "web": False}, "y/New2": {"vision": False, "web": False}}, "tiers": {}}) + "\n"
        rj.write_text(raw)
        r.ROUTING_FILE = rj
        side = Path(d, "cache", "dispatch-route")   # the real shape: sidecars off the json dir
        r.SIDECAR_DIR = side
        state = side / (rj.name + ".ranker-rejects")
        health = {m: {"ok": True} for m in ("a/Top", "b/Mid", "n/New", "y/New2")}
        latest = {"opus": "claude-opus-9"}                    # no web-capable flatiron model -> the Claude rung ranks
        lst = ["a/Top", "b/Mid", "n/New"]                     # unranked part: ["n/New"]
        r._selftest_ok = lambda *_: True

        # a ranker that returns no order (timeout / non-JSON) counts: 3 runs, then no 4th
        calls = []
        def no_reply(*a, **k):
            calls.append(a)
            return None
        r._run_ranker = no_reply
        for _ in range(3):
            r.sync_rank(latest, health, lst)
        assert len(calls) == 3 and json.loads(state.read_text())["attempts"] == 3, calls
        r.sync_rank(latest, health, lst)                      # 4th sync: no ranker call
        assert len(calls) == 3, f"ranker ran on the 4th sync: {len(calls)}"
        r.sync_rank(latest, health, lst + ["y/New2"])         # new unranked set -> new budget
        assert len(calls) == 4, f"changed unranked set must reset the count: {len(calls)}"

        # a selftest gate that rejects the order counts too: 3 runs, then no 4th
        state.unlink(missing_ok=True)
        calls.clear()
        r._selftest_ok = lambda *_: False
        def gate_bad(*a, **k):
            calls.append(a)
            return {"a/Top": 3, "b/Mid": 1, "n/New": 2}
        r._run_ranker = gate_bad
        for _ in range(3):
            r.sync_rank(latest, health, lst)
        assert len(calls) == 3 and rj.read_text() == raw, calls
        r.sync_rank(latest, health, lst)                      # 4th sync: no ranker call
        assert len(calls) == 3, f"ranker ran on the 4th sync after gate rejects: {len(calls)}"

        # a state file without the attempts key must not crash the budget check
        state.write_text(json.dumps({"models": ["n/New"]}))
        r._selftest_ok = lambda *_: True
        r._run_ranker = no_reply
        calls.clear()
        r.sync_rank(latest, health, lst)
        assert len(calls) == 1 and json.loads(state.read_text())["attempts"] == 1, calls

        # a malformed state value is a fresh budget of 0 and is rewritten on the next count
        state.write_text(json.dumps({"models": ["n/New"], "attempts": "x"}))
        calls.clear()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r.sync_rank(latest, health, lst)
        assert "ranker-rejects: malformed, reset" in buf.getvalue(), buf.getvalue()
        assert len(calls) == 1 and json.loads(state.read_text()) == {"models": ["n/New"], "attempts": 1}, calls

        # a raising ranker counts exactly like no reply: one attempt per run, then the budget stops it
        for boom in (RuntimeError("ranker exploded"), OSError("no hermes")):
            state.unlink(missing_ok=True)
            calls.clear()
            def raiser(*a, _e=boom, **k):
                calls.append(a)
                raise _e
            r._run_ranker = raiser
            for i in range(1, 4):
                r.sync_rank(latest, health, lst)
                assert len(calls) == i and json.loads(state.read_text())["attempts"] == i, calls
            r.sync_rank(latest, health, lst)                 # 4th sync: budget spent, no ranker call
            assert len(calls) == 3 and json.loads(rj.read_text()) == json.loads(raw), calls


def check_sync_config_fail():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        r.ROUTING_FILE = Path(d, "routing.json")
        r.ROUTING_FILE.write_text(json.dumps({"rank": {"a/Top": 1}, "routes": {}, "features": {}, "tiers": {}}))
        r.SIDECAR_DIR = Path(d, "cache", "dispatch-route")   # the real shape: sidecars off the json dir
        r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                       "haiku": "claude-haiku-9", "sol": "x"}
        r.flatiron_status = lambda *a: {"a/Top": {"ok": True}}
        r.load_cache = lambda: {"flatiron": {"listed": ["a/Top"]}}
        r.sync_features = lambda *a: None
        r.sync_rank = lambda *a: None
        log = []                                             # one tuple per hermes config call
        def run_factory(get_fn, fail=()):
            def run(cmd, **kw):
                if cmd[2] == "get":
                    return get_fn(cmd[3])
                log.append((cmd[2], cmd[3], cmd[4] if len(cmd) > 4 else None))
                if cmd[3] in fail and not str(cmd[4] if len(cmd) > 4 else "").startswith("OLD-"):
                    raise subprocess.CalledProcessError(1, cmd)   # new writes fail, the restores succeed
                return types.SimpleNamespace(stdout="ok", stderr="", returncode=0)
            return run
        ns = lambda rc, so, se: types.SimpleNamespace(stdout=so, stderr=se, returncode=rc)

        # a failed set exits nonzero and stops at the failed key
        r.subprocess = types.SimpleNamespace(run=run_factory(lambda k: ns(0, f"OLD-{k}", ""),
                                                             {"delegation.fallback_providers"}),
                                             TimeoutExpired=subprocess.TimeoutExpired,
                                             CalledProcessError=subprocess.CalledProcessError)
        assert r.sync(False) == 1, "a failed set must exit nonzero"
        assert [x[1] for x in log] == ["delegation.fallback_providers", "delegation.fallback_providers"], log

        # provider and model are written last, and a failed set rolls every attempted key back
        r.subprocess.run = run_factory(lambda k: ns(0, f"OLD-{k}", ""), {"delegation.model"})
        log.clear()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            assert r.sync(False) == 1
        assert [x[1] for x in log][:4] == ["delegation.fallback_providers", "delegation.tiers",
                                           "delegation.provider", "delegation.model"], log
        assert log[4:] == [("set", "delegation.model", "OLD-delegation.model"),
                           ("set", "delegation.provider", "OLD-delegation.provider"),
                           ("set", "delegation.tiers", "OLD-delegation.tiers"),
                           ("set", "delegation.fallback_providers", "OLD-delegation.fallback_providers")], log
        assert "restored delegation.model" in buf.getvalue(), buf.getvalue()

        # a real get failure (not an unset key) exits nonzero before any write
        r.subprocess.run = run_factory(lambda k: ns(2, "", "boom"))
        log.clear()
        assert r.sync(False) == 1 and log == [], log

        # an unset key is not a failed get: sync falls through to the writes
        r.subprocess.run = run_factory(lambda k: ns(1, "", f"Config key not set: {k}"))
        log.clear()
        assert r.sync(False) == 0, "an unset key must not fail the sync"
        assert [x[1] for x in log] == ["delegation.fallback_providers", "delegation.tiers",
                                       "delegation.provider", "delegation.model"], log

        # M4+M5: a set that lands in the store and then raises rolls EVERY attempted key back,
        # and the config lock is held across reads, writes and rollback
        store = {k: f"OLD-{k}" for k in ("delegation.fallback_providers", "delegation.tiers",
                                        "delegation.provider", "delegation.model")}
        oldvals = dict(store)
        lockfile = r.SIDECAR_DIR / "config-write.lock"

        def lock_held():
            with open(lockfile, "w") as fh:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return True                # busy: the config transaction holds it
            return False

        def run_store(cmd, **kw):
            assert lock_held(), f"{cmd[:3]} ran outside the config lock"
            key = cmd[3]
            if cmd[2] == "get":
                return types.SimpleNamespace(stdout=store[key], stderr="", returncode=0)
            store[key] = cmd[4]                # the write lands
            if key == "delegation.model" and not str(cmd[4]).startswith("OLD-"):
                raise subprocess.CalledProcessError(1, cmd)   # and then the call fails
            return types.SimpleNamespace(stdout="ok", stderr="", returncode=0)

        r.subprocess.run = run_store
        log.clear()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            assert r.sync(False) == 1
        assert store == oldvals, store        # all keys old again, the failing one included
        assert "restored delegation.model" in buf.getvalue(), buf.getvalue()
        assert not lock_held(), "the config lock must be released after the transaction"


def check_tier_min_rank():
    """The legacy tiers[TIER].min_rank is the tier floor when tier_floor names no model for the
    tier: only rungs at or above it serve. A non-integer value is ignored."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"a/Strong": 5, "b/Mid": 3, "c/Weak": 1}, "routes": {"code": ["a/Strong", "b/Mid", "c/Weak"]},
           "paid_ladder": [],
           "tiers": {"senior": {"reasoning_effort": "high", "min_rank": 4},
                     "intern": {"reasoning_effort": "low"}}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in cfg["rank"]}
    assert [x["model"] for x in r.lanes("code", "senior", [], [])] == ["a/Strong"]     # only rungs at or above rank 4
    got = r.pick("code", "senior", [], False)
    assert got["model"] == "a/Strong", got
    assert [x["model"] for x in r.lanes("code", "intern", [], [])] == ["c/Weak", "b/Mid", "a/Strong"]  # no key: whole ladder
    cfg["tiers"]["senior"]["min_rank"] = "four"                                       # a bad value is ignored
    assert [x["model"] for x in r.lanes("code", "senior", [], [])] == ["c/Weak", "b/Mid", "a/Strong"]
    # the v2.3.3 Sol case: a fixture with only the legacy intern min_rank routes an untiered and
    # an unknown tier to that min_rank start
    cfg["tiers"] = {"intern": {"reasoning_effort": "low", "min_rank": 3}}
    for tier in (None, "ghost"):
        assert [m for _p, m, _t in r.ladder([], [], tier)] == ["b/Mid", "a/Strong"], tier
    assert [x["model"] for x in r.lanes("code", "intern", [], [])] == ["b/Mid", "a/Strong"]
    assert r.pick("code", "intern", [], False)["model"] == "b/Mid"


def check_max_effort():
    """The entry's max_effort caps the rung's reasoning effort at min(requested, max_effort). The
    shipped table caps Qwen at medium, so a principal vision pick never asks high (HTTP 400)."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "x"}
    jpath = STAGE / "flatiron-routing.json"                       # staged runs judge the staged json
    cfg = json.loads((jpath if jpath.is_file() else r.ROUTING_FILE).read_text())
    QWEN = "Qwen/Qwen3.8-27B-FP8"
    assert (cfg.get("features") or {}).get(QWEN, {}).get("max_effort") == "medium", cfg.get("features")
    r.routing = lambda: cfg
    r.inflight_counts = lambda: {}
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in cfg["rank"]}
    out = r.pick("vision", "principal", [], False)
    assert out["model"] == QWEN, out
    effort = out["flags"].split("--reasoning ", 1)[1].split()[0]
    assert effort in ("none", "minimal", "low", "medium"), effort                     # never above the cap
    assert r._effort(QWEN, "xhigh", cfg) == "medium"                                  # min(requested, max_effort)
    assert r._effort(QWEN, "low", cfg) == "low"                                       # a request below the cap stays
    uncapped = dict(cfg); uncapped["features"] = {QWEN: {"vision": True, "web": False}}
    assert r._effort(QWEN, "high", uncapped) == "medium"                              # the efforts map still clamps


def check_sync_rank_reasons():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        rj = Path(d, "routing.json")
        feats = {m: {"vision": False, "web": False} for m in ("n/New", "y/New2", "z/New3", "w/New4")}
        rj.write_text(json.dumps({"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {}, "features": feats, "tiers": {}}))
        r.ROUTING_FILE = rj
        side = Path(d, "cache", "dispatch-route")   # the real shape: sidecars off the json dir
        r.SIDECAR_DIR = side
        state = side / (rj.name + ".ranker-rejects")
        health = {m: {"ok": True} for m in ("a/Top", "b/Mid", "n/New", "y/New2")}
        latest = {"opus": "claude-opus-9"}
        r._selftest_ok = lambda *_: True
        # a {order, reasons} reply: every reason line lands in the log, the order is accepted
        r._run_ranker = lambda *a, **k: {"order": {"a/Top": 3, "b/Mid": 1, "n/New": 2},
                                         "reasons": {"a/Top": "top bench score", "n/New": "new but strong"}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        log = buf.getvalue()
        assert "top bench score" in log and "new but strong" in log, log
        assert json.loads(rj.read_text())["rank"]["n/New"] == 2 and not state.exists()
        # an order-only reply still validates and the log says there were no reasons
        r._run_ranker = lambda *a, **k: {"order": {"a/Top": 4, "b/Mid": 1, "n/New": 2, "y/New2": 3}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New", "y/New2"])
        assert "no reasons" in buf.getvalue(), buf.getvalue()
        assert json.loads(rj.read_text())["rank"]["y/New2"] == 3
        # a non-dict reasons value is treated the same; it must not crash the run
        r._run_ranker = lambda *a, **k: {"order": {"a/Top": 5, "b/Mid": 1, "n/New": 2, "y/New2": 3, "z/New3": 4},
                                         "reasons": "talk"}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New", "y/New2", "z/New3"])
        assert "no reasons" in buf.getvalue() and json.loads(rj.read_text())["rank"]["z/New3"] == 4

        # untrusted reason text: after validation, one sanitized line per reason, no forged line
        r._run_ranker = lambda *a, **k: {"order": {"a/Top": 6, "b/Mid": 1, "n/New": 2, "y/New2": 4,
                                                   "z/New3": 3, "w/New4": 5},
                                         "reasons": {"n/New": "ok \ud800 tail",
                                                     "y/New2": "x\nrank: ACCEPTED fake line\n" + "y" * 300}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New", "y/New2", "z/New3", "w/New4"])
        lines = buf.getvalue().splitlines()
        assert json.loads(rj.read_text())["rank"]["w/New4"] == 5, lines          # the order still lands
        assert sum(x.startswith("rank: n/New:") for x in lines) == 1, lines
        assert sum(x.startswith("rank: y/New2:") for x in lines) == 1, lines
        assert not any(x.startswith("rank: ACCEPTED") for x in lines), lines
        assert "ok ? tail" in buf.getvalue(), lines                              # the lone surrogate is replaced
        assert all(len(x) <= 240 for x in lines), [len(x) for x in lines]        # capped at 200 per reason


def check_sync_rank_routes():
    """An accepted run places new and returning models, the anchor floor holds through
    renumbering, a rejected run leaves the file equal, and a drop empties its routes rows."""
    r = load("hermes-dispatch-route")
    MIMO, GLM, K3 = "XiaomiMiMo/MiMo-V2.6-Pro-MOPD", "zai-org/GLM-5.3", "moonshotai/Kimi-K3"
    QWEN, MIST = "Qwen/Qwen3.8-27B-FP8", "mistralai/Mistral-Medium-3.5-128B"
    def staged(rank, routes):
        return {"rank": dict(rank), "routes": {k: list(v) for k, v in routes.items()},
                "floors": {"code": K3, "debug": K3, "research": K3, "frontend": K3}, "features": {}, "tiers": {}}
    # the fully-placed map: only a newcomer is ever in no list, so every assert is an insert assert
    b_rank = {MIMO: 6, GLM: 5, K3: 4, QWEN: 3, MIST: 1}
    b_routes = {"code": [MIMO, K3, GLM], "debug": [MIMO, K3, GLM], "research": [MIMO, K3, GLM],
                "frontend": [MIMO, GLM, K3, QWEN], "prose": [MIST, MIMO, K3, GLM],
                "mechanical": [MIST, QWEN, GLM, QWEN, K3, MIMO]}   # QWEN twice: a one-copy drop must fail
    with tempfile.TemporaryDirectory() as d:
        rj = Path(d, "routing.json")
        side = Path(d, "cache", "dispatch-route")   # the real shape: sidecars off the json dir
        r.ROUTING_FILE = rj
        r.SIDECAR_DIR = side
        r._selftest_ok = lambda *_: True
        latest = {"opus": "claude-opus-9"}
        def sync(cfg, listed, order, ok=True):
            """One sync_rank with a stubbed ranker (order None = no usable reply). File bytes."""
            cfg.setdefault("features", {}).update({m: {"vision": False, "web": False} for m in listed})   # the probes succeeded
            rj.write_text(json.dumps(cfg) + "\n")
            side.mkdir(parents=True, exist_ok=True)
            (side / (rj.name + ".ranker-rejects")).unlink(missing_ok=True)
            r._run_ranker = (lambda *a, **k: dict(order)) if order is not None else (lambda *a, **k: None)
            before = rj.read_bytes()
            r.sync_rank(latest, {m: {"ok": ok} for m in listed}, listed)
            return before, rj.read_bytes()

        # a newcomer ranked top joins code/debug/research and every other kind at rank position
        cfg = staged(b_rank, b_routes)
        _, raw = sync(cfg, list(b_rank) + ["n/Above"], {MIMO: 5, GLM: 4, K3: 3, QWEN: 2, MIST: 1, "n/Above": 6})
        got = json.loads(raw)
        for kind, lst in b_routes.items():
            assert got["routes"][kind] == ["n/Above"] + lst, (kind, got["routes"][kind])

        # a newcomer ranked below the floor joins prose/mechanical (no floor kinds) and is
        # inserted last; code/debug/research/frontend keep byte-equal rows
        cfg = staged(b_rank, b_routes)
        _, raw = sync(cfg, list(b_rank) + ["n/Below"], {MIMO: 6, GLM: 5, K3: 4, QWEN: 3, MIST: 2, "n/Below": 1})
        got = json.loads(raw)
        for kind in ("code", "debug", "research", "frontend"):
            assert got["routes"][kind] == b_routes[kind], (kind, got["routes"][kind])
        for kind in ("prose", "mechanical"):
            assert got["routes"][kind] == b_routes[kind] + ["n/Below"], (kind, got["routes"][kind])

        # fail closed: a json with no floors key at all admits no newcomer to the floored
        # kinds, logs one line per kind, and still admits to prose/mechanical
        cfg = staged(b_rank, b_routes)
        cfg.pop("floors")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            _, raw = sync(cfg, list(b_rank) + ["n/Below"], {MIMO: 6, GLM: 5, K3: 4, QWEN: 3, MIST: 2, "n/Below": 1})
        got = json.loads(raw)
        for kind in ("code", "debug", "research", "frontend"):
            assert got["routes"][kind] == b_routes[kind], (kind, got["routes"][kind])
        for kind in ("prose", "mechanical"):
            assert got["routes"][kind] == b_routes[kind] + ["n/Below"], (kind, got["routes"][kind])
        log = buf.getvalue().splitlines()
        for kind in ("code", "debug", "research", "frontend"):
            assert sum(f"floors has no entry for {kind};" in x for x in log) == 1, log

        # a floors anchor that ranks no more fails closed for that kind only; the other
        # kinds still place the newcomer
        cfg = staged(b_rank, b_routes)
        cfg["floors"]["code"] = "n/Gone"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            _, raw = sync(cfg, list(b_rank) + ["n/Above"], {MIMO: 5, GLM: 4, K3: 3, QWEN: 2, MIST: 1, "n/Above": 6})
        got = json.loads(raw)
        for kind, lst in b_routes.items():
            assert got["routes"][kind] == (lst if kind == "code" else ["n/Above"] + lst), \
                (kind, got["routes"][kind])
        log = buf.getvalue().splitlines()
        assert sum("floor anchor n/Gone ranks no more; code takes no new model" in x
                   for x in log) == 1, log

        # an unhealthy newcomer ranks but takes no routes row
        cfg = staged(b_rank, b_routes)
        _, raw = sync(cfg, list(b_rank) + ["n/Away"], {MIMO: 5, GLM: 4, K3: 3, QWEN: 2, MIST: 1, "n/Away": 6},
                      ok=False)
        got = json.loads(raw)
        assert got["rank"]["n/Away"] == 6 and got["routes"] == b_routes, (got["rank"], got["routes"])

        # the same model recovered: a sync with no unranked model must place it without any
        # new ranking (placement is local, the ranker must not run)
        r._run_ranker = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ranker ran with no unranked model"))
        r.sync_rank(latest, {m: {"ok": True} for m in list(b_rank) + ["n/Away"]}, list(b_rank) + ["n/Away"])
        got = json.loads(rj.read_text())
        for kind, lst in b_routes.items():
            assert got["routes"][kind] == ["n/Away"] + lst, (kind, got["routes"][kind])

        # after a top newcomer renumbers the whole set Qwen and Mistral stay out of
        # code/debug/research/frontend; both returned from a drop, so they are placement candidates and
        # Qwen's value 4 is exactly what a literal rank >= 4 would let in
        rank0 = {MIMO: 4, GLM: 3, K3: 2, "moonshotai/Kimi-K2.6": 1}   # post-drop map: no Qwen/Mistral
        K26 = "moonshotai/Kimi-K2.6"
        routes0 = {"code": [MIMO, K3, GLM], "debug": [MIMO, K3, GLM], "research": [MIMO, K3, GLM],
                   "frontend": [MIMO, GLM, K3], "prose": [MIMO, K3, GLM], "mechanical": [GLM, K3, MIMO]}
        cfg = staged(rank0, routes0)
        models = [MIMO, GLM, K3, K26, QWEN, MIST, "n/Above", "n/Below"]
        order = {"n/Above": 8, MIMO: 7, GLM: 6, K3: 5, QWEN: 4, K26: 3, MIST: 2, "n/Below": 1}
        _, raw = sync(cfg, models, order)
        got = json.loads(raw)
        assert got["rank"] == order, got["rank"]
        for kind in ("code", "debug", "research", "frontend"):
            assert got["routes"][kind] == ["n/Above"] + routes0[kind], (kind, got["routes"][kind])
            assert QWEN not in got["routes"][kind] and MIST not in got["routes"][kind], (kind, got["routes"][kind])
        for kind in ("prose", "mechanical"):
            assert got["routes"][kind] == (["n/Above"] + routes0[kind]
                                           + [QWEN, K26, MIST, "n/Below"]), (kind, got["routes"][kind])

        # a rejected ranker run leaves routes byte-equal when every ranked model already sits in
        # some list and nothing drops (no reply, and an order that drops)
        for bad in (None, {MIMO: 6, GLM: 5, K3: 4, QWEN: 3, MIST: 1}):
            cfg = staged(b_rank, b_routes)
            before, after = sync(cfg, list(b_rank) + ["n/New"], bad)
            assert before == after, "a rejected ranker run must leave the file byte equal"

        # the same reject must not suppress unrelated recovery: a healthy, previously ranked model
        # missing from every routes list is placed on that sync (order None = no reply, the dict
        # drops n/New), while the reject is still counted (rejecting an order is not rejecting
        # recovery)
        q_routes = {k: [x for x in v if x != QWEN] for k, v in b_routes.items()}
        for bad in (None, {MIMO: 6, GLM: 5, K3: 4, QWEN: 3, MIST: 1}):
            cfg = staged(b_rank, q_routes)
            before, after = sync(cfg, list(b_rank) + ["n/New"], bad)
            assert before != after, "a reject must not suppress the placement of a recovered model"
            got = json.loads(after)
            assert got["rank"] == b_rank, got["rank"]                 # the reject never rewrites ranks
            for kind in ("code", "debug", "research"):
                assert got["routes"][kind] == q_routes[kind], (kind, got["routes"][kind])
            assert got["routes"]["frontend"] == q_routes["frontend"], got["routes"]["frontend"]  # below the floor
            assert got["routes"]["prose"] == q_routes["prose"] + [QWEN], got["routes"]["prose"]
            assert got["routes"]["mechanical"] == q_routes["mechanical"] + [QWEN], got["routes"]["mechanical"]
            att = json.loads((side / (rj.name + ".ranker-rejects")).read_text())
            assert att["attempts"] == 1, att                          # the reject still burns one run

        # a model the gateway lists no more leaves the rank map and every routes list at once
        cfg = staged(b_rank, b_routes)
        rj.write_text(json.dumps(cfg) + "\n")
        side.mkdir(parents=True, exist_ok=True)
        (side / (rj.name + ".ranker-rejects")).unlink(missing_ok=True)
        (side / (rj.name + ".last-listed")).write_text(json.dumps({QWEN: "2020-01-01", MIMO: "2020-01-01"}))
        r._run_ranker = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ranker ran on a drop-only sync"))
        r.sync_rank(latest, {m: {"ok": True} for m in b_rank}, [m for m in b_rank if m != QWEN])
        got = json.loads(rj.read_text())
        assert QWEN not in got["rank"], got["rank"]
        for kind, lst in b_routes.items():
            assert got["routes"][kind] == [x for x in lst if x != QWEN], (kind, got["routes"][kind])

        # a placement crash is not a ranker reject: the counter stays put, the routes rows keep
        # their bytes, the crash logs one line, and the accepted order still publishes
        cfg = staged(b_rank, b_routes)
        r._place_routes = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("placement crashed"))
        counted = []
        r._count_reject = lambda *a, **k: counted.append(a)   # spy: the reject counter must not move
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            before, after = sync(cfg, list(b_rank) + ["n/Above"],
                                 {MIMO: 5, GLM: 4, K3: 3, QWEN: 2, MIST: 1, "n/Above": 6})
        assert not counted, f"a placement crash must not burn a ranker retry: {counted}"
        assert not (side / (rj.name + ".ranker-rejects")).exists(), "the reject counter must stay put"
        assert sum("in _place_routes" in x for x in buf.getvalue().splitlines()) == 1, buf.getvalue()
        got = json.loads(after)
        assert json.dumps(got["routes"]) == json.dumps(json.loads(before)["routes"]), \
            "a placement crash must leave the parsed routes equal"
        assert got["rank"]["n/Above"] == 6, got["rank"]   # the accepted ranks still publish


def check_vision_probe():
    r = load("hermes-dispatch-route")
    real_images = r._probe_images
    imgs = [("G1", "red", "top left"), ("G1", "blue", "top right"),
            ("G2", "green", "bottom left"), ("G2", "yellow", "bottom right")]
    r._probe_images = lambda: list(imgs)                     # fixed wants: deterministic decisions
    def stub(replies, finish="stop", boom=None):
        it = iter(replies)
        def _req(path, body=None, timeout=60):
            if boom:
                raise boom
            return {"choices": [{"finish_reason": finish, "message": {"content": next(it)}}]}
        return _req
    r._req = stub(["red", "blue", "green", "yellow"]);        assert r._vision_probe("m") is True   # 4 of 4 right
    r._req = stub(["Red.", "blue!", "green?", "Yellow"]);     assert r._vision_probe("m") is True   # case and trailing punct
    r._req = stub(["red", "blue", "green", "black"]);         assert r._vision_probe("m") is None   # 3 of 4 is not vision=true
    r._req = stub(["red", "yellow", "green", "red"]);         assert r._vision_probe("m") is False  # 2 clear wrong answers
    r._req = stub(["yellow", "green", "red", "blue"]);        assert r._vision_probe("m") is False  # 4 clear wrong answers
    r._req = stub(["red", "blue", "nonsense!", "black"]);     assert r._vision_probe("m") is None   # one inconclusive: no false
    r._req = stub(["red", "blue", "green", "The square is blue"]); assert r._vision_probe("m") is None
    r._req = stub(["I cannot see the image, so I cannot tell whether it is red", "blue", "green", "yellow"])
    assert r._vision_probe("m") is None                       # a refusal naming a colour is inconclusive
    r._req = stub(["red", "blue", "green", "yellow"], finish="length"); assert r._vision_probe("m") is None  # truncated
    r._req = lambda *a, **k: {};                    assert r._vision_probe("m") is None   # malformed
    r._req = stub([], boom=TimeoutError());          assert r._vision_probe("m") is None   # HTTP error
    # M3: the parser takes one colour word, or that word then end or punctuation, nothing else
    png = r._grid_png_b64([(0, 0, 0)] * 4)
    for text in ("red", "Red.", "RED!", "  red  ,", "red; next"):
        r._req = stub([text]); assert r._vision_question("m", png, "red", "top left") is True, text
    for text in ("The square is red", "red or blue", "I see red", "answer: red",
                 "I cannot see the image, so I cannot tell whether it is red", ""):
        r._req = stub([text]); assert r._vision_question("m", png, "red", "top left") is None, text
    r._req = stub(["Blue, not red"]); assert r._vision_question("m", png, "red", "top left") is False
    # a constant guesser runs against random grids: the four answers are never all equal
    r._probe_images = real_images
    for _ in range(20):
        r._req = stub(["Red"] * 4)                            # a fresh set of grids per probe
        assert r._vision_probe("m") is not True, "one guess must not mark a model vision-capable"
    # inconclusive evidence never writes vision=false
    r._vision_probe = lambda *a: None
    assert r.probe_features("x") is None
    r._vision_probe = lambda *a: True
    assert r.probe_features("x") == {"vision": True, "probed": time.strftime("%Y-%m-%d")}
    # the generator: two grids, two quadrant questions each, answers not all equal
    for _ in range(20):
        items = real_images()
        assert len(items) == 4, items
        assert all(w in r._VOCAB and qd in r._QUADS for _, w, qd in items), items
        assert len({p for p, _, _ in items}) == 2, items                        # two grids
        for p in {p for p, _, _ in items}:
            ws = [w for p2, w, _ in items if p2 == p]
            assert len(ws) == 2 and ws[0] != ws[1], (p, ws)                     # answers differ within a grid
        assert len({w for _, w, _ in items}) >= 2, items                        # answers not all equal


def check_assign():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"m1": 3, "m2": 2, "m3": 1, "x/Idle": 9}, "tiers": json.loads(r.ROUTING_FILE.read_text())["tiers"],
           "routes": {"code": ["m1", "m2", "m3"]},
           "paid_ladder": ["haiku", "sonnet", "opus"],
           "features": {"m1": {"vision": True}, "m2": {"vision": True}, "m3": {"vision": False}, "x/Idle": {"vision": False},
                        "haiku": {"vision": True, "web": True}, "sonnet": {"vision": True, "web": True},
                        "opus": {"vision": True, "web": True}}}
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    def run(specs, inflight):
        r.inflight_counts = lambda: dict(inflight)
        return r.assign(specs)
    specs = [(f"n{i}", "code", "senior", []) for i in (1, 2, 3, 4)]
    health(m1=True, m2=True, m3=True, x_Idle=True)
    out = run(specs, {})                                # one empty batch spreads in ladder order
    assert [o["model"] for o in out] == ["m3", "m2", "m1", "x/Idle"], out
    assert [o["node"] for o in out] == ["n1", "n2", "n3", "n4"], out
    assert [o["load"] for o in out] == [0, 0, 0, 0], out
    assert all(o["provider"] == "flatiron" and o["fallback"] is False for o in out), out
    assert all(o["kind"] == "code" and o["tier"] == "senior" for o in out), out
    assert all(o["reason"] for o in out), out
    assert set(out[0]) == {"node", "kind", "tier", "provider", "model", "flags", "load", "reason", "fallback"}, out
    assert out[0]["flags"] == r.pick("code", "senior", [], False)["flags"], out     # flags == pick's

    out = run([("n1", "code", "senior", [])], {"m3": 3})           # 3 live jobs on m3 -> the next rung
    assert out[0]["model"] == "m2" and out[0]["load"] == 0, out

    out = run([("n1", "code", "senior", []), ("n2", "code", "senior", [])], {"m3": 3, "m2": 2, "m1": 1})
    # busy flatiron rungs never push a node to the paid rungs: x/Idle and then the tie in ladder order
    assert [o["model"] for o in out] == ["x/Idle", "m1"], out
    assert [o["load"] for o in out] == [0, 1], out
    out = run([("n1", "code", "senior", [])], {"m3": 9, "m2": 9, "m1": 9, "x/Idle": 9})
    assert out[0]["provider"] == "flatiron", out                    # every local rung busy: still no paid rung

    # kind vision (no routes list) serves the vision rungs: local first, paid when no local fits
    cfg["rank"], cfg["routes"] = {"v1": 2, "v2": 9}, {"code": ["v1"]}
    cfg["features"].update({"v1": {"vision": True, "web": False}, "v2": {"vision": False, "web": False}})
    health(v1=True, v2=True)
    out = run([("n1", "vision", "junior", [])], {})
    assert out[0]["model"] == "v1" and "v2" not in str(out), out
    health(v1=False, v2=True)                                      # no local vision rung -> the paid rungs
    out = run([("n1", "vision", "junior", [])], {})
    assert out[0]["model"] == "claude-haiku-9" and out[0]["provider"] != "flatiron", out
    out = run([("n1", "code", "senior", ["telepathy"])], {})        # no rung of any kind: the blocked line
    assert out[0]["fallback"] is True and out[0]["model"] is None, out
    assert out[0]["provider"] is None and out[0]["load"] == 0 and out[0]["reason"].startswith("blocked:"), out


def check_assign_capacity():
    # the capacity map is gone: a model serves every node, no skip and no serialization
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"s/One": 3, "q/Qwen": 2, "s/Two": 1}, "tiers": json.loads(r.ROUTING_FILE.read_text())["tiers"],
           "routes": {"mechanical": ["s/One", "q/Qwen", "s/Two"]},
           "paid_ladder": [], "capacity": {"q/Qwen": 4, "s/One": 1, "s/Two": 1}, "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in ("s/One", "q/Qwen", "s/Two")}
    r.inflight_counts = lambda: {}
    out = r.assign([(f"n{i}", "mechanical", "senior", []) for i in range(1, 6)])
    models = [o["model"] for o in out]
    # 5 nodes spread over 3 rungs in ladder order by in-flight count; the leftover capacity key is ignored
    assert models == ["s/Two", "q/Qwen", "s/One", "s/Two", "q/Qwen"], out
    assert [o["load"] for o in out] == [0, 0, 0, 1, 1], out
    assert all(o["provider"] == "flatiron" and o["fallback"] is False for o in out), out
    assert all(o["kind"] == "mechanical" and o["reason"] for o in out), out
    # a live count above every old cap never skips the rung
    r.inflight_counts = lambda: {"s/One": 9, "q/Qwen": 9, "s/Two": 9}
    out = r.assign([("n1", "mechanical", "senior", [])])
    assert out[0]["model"] == "s/Two" and out[0]["fallback"] is False, out


def check_assign_capacity_inflight():
    # assign spreads by in-flight count only: the least busy rung serves, ties go to ladder order
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"s/One": 3, "q/Qwen": 2}, "tiers": json.loads(r.ROUTING_FILE.read_text())["tiers"],
           "routes": {"mechanical": ["s/One", "q/Qwen"]}, "paid_ladder": [], "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in ("s/One", "q/Qwen")}
    r.inflight_counts = lambda: {"s/One": 3, "q/Qwen": 1}
    out = r.assign([("n1", "mechanical", "senior", [])])
    assert out[0]["model"] == "q/Qwen" and out[0]["load"] == 1, out
    r.inflight_counts = lambda: {"s/One": 1, "q/Qwen": 1}
    out = r.assign([("n1", "mechanical", "senior", []), ("n2", "mechanical", "senior", [])])
    assert [o["model"] for o in out] == ["q/Qwen", "s/One"], out   # tie: ladder order, then the count moves
    # pick for one node takes the head of the ladder, whatever the in-flight counts
    r.inflight_counts = lambda: {"s/One": 9, "q/Qwen": 0}
    got = r.pick("mechanical", "senior", [], False)
    assert got["model"] == "q/Qwen", got


def check_ladder_order():
    """The ladder order is ascending rank, then the paid rungs. A routing table with no tier_floor
    gives every tier the same rungs. The retired prefer key is gone from the shipped tier table,
    and a model outside the rank map is no rung."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    tiers = json.loads(r.ROUTING_FILE.read_text())["tiers"]                       # the real tier table
    assert all("prefer" not in t for t in tiers.values()), tiers                   # the tier no longer chooses
    assert all("min_rank" not in t for t in tiers.values()), tiers                 # the floors live in tier_floor
    cfg = {"rank": {"s/Strong": 5, "m/Mid": 4, "c/Cheap": 2, "d/Down": 1}, "tiers": tiers,
           "routes": {"code": ["s/Strong", "m/Mid", "c/Cheap", "d/Down"], "mechanical": ["s/Strong", "c/Cheap", "m/Mid"]},
           "paid_ladder": [], "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": m != "d/Down"} for m in
                                    ("s/Strong", "m/Mid", "c/Cheap", "d/Down", "u/Unlisted")}
    pick = lambda kind, tier, failed=(): r.pick(kind, tier, list(failed), False)["model"]
    for tier in ("intern", "junior", "senior", "principal"):
        assert pick("code", tier) == "c/Cheap", tier                               # every tier: the lowest rank first
    assert pick("code", "intern", ["c/Cheap"]) == "m/Mid"                          # --failed skips: the next rung serves
    assert [x["model"] for x in r.lanes("code", "intern", [], [])] == ["c/Cheap", "m/Mid", "s/Strong"]
    assert "u/Unlisted" not in str(r.lanes("code", "intern", [], [])), "a model outside the rank map is never a rung"
    r.inflight_counts = lambda: {"c/Cheap": 1}
    out = r.assign([("a", "mechanical", "intern", []), ("b", "mechanical", "intern", []), ("c", "mechanical", "intern", [])])
    assert [o["model"] for o in out] == ["m/Mid", "s/Strong", "c/Cheap"], out       # load first, ladder order breaks ties
    r.inflight_counts = lambda: {}
    out = r.assign([("a", "mechanical", "intern", []), ("b", "mechanical", "intern", [])])
    assert [o["model"] for o in out] == ["c/Cheap", "m/Mid"], out
    cfg["rank"]["c/Cheap"] = cfg["rank"]["m/Mid"] = 3                              # tied ranks keep map order (stable sort)
    assert pick("code", "intern") == "m/Mid"
    del cfg["rank"]["m/Mid"]                                                       # a model outside the rank map is no rung
    assert pick("code", "intern") == "c/Cheap"


def check_sync_tier_models():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        r.SIDECAR_DIR = Path(d, "cache", "dispatch-route")
        r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
        tiers = json.loads(r.ROUTING_FILE.read_text())["tiers"]
        cfg = {"rank": {"s/Strong": 5, "c/Cheap": 2, "d/Down": 1}, "tiers": tiers,
               "routes": {"code": ["s/Strong", "c/Cheap", "d/Down"], "mechanical": ["d/Down", "s/Strong", "c/Cheap"]}}
        r.routing = lambda: cfg
        r.flatiron_status = lambda *a: {"s/Strong": {"ok": True}, "c/Cheap": {"ok": True}, "d/Down": {"ok": False}}
        r.load_cache = lambda: {"flatiron": {"listed": ["s/Strong", "c/Cheap", "d/Down"]}}
        r.sync_features = lambda *a: None
        r.sync_rank = lambda *a: None
        routing_before = r.ROUTING_FILE.read_text()                     # the real file: sync must not touch it
        store = {}                                                                 # fake hermes config: values stored as the yaml `get` prints
        def run(cmd, **kw):
            if cmd[2] == "get":
                if cmd[3] not in store:
                    return types.SimpleNamespace(stdout="", stderr="Config key not set", returncode=1)
                v = store[cmd[3]]
                out = v if isinstance(v, str) else __import__("yaml").safe_dump(v, sort_keys=False)   # real `config get` prints yaml
                return types.SimpleNamespace(stdout=out, stderr="", returncode=0)
            store[cmd[3]] = json.loads(cmd[4]) if cmd[3] != "delegation.provider" and cmd[3] != "delegation.model" else cmd[4]
            return types.SimpleNamespace(stdout="ok", stderr="", returncode=0)
        r.subprocess = types.SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired, CalledProcessError=subprocess.CalledProcessError)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            assert r.sync(False) == 0
        t = store["delegation.tiers"]
        claude = "claude-subscription-directsdk-experimental"
        chain = [{"provider": "flatiron", "model": "s/Strong"}] + [{"provider": claude, "model": m}
                 for m in ("claude-haiku-9", "claude-sonnet-9", "claude-opus-9")]
        assert (store["delegation.model"], store["delegation.provider"]) == ("c/Cheap", "flatiron"), store
        assert store["delegation.fallback_providers"] == chain, store["delegation.fallback_providers"]
        for tier in ("intern", "junior", "senior", "principal"):
            assert "model" not in t[tier] and "provider" not in t[tier], t[tier]    # no tier pins a model
            assert t[tier]["fallback"] == chain, t[tier]                            # every tier carries the ladder tail
        assert t["intern"]["reasoning_effort"] == "low", t["intern"]
        assert t["principal"]["skills"] == ["brainstorm", "agent-comms", "team", "manager"], t["principal"]
        assert r.ROUTING_FILE.read_text() == routing_before            # sync keeps the routing file
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            assert r.sync(False) == 0
        assert "config already current" in buf.getvalue(), buf.getvalue()           # second run: no rewrite
        cfg["rank"]["c/Cheap"] = 9                                                  # the ladder head moves up
        with contextlib.redirect_stdout(buf := io.StringIO()):
            r.sync(False)
        assert store["delegation.model"] == "s/Strong", store["delegation.model"]
        assert store["delegation.fallback_providers"] == [{"provider": "flatiron", "model": "c/Cheap"}] \
            + [{"provider": claude, "model": m} for m in ("claude-haiku-9", "claude-sonnet-9", "claude-opus-9")]
        assert "delegation.fallback_providers=" in buf.getvalue(), buf.getvalue()


def _sync_fake_config(r, cfg, health, listed):
    """Shared sync harness: stub the routing inputs and record every hermes config write in store."""
    r.SIDECAR_DIR = Path(tempfile.mkdtemp()) / "cache" / "dispatch-route"
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "gpt-5.2-sol"}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: health
    r.load_cache = lambda: {"flatiron": {"listed": listed}}
    r.sync_features = lambda *a: None
    r.sync_rank = lambda *a: None
    store = {}                                          # fake hermes config: values stored as the yaml `get` prints
    def run(cmd, **kw):
        if cmd[2] == "get":
            if cmd[3] not in store:
                return types.SimpleNamespace(stdout="", stderr="Config key not set", returncode=1)
            v = store[cmd[3]]
            out = v if isinstance(v, str) else __import__("yaml").safe_dump(v, sort_keys=False)
            return types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        store[cmd[3]] = json.loads(cmd[4]) if cmd[3] not in ("delegation.provider", "delegation.model") else cmd[4]
        return types.SimpleNamespace(stdout="ok", stderr="", returncode=0)
    r.subprocess = types.SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired,
                                         CalledProcessError=subprocess.CalledProcessError)
    return store


def check_sync_fallback_chain():
    """The written fallback lists are the ladder tail after delegation.model: the local rungs in
    ascending rank, then the paid rungs. A dead flatiron model drops out; the paid rungs stay
    because they are rungs now, and sol is never one."""
    r = load("hermes-dispatch-route")
    tiers = json.loads(r.ROUTING_FILE.read_text())["tiers"]               # the real tier table
    cfg = {"rank": {"s/Strong": 5, "m/Mid": 4, "c/Cheap": 2}, "tiers": tiers,
           "routes": {"code": ["s/Strong", "m/Mid", "c/Cheap"], "mechanical": ["m/Mid", "s/Strong", "c/Cheap"]},
           "features": {}}
    health = {"s/Strong": {"ok": True}, "m/Mid": {"ok": False}, "c/Cheap": {"ok": True},
              "claude-haiku-9": {"ok": True}, "claude-sonnet-9": {"ok": True},
              "claude-opus-9": {"ok": True}, "gpt-5.2-sol": {"ok": True}}
    store = _sync_fake_config(r, cfg, health, list(cfg["rank"]))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert r.sync(False) == 0
    claude = "claude-subscription-directsdk-experimental"
    chain = [{"provider": "flatiron", "model": "s/Strong"}] + [{"provider": claude, "model": m}
             for m in ("claude-haiku-9", "claude-sonnet-9", "claude-opus-9")]
    assert store["delegation.model"] == "c/Cheap", store                  # the head: cheapest healthy rung
    assert store["delegation.fallback_providers"] == chain, store["delegation.fallback_providers"]
    fb = {t: v["fallback"] for t, v in store["delegation.tiers"].items()}
    assert fb == {t: chain for t in ("intern", "junior", "senior", "principal", "super")}, fb   # every tier: the same chain
    assert "sol" not in json.dumps([chain] + list(fb.values())).lower(), fb            # the reviewer is no rung


def check_sync_fallback_single_model():
    """One healthy flatiron model is the head; the paid rungs are the whole fallback chain, and a
    second sync rewrites nothing."""
    r = load("hermes-dispatch-route")
    tiers = json.loads(r.ROUTING_FILE.read_text())["tiers"]
    cfg = {"rank": {"a/Only": 1}, "tiers": tiers,
           "routes": {"code": ["a/Only"], "mechanical": ["a/Only"]}, "features": {}}
    store = _sync_fake_config(r, cfg, {"a/Only": {"ok": True}}, ["a/Only"])
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert r.sync(False) == 0
    claude = "claude-subscription-directsdk-experimental"
    chain = [{"provider": claude, "model": m} for m in ("claude-haiku-9", "claude-sonnet-9", "claude-opus-9")]
    assert store["delegation.model"] == "a/Only", store
    assert store["delegation.fallback_providers"] == chain, store["delegation.fallback_providers"]
    assert {t: v["fallback"] for t, v in store["delegation.tiers"].items()} == \
           {t: chain for t in ("intern", "junior", "senior", "principal", "super")}, store["delegation.tiers"]
    with contextlib.redirect_stdout(buf := io.StringIO()):
        assert r.sync(False) == 0
    assert "config already current" in buf.getvalue(), buf.getvalue()


def check_sync_fallback_user_kept():
    """A hand-edited fallback list keeps its user-named entries. The stamp holds the chain sync wrote
    last round: the new ladder chain replaces that chain in delegation.fallback_providers and in
    every tier fallback list, while the user-named entries stay where the user put them."""
    r = load("hermes-dispatch-route")
    tiers = json.loads(r.ROUTING_FILE.read_text())["tiers"]
    cfg = {"rank": {"s/Strong": 5, "m/Mid": 4, "c/Cheap": 2}, "tiers": tiers,
           "routes": {"code": ["s/Strong", "m/Mid", "c/Cheap"], "mechanical": ["m/Mid", "s/Strong", "c/Cheap"]},
           "features": {}}
    health = {"s/Strong": {"ok": True}, "m/Mid": {"ok": True}, "c/Cheap": {"ok": True}}
    store = _sync_fake_config(r, cfg, health, list(cfg["rank"]))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert r.sync(False) == 0                                   # round one writes and stamps the chains
    claude = "claude-subscription-directsdk-experimental"
    round1 = [{"provider": "flatiron", "model": "m/Mid"}, {"provider": "flatiron", "model": "s/Strong"}] \
        + [{"provider": claude, "model": m} for m in ("claude-haiku-9", "claude-sonnet-9", "claude-opus-9")]
    assert store["delegation.fallback_providers"] == round1, store
    # the hand edit: user-named entries replace the sync-written lists
    store["delegation.fallback_providers"] = [{"provider": "anthropic", "model": "claude-haiku-5-5"}]
    store["delegation.tiers"]["senior"]["fallback"] = [{"provider": "openai", "model": "gpt-5.4"}]
    health["m/Mid"]["ok"] = False                                   # the new ladder drops m/Mid
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert r.sync(False) == 0
    chain = [{"provider": "flatiron", "model": "s/Strong"}] + [{"provider": claude, "model": m}
             for m in ("claude-haiku-9", "claude-sonnet-9", "claude-opus-9")]
    out = store["delegation.fallback_providers"]
    assert out == chain + [{"provider": "anthropic", "model": "claude-haiku-5-5"}], out   # user entry kept
    fb = {t: v["fallback"] for t, v in store["delegation.tiers"].items()}
    assert fb["senior"] == chain + [{"provider": "openai", "model": "gpt-5.4"}], fb       # user entry kept
    assert fb["principal"] == chain, fb                                # the stamped chain is replaced
    assert "m/Mid" not in json.dumps(fb), fb                           # round one's chain is gone
    stamp = json.loads((r.SIDECAR_DIR / "fallback-stamp.json").read_text())
    assert stamp["fallback_providers"] == [e["model"] for e in chain], stamp   # the stamp holds the new chain
    assert stamp["tiers"]["senior"] == [e["model"] for e in chain], stamp
    with contextlib.redirect_stdout(buf := io.StringIO()):
        assert r.sync(False) == 0
    assert "config already current" in buf.getvalue(), buf.getvalue()  # a kept list is stable


def check_inflight_scan():
    r = load("hermes-dispatch-route")
    hermes = ["python3", "/tmp/probe/hermes", "chat", "--provider", "flatiron", "-m", "moonshotai/Kimi-K3", "-q", "x"]
    nice = ["nice", "-n", "19", "/usr/bin/python3", "/tmp/probe/hermes", "chat", "--provider", "flatiron",
            "--model=moonshotai/Kimi-K3", "-q", "x"]
    ionice = ["ionice", "-c", "3", "/usr/bin/env", "python3", "/tmp/probe/hermes", "chat",
              "--provider=flatiron", "--model", "moonshotai/Kimi-K3", "-q", "x"]
    bash = ["bash", "-c", "nice -n 19 /tmp/probe/hermes chat --provider flatiron -m moonshotai/Kimi-K3 -q x"]
    entry = ["/opt/python3", "-I", "-c", "from hermes_cli.main import main", "chat", "--provider", "flatiron",
             "-m", "moonshotai/Kimi-K3", "-q", "x"]
    flagged = ["/usr/bin/python3", "-u", "-X", "utf8", "-c", "from hermes_cli.main import main",
               "chat", "--provider", "flatiron", "--model=moonshotai/Kimi-K3", "-q", "x"]
    direct = ["/usr/local/bin/hermes", "chat", "--provider", "flatiron", "--model", "moonshotai/Kimi-K3", "-q", "x"]
    other = ["python3", "/tmp/probe/hermes", "chat", "--provider", "openrouter", "-m", "moonshotai/Kimi-K3", "-q", "x"]
    counts = {}
    for argv in (hermes, nice, ionice, bash, entry, flagged, direct, other):
        m = r._job_model(argv)
        if m:
            counts[m] = counts.get(m, 0) + 1
    # one count per hermes process: 4 jobs stand (hermes script, -c entry, python flags before
    # -c, binary), the nice, ionice and bash wrappers never add a second count
    assert counts == {"moonshotai/Kimi-K3": 4}, counts
    assert r._job_model([]) is None, "an empty argv is no job"


def check_review():
    if not tool_path("hermes-adversarial-review").is_file():   # host-local script, not shipped with the release
        print("SKIP: hermes-adversarial-review not found, check_review skipped")
        return
    v = load("hermes-adversarial-review")
    q = "INSTR\n=== DIFF START ===\n+AGENTS.md mention\n=== DIFF END ===\n"
    with tempfile.TemporaryDirectory() as d:
        def dump(body):
            p = Path(d, f"request_dump_{len(os.listdir(d))}.json"); p.write_text(json.dumps({"request": {"body": body}})); return [str(p)]
        good = {"instructions": "You are Hermes Agent.", "input": [{"role": "user", "content": [{"type": "input_text", "text": q}]}]}
        assert v.verify_isolation(dump(good), q) == []                                  # AGENTS.md inside diff is fine
        assert v.verify_isolation(dump({}), q)                                          # shapeless dump rejected
        assert v.verify_isolation(dump(dict(good, tools=[{}])), q)                      # tools rejected
        assert v.verify_isolation(dump(dict(good, instructions="MEMORY (your personal notes)")), q)
        bad = dict(good, input=good["input"] + [{"role": "developer", "content": "<available_skills>"}])
        assert v.verify_isolation(dump(bad), q)                                         # injected developer item
        assert v.verify_isolation(dump(dict(good, input=good["input"] * 2)), q)         # two user messages
        assert v.verify_isolation([], q)                                                # no dump = no proof
        uq = q + "non-ascii — ü\n"                                                     # dump stores raw UTF-8
        ud = Path(d, "u.json"); ud.write_text(json.dumps({"request": {"body": dict(good, input=[{"role": "user",
            "content": [{"type": "input_text", "text": uq}]}])}}, ensure_ascii=False))
        assert v._dump_has_query(str(ud), uq) and not v._dump_has_query(str(ud), "other")
        # snapshot: nested trace excluded, real file reviewed, swapped symlink visible
        root = Path(d, "tree"); (root / "sub").mkdir(parents=True)
        (root / "a.txt").write_text("old\n"); Path(d, "t1").write_text("1\n"); Path(d, "t2").write_text("2\n")
        (root / "link").symlink_to(Path(d, "t1"))
        v.SNAPSHOTS = Path(d, "snaps")
        v.snapshot_create("t", [str(root)])
        (root / "a.txt").write_text("new\n"); (root / "sub" / "x-brief.md").write_text("secret brief\n")
        (root / "link").unlink(); (root / "link").symlink_to(Path(d, "t2"))
        diff, dropped = v.snapshot_diff("t", 3, [p for p in v.DEFAULT_EXCLUDES if not p.startswith(".")])
        assert "+new" in diff and "secret brief" not in diff and any("x-brief.md" in x for x in dropped), (diff, dropped)
        assert "t2" in diff, diff
    # usage errors exit 2, never 1 (FAIL); the binary resolves like load() does (STAGE first)
    rc = subprocess.run([str(v.__file__), "--patch", "/dev/null"], capture_output=True).returncode
    assert rc == 2, rc


def _ledger_case():
    """Fixture router for the ledger cases: three healthy models in one rank band, no paid rungs."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    r.inflight_counts = lambda: {}
    qwen, mist, kimi = "Qwen/Qwen3.8-27B-FP8", "mistralai/Mistral-Medium-3.5-128B", "moonshotai/Kimi-K3"
    cfg = {"rank": {qwen: 5, mist: 4, kimi: 3},
           "routes": {"mechanical": [mist, qwen, kimi], "code": [mist, qwen, kimi]},
           "tiers": {"senior": {"reasoning_effort": "high"},
                     "intern": {"reasoning_effort": "low"}},
           "paid_ladder": [], "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in cfg["rank"]}
    return r, qwen, mist, kimi


def _ledger_row(i, model, verdict, kind="mechanical"):
    return {"ts": i, "node": "n", "kind": kind, "tier": "senior", "model": model, "verdict": verdict, "note": ""}


def check_ledger_demotes():
    """Three counted rows for a kind demote the model: the next ladder rung takes the pick.
    A row counts only when its verdict string is exactly 'failed'."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(Path(d, "missing.jsonl"))   # a missing file is an empty ledger
        assert r.pick("mechanical", "senior", [], False)["model"] == kimi       # the ladder head: kimi first
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        rows = [_ledger_row(i, "MOONSHOTAI/KIMI-K3", "failed")                 # upper-case id pins the lowercase match
                for i in range(3)]
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        p = r.pick("mechanical", "senior", [], False)
        assert p["model"] == mist, p
        assert any(s.startswith(kimi) and s.endswith("ledger: last 3 mechanical runs failed")
                   for s in p["skipped"]), p["skipped"]
        assert [x["model"] for x in r.lanes("mechanical", "senior", [], [])] == [mist, qwen]   # lanes obeys the demotion
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER


def check_ledger_verdict():
    """D3: only the exact verdict 'failed' counts toward the 3-strike drop. missed-defects,
    blocked, interrupted, hung and fabricated never count, hyphenated forms included."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        for v in ("failed-garbled-report", "hung", "fabricated-report", "missed-defects",
                  "blocked", "interrupted", "failed-check", "FAILED"):
            rows = [_ledger_row(i, kimi, v) for i in range(3)]                 # three rows, none exact 'failed'
            led.write_text("".join(json.dumps(x) + "\n" for x in rows))
            p = r.pick("mechanical", "senior", [], False)
            assert p["model"] == kimi, (v, p)
            assert not any("ledger" in s for s in p["skipped"]), (v, p["skipped"])
        rows = [_ledger_row(i, kimi, "failed") for i in range(3)]
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        assert r.pick("mechanical", "senior", [], False)["model"] == mist       # three exact 'failed' rows drop
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER


def check_ledger_mixed_verdicts():
    """Two counted strikes plus one clean run in the last 3 rows do not demote."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        rows = [_ledger_row(i, kimi, v) for i, v in enumerate(("failed", "failed", "done-clean"))]
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        p = r.pick("mechanical", "senior", [], False)
        assert p["model"] == kimi, p
        assert not any("ledger" in s for s in p["skipped"]), p["skipped"]
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER


def check_ledger_bad_lines():
    """A garbage line is skipped: it never crashes pick and never counts as history."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        bad = ["not json at all", "null", "", '{"kind": "mechanical", "model": "moonshotai/Kimi-K3"}',
               '{"kind": "mechanical", "model": "x/y", "verdict": 5}']
        lines = []
        for i in range(3):
            lines.append(json.dumps(_ledger_row(i, kimi, "failed")) + "\n")
            lines.append(bad[i] + "\n")
        led.write_text("".join(lines))
        p = r.pick("mechanical", "senior", [], False)
        assert p["model"] == mist, p                                         # the 3 bad rows still demote kimi
        assert [x["model"] for x in r.lanes("mechanical", "senior", [], [])] == [mist, qwen], p
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER


def check_ledger_all_skipped():
    """Every rung dead in the ledger: fall back to the unskipped order and say so in reason."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        rows = []
        for m in (qwen, "mistralai/Mistral-Medium-3.5-128K", kimi):           # the -128K suffix pins the size normalization
            for i in range(3):
                rows.append(_ledger_row(len(rows), m, "failed"))
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        p = r.pick("mechanical", "senior", [], False)
        assert p["model"] == kimi, p                                         # demotion is advisory when every rung is dead
        assert "ledger fallback" in p["reason"] and "unskipped order" in p["reason"], p
        assert any("serving the unskipped order" in s for s in p["skipped"]), p["skipped"]
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER


def check_effort_at_most_high():
    """F2: the user rule over the live value: every tier effort in the json is at most high, never max."""
    r = load("hermes-dispatch-route")
    jpath = STAGE / "flatiron-routing.json"                            # staged runs judge the staged json
    cfg = json.loads((jpath if jpath.is_file() else r.ROUTING_FILE).read_text())
    allowed = {"none", "minimal", "low", "medium", "high"}
    bad = {t: c["reasoning_effort"] for t, c in cfg["tiers"].items() if c["reasoning_effort"] not in allowed}
    assert not bad, bad


def check_ledger_fallback_note_lanes_assign():
    """F5: the all-dead fallback note reaches the lanes and assign output, not only pick."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        rows = []
        for m in (qwen, mist, kimi):
            for i in range(3):
                rows.append(_ledger_row(len(rows), m, "failed"))
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        note = "ledger fallback: serving the unskipped order"
        for x in r.lanes("mechanical", "senior", [], []):
            assert note in x.get("reason", ""), x
        a = r.assign([("n1", "mechanical", "senior", [])])[0]
        assert note in a["reason"], a
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER


def check_norm_model_size_suffix():
    """F6: only a trailing -128b or -128k normalizes away: distinct size variants keep distinct keys."""
    r = load("hermes-dispatch-route")
    n = r._norm_model
    assert n("MISTRALAI/MISTRAL-MEDIUM-3.5-128K") == n("mistralai/Mistral-Medium-3.5-128B")
    assert n("Qwen/Qwen3.8-27B") != n("Qwen/Qwen3.8-32B"), "27B and 32B must not share one history key"
    assert n("Qwen/Qwen3.8-27B-FP8") == "qwen/qwen3.8-27b-fp8", "a non-size suffix stays"


QWEN, MIST, KIMI = "Qwen/Qwen3.8-27B-FP8", "mistralai/Mistral-Medium-3.5-128B", "moonshotai/Kimi-K3"
# One fixture table for the CLI cases: flatiron trio, intern and senior tiers. pick reads no
# in-flight counts, so a real job on this machine never moves it.
_CLI_TABLE = json.dumps({
    "rank": {QWEN: 5, MIST: 4, KIMI: 3},
    "routes": {"mechanical": [MIST, QWEN, KIMI], "code": [MIST, QWEN, KIMI]},
    "tiers": {"intern": {"reasoning_effort": "low", "skills": [], "fallback": ["haiku", "sonnet"]},
              "senior": {"reasoning_effort": "high", "skills": [], "fallback": ["sonnet"]}},
    "features": {}})


def _cli(args, routing=_CLI_TABLE, models=None, ledger=b"", latest=None):
    """Run the router CLI offline: the scratch HERMES_HOME cache is fresh, so no probe and no
    model discovery reach the network. Returns the CompletedProcess for the caller to assert on."""
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        (home / "cache").mkdir()
        (home / "cache" / "dispatch-route.json").write_text(json.dumps(
            {"flatiron": {"at": time.time(), "models": models or {}, "listed": []},
             "latest": latest or {"at": time.time(), "opus": "fixture-opus", "sonnet": "fixture-sonnet",
                                  "haiku": "fixture-haiku", "sol": "x"}}))
        rfile, led = home / "routing.json", home / "outcomes.jsonl"
        rfile.write_text(routing)
        led.write_bytes(ledger)
        env = {**os.environ, "HERMES_HOME": d, "HERMES_DISPATCH_ROUTING_FILE": str(rfile),
               "HERMES_DISPATCH_LEDGER": str(led)}
        return subprocess.run([sys.executable, str(tool_path("hermes-dispatch-route")), *args],
                              env=env, capture_output=True, text=True, timeout=60)


def check_ledger_invalid_utf8():
    """F1: one raw non-UTF-8 line must not kill the ledger reader. pick exits 0 and the rows
    around the bad line still demote Qwen."""
    rows = [json.dumps(_ledger_row(i, QWEN, v)).encode() for i, v in enumerate(("failed", "failed", "failed"))]
    ledger = rows[0] + b"\n\xff\n" + rows[1] + b"\n" + rows[2] + b"\n"
    p = _cli(["pick", "mechanical", "--tier", "intern"], models={m: {"ok": True} for m in (QWEN, MIST, KIMI)}, ledger=ledger)
    assert p.returncode == 0, p.stderr[-300:]
    out = json.loads(p.stdout)
    assert out["model"] == KIMI, out                      # Qwen demoted, rows after the bad line kept
    assert any(s.startswith(QWEN) and s.endswith("ledger: last 3 mechanical runs failed")
               for s in out["skipped"]), out["skipped"]


def check_fallback_ledger_demotes():
    """F2: a dead paid rung demotes to the next rung and never blocks; when every rung is dead the
    unskipped ladder serves and the reason says so. An impossible need still blocks."""
    def rows(m):
        return b"".join(json.dumps(_ledger_row(i, m, "failed", "code")).encode() + b"\n" for i in range(3))
    dead_haiku = rows("fixture-haiku")                    # no flatiron health: the paid rungs lead
    p = _cli(["pick", "code", "--tier", "intern"], ledger=dead_haiku)
    out = json.loads(p.stdout)
    assert (out["model"], out["provider"]) == ("fixture-sonnet", "claude-subscription-directsdk-experimental"), out
    assert any(s.startswith("fixture-haiku") for s in out["skipped"]), out["skipped"]
    ln = _cli(["lanes", "code", "--tier", "intern"], ledger=dead_haiku)
    assert [x["model"] for x in json.loads(ln.stdout)] == ["fixture-sonnet", "fixture-opus"], ln.stdout
    a = _cli(["assign", "n1=code:intern"], ledger=dead_haiku)
    assert json.loads(a.stdout)[0]["model"] == "fixture-sonnet", a.stdout
    all_dead = dead_haiku + rows("fixture-sonnet") + rows("fixture-opus")
    p2 = _cli(["pick", "code", "--tier", "intern"], ledger=all_dead)
    out2 = json.loads(p2.stdout)
    assert out2["model"] == "fixture-haiku", out2          # advisory: the unskipped ladder head serves
    assert "ledger fallback" in out2["reason"], out2
    p3 = _cli(["pick", "code", "--tier", "intern", "--needs", "telepathy"], ledger=all_dead)
    assert p3.returncode == 3 and p3.stdout.startswith("blocked:"), p3.stdout   # no rung of any kind: blocked


def check_fallback_missing_id():
    """N1: `--pin` names the model and nothing else: a pinned family with no live id exits
    naming that family, and a pinned paid id comes back exactly as named."""
    r, qwen, mist, kimi = _ledger_case()
    r.routing()["tiers"]["intern"]["fallback"] = ["haiku", "sonnet", "opus"]
    r.flatiron_status = lambda *a: {}                                        # no free fit either way
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        led.write_text("")                                                   # clean ledger
        r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sol": "x"}  # sonnet and haiku have no id
        try:
            r.pick("code", "intern", [], False, pin="haiku")
        except SystemExit as e:
            msg = str(e)
        else:
            raise AssertionError("pick --pin haiku did not exit on a missing id")
        assert "haiku" in msg, msg
        got = r.pick("code", "intern", [], False, pin="claude-opus-9")
        assert (got["provider"], got["model"]) == (r.CLAUDE, "claude-opus-9"), got   # the named id runs
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER


def check_routing_null_list():
    """F4: a routing file whose top level is null or a list fails loud: non-zero exit and the
    message names the file and the paths tried. There is no built-in table fallback."""
    for raw in ("null", "[]"):
        p = _cli(["pick", "code", "--tier", "senior"], routing=raw)
        assert p.returncode != 0, (raw, p.returncode)
        assert "tried" in p.stderr and "lacks rank/routes" in p.stderr, p.stderr
        assert "built-in" not in p.stderr, p.stderr


def check_discovery_failure_names_family():
    """A family whose discovery returns no models is named as failed with its fix hint
    (PATH for claude, `hermes auth` for codex). It is never printed as ok: the workstation
    hid a missing `claude` behind `claude: ok`."""
    r = load("hermes-dispatch-route")
    r.load_cache = lambda: {}
    calls = []
    r.save_section = lambda *a: calls.append(a)   # the exit must happen before any cache write
    ns = types.SimpleNamespace(stdout=json.dumps({"claude": [], "codex": []}),
                               stderr="", returncode=0)   # discover_models() returned None, so the list is empty
    r.subprocess = types.SimpleNamespace(run=lambda *a, **k: ns, TimeoutExpired=subprocess.TimeoutExpired)
    try:
        r.resolve_latest()
    except SystemExit as e:
        msg = str(e)
    else:
        raise AssertionError("resolve_latest did not exit on a failed discovery")
    assert "claude: failed" in msg, msg
    assert "claude: ok" not in msg, msg
    assert "export PATH=$HOME/.local/bin:$PATH" in msg, msg
    assert "codex: ok" not in msg, msg
    assert "check `codex` is on PATH" not in msg, msg
    assert "check `hermes auth` for openai-codex" in msg, msg
    assert not calls, f"cache write before the exit: {calls}"


def check_failed_comma_list():
    """F6: `--failed MODEL,...` splits before the exclusions. The comma list picks exactly what
    the space list picks, and a failed model never serves again."""
    health = {m: {"ok": True} for m in (QWEN, MIST, KIMI)}
    comma = _cli(["pick", "code", "--tier", "senior", "--failed", f"{MIST},{KIMI}"], models=health)
    space = _cli(["pick", "code", "--tier", "senior", "--failed", MIST, KIMI], models=health)
    assert comma.returncode == 0 and space.returncode == 0, (comma.stderr, space.stderr)
    assert json.loads(comma.stdout) == json.loads(space.stdout), (comma.stdout, space.stdout)
    assert json.loads(comma.stdout)["model"] == QWEN, comma.stdout    # the only local rung left
    both = _cli(["pick", "code", "--tier", "senior", "--failed", f"{QWEN},{MIST},{KIMI}"], models=health)
    assert json.loads(both.stdout)["model"] == "fixture-haiku", both.stdout   # every local rung failed: the paid rungs


def _cli_fresh(args, home, script):
    """Run a staged router copy with HERMES_HOME=home and no routing override, so only the
    resolution search finds the table."""
    env = {**os.environ, "HERMES_HOME": str(home)}
    env.pop("HERMES_DISPATCH_ROUTING_FILE", None)
    return subprocess.run([sys.executable, str(script), *args], env=env, capture_output=True, text=True, timeout=60)


def _staged_home(d):
    """A scratch HERMES_HOME with a fresh health cache and resolved latest ids: fully offline.
    The router copy sits outside any skill dir, so no references/ dir is beside it."""
    home = Path(d, "home")
    (home / "cache").mkdir(parents=True)
    (home / "cache" / "dispatch-route.json").write_text(json.dumps(
        {"flatiron": {"at": time.time(), "models": {QWEN: {"ok": True}, MIST: {"ok": True}}, "listed": [QWEN, MIST]},
         "latest": {"at": time.time(), "opus": "fixture-opus", "sonnet": "fixture-sonnet",
                    "haiku": "fixture-haiku", "sol": "x"}}))
    tool = Path(d, "tool")
    tool.mkdir()
    script = tool / "hermes-dispatch-route"
    script.write_bytes(tool_path("hermes-dispatch-route").read_bytes())
    return home, script


_L1_TABLE = {"rank": {QWEN: 5, MIST: 4}, "routes": {"code": [MIST, QWEN]},
             "features": {QWEN: {"vision": True, "web": False}, MIST: {"vision": False, "web": False}}}


def check_new_skill_layout():
    """L1: the skill layout skills/tiered-subagent-dispatch carries the data: pick vision is
    the flatiron vision model Qwen/Qwen3.8-27B-FP8, not a paid rung."""
    with tempfile.TemporaryDirectory() as d:
        home, script = _staged_home(d)
        ref = home / "skills" / "tiered-subagent-dispatch" / "references"
        ref.mkdir(parents=True)
        (ref / "flatiron-routing.json").write_text(json.dumps(_L1_TABLE))
        p = _cli_fresh(["pick", "vision"], home, script)
        assert p.returncode == 0, (p.returncode, p.stdout, p.stderr[-300:])
        out = json.loads(p.stdout)
        assert (out["provider"], out["model"]) == ("flatiron", QWEN), out


def check_routing_file_missing():
    """L2: no routing file in any candidate place: non-zero exit, and the message prints every
    path it tried. There is no silent built-in table."""
    with tempfile.TemporaryDirectory() as d:
        home, script = _staged_home(d)
        p = _cli_fresh(["pick", "code"], home, script)
        assert p.returncode != 0, (p.returncode, p.stdout)
        assert "tried" in p.stderr, p.stderr
        for cand in ("flatiron-routing.json",
                     os.path.join("skills", "tiered-subagent-dispatch"),
                     os.path.join("skills", "autonomous-ai-agents", "tiered-subagent-dispatch")):
            assert cand in p.stderr, (cand, p.stderr)
        assert not p.stdout.strip(), p.stdout


def check_blocked_no_paid():
    """L3: no rung of any kind is one `blocked:` line and exit 3: the healthy free models with
    their features, the paid models with theirs, and no model returned."""
    with tempfile.TemporaryDirectory() as d:
        home, script = _staged_home(d)
        ref = home / "skills" / "tiered-subagent-dispatch" / "references"
        ref.mkdir(parents=True)
        (ref / "flatiron-routing.json").write_text(json.dumps(_L1_TABLE))
        for cmd in (["pick", "code", "--needs", "telepathy"], ["lanes", "code", "--needs", "telepathy"],
                    ["assign", "n1=code:intern:telepathy"]):
            p = _cli_fresh(cmd, home, script)
            assert p.returncode == 3, (cmd, p.returncode, p.stdout, p.stderr)
            assert p.stdout.startswith("blocked:") and "no ladder rung fits" in p.stdout, (cmd, p.stdout)
            assert "Qwen/Qwen3.8-27B-FP8 (vision=true, web=false)" in p.stdout, (cmd, p.stdout)
            assert "fixture-haiku (vision=true, web=true)" in p.stdout, (cmd, p.stdout)   # paid features help the manager
            assert '"model"' not in p.stdout and "claude-subscription" not in p.stdout, (cmd, p.stdout)


def check_pin_returns_paid():
    """L4: an explicitly named paid model is still returned: `--pin` resolves the family and
    returns the paid rung with its provider."""
    p = _cli(["pick", "code", "--tier", "intern", "--pin", "haiku"])
    assert p.returncode == 0, (p.returncode, p.stderr[-300:])
    out = json.loads(p.stdout)
    assert (out["provider"], out["model"]) == ("claude-subscription-directsdk-experimental", "fixture-haiku"), out
    assert "--reasoning" not in out["flags"] and "-m fixture-haiku" in out["flags"], out
    ln = _cli(["lanes", "code", "--tier", "intern", "--pin", "fixture-sonnet"])
    assert [x["model"] for x in json.loads(ln.stdout)] == ["fixture-sonnet", "fixture-opus"], ln.stdout   # pin, then up


def check_pin_non_latest_paid():
    """P1: a pinned paid id resolves to its provider even when it is not the latest of its
    family. The provider comes from the model id, never the flatiron default."""
    for pin, prov in (("claude-sonnet-8", "claude-subscription-directsdk-experimental"),
                      ("gpt-5.5-sol", "openai-codex")):
        p = _cli(["pick", "code", "--tier", "intern", "--pin", pin])
        assert p.returncode == 0, (pin, p.returncode, p.stderr[-300:])
        out = json.loads(p.stdout)
        assert (out["provider"], out["model"]) == (prov, pin), (pin, out)
    ln = _cli(["lanes", "code", "--tier", "intern", "--pin", "claude-sonnet-8"])
    assert [(x["provider"], x["model"]) for x in json.loads(ln.stdout)] \
        == [("claude-subscription-directsdk-experimental", "claude-sonnet-8"),
            ("claude-subscription-directsdk-experimental", "fixture-opus")], ln.stdout   # pin, then up


def check_pin_unknown_id():
    """P2: `--pin` with an id the routing file does not know exits non-zero with a clear
    error. It never falls through to flatiron."""
    for cmd in (["pick", "code", "--tier", "intern", "--pin", "mystery-model"],
                ["lanes", "code", "--tier", "intern", "--pin", "mystery-model"],
                ["pick", "code", "--tier", "intern", "--pin", "claude-fable-1"]):
        p = _cli(cmd)
        assert p.returncode != 0, (cmd, p.returncode, p.stdout)
        assert "unknown" in p.stderr and "pin" in p.stderr, (cmd, p.stderr)
        assert not p.stdout.strip(), (cmd, p.stdout)


def check_pin_failed_blocked():
    """P3: a pinned model in --failed prints the blocked line naming the pin and the reason
    and exits 3. pick and lanes never substitute another model."""
    cases = [(["pick", "code", "--tier", "intern", "--failed", "fixture-sonnet", "--pin", "sonnet"], "fixture-sonnet"),
             (["pick", "code", "--tier", "intern", "--failed", "fixture-sonnet", "--pin", "fixture-sonnet"], "fixture-sonnet"),
             (["pick", "code", "--tier", "intern", "--failed", "claude-sonnet-8", "--pin", "claude-sonnet-8"], "claude-sonnet-8"),
             (["lanes", "code", "--tier", "intern", "--failed", "fixture-sonnet", "--pin", "sonnet"], "fixture-sonnet")]
    for cmd, named in cases:
        p = _cli(cmd)
        assert p.returncode == 3, (cmd, p.returncode, p.stdout, p.stderr)
        assert p.stdout.startswith("blocked:") and named in p.stdout, (cmd, p.stdout)
        assert "failed" in p.stdout, (cmd, p.stdout)                # the reason names the exclusion
        assert '"model"' not in p.stdout, (cmd, p.stdout)           # never a substitute


def check_pin_needs_blocked():
    """P4: a pinned model that lacks a needed feature prints the blocked line naming the pin
    and exits 3. `pick vision --pin Qwen...` with Qwen vision false never returns Qwen."""
    table = json.loads(_CLI_TABLE)
    table["features"] = {QWEN: {"vision": False, "web": False}}
    routing = json.dumps(table)
    cases = [(["pick", "vision", "--pin", QWEN], QWEN, "vision"),
             (["lanes", "vision", "--pin", QWEN], QWEN, "vision"),
             (["pick", "code", "--tier", "intern", "--needs", "web", "--pin", QWEN], QWEN, "web")]
    for cmd, named, feat in cases:
        p = _cli(cmd, routing=routing)
        assert p.returncode == 3, (cmd, p.returncode, p.stdout, p.stderr)
        assert p.stdout.startswith("blocked:") and named in p.stdout, (cmd, p.stdout)
        assert feat in p.stdout, (cmd, p.stdout)                    # the reason names the missing feature
        assert '"model"' not in p.stdout, (cmd, p.stdout)           # never a substitute


def check_pin_invalid_id():
    """P5: a malformed --pin or --failed id is rejected: an id is one token of [A-Za-z0-9./_-],
    no whitespace, no leading '-'. An argument suffix or an efforts metadata key is never a
    model id. pick and lanes exit non-zero and return nothing."""
    bad = ["claude-sonnet-8 --provider flatiron", "-claude-sonnet-8", "gpt-5.5-sol --refresh"]
    for pin in bad:
        for sub in ("pick", "lanes"):
            p = _cli([sub, "code", "--tier", "intern", "--pin", pin])
            assert p.returncode != 0, (sub, pin, p.returncode, p.stdout)
            assert not p.stdout.strip(), (sub, pin, p.stdout)
    table = json.loads(_CLI_TABLE); table["efforts"] = {"_doc": "merger notes, not a model"}
    p = _cli(["pick", "code", "--tier", "intern", "--pin", "_doc"], routing=json.dumps(table))
    assert p.returncode != 0, (p.returncode, p.stdout)
    assert not p.stdout.strip(), p.stdout
    for sub in ("pick", "lanes"):  # the --failed entries parse the same way
        p = _cli([sub, "code", "--tier", "intern", "--failed", "claude-sonnet-8 --provider flatiron"])
        assert p.returncode != 0, (sub, p.returncode, p.stdout)
        assert not p.stdout.strip(), (sub, p.stdout)


def check_pin_empty_exact_features():
    """P6: an exact features entry wins over the family entry even when it is empty: {} means
    no features, not "absent". pick and lanes block the pin with exit 3 and no substitute."""
    table = json.loads(_CLI_TABLE)
    table["features"] = {"fixture-sonnet": {}, "sonnet": {"vision": True, "web": True}}
    routing = json.dumps(table)
    cases = [(["pick", "vision", "--pin", "sonnet"], "vision"),
             (["lanes", "vision", "--pin", "sonnet"], "vision"),
             (["pick", "code", "--tier", "intern", "--needs", "web",
               "--pin", "fixture-sonnet"], "web")]
    for cmd, feat in cases:
        p = _cli(cmd, routing=routing)
        assert p.returncode == 3, (cmd, p.returncode, p.stdout, p.stderr)
        assert p.stdout.startswith("blocked:") and "fixture-sonnet" in p.stdout, (cmd, p.stdout)
        assert feat in p.stdout, (cmd, p.stdout)                    # the reason names the missing feature
        assert '\"model\"' not in p.stdout, (cmd, p.stdout)           # never a substitute


_LADDER_FIX_TABLE = json.dumps({
    "rank": {MIST: 1, QWEN: 3, KIMI: 4},
    "routes": {"code": [KIMI, QWEN, MIST]},
    "paid_ladder": ["haiku", "sonnet", "opus"],
    "tiers": {"intern": {"reasoning_effort": "low"}, "senior": {"reasoning_effort": "high"}},
    "features": {QWEN: {"vision": True, "web": False},
                 "haiku": {"vision": True, "web": True},
                 "sonnet": {"vision": True, "web": True},
                 "opus": {"vision": True, "web": True}},
    "efforts": {MIST: ["none", "high"], QWEN: ["xhigh", "medium", "low"]}})
# The id shape the account picker emits, bracket suffix and all.
HAIKU_B, SONNET_B, OPUS_B = "claude-haiku-5-5[1m]", "claude-sonnet-5-5[1m]", "claude-opus-5-5[1m]"
_LATEST_B = {"at": time.time(), "haiku": HAIKU_B, "sonnet": SONNET_B, "opus": OPUS_B, "sol": "gpt-6.1-sol"}
_HEALTH_B = {m: {"ok": True} for m in (MIST, QWEN, KIMI)}


def check_emitted_ids_pass_failed_validation():
    """S5: every id pick and lanes emit passes --failed validation. Bracketed discovered ids
    pass, and the documented escalation runs on them. Whitespace, a leading '-' and an
    argument suffix are rejected."""
    for tier in ("intern", "senior"):
        for needs in ("", "vision", "web"):
            args = ["--tier", tier] + (["--needs", needs] if needs else [])
            for cmd in ("pick", "lanes"):
                p = _cli([cmd, "code", *args], routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
                assert p.returncode in (0, 3), (cmd, tier, needs, p.stderr)
                out = json.loads(p.stdout)
                for e in (out if isinstance(out, list) else [out]):
                    if e.get("model"):
                        _emitted_ids_seen.add(e["model"])
    assert any(m.endswith("[1m]") for m in _emitted_ids_seen), _emitted_ids_seen
    for m in sorted(_emitted_ids_seen):
        p = _cli(["pick", "code", "--tier", "intern", "--failed", m],
                 routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
        assert "invalid model id" not in p.stderr, (m, p.stderr)
        assert p.returncode in (0, 3), (m, p.returncode, p.stderr)
    p = _cli(["pick", "code", "--tier", "intern", "--needs", "vision", "--failed", QWEN, HAIKU_B],
             routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
    assert p.returncode == 0 and json.loads(p.stdout)["model"] == SONNET_B, p.stdout
    for bad in ("x y", "x;y", "x$y", f"{HAIKU_B}extra", f"{HAIKU_B} --reasoning high"):
        p = _cli(["pick", "code", "--tier", "intern", "--failed", bad],
                 routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
        assert p.returncode == 1 and "invalid model id" in p.stderr, (bad, p.returncode, p.stderr)
    p = _cli(["pick", "code", "--tier", "intern", "--failed", "-x"],
             routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
    assert p.returncode != 0, (p.returncode, p.stderr)
    p = _cli(["pick", "code", "--tier", "intern", "--failed=-x"],
             routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
    assert p.returncode == 1 and "invalid model id" in p.stderr, (p.returncode, p.stderr)


_emitted_ids_seen = set()


def check_paid_discovery_failure_keeps_local_rungs():
    """S6: a paid discovery failure keeps healthy local rungs. ladder, lanes and assign serve
    the local models, and the paid rungs drop with one stderr warning."""
    r = load("hermes-dispatch-route")
    r.routing = lambda: json.loads(_LADDER_FIX_TABLE)
    r.flatiron_status = lambda *a: _HEALTH_B
    r.inflight_counts = lambda: {}

    def boom(*a, **k):
        raise SystemExit("hermes-dispatch-route: could not discover latest opus, sonnet "
                         "(claude: failed; check `claude` is on PATH)")
    r.resolve_latest = boom
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rungs = r.ladder([])
        lanes = r.lanes("code", "intern", [], [])
        nodes = r.assign([("n1", "code", "intern", []), ("n2", "code", "intern", [])])
    assert [x[1] for x in rungs] == [MIST, QWEN, KIMI], rungs
    assert [x["model"] for x in lanes] == [MIST, QWEN, KIMI], lanes
    assert {x["model"] for x in nodes} == {MIST, QWEN}, nodes
    assert "paid rungs dropped" in buf.getvalue(), buf.getvalue()


def check_pin_contract_pick_assign_lanes():
    """S7: pick --pin and assign --pin print exactly the pinned model, and nothing else.
    lanes --pin prints it, then the rungs above it."""
    p = _cli(["pick", "code", "--tier", "intern", "--pin", QWEN],
             routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
    assert p.returncode == 0 and json.loads(p.stdout)["model"] == QWEN, p.stdout
    p = _cli(["assign", "n1=code:intern", "n2=code:senior", "--pin", QWEN],
             routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    assert [e["model"] for e in json.loads(p.stdout)] == [QWEN, QWEN], p.stdout
    p = _cli(["lanes", "code", "--tier", "intern", "--pin", QWEN],
             routing=_LADDER_FIX_TABLE, models=_HEALTH_B, latest=_LATEST_B)
    assert [e["model"] for e in json.loads(p.stdout)] == [QWEN, KIMI, HAIKU_B, SONNET_B, OPUS_B], p.stdout


def check_unhealthy_floor():
    """D2: a failed or unhealthy floor model opens the exception. With no healthy fitting local
    rung at or above the tier floor, the local rungs start at the strongest healthy fitting model
    below it, then the paid rungs at the paid floor; the paid floor never drops."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"a/Weak": 1, "b/Mid": 2, "c/Floor": 3, "d/High": 4},
           "routes": {"code": ["a/Weak", "b/Mid", "c/Floor", "d/High"]},
           "paid_ladder": ["haiku", "sonnet", "opus"],
           "tier_floor": {"intern": "a/Weak", "senior": "c/Floor"},
           "paid_floor": {"intern": "haiku", "senior": "sonnet"},
           "tiers": {"intern": {"reasoning_effort": "low"}, "senior": {"reasoning_effort": "high"}},
           "features": {}}
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    lanes = lambda failed=(): [x["model"] for x in r.lanes("code", "senior", list(failed), [])]
    paid = ["claude-haiku-9", "claude-sonnet-9", "claude-opus-9"]
    health(a_Weak=True, b_Mid=True, c_Floor=True, d_High=True)
    assert lanes() == ["c/Floor", "d/High"] + paid[1:], lanes()
    health(a_Weak=True, b_Mid=True, c_Floor=False, d_High=False)      # the whole floor band is down
    assert lanes() == ["b/Mid"] + paid[1:], lanes()                   # the exception starts below the floor
    health(a_Weak=True, b_Mid=True, c_Floor=True, d_High=True)
    assert lanes(["c/Floor", "d/High"]) == ["b/Mid"] + paid[1:], "a failed floor opens the exception"
    health(a_Weak=False, b_Mid=False, c_Floor=False, d_High=False)
    assert lanes() == paid[1:], lanes()                               # nothing healthy below: the paid floor serves


def check_caller_cap():
    """D4: the caller model caps the ladder in the one strength order Qwen < GLM < MiMo <
    Kimi-K3 < Haiku < Sonnet < Opus. Stronger rungs drop, the same model is allowed, a pin above
    the cap is blocked, an exhausted capped ladder is blocked, gpt-6.1-sol is exempt through a
    pin, and an unknown caller id opens no cap."""
    MIMO = "XiaomiMiMo/MiMo-V2.6-Pro-MOPD"
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "gpt-9-sol"}
    cfg = {"rank": {QWEN: 3, "zai-org/GLM-5.3": 4, MIMO: 5, KIMI: 6},
           "routes": {"code": [QWEN, "zai-org/GLM-5.3", MIMO, KIMI]},
           "paid_ladder": ["haiku", "sonnet", "opus"],
           "tier_floor": {"intern": QWEN, "senior": MIMO},
           "paid_floor": {"intern": "haiku", "senior": "sonnet"},
           "tiers": {"intern": {"reasoning_effort": "low"}, "senior": {"reasoning_effort": "high"}},
           "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in cfg["rank"]}
    paid = ["claude-haiku-9", "claude-sonnet-9", "claude-opus-9"]
    full = [QWEN, "zai-org/GLM-5.3", MIMO, KIMI] + paid
    lanes = lambda caller, tier="intern": [x["model"] for x in r.lanes("code", tier, [], [], None, False, caller)]
    assert lanes(None) == full, lanes(None)
    assert lanes("claude-sonnet-9") == full[:-1], "a Sonnet caller never gets opus"
    assert lanes("claude-opus-9") == full, "an Opus caller keeps the whole ladder"
    assert lanes(MIMO) == [QWEN, "zai-org/GLM-5.3", MIMO], "a MiMo caller never climbs"
    assert lanes(MIMO, "senior") == [MIMO], "the same model is allowed"
    assert lanes("zz/Unknown") == full, "an unknown caller id opens no cap"
    got = r.pick("code", "intern", [], False, [], None, MIMO)
    assert any(s.startswith("claude-haiku-9") and "cap" in s for s in got["skipped"]), got["skipped"]
    assert r.lanes("code", "senior", [], [], None, False, QWEN) == [], "the cap exhausts the capped ladder"
    assert r.pick("code", "senior", [], False, [], None, QWEN)["reason"].startswith("blocked:"), "an exhausted capped ladder is blocked"
    for pin, caller in ((KIMI, MIMO), (KIMI, QWEN), (MIMO, QWEN)):     # a pin above the cap
        got = r.pick("code", "intern", [], False, [], pin, caller)
        assert got["model"] is None and got["reason"].startswith("blocked:") and "caller" in got["reason"], (pin, caller, got)
    assert r.pick("code", "intern", [], False, [], MIMO, MIMO)["model"] == MIMO, "the caller's own model runs"
    sol = r.pick("code", "intern", [], False, [], "sol", QWEN)
    assert (sol["provider"], sol["model"]) == ("openai-codex", "gpt-9-sol"), "gpt-6.1-sol is exempt through a pin"
    ln = r.lanes("code", "intern", [], [], "sol", False, QWEN)
    assert [x["model"] for x in ln] == ["gpt-9-sol"], ln            # nothing stronger sits above sol


def check_team_size():
    """D6: lanes and assign mark the team rungs with team_size 3: principal's local rungs and
    every super rung. Principal's paid rung is one Opus child before super and stays unmarked."""
    MIMO = "XiaomiMiMo/MiMo-V2.6-Pro-MOPD"
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    r.inflight_counts = lambda: {}
    cfg = {"rank": {QWEN: 3, MIMO: 5, KIMI: 6},
           "routes": {"code": [QWEN, MIMO, KIMI]},
           "paid_ladder": ["haiku", "sonnet", "opus"],
           "tier_floor": {"intern": QWEN, "principal": MIMO, "super": None},
           "paid_floor": {"intern": "haiku", "principal": "opus", "super": "opus"},
           "tiers": {"intern": {"reasoning_effort": "low"}, "principal": {"reasoning_effort": "high"},
                     "super": {"reasoning_effort": "high"}},
           "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in cfg["rank"]}
    out = r.lanes("code", "principal", [], [])
    assert [x["model"] for x in out] == [MIMO, KIMI, "claude-opus-9"], out
    assert [x.get("team_size") for x in out] == [3, 3, None], out
    sup = r.lanes("code", "super", [], [])
    assert [x["model"] for x in sup] == ["claude-opus-9"] and sup[0].get("team_size") == 3, sup
    a = r.assign([("n1", "code", "principal", []), ("n2", "code", "super", [])])
    assert [x.get("team_size") for x in a] == [3, 3], a
    assert all("team_size" not in x for x in r.lanes("code", "intern", [], [])), "a plain rung carries no team_size"


def _probe_world(d, rank, listed_ids):
    """The D7 probe world: a live routing file, sidecars and cache beside it, offline probes."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"at": 0, "opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "x"}
    home = Path(d)
    (home / "cache").mkdir()
    r.CACHE = home / "cache" / "dispatch-route.json"
    r.SIDECAR_DIR = home / "side"
    rj = home / "routing.json"
    rj.write_text(json.dumps({"rank": dict(rank), "routes": {"code": list(rank)}, "tiers": {},
                              "paid_ladder": []}))
    r.ROUTING_FILE = rj
    down = set()
    def req(path, body=None, timeout=60):
        if path == "/models":
            return {"data": [{"id": m} for m in listed_ids]}
        if body and body.get("model") in down:
            raise OSError("down")
        return {"choices": [{"message": {"content": "ok"}}]}
    r._req = req
    return r, rj, down


def check_new_id_sync():
    """D7: when the 60 s probe sees a served id with no rank, the router runs the sync ranking
    step for it at once, under the lock, before it builds the ladder. A new id joins only after a
    rank and a features probe."""
    with tempfile.TemporaryDirectory() as d:
        r, rj, _down = _probe_world(d, {"a/One": 2}, ["a/One", "n/New"])
        r.probe_features = lambda m: {"vision": False, "web": False, "probed": "2026-11-10"}
        r._selftest_ok = lambda *_: True
        ranked = []
        def fake_ranker(provider, model, rank, listed, timeout=600):
            ranked.append((provider, model, sorted(listed)))
            return {"order": {"a/One": 2, "n/New": 1}}
        r._run_ranker = fake_ranker
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            r.flatiron_status(True)                       # the probe sees the unranked served id
        assert ranked and ranked[0][2] == ["a/One", "n/New"], ranked
        cfg = json.loads(rj.read_text())
        assert cfg["rank"]["n/New"] == 1, cfg["rank"]     # the sync ranking step ranked it at once
        assert cfg["features"]["n/New"]["vision"] is False, cfg["features"]   # and probed its features
        assert [m for _p, m, _t in r.ladder([], [], "intern")] == ["n/New", "a/One"]


def check_recovered_model():
    """D7: a recovered model rejoins the ladder with no edit. Health alone moves it, no sync runs
    for a ranked model, and the routing file stays byte for byte."""
    with tempfile.TemporaryDirectory() as d:
        r, rj, down = _probe_world(d, {"a/One": 2, "b/Two": 1}, ["a/One", "b/Two"])
        def no_sync(*a, **k):
            raise AssertionError("the sync steps ran for a ranked model")
        r.sync_features = no_sync
        r.sync_rank = no_sync
        before = rj.read_text()
        down.add("b/Two")
        out = r.flatiron_status(True)                     # b/Two is down
        assert not out["b/Two"]["ok"], out
        assert [m for _p, m, _t in r.ladder([], [], "intern")] == ["a/One"]
        down.clear()                                      # b/Two recovers
        out = r.flatiron_status(True)
        assert out["b/Two"]["ok"], out
        assert [m for _p, m, _t in r.ladder([], [], "intern")] == ["b/Two", "a/One"]
        assert rj.read_text() == before, "a recovery needs no routing edit"


def check_ledger_window():
    """M1: the drop needs the last 3 counted rows of one kind to be exactly 'failed', not a
    lifetime count. Rows with verdict missed-defects, blocked or interrupted are ignored; every
    other verdict sits in the window and stops the drop. A later success clears the drop."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)

        def rows(verdicts):
            led.write_text("".join(json.dumps(_ledger_row(i, kimi, v)) + "\n" for i, v in enumerate(verdicts)))

        rows(["failed", "done-clean"] * 3)        # alternating failures and successes never demote
        assert r.pick("mechanical", "senior", [], False)["model"] == kimi
        rows(["failed", "missed-defects", "failed", "blocked", "failed", "interrupted"])
        assert r.pick("mechanical", "senior", [], False)["model"] == mist   # ignored rows leave 3 failed
        rows(["failed", "failed", "failed", "done-clean"])
        assert r.pick("mechanical", "senior", [], False)["model"] == kimi   # a later success clears the drop
        rows(["failed", "failed", "hung"])
        assert r.pick("mechanical", "senior", [], False)["model"] == kimi   # hung is not ignored: it sits in the window
        rows(["failed", "failed", "failed", "missed-defects"])
        assert r.pick("mechanical", "senior", [], False)["model"] == mist   # an ignored row never clears the drop
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER


def _run_cli(r, args):
    """One router CLI run on the in-memory router: (stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    previous = sys.argv
    sys.argv = ["hermes-dispatch-route"] + args
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            r.main()
    finally:
        sys.argv = previous
    return out.getvalue(), err.getvalue()


def check_sync_stdout_json():
    """M2: auto-sync diagnostics go to stderr. pick, lanes and assign stdout parses as JSON while
    a sync runs: a failed features probe and a rejected ranker attempt name themselves on stderr."""
    with tempfile.TemporaryDirectory() as d:
        r, _rj, _down = _probe_world(d, {"a/One": 2}, ["a/One", "n/New"])
        r.probe_features = lambda m: None
        r._selftest_ok = lambda *_: True
        r._run_ranker = lambda *a, **k: {"a/One": 2, "n/New": 1}
        out, err = _run_cli(r, ["lanes", "code", "--tier", "intern"])
        json.loads(out)                                             # stdout holds only the JSON result
        assert "features:" in err, err
        out, _err = _run_cli(r, ["pick", "code", "--tier", "intern"])
        json.loads(out)
        out, _err = _run_cli(r, ["assign", "n1=code:intern"])
        json.loads(out)
    with tempfile.TemporaryDirectory() as d:
        r, _rj, _down = _probe_world(d, {"a/One": 2}, ["a/One", "m/Bad"])
        r.probe_features = lambda m: {"vision": False, "web": False, "probed": "2026-11-10"}
        r._selftest_ok = lambda *_: True
        r._run_ranker = lambda *a, **k: None                        # a rejected ranking attempt
        out, err = _run_cli(r, ["lanes", "code", "--tier", "intern"])
        json.loads(out)
        assert "attempt" in err, err


def check_ladder_fresh_routing():
    """M3: discovery and auto-sync run before ladder() reads the rank map and config, so the same
    dispatch sees the newly ranked model. No separate health preflight."""
    with tempfile.TemporaryDirectory() as d:
        r, rj, _down = _probe_world(d, {"a/One": 2}, ["a/One", "n/New"])
        r.probe_features = lambda m: {"vision": False, "web": False, "probed": "2026-11-10"}
        r._selftest_ok = lambda *_: True
        r._run_ranker = lambda *a, **k: {"a/One": 2, "n/New": 1}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            first = [m for _p, m, _t in r.ladder([], [], "intern")]
        assert first == ["n/New", "a/One"], first
        assert json.loads(rj.read_text())["rank"]["n/New"] == 1


def _features_gaps(cfg):
    """Ranked ids with no features entry: D7 allows no rank before a successful features probe."""
    return sorted(m for m in (cfg.get("rank") or {}) if m not in (cfg.get("features") or {}))


def check_ranked_features():
    """D7: every ranked id carries a features entry. The gate judges the routing file the router
    reads, so the selftest on a sync candidate rejects a rank without one."""
    r = load("hermes-dispatch-route")
    cfg = json.loads(r.ROUTING_FILE.read_text())
    assert not _features_gaps(cfg), f"ranked ids with no features entry: {_features_gaps(cfg)}"


def check_features_probe_gate():
    """M4: a new model joins the rank map only after its features probe succeeds. A failed probe
    leaves the id out of the rank map and out of the ladder, and the next probe cycle retries it."""
    assert _features_gaps({"rank": {"a/One": 2, "x/Unprobed": 7},
                           "features": {"a/One": {"vision": False, "web": False}}}) == ["x/Unprobed"]
    with tempfile.TemporaryDirectory() as d:
        r, rj, _down = _probe_world(d, {"a/One": 2}, ["a/One", "n/New"])
        r.probe_features = lambda m: None                           # the features probe fails
        r._selftest_ok = lambda *_: True
        ranker = []
        r._run_ranker = lambda *a, **k: ranker.append(a) or {"a/One": 2, "n/New": 1}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            r.flatiron_status(True)
        cfg = json.loads(rj.read_text())
        assert "n/New" not in cfg["rank"] and "n/New" not in (cfg.get("features") or {}), cfg
        assert ranker == [], "an unprobed new id must not reach the ranker"
        assert [m for _p, m, _t in r.ladder([], [], "intern")] == ["a/One"]
        r.probe_features = lambda m: {"vision": False, "web": False, "probed": "2026-11-10"}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            r.flatiron_status(True)                                 # the next probe cycle retries
        cfg = json.loads(rj.read_text())
        assert cfg["rank"]["n/New"] == 1 and cfg["features"]["n/New"], cfg
        assert [m for _p, m, _t in r.ladder([], [], "intern")] == ["n/New", "a/One"]


def check_caller_cap_paid_strength():
    """M5: the caller cap compares paid families in the one strength order Qwen < GLM < MiMo <
    Kimi-K3 < Haiku < Sonnet < Opus, never in the enabled paid_ladder order. A Haiku caller gets no
    Sonnet or Opus and a Sonnet caller gets no Opus, even when paid_ladder omits their families."""
    MIMO = "XiaomiMiMo/MiMo-V2.6-Pro-MOPD"
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "gpt-9-sol"}
    cfg = {"rank": {QWEN: 3, MIMO: 5}, "routes": {"code": [QWEN, MIMO]},
           "paid_ladder": ["sonnet", "opus"],                       # haiku holds no enabled rung
           "tier_floor": {"intern": QWEN}, "paid_floor": {"intern": "sonnet"},
           "tiers": {"intern": {"reasoning_effort": "low"}}, "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in cfg["rank"]}
    lanes = lambda caller: [x["model"] for x in r.lanes("code", "intern", [], [], None, False, caller)]
    assert lanes("claude-haiku-9") == [QWEN, MIMO], lanes("claude-haiku-9")
    assert lanes("claude-sonnet-9") == [QWEN, MIMO, "claude-sonnet-9"], lanes("claude-sonnet-9")
    assert lanes("claude-opus-9") == [QWEN, MIMO, "claude-sonnet-9", "claude-opus-9"], lanes("claude-opus-9")
    cfg["paid_ladder"] = []                                          # no rung: the pin comparison stays strict
    got = r.pick("code", "intern", [], False, [], "opus", "claude-haiku-9")
    assert got["model"] is None and got["reason"].startswith("blocked:"), got
    got = r.pick("code", "intern", [], False, [], "sonnet", "claude-haiku-9")
    assert got["model"] is None and got["reason"].startswith("blocked:"), got


def check_team_skill_flags():
    """M6: principal and super carry skills brainstorm and agent-comms in the data, the built-in
    defaults and the doc tables. lanes and assign emit both on every team rung."""
    r = load("hermes-dispatch-route")
    cfg = json.loads(r.ROUTING_FILE.read_text())
    tiers = cfg["tiers"]
    assert tiers["principal"]["skills"] == ["brainstorm", "agent-comms", "team", "manager"], tiers["principal"]
    assert tiers["super"]["skills"] == ["brainstorm", "agent-comms"], tiers["super"]
    default = (r.DEFAULT_ROUTING["tiers"]["principal"]["skills"], r.DEFAULT_ROUTING["tiers"]["super"]["skills"])
    assert default == (["brainstorm", "agent-comms", "team", "manager"], ["brainstorm", "agent-comms"]), default
    skill_dir = Path(tool_path("hermes-dispatch-route")).resolve().parent.parent
    doc = (skill_dir / "SKILL.md").read_text()
    for tier in ("principal", "super"):
        row = next(line for line in doc.splitlines() if line.startswith(f"| {tier} |"))
        listed = row.split("|")[3].strip()
        assert listed == ", ".join(tiers[tier]["skills"]), (tier, listed)
    mech = (skill_dir / "references" / "routing-mechanics.md").read_text()
    for tier in ("principal", "super"):
        assert "skills " + ", ".join(tiers[tier]["skills"]) in mech, tier
    MIMO, KIMI = "XiaomiMiMo/MiMo-V2.6-Pro-MOPD", "moonshotai/Kimi-K3"
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "x"}
    r.inflight_counts = lambda: {}
    world = {"rank": {MIMO: 5, KIMI: 6}, "routes": {"code": [MIMO, KIMI]}, "paid_ladder": ["opus"],
             "tier_floor": {"principal": MIMO, "super": None},
             "paid_floor": {"principal": "opus", "super": "opus"},
             "tiers": {"principal": tiers["principal"], "super": tiers["super"]}, "features": {}}
    r.routing = lambda: world
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in world["rank"]}
    out = r.lanes("code", "principal", [], [])
    assert [x.get("team_size") for x in out] == [3, 3, None], out
    for x in out:
        assert "-s brainstorm -s agent-comms" in x["flags"], x
    a = r.assign([("n1", "code", "super", [])])
    assert a[0].get("team_size") == 3 and "-s brainstorm -s agent-comms" in a[0]["flags"], a


if __name__ == "__main__":
    os.environ["HERMES_DISPATCH_LEDGER"] = NO_LEDGER   # the live ledger never touches a check
    check_route(); check_tiers(); check_effort_clamp(); check_effort_round_down(); check_effort_unknown_names(); check_lanes(); check_needs(); check_default_features()
    check_probe_fallback()
    check_sync_features(); check_sync_rank(); check_sync_rank_gates()
    check_sync_rank_gate_crash(); check_sync_rank_budget(); check_sync_config_fail()
    check_tier_min_rank(); check_max_effort(); check_sync_rank_reasons(); check_sync_rank_routes(); check_vision_probe()
    check_assign(); check_assign_capacity(); check_assign_capacity_inflight()
    check_ladder_order(); check_sync_tier_models(); check_sync_fallback_chain()
    check_sync_fallback_single_model(); check_sync_fallback_user_kept(); check_inflight_scan(); check_review()
    check_ledger_demotes(); check_ledger_mixed_verdicts()
    check_ledger_bad_lines(); check_ledger_all_skipped()
    check_effort_at_most_high(); check_ledger_fallback_note_lanes_assign()
    check_norm_model_size_suffix()
    check_ledger_invalid_utf8(); check_fallback_ledger_demotes(); check_routing_null_list()
    check_fallback_missing_id()
    check_discovery_failure_names_family()
    check_failed_comma_list()
    check_new_skill_layout(); check_routing_file_missing(); check_blocked_no_paid(); check_pin_returns_paid()
    check_pin_non_latest_paid(); check_pin_unknown_id(); check_pin_invalid_id()
    check_pin_failed_blocked(); check_pin_needs_blocked(); check_pin_empty_exact_features()
    check_emitted_ids_pass_failed_validation(); check_paid_discovery_failure_keeps_local_rungs()
    check_pin_contract_pick_assign_lanes()
    check_unhealthy_floor(); check_caller_cap(); check_team_size()
    check_ledger_verdict(); check_new_id_sync(); check_recovered_model()
    check_ledger_window(); check_sync_stdout_json(); check_ladder_fresh_routing()
    check_features_probe_gate(); check_ranked_features()
    check_caller_cap_paid_strength(); check_team_skill_flags()
    print("selftest OK")
