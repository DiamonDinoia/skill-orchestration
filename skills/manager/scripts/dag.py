#!/usr/bin/env python3
"""Schedule subagent dispatch. GRAPH: {"nodes": {"ID": {"deps": [], "files": [], "resources": [], "state": "todo", "tier": "junior"}}}.
A '#' in a files entry separates the path from the symbol, so a filename that contains '#' cannot be named.
Tiers: intern < junior < senior < principal; a node without a tier is senior. escalate retries a failed node one tier up.
States: todo, running, done, failed. Every command first rejects a graph that `check` rejects.
Exit 0 ok, 1 invalid graph or refused move, 2 usage or filesystem. Stdlib only, python3 >= 3.9."""

import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from graphlib import CycleError, TopologicalSorter

USAGE = "usage: dag.py check GRAPH | plan GRAPH | show GRAPH [--slots N] | dag.py ready GRAPH [--max N] | dag.py start|done|fail|retry GRAPH ID... | dag.py escalate GRAPH ID | dag.py add GRAPH ID [--deps a,b] [--files x,y] [--resources r] [--tier T]"
MOVES = {"start": ("todo", "running"), "done": ("running", "done"), "fail": ("running", "failed")}
STATES = {"todo", "running", "done", "failed"}
TIERS = ("intern", "junior", "senior", "principal")

def dependents(nodes, ids):
    """Every node whose output depends on one of `ids`; reads deps only, not states."""
    seen = set(ids)
    changed = True
    while changed:
        changed = {i for i, n in nodes.items() if i not in seen and seen.intersection(n["deps"])}
        seen |= changed
    return seen

def scope(entry):
    """Split a files entry 'path#symbol' into (normalized path, symbol); symbol None names the whole file."""
    path, sep, symbol = entry.partition("#")
    return os.path.normpath(path), symbol if sep else None

def problems(nodes):
    """Bad tier, unknown deps, a path outside the repo, a cycle, or a file that two unordered nodes write.
    Reports every class at once, so one fix round sees them all."""
    out = [f"node {i}: invalid tier {n['tier']}" for i, n in nodes.items() if n["tier"] not in TIERS]
    out += [f"unknown dep: {i} -> {d}" for i, n in nodes.items() for d in n["deps"] if d not in nodes]
    out += [f"path not repo-relative: {i} {f}" for i, n in nodes.items() for f in n["files"]
            if os.path.isabs(scope(f)[0]) or scope(f)[0].split(os.sep)[0] == ".."]
    out += [f"empty symbol in files entry: {i} {f}" for i, n in nodes.items() for f in n["files"]
            if scope(f)[1] == ""]
    out += [f"empty path in files entry: {i} {f}" for i, n in nodes.items() for f in n["files"]
            if f.partition("#")[0] == ""]  # the raw part: normpath maps an empty one to "."
    deps = {i: [d for d in n["deps"] if d in nodes] for i, n in nodes.items()}  # unknown deps are reported above
    try:
        order = list(TopologicalSorter(deps).static_order())
    except CycleError as err:
        out.append(f"cycle: {' -> '.join(err.args[1])}")
        order = list(nodes)  # the overlap class still reports; order only sets the message order
    out += [f"bad dependency state: {i} is {n['state']}, but {d} is {nodes[d]['state']}"
            for i, n in nodes.items() if n["state"] in ("running", "done")
            for d in deps[i] if nodes[d]["state"] != "done"]
    above = {i: set() for i in nodes}  # above[i]: every node that i reaches through deps
    while True:  # fixpoint reachability, so a cycle cannot hide the overlap class
        grown = {i: set().union(*({d} | above[d] for d in deps[i])) for i in nodes}
        if grown == above:
            break
        above = grown
    writers = {}
    for i in order:
        entries = {}
        for f in nodes[i]["files"]:
            entries.setdefault(scope(f), f)  # one writer record per normalized scope; aliases must not double-report
        for (path, symbol), entry in entries.items():
            # A bare path names the whole file and overlaps every symbol on it; equal symbols overlap.
            out += [f"file overlap: {path} written by {j} ({e}) and {i} ({entry})"
                    if s is not None or symbol is not None
                    else f"file overlap: {path} written by {j} and {i}"
                    for j, s, e in writers.get(path, [])
                    if j != i and j not in above[i] and i not in above[j] and (symbol is None or s is None or symbol == s)]
            writers.setdefault(path, []).append((i, symbol, entry))
    return out

