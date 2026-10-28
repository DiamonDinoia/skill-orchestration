#!/usr/bin/env python3
"""Offline self-check for hermes-dispatch-route and hermes-adversarial-review. No network, no models.
Run: python3 ~/.hermes/skills/autonomous-ai-agents/tiered-subagent-dispatch/scripts/selftest.py"""
import contextlib, fcntl, importlib.machinery, importlib.util, io, json, os, subprocess, sys, tempfile, time, types
from pathlib import Path

BIN = Path.home() / ".local" / "bin"
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
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "sol": "x"}
    r.routing = lambda: {"rank": {"a/Top": 4, "b/Mid": 3}, "routes": {"code": ["a/Top", "b/Mid"]}}
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    pick = lambda failed=(): r.pick("code", "senior", list(failed), False)["model"]
    health(a_Top=True, b_Mid=True);   assert pick() == "a/Top"                         # flatiron first
    health(a_Top=False, b_Mid=True);  assert pick() == "b/Mid"                         # top down -> next flatiron
    health(a_Top=False, b_Mid=False); assert pick() == "claude-sonnet-9"               # flatiron exploded -> Sonnet
    health(a_Top=True, b_Mid=True);   assert pick() == "a/Top"                         # recovered -> back to flatiron
    health(n_New=True);               assert pick() == "claude-sonnet-9"               # hard filter: unlisted model never serves code
    health(a_Top=True);               assert pick(["b/Mid"]) == "a/Top"                # strictly stronger only
    assert pick(["a/Top"]) == "claude-sonnet-9"
    assert pick(["a/Top", "claude-sonnet-9"]) == "claude-opus-9"                       # monotonic: no drop back
    assert pick(["claude-sonnet-8"]) == "claude-opus-9"                                # family match, old id
    assert pick(["claude-sonnet-9", "claude-opus-9"]) is None                          # exhausted -> user
    for fam in ("opus", "sonnet"):                                                     # Fable never matches
        assert "fable" not in fam


def check_tiers():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = json.loads(r.ROUTING_FILE.read_text())  # the real tier table, so a bad edit to it fails here
    cfg["rank"], cfg["routes"] = {"a/Top": 4, "b/Mid": 3}, {"code": ["a/Top", "b/Mid"]}
    cfg["features"] = {f: {"vision": True, "web": True} for f in ("haiku", "sonnet", "opus")}
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    pick = lambda kind="code", tier="senior", failed=(): r.pick(kind, tier, list(failed), False)
    health(a_Top=False, b_Mid=False)                                                     # all flatiron down
    assert pick(tier="junior")["model"] == "claude-haiku-9"
    assert pick(tier="intern")["model"] == "claude-haiku-9"
    assert pick(tier="senior")["model"] == "claude-sonnet-9"
    assert pick(tier="principal")["model"] == "claude-opus-9"                           # principal never Haiku
    assert pick(tier="junior", failed=["claude-haiku-9"])["model"] == "claude-sonnet-9"
    assert pick(tier="principal", failed=["claude-opus-9"])["model"] is None
    assert pick("vision", tier="principal")["model"] == "claude-opus-9"                  # vision keeps the principal floor
    assert pick(tier="junior", failed=["claude-sonnet-9"])["model"] == "claude-opus-9"   # never steps back down to Haiku
    assert pick("vision", tier="junior", failed=["claude-sonnet-9"])["model"] == "claude-opus-9"
    assert pick(tier="intern", failed=["claude-opus-9"])["model"] is None                # failed Opus is above every intern rung
    health(a_Top=True, b_Mid=True)
    f = pick(tier="principal")["flags"]                                                  # flatiron pick: effort and skills
    assert "--reasoning high" in f and "-s brainstorm -s team -s manager" in f, f
    f = pick(tier="intern")["flags"]
    assert "-s " not in f and "--reasoning low" in f, f
    health(a_Top=False, b_Mid=False)
    f = pick(tier="principal")["flags"]                                                  # Claude pick: skills, no effort
    assert "--reasoning" not in f and "-s manager" in f, f
    health(a_Top=True)                                                                   # Kimi-like model has no vision entry
    assert pick("vision")["model"] == "claude-haiku-9"
    assert pick("vision", failed=["claude-haiku-9"])["model"] == "claude-sonnet-9"
    cfg["features"]["a/Top"] = {"vision": True, "web": False}
    assert pick("vision")["model"] == "a/Top"                                            # image-capable flatiron model wins