def ready(nodes, limit=None):
    """Todo ids with all deps done, up to `limit`; none shares a resource with a running or picked node."""
    busy = {r for n in nodes.values() if n["state"] == "running" for r in n["resources"]}
    picked = []
    for i, n in nodes.items():
        if len(picked) == limit:
            break
        if n["state"] == "todo" and all(nodes[d]["state"] == "done" for d in n["deps"]) \
                and busy.isdisjoint(n["resources"]):
            picked.append(i)
            busy.update(n["resources"])
    return picked

def move(nodes, cmd, ids):
    """Apply cmd to every id, or to none; return (error list, note) or (None, note)."""
    if len(set(ids)) != len(ids):  # one tracked run per id
        return [f"duplicate id in {cmd}: {' '.join(sorted({i for i in ids if ids.count(i) > 1}))}"], ""
    if cmd == "escalate":
        i = ids[0]
        if i not in nodes:
            return [f"unknown node {i}"], ""
        if nodes[i]["state"] != "failed":
            return [f"cannot escalate {i}: state is not failed"], ""
        if nodes[i]["tier"] == "principal":
            return [f"cannot escalate {i}: already principal; the failure goes to the parent manager"], ""
        errs, _ = move(nodes, "retry", ids)
        if errs:
            return errs, ""
        old = nodes[i]["tier"]
        nodes[i]["tier"] = new = TIERS[TIERS.index(old) + 1]
        return None, f"{i}: {old} -> {new}"
    if cmd == "retry":
        if any(i not in nodes for i in ids):
            return [f"unknown node {' '.join(i for i in ids if i not in nodes)}"], ""
        bad = [i for i in ids if nodes[i]["state"] not in ("failed", "done")]
        if bad:
            return [f"cannot retry {' '.join(bad)}: state is not failed or done"], ""
        reset = dependents(nodes, ids)
        running = [i for i in sorted(reset) if nodes[i]["state"] == "running"]
        if running:
            return [f"cannot retry {' '.join(running)}: still running"], ""
        for i in reset:  # a rerun node changes the input of everything below it
            if nodes[i]["state"] in ("done", "failed"):
                nodes[i]["state"] = "todo"
        return None, f"retry: reset {' '.join(sorted(reset))}"
    want, new = MOVES[cmd]
    unknown = [i for i in ids if i not in nodes]
    bad = [i for i in ids if i in nodes and nodes[i]["state"] != want]
    errs = ([f"unknown node {' '.join(unknown)}"] if unknown else []) \
        + ([f"cannot {cmd} {' '.join(bad)}: state is not {want}"] if bad else [])
    if errs:
        return errs, ""
    if cmd == "start":  # start takes only ids that ready would return right now
        eligible = set(ready(nodes))
        blocked = [i for i in ids if i not in eligible]
        if blocked:
            return [f"cannot start {' '.join(blocked)}: not ready"], ""
    for i in ids:
        nodes[i]["state"] = new
    return None, ""

def show(nodes):
    return [f"{i} {n['state']} unmet: {' '.join(d for d in n['deps'] if nodes[d]['state'] != 'done') or '-'}"
            for i, n in nodes.items()]

def plan(nodes):
    """Group todo and running ids by dependency depth; report each level, the widest level, the level count.
    A node with a failed dependency, direct or transitive, is blocked. Plan leaves it out of the levels and lists it."""
    open_ids = {i for i, n in nodes.items() if n["state"] in ("todo", "running")}
    blocked = open_ids & dependents(nodes, [i for i, n in nodes.items() if n["state"] == "failed"])
    open_ids -= blocked
    graph = {i: [d for d in nodes[i]["deps"] if d in open_ids] for i in open_ids}  # a satisfied dep adds no level
    depth = {}
    for i in TopologicalSorter(graph).static_order():
        depth[i] = 0 if not graph[i] else 1 + max(depth[d] for d in graph[i])
    groups = {}
    for i in depth:  # blocked ids get no depth
        groups.setdefault(depth[i], []).append(i)
    out = [f"L{k}: {' '.join(sorted(groups[k]))}" for k in sorted(groups)]
    if blocked:
        out.append(f"blocked: {' '.join(sorted(blocked))}")
    return out + [f"width={max(map(len, groups.values()), default=0)} critical_path={len(groups)}"]

def normalize(nodes):
    for i, n in nodes.items():
        for key in ("deps", "files", "resources"):
            value = n.setdefault(key, [])
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise TypeError(f"node {i}: {key} is not a list of strings")
        state = n.setdefault("state", "todo")
        if state not in STATES:
            raise TypeError(f"node {i}: bad state {state!r}")
        n.setdefault("tier", "senior")
    return nodes