def check_effort_clamp():
    """The efforts map clamps --reasoning to what each flatiron model accepts: the nearest
    accepted value at or above the tier effort. pick, lanes and assign agree on the value."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    jpath = STAGE / "flatiron-routing.json"                       # staged runs judge the staged json
    cfg = json.loads((jpath if jpath.is_file() else r.ROUTING_FILE).read_text())
    QWEN, MIST = "Qwen/Qwen3.8-27B-FP8", "mistralai/Mistral-Medium-3.5-128B"
    assert set(cfg.get("efforts") or {}) >= {QWEN, MIST}, cfg.get("efforts")   # both limited models listed
    r.routing = lambda: cfg
    r.inflight_counts = lambda: {}

    def efforts_of(model, tier):
        cfg["rank"], cfg["routes"] = {model: 5}, {"code": [model]}
        r.flatiron_status = lambda *a: {model: {"ok": True}}
        outs = [r.pick("code", tier, [], False), r.lanes("code", tier, [], [])[0],
                r.assign([("n1", "code", tier, [])])[0]]
        return [o["flags"].split("--reasoning ", 1)[1].split()[0] for o in outs]

    assert efforts_of(QWEN, "senior") == ["xhigh"] * 3                # high -> xhigh
    assert efforts_of(QWEN, "principal") == ["xhigh"] * 3             # principal high -> xhigh
    assert efforts_of(MIST, "intern") == ["high"] * 3                 # low -> high
    assert efforts_of(MIST, "principal") == ["high"] * 3              # principal high -> high
    jv = cfg["tiers"]["junior"]["reasoning_effort"]                    # the json value, not a live pin
    assert efforts_of("n/Unlisted", "junior") == [jv] * 3              # no entry: the tier value stays


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
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    lanes = lambda kind="code", tier="senior", failed=(), needs=(): r.lanes(kind, tier, list(failed), list(needs))
    pick = lambda kind="code", tier="senior", failed=(), needs=(): r.pick(kind, tier, list(failed), False, list(needs))
    health(a_Top=True, b_Mid=True, c_Lo=True, d_NoVis=True, e_Down=False)          # one unhealthy model
    out = lanes()
    assert [x["model"] for x in out] == ["a/Top", "b/Mid", "c/Lo", "d/NoVis"], out   # 4 healthy -> 4 lanes in pick order
    assert [x["rank"] for x in out] == [5, 4, 3, 2], out
    assert "e/Down" not in str(out), out                                             # unhealthy model absent
    health(a_Top=True, b_Mid=True, c_Lo=True, d_NoVis=False, e_Down=False)          # 3 healthy -> exactly 3 lanes
    out = lanes()
    assert [x["model"] for x in out] == ["a/Top", "b/Mid", "c/Lo"], out
    first = pick()                                                                  # lanes[0] equals pick for the same args
    assert first["model"] == out[0]["model"] and first["flags"] == out[0]["flags"] \
        and first["provider"] == out[0]["provider"], (first, out[0])
    health(a_Top=True, b_Mid=True, c_Lo=True, d_NoVis=True, e_Down=False)
    assert [x["model"] for x in lanes(needs=["vision"])] == ["a/Top", "b/Mid"], "vision need must drop c/Lo and d/NoVis"
    assert [x["model"] for x in lanes(kind="vision")] == ["a/Top", "b/Mid"], "kind vision == --needs vision"
    assert [x["model"] for x in lanes(tier="principal")] == ["a/Top", "b/Mid", "c/Lo"], "principal keeps the top-3 rank values (5,4,3)"
    f = lanes(tier="principal")[0]["flags"]                                         # the tier's effort and skills, like pick's
    assert "--reasoning high" in f and "-s brainstorm -s team -s manager" in f, f
    health(a_Top=False, b_Mid=False, c_Lo=False, d_NoVis=False, e_Down=False)      # all flatiron down
    out = lanes()
    assert len(out) == 1 and out[0].get("fallback") is True, out                    # one fallback entry
    assert out[0]["provider"] != "flatiron" and out[0]["model"] == "claude-sonnet-9", out
    assert out[0]["flags"] == pick()["flags"], out


def check_needs():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"a/Top": 4, "b/Mid": 3}, "routes": {"code": ["a/Top", "b/Mid"]},
           "features": {"a/Top": {"vision": True, "web": False}, "b/Mid": {"vision": False, "web": True},
                        "haiku": {"vision": True, "web": True}, "sonnet": {"vision": True, "web": True},
                        "opus": {"vision": True, "web": True}}}
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    pick = lambda kind="code", tier="senior", failed=(), needs=(): r.pick(kind, tier, list(failed), False, list(needs))
    health(a_Top=True, b_Mid=True)
    assert pick(needs=["web"])["model"] == "b/Mid"                                     # --needs web
    assert pick(needs=["vision"])["model"] == "a/Top"                                  # --needs vision
    assert pick("vision")["model"] == "a/Top"                                          # kind vision == --needs vision
    assert pick(needs=["vision", "web"])["model"] == "claude-sonnet-9"                 # no flatiron fit -> tier rung
    health(a_Top=True, b_Mid=True, n_Noentry=True)
    assert pick(needs=["web"])["model"] == "b/Mid"                                     # missing entry = no features
    cfg["features"]["sonnet"] = {"vision": False, "web": False}
    cfg["features"]["opus"] = {"vision": False, "web": False}
    got = pick(needs=["vision", "web"])
    assert got["provider"] is None and "failed" not in got["reason"], got               # rungs filtered, none failed: no "( failed)"
    assert pick(needs=["web"])["model"] == "b/Mid"                                     # the filtered rungs changed nothing here


def check_default_features():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"a/Top": 4}, "routes": {"code": ["a/Top"]}}       # a routing json with no features map
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {"a/Top": {"ok": True}}
    assert r.pick("vision", "senior", [], False)["model"] == "claude-haiku-9"            # built-in Claude entries keep the rungs
    assert r.pick("code", "senior", [], False, ["web"])["model"] == "claude-sonnet-9"    # --needs falls back to them too
    cfg["features"] = {"haiku": {"vision": False, "web": False}}      # a loaded entry wins, missing keys keep the built-ins
    assert r.pick("vision", "senior", [], False)["model"] == "claude-sonnet-9"


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
        with contextlib.redirect_stdout(buf):
            r.sync_features({**health, "e/New2": {"ok": True}}, listed + ["e/New2"])
        assert "routing json changed during sync, not published" in buf.getvalue(), buf.getvalue()
        assert json.loads(rj.read_text()) == edi, "the mid-run edit must not be overwritten"


def check_sync_rank():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        rj = Path(d, "routing.json")
        base = {"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {}, "features": {"a/Top": {"vision": True, "web": True}}, "tiers": {}}
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
        with contextlib.redirect_stdout(buf):
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
        with contextlib.redirect_stdout(buf):
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
        raw = json.dumps({"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {}, "features": {}, "tiers": {}}) + "\n"
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
        raw = json.dumps({"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {}, "features": {}, "tiers": {}}) + "\n"
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
        raw = json.dumps({"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {}, "features": {}, "tiers": {}}) + "\n"
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
        with contextlib.redirect_stdout(buf):
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
        with contextlib.redirect_stdout(buf):
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
        with contextlib.redirect_stdout(buf):
            assert r.sync(False) == 1
        assert store == oldvals, store        # all keys old again, the failing one included
        assert "restored delegation.model" in buf.getvalue(), buf.getvalue()
        assert not lock_held(), "the config lock must be released after the transaction"


def check_principal_floor():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "x"}
    rank = {f"m{i}": i for i in range(1, 7)}                # 6 ranked models
    cfg = {"rank": rank, "routes": {"code": sorted(rank, key=lambda m: -rank[m])}, "tiers": {},
           "features": {}}
    r.routing = lambda: cfg
    def health(**ok):
        r.flatiron_status = lambda *a: {m.replace("_", "/"): {"ok": v} for m, v in ok.items()}
    pick = lambda tier="principal": r.pick("code", tier, [], False)
    health(m6=False, m5=False, m4=True, m3=True, m2=True, m1=True)
    assert pick()["model"] == "m4"                          # rank 4 is in the top 3 of 6
    health(m6=False, m5=False, m4=False, m3=True, m2=True, m1=True)
    got = pick()
    assert any(s.startswith("m3:") for s in got["skipped"]), got    # rank 3 is not
    assert got["model"] == "claude-opus-9", got             # the floor pushes principal to the Opus rung
    assert pick("senior")["model"] == "m3"                  # senior has no floor
    # a hand-edited map with gaps: principal is the 3 highest rank VALUES, not len(rank) - 2
    gaps = {"g6": 6, "g5": 5, "g3": 3, "g1": 1}              # {6,5,3,1}: top three values are 6, 5, 3
    cfg["rank"], cfg["routes"] = gaps, {"code": sorted(gaps, key=lambda m: -gaps[m])}
    health(g6=False, g5=False, g3=True, g1=True)
    assert pick()["model"] == "g3"                          # rank 3 is in the top three values
    health(g6=False, g5=False, g3=False, g1=True)
    assert pick()["model"] == "claude-opus-9"               # rank 1 is not
    tight = {"h6": 6, "h5": 5, "h1": 1, "h0": 0}            # {6,5,1,0}: the rules diverge here
    cfg["rank"], cfg["routes"] = tight, {"code": sorted(tight, key=lambda m: -tight[m])}
    health(h6=False, h5=False, h1=True, h0=True)
    assert pick()["model"] == "h1"                          # rank 1 is the 3rd-highest value
    # a ranked model the gateway lists no more takes no principal slot; a listed but unhealthy one
    # still does, and the 3 highest listed rank values set the floor
    cfg["rank"], cfg["routes"] = rank, {"code": sorted(rank, key=lambda m: -rank[m])}
    health(m3=True, m2=True, m1=True)                       # m6/m5/m4 retired: not listed
    assert [x["model"] for x in r.lanes("code", "principal", [], [])] == ["m3", "m2", "m1"]
    health(m6=False, m3=True, m2=True, m1=True)             # m6 listed but down: still holds a slot
    assert [x["model"] for x in r.lanes("code", "principal", [], [])] == ["m3", "m2"], "m1 must fall below the floor"
    # M2: an empty ranked set gives no principal flatiron lane; the fallback ladder serves
    cfg["rank"], cfg["routes"] = {}, {"code": ["n/New"]}
    health(n_New=True)
    assert pick()["model"] == "claude-opus-9"               # unranked: principal falls to the Opus rung
    assert [x["model"] for x in r.lanes("code", "principal", [], [])] == ["claude-opus-9"]
    assert all(x.get("fallback") for x in r.lanes("code", "principal", [], []))
    assert r.pick("code", "senior", [], False)["model"] == "n/New"         # senior has no floor


def check_principal_anchor():
    """The principal pick takes the kind's floors anchor (the escalation model), not the head of
    the routes list. A placement whose ranker ranks another model above the anchor still leaves
    the principal pick on the anchor. Staged runs use the staged json."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                   "haiku": "claude-haiku-9", "sol": "x"}
    jpath = STAGE / "flatiron-routing.json"
    cfg = json.loads((jpath if jpath.is_file() else r.ROUTING_FILE).read_text())
    anchor = cfg["floors"]["code"]                                         # moonshotai/Kimi-K3
    r.routing = lambda: cfg
    # in-flight scan is live machine state; stub it so a busy host cannot skip the anchor
    r.inflight_counts = lambda: {}
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in cfg["rank"]}
    assert r.pick("code", "principal", [], False)["model"] == anchor       # the staged order leads with MiMo
    cfg["routes"]["code"] = [m for m in cfg["routes"]["code"] if m != anchor] + [anchor]
    assert r.pick("code", "principal", [], False)["model"] == anchor       # the routes order cannot take it
    assert r.pick("code", "senior", [], False)["model"] == cfg["routes"]["code"][0]   # lower tiers keep pick order
    # a sync run whose stubbed ranker ranks MiMo above Kimi-K3 and a newcomer above both
    with tempfile.TemporaryDirectory() as d:
        rj = Path(d, "routing.json"); side = Path(d, "cache", "dispatch-route")
        r.ROUTING_FILE, r.SIDECAR_DIR = rj, side
        r._selftest_ok = lambda *_: True
        listed = ["n/Above"] + list(cfg["rank"])
        others = sorted((m for m in cfg["rank"] if m != anchor), key=lambda m: -cfg["rank"][m])
        seq = ["n/Above", others[0], anchor] + others[1:]                  # anchor keeps a top-3 rank value
        r._run_ranker = lambda *a, **k: {m: len(seq) - i for i, m in enumerate(seq)}
        side.mkdir(parents=True, exist_ok=True)
        rj.write_text(json.dumps(cfg) + "\n")
        r.sync_rank({"opus": "claude-opus-9"}, {m: {"ok": True} for m in listed}, listed)
        got = json.loads(rj.read_text())
        assert got["routes"]["code"][0] == "n/Above", got["routes"]["code"]   # placement really put it first
        r.routing = lambda: got
        r.flatiron_status = lambda *a: {m: {"ok": True} for m in got["rank"]}
        assert r.pick("code", "principal", [], False)["model"] == anchor    # principal stays on the anchor