def selftest():
    def ok(cond, msg):
        if not cond:
            raise RuntimeError(f"selftest: {msg}")
    me = os.path.abspath(__file__)
    with tempfile.TemporaryDirectory(prefix="dag-selftest-") as tmp:
        graph = os.path.join(tmp, "graph.json")
        nodes = lambda d: normalize({i: {"tier": "junior", **n} for i, n in d.items()})  # junior unless a row picks another tier
        files = lambda pairs: nodes({i: {"files": f} for i, f in pairs.items()})
        write = lambda g, p=graph: json.dump({"nodes": g}, open(p, "w", encoding="utf-8"))
        run = lambda *a, p=graph: subprocess.run([sys.executable, me, a[0], p, *a[1:]],
                                                 capture_output=True, text=True)
        g = lambda **deps: nodes({i: {"deps": d} for i, d in deps.items()})
        diamond = g(a=[], b=["a"], c=["a"], d=["b", "c"])
        for cond, msg in [
                (not problems(diamond) and ready(diamond) == ["a"], "diamond"),
                (problems(g(a=["b"], b=["a"]))[0].startswith("cycle"), "cycle"),
                ("unknown dep" in problems(g(a=["x"]))[0], "unknown dep"),
                (problems(files({"x": ["f"], "y": ["f"]})) == ["file overlap: f written by x and y"], "overlap"),
                (not problems(nodes({"x": {"files": ["f"]}, "z": {"deps": ["x"], "files": ["f"]}})), "ordered overlap"),
                (all(problems(files({"x": [p], "y": ["x"]})) for p in ("./x", "a/../x", ".//x")), "aliases of 'x' overlap"),
                (all(problems(files({"x": [p]})) for p in ("/x", "../x", "a/../../x")), "absolute and '..' paths rejected"),
                (not any(problems(files({"x": [p]})) for p in ("./x", "a/../x", "..x")), "'./x' and 'a/../x' accepted"),
                (ready(g(a=[], b=[], c=[]), 2) == ["a", "b"] and ready(g(a=[]), 0) == [], "limits")]:
            ok(cond, msg)
        for cond, msg in [
                (problems(files({"x": ["a.py#f"], "y": ["a.py#g"]})) == [], "different symbols of one file coexist"),
                (problems(files({"x": ["a.py"], "y": ["a.py#f"]}))
                 == ["file overlap: a.py written by x (a.py) and y (a.py#f)"], "a bare path overlaps every symbol"),
                (problems(files({"x": ["a.py#f"], "y": ["a.py#f"]}))
                 == ["file overlap: a.py written by x (a.py#f) and y (a.py#f)"],
                 "the same symbol written twice overlaps"),
                (problems(files({"x": ["a.py#f"], "y": ["a.py"]}))
                 == ["file overlap: a.py written by x (a.py#f) and y (a.py)"], "a mixed overlap names both entries as written"),
                (problems(files({"x": ["a.py#"]})) == ["empty symbol in files entry: x a.py#"],
                 "an empty symbol is rejected"),
                (all(problems(files({"x": [p]})) == [f"empty path in files entry: x {p}"] for p in ("", "#f")),
                 "an empty path part is rejected"),
                (problems(files({"x": ["/x#f"]})) == ["path not repo-relative: x /x#f"],
                 "path checks reject an absolute scoped path"),
                ("repo-relative" not in str(problems(files({"x": ["a.py#x/../.."]}))), "path checks read only the path part"),
                (problems(files({"x": ["x.py", "./x.py"], "y": ["x.py", "./x.py"]})) == ["file overlap: x.py written by x and y"],
                 "two nodes writing aliased paths give one overlap")]:
            ok(cond, msg)
        for cmd, ids, want in [("start", ["a"], []), ("done", ["a"], ["b", "c"]), ("start", ["b", "c"], []),
                               ("done", ["b"], []), ("done", ["c"], ["d"])]:
            ok(move(diamond, cmd, ids)[0] is None and ready(diamond) == want, f"{cmd} {ids}")
        shared = nodes({"p": {"resources": ["db"]}, "q": {"resources": ["db"]}, "r": {}})
        ok(ready(shared) == ["p", "r"] and move(shared, "start", ["q"])[0] and ready(shared) == ["p", "r"], "resources")
        chain = g(a=[], b=["a"])
        ok(move(chain, "start", ["a"])[0] is None and move(chain, "fail", ["a"])[0] is None, "start+fail")
        ok(show(chain) == ["a failed unmet: -", "b todo unmet: a"], "show")
        err, note = move(chain, "retry", ["a"])
        ok(err is None and "a" in note and chain["a"]["state"] == "todo", "retry failed node prints the reset")
        done_graph = nodes({"a": {"state": "done"}, "b": {"deps": ["a"], "state": "done"}, "c": {"deps": ["b"], "state": "done"}})
        err, note = move(done_graph, "retry", ["a"])
        ok(err is None and note.split()[-3:] == ["a", "b", "c"]
           and all(n["state"] == "todo" for n in done_graph.values()), "retry a done node resets done dependents")
        mixed = nodes({"a": {"state": "done"}, "b": {"deps": ["a"], "state": "running"}})
        err, _ = move(mixed, "retry", ["a"])
        ok(err and "b" in err[0] and mixed["a"]["state"] == "done", "retry refuses a running dependent")
        ok(move(g(a=[]), "retry", ["zzz"])[0], "retry an unknown id")
        for g2, args, frag in [({"a": {"deps": ["b"], "tier": "junior"}, "b": {"tier": "junior"}}, ("start", "a"), "not ready"),
                               ({"a": {"resources": ["db"], "tier": "junior"}, "b": {"resources": ["db"], "tier": "junior"}}, ("start", "a", "b"), "not ready"),
                               ({"a": {"tier": "junior"}, "b": {"deps": ["a"], "state": "running", "tier": "junior"}}, ("check",), "b is running, but a is todo"),
                               ({"a": {"state": "weird"}}, ("check",), "bad state"),
                               ({"a": {"deps": [1]}}, ("check",), "strings"),
                               ({"a": {"files": ["/x"], "tier": "junior"}}, ("check",), "not repo-relative: a /x"),
                               ({"a": {"tier": "junior"}}, ("start", "a", "a"), "duplicate id")]:
            write(g2)
            before = open(graph, "rb").read()
            res = run(*args)
            ok(res.returncode == 1 and frag in res.stderr and res.stderr.count("\n") == 1
               and open(graph, "rb").read() == before, frag)
        write({"a": {"tier": "junior"}})
        lockfd = os.open(graph + ".lock", os.O_CREAT | os.O_RDWR)
        fcntl.flock(lockfd, fcntl.LOCK_EX)  # this process holds the lock; a writer must block
        proc = subprocess.Popen([sys.executable, me, "start", graph, "a"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            proc.communicate(timeout=2)
            raise RuntimeError("selftest: writer did not block on the held lock")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
        os.close(lockfd)  # closing the descriptor drops the flock
        t0 = time.monotonic()
        res = run("start", "a")
        ran = json.load(open(graph, encoding="utf-8"))["nodes"]["a"]["state"] == "running"
        ok(res.returncode == 0 and ran and time.monotonic() - t0 < 2, "lock released")
        ok(run("check", p=os.path.join(tmp, "missing.json")).returncode == 2, "missing graph exits 2")
        rodir = os.path.join(tmp, "ro")
        rograph = os.path.join(rodir, "graph.json")
        os.mkdir(rodir)
        write({"a": {"tier": "junior"}}, rograph)
        os.chmod(rodir, 0o555)
        if not os.access(rodir, os.W_OK):  # root bypasses the mode; the test is meaningless then
            try:
                res = run("start", "a", p=rograph)
                ok(res.returncode == 2 and res.stderr.count("\n") == 1 and "Traceback" not in res.stderr
                   and os.listdir(rodir) == ["graph.json"], "read-only dir: exit 2, one message, no temp file")
            finally:
                os.chmod(rodir, 0o755)
        for g3, args, frag in [({"a": {"tier": "chief"}}, ("check",), "node a: invalid tier chief"),
                               ({"a": {"state": "failed", "tier": "principal"}}, ("escalate", "a"), "already principal"),
                               ({"a": {"state": "todo", "tier": "junior"}}, ("escalate", "a"), "state is not failed")]:
            write(g3)
            before = open(graph, "rb").read()
            res = run(*args)
            ok(res.returncode == 1 and frag in res.stderr and "a" in res.stderr
               and open(graph, "rb").read() == before, frag)
        write({"a": {}})
        res = run("check")
        ok(res.returncode == 0 and res.stdout == "ok\n", "a missing tier defaults to senior")
        write({"a": {"state": "failed"}})
        res = run("escalate", "a")
        got = json.load(open(graph, encoding="utf-8"))["nodes"]
        ok(res.returncode == 0 and res.stdout == "a: senior -> principal\n" and got["a"]["tier"] == "principal",
           "escalate of a missing-tier node starts at senior")
        write({"nt": {"tier": "chief"}, "x": {"files": ["f"]}, "y": {"files": ["f"]}, "c": {"deps": ["d"]}, "d": {"deps": ["c"]}})
        res = run("check")
        ok(res.returncode == 1 and res.stderr.count("\n") == 3 and all(s in res.stderr
           for s in ("invalid tier", "file overlap", "cycle")), "check reports every error class")
        write({"a": {"tier": "junior"}})
        before = open(graph, "rb").read()
        res = run("done", "zzz")
        ok(res.returncode == 1 and res.stderr == "unknown node zzz\n" and open(graph, "rb").read() == before,
           "a move on an unknown id reports unknown node")
        json.dump({"nodes": {"a": {"tier": "junior"}}, "b": {"tier": "junior"}}, open(graph, "w", encoding="utf-8"))
        res = run("check")
        ok(res.returncode == 0 and res.stdout == "ok\n" and "stray top-level key b" in res.stderr,
           "check warns on a stray top-level key")
        res = run("start", "b")
        ok(res.returncode == 1 and res.stderr.endswith("unknown node b\n"), "start of a stray key reports unknown node")
        write({"a": {"tier": "junior"}})
        before = open(graph, "rb").read()
        res = run("add", "c", "--bogus", "x")
        ok(res.returncode == 2 and res.stderr == USAGE + "\n" and open(graph, "rb").read() == before,
           "add with a bad flag prints usage")
        res = run("add", "a")
        ok(res.returncode == 1 and "already exists" in res.stderr and open(graph, "rb").read() == before,
           "add refuses a duplicate id")
        res = run("add", "c", "--deps", "a", "--files", "x,y", "--resources", "r", "--tier", "chief")
        ok(res.returncode == 1 and "node c: invalid tier chief" in res.stderr and open(graph, "rb").read() == before,
           "add runs the check and writes nothing on a bad node")
        res = run("add", "c", "--deps", "a", "--files", "x,y", "--resources", "r", "--tier", "junior")
        got = json.load(open(graph, encoding="utf-8"))["nodes"]
        ok(res.returncode == 0 and got["c"] == {"deps": ["a"], "files": ["x", "y"], "resources": ["r"],
                                                "state": "todo", "tier": "junior"} and not problems(normalize(got)),
           "add appends a todo node")
        write({"a": {"state": "failed", "tier": "junior"}, "b": {"deps": ["a"], "state": "failed", "tier": "junior"}})
        res = run("escalate", "a")
        got = json.load(open(graph, encoding="utf-8"))["nodes"]
        ok(res.returncode == 0 and res.stdout == "a: junior -> senior\n" and got["a"]["tier"] == "senior"
           and got["a"]["state"] == "todo" and got["b"]["state"] == "todo", "escalate bumps the tier and retries")
        write({"a": {"tier": "junior"}, "b": {"deps": ["a"], "tier": "junior"}})
        plain = run("show")
        idle = run("show", "--slots", "2")
        ok(plain.returncode == 0 and idle.stdout.splitlines() == plain.stdout.splitlines()
           + ["IDLE: 1 ready for 2 free slots; split todo nodes"], "show --slots adds the IDLE line")
        ok(run("show", "--slots", "1").stdout == plain.stdout and run("show").stdout == plain.stdout,
           "show --slots satisfied stays quiet; no flag keeps the old output")
        write(g(a=[], b=["a"], c=["a"], d=["b", "c"]))
        before = open(graph, "rb").read()
        res = run("plan")
        ok(res.returncode == 0 and res.stdout == "L0: a\nL1: b c\nL2: d\nwidth=2 critical_path=3\n"
           and open(graph, "rb").read() == before, "plan diamond: levels, width, read-only")
        write({"a": {"state": "done"}, "b": {"deps": ["a"], "state": "done"}, "c": {}, "x": {"deps": ["b"]}})
        ok(run("plan").stdout == "L0: c x\nwidth=2 critical_path=1\n",
           "plan counts levels of open nodes only; done deps are satisfied")
        write({"a": {"state": "failed"}, "b": {"deps": ["a"]}, "c": {}})
        ok(run("plan").stdout == "L0: c\nblocked: b\nwidth=1 critical_path=1\n",
           "plan names blocked nodes and leaves them out of the levels")
        write({"a": {"state": "failed"}, "b": {"deps": ["a"]}, "c": {"deps": ["b"]}, "d": {}})
        ok(run("plan").stdout == "L0: d\nblocked: b c\nwidth=1 critical_path=1\n", "plan blocks transitive dependents")
        write({"a": {"state": "done"}})
        ok(run("plan").stdout == "width=0 critical_path=0\n", "plan with nothing left")
        write(g(a=["b"], b=["a"]))
        res = run("plan")
        ok(res.returncode == 1 and res.stdout == "" and "cycle" in res.stderr, "plan on a cycle: exit 1, empty stdout")
        write({})
        ok(run("plan").stdout == "width=0 critical_path=0\n", "plan on an empty graph")
        for args in (("show", "--slots", "\u00b2"), ("ready", "--max", "\u00b2")):
            res = run(*args)
            ok(res.returncode == 2 and res.stderr == USAGE + "\n", f"{args[1]} non-ASCII digits: usage exit 2")
        ok("check|show" not in USAGE and "show GRAPH [--slots N]" in USAGE, "usage shows --slots on show only")
        write({"a": {"state": "failed", "tier": "junior"}})
        for args in (("escalate", "zzz"), ("retry", "zzz")):
            before = open(graph, "rb").read()
            res = run(*args)
            ok(res.returncode == 1 and res.stderr == "unknown node zzz\n"
               and open(graph, "rb").read() == before, f"{args[0]} an unknown id")
    print("selftest: PASS")
    return 0

def main(argv):
    cmd, path, rest = (argv + ["", ""])[1], (argv + ["", ""])[2], argv[3:]
    if cmd == "selftest" and not path:
        return selftest()
    limit = slots = None
    if len(rest) == 2 and (cmd, rest[0]) in (("ready", "--max"), ("show", "--slots")) \
            and rest[1].isascii() and rest[1].isdigit():  # ASCII only: int() rejects the unicode digits isdigit() accepts
        if cmd == "ready":
            limit = int(rest[1])
        else:
            slots = int(rest[1])
        rest = []
    spec = {}
    if cmd == "add":
        flags = {"--deps": "deps", "--files": "files", "--resources": "resources", "--tier": "tier"}
        args = rest[1:]
        pairs = dict(zip(args[::2], args[1::2]))
        if len(args) % 2 or not set(pairs) <= set(flags):
            spec = None
        else:
            spec = {"state": "todo", "deps": [], "files": [], "resources": [], "tier": "senior"}
            for flag, value in pairs.items():
                key = flags[flag]
                spec[key] = value if key == "tier" else [x for x in value.split(",") if x]
    writes = cmd in MOVES or cmd in ("retry", "escalate", "add")
    if not path or cmd not in ("check", "ready", "show", "plan", *MOVES, "retry", "escalate", "add") \
            or bool(rest) != writes or (cmd == "escalate" and len(rest) != 1) or spec is None:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        with open(path + ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # one writer at a time, for the whole read-modify-write
            try:
                with open(path, encoding="utf-8") as handle:
                    graph = json.load(handle)
                nodes = normalize(graph["nodes"])
            except (ValueError, KeyError, TypeError, AttributeError) as err:
                print(f"bad graph {path}: {err}", file=sys.stderr)
                return 1
            except OSError as err:
                print(f"cannot read graph {path}: {err}", file=sys.stderr)
                return 2
            errs, note = problems(nodes), ""
            if not errs and cmd == "add":
                if rest[0] in nodes:
                    errs = [f"cannot add {rest[0]}: node already exists"]
                else:
                    nodes[rest[0]] = spec  # the re-check refuses a bad add before any write
                    errs = problems(nodes)
            elif not errs and writes:
                errs, note = move(nodes, cmd, rest)
            for k in graph:
                if k != "nodes":
                    print(f"warning: stray top-level key {k} outside nodes", file=sys.stderr)
            if errs:
                print("\n".join(errs), file=sys.stderr)
                return 1
            if writes:
                fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump(graph, handle, indent=2)
                    os.replace(tmp, path)  # a crash never leaves half a graph
                finally:  # remove the temp on every failure path
                    os.path.exists(tmp) and os.unlink(tmp)
            out = ready(nodes, limit) if cmd == "ready" else plan(nodes) if cmd == "plan" \
                else show(nodes) if cmd == "show" else ["ok"]
            if cmd == "show" and slots is not None and len(ready(nodes)) < slots \
                    and any(n["state"] == "todo" for n in nodes.values()):
                out.append(f"IDLE: {len(ready(nodes))} ready for {slots} free slots; split todo nodes")
            print(note or "\n".join(out))
    except OSError as err:
        print(f"dag.py: {err}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