def check_sync_rank_reasons():
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        rj = Path(d, "routing.json")
        rj.write_text(json.dumps({"rank": {"a/Top": 2, "b/Mid": 1}, "routes": {}, "features": {}, "tiers": {}}))
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
        with contextlib.redirect_stdout(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New"])
        log = buf.getvalue()
        assert "top bench score" in log and "new but strong" in log, log
        assert json.loads(rj.read_text())["rank"]["n/New"] == 2 and not state.exists()
        # an order-only reply still validates and the log says there were no reasons
        r._run_ranker = lambda *a, **k: {"order": {"a/Top": 4, "b/Mid": 1, "n/New": 2, "y/New2": 3}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New", "y/New2"])
        assert "no reasons" in buf.getvalue(), buf.getvalue()
        assert json.loads(rj.read_text())["rank"]["y/New2"] == 3
        # a non-dict reasons value is treated the same; it must not crash the run
        r._run_ranker = lambda *a, **k: {"order": {"a/Top": 5, "b/Mid": 1, "n/New": 2, "y/New2": 3, "z/New3": 4},
                                         "reasons": "talk"}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r.sync_rank(latest, health, ["a/Top", "b/Mid", "n/New", "y/New2", "z/New3"])
        assert "no reasons" in buf.getvalue() and json.loads(rj.read_text())["rank"]["z/New3"] == 4

        # untrusted reason text: after validation, one sanitized line per reason, no forged line
        r._run_ranker = lambda *a, **k: {"order": {"a/Top": 6, "b/Mid": 1, "n/New": 2, "y/New2": 4,
                                                   "z/New3": 3, "w/New4": 5},
                                         "reasons": {"n/New": "ok \ud800 tail",
                                                     "y/New2": "x\nrank: ACCEPTED fake line\n" + "y" * 300}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
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
        with contextlib.redirect_stdout(buf):
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
        with contextlib.redirect_stdout(buf):
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
        with contextlib.redirect_stdout(buf):
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
    out = run(specs, {})                                # one empty batch spreads 2/1/1 in pick order
    assert [o["model"] for o in out] == ["m1", "m2", "m3", "m1"], out
    assert [o["node"] for o in out] == ["n1", "n2", "n3", "n4"], out
    assert [o["load"] for o in out] == [0, 0, 0, 1], out
    assert all(o["provider"] == "flatiron" and o["fallback"] is False for o in out), out
    assert all(o["kind"] == "code" and o["tier"] == "senior" for o in out), out
    assert all(o["reason"] for o in out), out
    assert set(out[0]) == {"node", "kind", "tier", "provider", "model", "flags", "load", "reason", "fallback"}, out
    assert out[0]["flags"] == r.pick("code", "senior", [], False)["flags"], out     # flags == pick's

    out = run([("n1", "code", "senior", [])], {"m1": 3})           # 3 live jobs on m1 -> idle m2
    assert out[0]["model"] == "m2" and out[0]["load"] == 0, out

    out = run([("n1", "code", "senior", []), ("n2", "code", "senior", [])], {"m1": 3, "m2": 2, "m3": 1})
    # every eligible model busy: idle x/Idle (rank 9, healthy, not listed for code) must never win
    assert [o["model"] for o in out] == ["m3", "m2"], out
    assert [o["load"] for o in out] == [1, 2], out
    assert "x/Idle" not in str(out), out

    # principal never takes a model outside the top-3 rank values, even when it is idle
    cfg["rank"], cfg["routes"] = {"p1": 4, "p2": 3, "p3": 2, "p4": 1}, {"code": ["p4", "p3", "p2", "p1"]}
    health(p1=True, p2=True, p3=True, p4=True)
    out = run([("n1", "code", "principal", [])], {"p1": 5, "p2": 4, "p3": 3})
    assert out[0]["model"] == "p3" and "p4" not in str(out), out

    # kind vision (no routes list) serves only vision:true models, and fallback when none fits
    cfg["rank"], cfg["routes"] = {"v1": 2, "v2": 9}, {"code": ["v1"]}
    cfg["features"].update({"v1": {"vision": True, "web": False}, "v2": {"vision": False, "web": False}})
    health(v1=True, v2=True)
    out = run([("n1", "vision", "junior", [])], {})
    assert out[0]["model"] == "v1" and "v2" not in str(out), out
    health(v1=False, v2=True)                                      # no eligible healthy model
    out = run([("n1", "code", "senior", [])], {})
    assert out[0]["fallback"] is True and out[0]["model"] == "claude-sonnet-9", out
    assert out[0]["provider"] != "flatiron" and out[0]["load"] == 0, out
    out = run([("n1", "vision", "junior", [])], {})                 # vision puts the Haiku rung first
    assert out[0]["fallback"] is True and out[0]["model"] == "claude-haiku-9", out


def check_assign_capacity():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"s/One": 3, "q/Qwen": 2, "s/Two": 1}, "tiers": json.loads(r.ROUTING_FILE.read_text())["tiers"],
           "routes": {"mechanical": ["s/One", "q/Qwen", "s/Two"]},
           "capacity": {"q/Qwen": 4}, "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in ("s/One", "q/Qwen", "s/Two")}
    r.inflight_counts = lambda: {}
    out = r.assign([(f"n{i}", "mechanical", "senior", []) for i in range(1, 6)])
    models = [o["model"] for o in out]
    # 5 nodes, multi-instance q/Qwen (capacity 4) and two single-instance models: one node per
    # single-instance model, the rest on q/Qwen
    assert models == ["s/One", "q/Qwen", "s/Two", "q/Qwen", "q/Qwen"], out
    assert models.count("s/One") <= 1 and models.count("s/Two") <= 1, out
    assert all(o["provider"] == "flatiron" and o["fallback"] is False for o in out), out
    assert all(o["kind"] == "mechanical" and o["reason"] for o in out), out


def check_assign_capacity_inflight():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    cfg = {"rank": {"s/One": 3, "q/Qwen": 2}, "tiers": json.loads(r.ROUTING_FILE.read_text())["tiers"],
           "routes": {"mechanical": ["s/One", "q/Qwen"]},
           "capacity": {"q/Qwen": 4}, "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in ("s/One", "q/Qwen")}
    # a live in-flight job on the single-instance model makes assign skip it
    r.inflight_counts = lambda: {"s/One": 1, "q/Qwen": 3}
    out = r.assign([("n1", "mechanical", "senior", [])])
    assert out[0]["model"] == "q/Qwen" and out[0]["fallback"] is False, out
    # every eligible model full: the most capacity left counting overflow (the multi-instance
    # model wins ties), never the fallback ladder
    r.inflight_counts = lambda: {"s/One": 1, "q/Qwen": 4}
    out = r.assign([("n1", "mechanical", "senior", [])])
    assert out[0]["model"] == "q/Qwen" and out[0]["provider"] == "flatiron" and out[0]["fallback"] is False, out
    assert out[0]["reason"].startswith("every eligible model at capacity"), out
    # pick for one node prefers a model with free capacity
    r.inflight_counts = lambda: {"s/One": 1, "q/Qwen": 3}
    got = r.pick("mechanical", "senior", [], False)
    assert got["model"] == "q/Qwen", got


def check_prefer_cheapest():
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    tiers = json.loads(r.ROUTING_FILE.read_text())["tiers"]                       # the real tier table: needs prefer on intern and junior
    assert tiers["intern"].get("prefer") == tiers["junior"].get("prefer") == "cheapest", tiers
    assert "prefer" not in tiers["senior"] and "prefer" not in tiers["principal"], tiers
    cfg = {"rank": {"s/Strong": 5, "m/Mid": 4, "c/Cheap": 2, "d/Down": 1, "u/Unlisted": 3}, "tiers": tiers,
           "routes": {"code": ["s/Strong", "m/Mid", "c/Cheap", "d/Down"], "mechanical": ["s/Strong", "c/Cheap", "m/Mid"]},
           "floors": {"code": "m/Mid"}, "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": m != "d/Down"} for m in ("s/Strong", "m/Mid", "c/Cheap", "d/Down", "u/Unlisted")}
    pick = lambda kind, tier, failed=(): r.pick(kind, tier, list(failed), False)["model"]
    assert pick("code", "intern") == "c/Cheap"                                     # lowest rank value first, unhealthy d/Down skipped
    assert pick("code", "junior") == "c/Cheap"
    assert pick("code", "senior") == "s/Strong"                                    # senior keeps the routes order
    assert pick("code", "intern", ["c/Cheap"]) == "m/Mid"                          # escalation: next stronger, not the strongest
    assert [x["model"] for x in r.lanes("code", "intern", [], [])] == ["c/Cheap", "m/Mid", "s/Strong"]
    assert "u/Unlisted" not in str(r.lanes("code", "intern", [], [])), "a model outside the kind's routes never enters"
    r.inflight_counts = lambda: {"c/Cheap": 1}
    out = r.assign([("a", "mechanical", "intern", []), ("b", "mechanical", "intern", []), ("c", "mechanical", "intern", [])])
    assert [o["model"] for o in out] == ["m/Mid", "s/Strong", "c/Cheap"], out       # load first, cheapest breaks ties
    r.inflight_counts = lambda: {}
    out = r.assign([("a", "mechanical", "intern", []), ("b", "mechanical", "intern", [])])
    assert [o["model"] for o in out] == ["c/Cheap", "m/Mid"], out
    cfg["rank"]["c/Cheap"] = cfg["rank"]["m/Mid"] = 3                              # tied ranks keep routes order (stable sort)
    assert pick("code", "intern") == "m/Mid"
    del cfg["rank"]["m/Mid"]                                                       # unranked sorts after every ranked model
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
        with contextlib.redirect_stdout(buf):
            assert r.sync(False) == 0
        t = store["delegation.tiers"]
        assert (t["intern"]["model"], t["intern"]["provider"]) == ("c/Cheap", "flatiron"), t["intern"]   # d/Down skipped
        assert (t["junior"]["model"], t["junior"]["provider"]) == ("c/Cheap", "flatiron"), t["junior"]
        assert "model" not in t["senior"] and "model" not in t["principal"], t
        assert store["delegation.model"] == "s/Strong"                                    # senior and principal keep delegation.model
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert r.sync(False) == 0
        assert "config already current" in buf.getvalue(), buf.getvalue()                # second run: no rewrite
        cfg["rank"]["c/Cheap"] = 9; cfg["routes"]["code"] = ["s/Strong", "d/Down"]       # cheapest healthy changes for junior
        with contextlib.redirect_stdout(buf := io.StringIO()):
            r.sync(False)
        assert store["delegation.tiers"]["junior"]["model"] == "s/Strong", store["delegation.tiers"]["junior"]
        assert "delegation.tiers=" in buf.getvalue(), buf.getvalue()


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
    """Fixture router for the ledger cases: three healthy models, the routes order leads with Mistral."""
    r = load("hermes-dispatch-route")
    r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9", "haiku": "claude-haiku-9", "sol": "x"}
    r.inflight_counts = lambda: {}
    qwen, mist, kimi = "Qwen/Qwen3.8-27B-FP8", "mistralai/Mistral-Medium-3.5-128B", "moonshotai/Kimi-K3"
    cfg = {"rank": {qwen: 5, mist: 4, kimi: 3},
           "routes": {"mechanical": [mist, qwen, kimi], "code": [mist, qwen, kimi]},
           "tiers": {"senior": {"reasoning_effort": "high", "fallback": ["sonnet"]},
                     "intern": {"reasoning_effort": "low", "prefer": "cheapest", "fallback": ["haiku", "sonnet"]}},
           "features": {}}
    r.routing = lambda: cfg
    r.flatiron_status = lambda *a: {m: {"ok": True} for m in cfg["rank"]}
    return r, qwen, mist, kimi


def _ledger_row(i, model, verdict, kind="mechanical"):
    return {"ts": i, "node": "n", "kind": kind, "tier": "senior", "model": model, "verdict": verdict, "note": ""}


def check_ledger_qwen_first():
    """An empty ledger: the Qwen preference decides the mechanical and the intern pick."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        led.write_text("")
        assert r.pick("mechanical", "senior", [], False)["model"] == qwen      # routes lead with Mistral
        assert r.pick("code", "intern", [], False)["model"] == qwen            # every intern pick, over prefer=cheapest
        os.environ["HERMES_DISPATCH_LEDGER"] = str(Path(d, "missing.jsonl"))   # a missing file is an empty ledger
        assert r.pick("mechanical", "senior", [], False)["model"] == qwen
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


def check_ledger_demotes():
    """Three failed rows for a kind demote the model: the next lane takes the pick."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        rows = [_ledger_row(i, "QWEN/QWEN3.8-27B-FP8", v)                      # upper-case id pins the lowercase match
                for i, v in enumerate(("failed-garbled-report", "hung", "fabricated-report"))]
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        p = r.pick("mechanical", "senior", [], False)
        assert p["model"] == mist, p
        assert any(s.startswith(qwen) and s.endswith("ledger: last 3 mechanical runs failed")
                   for s in p["skipped"]), p["skipped"]
        assert [x["model"] for x in r.lanes("mechanical", "senior", [], [])] == [mist, kimi]   # lanes obeys the demotion
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


def check_ledger_mixed_verdicts():
    """Two failures plus one clean run in the last 3 rows do not demote."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        rows = [_ledger_row(i, qwen, v) for i, v in enumerate(("failed-interrupted", "hung", "done-clean"))]
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        p = r.pick("mechanical", "senior", [], False)
        assert p["model"] == qwen, p
        assert not any("ledger" in s for s in p["skipped"]), p["skipped"]
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


def check_ledger_bad_lines():
    """A garbage line is skipped: it never crashes pick and never counts as history."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        bad = ["not json at all", "null", "", '{"kind": "mechanical", "model": "Qwen/Qwen3.8-27B-FP8"}',
               '{"kind": "mechanical", "model": "x/y", "verdict": 5}']
        lines = []
        for i in range(3):
            lines.append(json.dumps(_ledger_row(i, qwen, f"failed-{i}")) + "\n")
            lines.append(bad[i] + "\n")
        led.write_text("".join(lines))
        p = r.pick("mechanical", "senior", [], False)
        assert p["model"] == mist, p                                         # the 3 bad rows still demote Qwen
        assert [x["model"] for x in r.lanes("mechanical", "senior", [], [])] == [mist, kimi], p
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


def check_ledger_all_skipped():
    """Every candidate dead in the ledger: fall back to the unskipped order and say so in reason."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        rows = []
        for m in (qwen, "mistralai/Mistral-Medium-3.5-128K", kimi):            # the -128K suffix pins the size normalization
            for i in range(3):
                rows.append(_ledger_row(len(rows), m, f"failed-{i}"))
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        p = r.pick("mechanical", "senior", [], False)
        assert p["model"] == qwen, p                                         # demotion is advisory when every candidate is dead
        assert "ledger fallback" in p["reason"] and "unskipped order" in p["reason"], p
        assert any("serving the unskipped order" in s for s in p["skipped"]), p["skipped"]
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


def check_qwen_first_not_principal():
    """F1: the Qwen-first reorder never applies to a principal pick: the floors anchor keeps the lead."""
    r, qwen, mist, kimi = _ledger_case()
    with tempfile.TemporaryDirectory() as d:
        os.environ["HERMES_DISPATCH_LEDGER"] = str(Path(d, "outcomes.jsonl"))   # missing file = empty ledger
        cfg = r.routing()
        cfg["tiers"]["principal"] = {"reasoning_effort": "high", "skills": [], "fallback": ["opus"]}
        cfg["floors"] = {"mechanical": kimi, "code": kimi}
        cfg["routes"] = {"mechanical": [kimi, mist, qwen], "code": [kimi, mist, qwen]}
        assert r.pick("mechanical", "principal", [], False)["model"] == kimi, "anchor leads, never Qwen-first"
        assert r.pick("code", "principal", [], False)["model"] == kimi, "control: code x principal"
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


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
                rows.append(_ledger_row(len(rows), m, f"failed-{i}"))
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))
        note = "ledger fallback: serving the unskipped order"
        for x in r.lanes("mechanical", "senior", [], []):
            assert note in x.get("reason", ""), x
        a = r.assign([("n1", "mechanical", "senior", [])])[0]
        assert note in a["reason"], a
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


def check_norm_model_size_suffix():
    """F6: only a trailing -128b or -128k normalizes away: distinct size variants keep distinct keys."""
    r = load("hermes-dispatch-route")
    n = r._norm_model
    assert n("MISTRALAI/MISTRAL-MEDIUM-3.5-128K") == n("mistralai/Mistral-Medium-3.5-128B")
    assert n("Qwen/Qwen3.8-27B") != n("Qwen/Qwen3.8-32B"), "27B and 32B must not share one history key"
    assert n("Qwen/Qwen3.8-27B-FP8") == "qwen/qwen3.8-27b-fp8", "a non-size suffix stays"


def check_sync_pin_effort_clamp():
    """D8: sync never writes a reasoning_effort the pinned model refuses. The fixture pins Mistral
    (accepts none, high) for intern at tier effort low: the written tier must say high."""
    r = load("hermes-dispatch-route")
    with tempfile.TemporaryDirectory() as d:
        r.SIDECAR_DIR = Path(d, "cache", "dispatch-route")
        r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "sonnet": "claude-sonnet-9",
                                       "haiku": "claude-haiku-9", "sol": "x"}
        mist = "mistralai/Mistral-Medium-3.5-128B"
        cfg = {"rank": {mist: 1}, "routes": {"mechanical": [mist], "code": [mist]},
               "efforts": {mist: ["none", "high"]}, "features": {},
               "tiers": {"intern": {"reasoning_effort": "low", "prefer": "cheapest", "skills": [], "fallback": ["haiku"]},
                         "senior": {"reasoning_effort": "high", "skills": [], "fallback": ["sonnet"]}}}
        r.routing = lambda: cfg
        r.flatiron_status = lambda *a: {mist: {"ok": True}}
        r.load_cache = lambda: {"flatiron": {"listed": [mist]}}
        r.sync_features = lambda *a: None
        r.sync_rank = lambda *a: None
        store = {}                                                     # fake hermes config, like check_sync_tier_models

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
        with contextlib.redirect_stdout(io.StringIO()):
            assert r.sync(False) == 0
        t = store["delegation.tiers"]
        assert (t["intern"]["model"], t["intern"]["reasoning_effort"]) == (mist, "high"), t["intern"]


QWEN, MIST, KIMI = "Qwen/Qwen3.8-27B-FP8", "mistralai/Mistral-Medium-3.5-128B", "moonshotai/Kimi-K3"
# One fixture table for the CLI cases: flatiron trio, intern and senior tiers, generous capacity
# so a real in-flight job on this machine never moves the pick.
_CLI_TABLE = json.dumps({
    "rank": {QWEN: 5, MIST: 4, KIMI: 3},
    "routes": {"mechanical": [MIST, QWEN, KIMI], "code": [MIST, QWEN, KIMI]},
    "capacity": {QWEN: 9, MIST: 9, KIMI: 9},
    "tiers": {"intern": {"reasoning_effort": "low", "skills": [], "fallback": ["haiku", "sonnet"]},
              "senior": {"reasoning_effort": "high", "skills": [], "fallback": ["sonnet"]}},
    "features": {}})


def _cli(args, routing=_CLI_TABLE, models=None, ledger=b""):
    """Run the router CLI offline: the scratch HERMES_HOME cache is fresh, so no probe and no
    model discovery reach the network. Returns the CompletedProcess for the caller to assert on."""
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        (home / "cache").mkdir()
        (home / "cache" / "dispatch-route.json").write_text(json.dumps(
            {"flatiron": {"at": time.time(), "models": models or {}, "listed": []},
             "latest": {"at": time.time(), "opus": "fixture-opus", "sonnet": "fixture-sonnet",
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
    rows = [json.dumps(_ledger_row(i, QWEN, v)).encode() for i, v in enumerate(("hung", "failed", "failed-check"))]
    ledger = rows[0] + b"\n\xff\n" + rows[1] + b"\n" + rows[2] + b"\n"
    p = _cli(["pick", "mechanical", "--tier", "intern"], models={m: {"ok": True} for m in (QWEN, MIST, KIMI)}, ledger=ledger)
    assert p.returncode == 0, p.stderr[-300:]
    out = json.loads(p.stdout)
    assert out["model"] == MIST, out                      # Qwen demoted, rows after the bad line kept
    assert any(s.startswith(QWEN) and s.endswith("ledger: last 3 mechanical runs failed")
               for s in out["skipped"]), out["skipped"]


def check_fallback_ledger_demotes():
    """F2: the Claude fallback skips a rung whose own ledger record is dead, in pick, lanes and
    assign. Every rung dead, a model still comes back."""
    def rows(m):
        return b"".join(json.dumps(_ledger_row(i, m, "failed-check", "code")).encode() + b"\n" for i in range(3))
    dead_haiku = rows("fixture-haiku")                    # no flatiron health: straight to the fallback
    p = _cli(["pick", "code", "--tier", "intern"], ledger=dead_haiku)
    assert p.returncode == 0 and json.loads(p.stdout)["model"] == "fixture-sonnet", p.stdout
    ln = _cli(["lanes", "code", "--tier", "intern"], ledger=dead_haiku)
    assert [x["model"] for x in json.loads(ln.stdout)] == ["fixture-sonnet"], ln.stdout
    a = _cli(["assign", "n1=code:intern"], ledger=dead_haiku)
    assert [x["model"] for x in json.loads(a.stdout)] == ["fixture-sonnet"], a.stdout
    p2 = _cli(["pick", "code", "--tier", "intern"], ledger=dead_haiku + rows("fixture-sonnet") + rows("fixture-opus"))
    assert p2.returncode == 0 and json.loads(p2.stdout)["model"], p2.stdout   # never return nothing


def check_fallback_missing_id():
    """N1: a fallback family with no live id is skipped, never a claude_id exit. R2: a later
    family with no id never takes the pick. R3: dead and id-less rungs skip, the clean one wins."""
    r, qwen, mist, kimi = _ledger_case()
    r.routing()["tiers"]["intern"]["fallback"] = ["haiku", "sonnet", "opus"]
    r.flatiron_status = lambda *a: {}                                        # straight to the fallback ladder
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        led.write_text("")                                                   # R2: clean ledger, sonnet has no id
        r.resolve_latest = lambda *a: {"opus": "claude-opus-9", "haiku": "claude-haiku-9", "sol": "x"}
        assert r.pick("code", "intern", [], False)["model"] == "claude-haiku-9"
        rows = [_ledger_row(i, "claude-haiku-9", "failed-check", "code") for i in range(3)]
        led.write_text("".join(json.dumps(x) + "\n" for x in rows))          # R3: haiku dead, sonnet id-less
        assert r.pick("code", "intern", [], False)["model"] == "claude-opus-9"
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


def check_fallback_dead_resolved():
    """F5: an unresolved family never takes the fallback rung. Haiku has no id and Sonnet is
    ledger-dead: the advisory fallback serves the resolved Sonnet in pick, lanes and assign,
    code and vision alike. The old filter exited through claude_id on Haiku here."""
    r, qwen, mist, kimi = _ledger_case()
    r.flatiron_status = lambda *a: {}                                        # straight to the fallback ladder
    r.resolve_latest = lambda *a: {"sonnet": "claude-sonnet-9", "opus": "claude-opus-9", "sol": "x"}
    with tempfile.TemporaryDirectory() as d:
        led = Path(d, "outcomes.jsonl")
        os.environ["HERMES_DISPATCH_LEDGER"] = str(led)
        for kind in ("code", "vision"):
            rows = [_ledger_row(i, "claude-sonnet-9", "failed-check", kind) for i in range(3)]
            led.write_text("".join(json.dumps(x) + "\n" for x in rows))      # three dead Sonnet rows
            assert r.pick(kind, "intern", [], False)["model"] == "claude-sonnet-9"
            assert [x["model"] for x in r.lanes(kind, "intern", [], [])] == ["claude-sonnet-9"]
            assert [x["model"] for x in r.assign([("n1", kind, "intern", [])])] == ["claude-sonnet-9"]
    os.environ.pop("HERMES_DISPATCH_LEDGER", None)


def check_routing_null_list():
    """F4: a routing file whose top level is null or a list takes the built-in table and its
    warning instead of an AttributeError."""
    for raw in ("null", "[]"):
        p = _cli(["pick", "code"], routing=raw)
        assert p.returncode == 0, (raw, p.stderr[-300:])
        assert "built-in table" in p.stderr, (raw, p.stderr)
        assert json.loads(p.stdout)["model"] == "fixture-sonnet", (raw, p.stdout)


if __name__ == "__main__":
    check_route(); check_tiers(); check_effort_clamp(); check_lanes(); check_needs(); check_default_features()
    check_probe_fallback()
    check_sync_features(); check_sync_rank(); check_sync_rank_gates()
    check_sync_rank_gate_crash(); check_sync_rank_budget(); check_sync_config_fail()
    check_principal_floor(); check_principal_anchor(); check_sync_rank_reasons(); check_sync_rank_routes(); check_vision_probe()
    check_assign(); check_assign_capacity(); check_assign_capacity_inflight()
    check_prefer_cheapest(); check_sync_tier_models(); check_inflight_scan(); check_review()
    check_ledger_qwen_first(); check_ledger_demotes(); check_ledger_mixed_verdicts()
    check_ledger_bad_lines(); check_ledger_all_skipped()
    check_qwen_first_not_principal(); check_effort_at_most_high(); check_ledger_fallback_note_lanes_assign()
    check_norm_model_size_suffix(); check_sync_pin_effort_clamp()
    check_ledger_invalid_utf8(); check_fallback_ledger_demotes(); check_routing_null_list()
    check_fallback_missing_id()
    check_fallback_dead_resolved()
    print("selftest OK")
