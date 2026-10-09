#!/usr/bin/env python3
"""Schedule subagent dispatch. GRAPH: {"nodes": {"ID": {"deps": [], "files": [], "resources": [], "state": "todo"}}}.
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

USAGE = "usage: dag.py check|show GRAPH | dag.py ready GRAPH [--max N] | dag.py start|done|fail|retry GRAPH ID..."
MOVES = {"start": ("todo", "running"), "done": ("running", "done"), "fail": ("running", "failed")}
STATES = {"todo", "running", "done", "failed"}

def dependents(nodes, ids):
    """Every node whose output depends on one of `ids`; reads deps only, not states."""
    seen = set(ids)
    changed = True
    while changed:
        changed = {i for i, n in nodes.items() if i not in seen and seen.intersection(n["deps"])}
        seen |= changed
    return seen

def problems(nodes):
    """Unknown deps, a path outside the repo, a cycle, or a file that two unordered nodes write."""
    out = [f"unknown dep: {i} -> {d}" for i, n in nodes.items() for d in n["deps"] if d not in nodes]
    out += [f"path not repo-relative: {i} {f}" for i, n in nodes.items() for f in n["files"]
            if os.path.isabs(f) or os.path.normpath(f).split(os.sep)[0] == ".."]
    if out:
        return out
    try:
        order = list(TopologicalSorter({i: n["deps"] for i, n in nodes.items()}).static_order())
    except CycleError as err:
        return [f"cycle: {' -> '.join(err.args[1])}"]
    out += [f"bad dependency state: {i} is {n['state']}, but {d} is {nodes[d]['state']}"
            for i, n in nodes.items() if n["state"] in ("running", "done")
            for d in n["deps"] if nodes[d]["state"] != "done"]
    above, writers = {}, {}  # above[i]: every node that i reaches through deps
    for i in order:
        above[i] = set().union(*({d} | above[d] for d in nodes[i]["deps"]))
        for f in dict.fromkeys(os.path.normpath(f) for f in nodes[i]["files"]):
            # Every earlier writer j comes first in topological order, so only i can reach j.
            out += [f"file overlap: {f} written by {j} and {i}" for j in writers.get(f, []) if j not in above[i]]
            writers.setdefault(f, []).append(i)
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
    if cmd == "retry":
        bad = [i for i in ids if i not in nodes or nodes[i]["state"] not in ("failed", "done")]
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
    bad = [i for i in ids if i not in nodes or nodes[i]["state"] != want]
    if bad:
        return [f"cannot {cmd} {' '.join(bad)}: state is not {want}"], ""
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

def normalize(nodes):
    for i, n in nodes.items():
        for key in ("deps", "files", "resources"):
            value = n.setdefault(key, [])
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise TypeError(f"node {i}: {key} is not a list of strings")
        state = n.setdefault("state", "todo")
        if state not in STATES:
            raise TypeError(f"node {i}: bad state {state!r}")
    return nodes

def selftest():
    def ok(cond, msg):
        if not cond:
            raise RuntimeError(f"selftest: {msg}")
    me = os.path.abspath(__file__)
    with tempfile.TemporaryDirectory(prefix="dag-selftest-") as tmp:
        graph = os.path.join(tmp, "graph.json")
        nodes = normalize
        files = lambda pairs: normalize({i: {"files": f} for i, f in pairs.items()})
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
        for g2, args, frag in [({"a": {"deps": ["b"]}, "b": {}}, ("start", "a"), "not ready"),
                               ({"a": {"resources": ["db"]}, "b": {"resources": ["db"]}}, ("start", "a", "b"), "not ready"),
                               ({"a": {}, "b": {"deps": ["a"], "state": "running"}}, ("check",), "b is running, but a is todo"),
                               ({"a": {"state": "weird"}}, ("check",), "bad state"),
                               ({"a": {"deps": [1]}}, ("check",), "strings"),
                               ({"a": {"files": ["/x"]}}, ("check",), "not repo-relative: a /x"),
                               ({"a": {}}, ("start", "a", "a"), "duplicate id")]:
            write(g2)
            before = open(graph, "rb").read()
            res = run(*args)
            ok(res.returncode == 1 and frag in res.stderr and res.stderr.count("\n") == 1
               and open(graph, "rb").read() == before, frag)
        write({"a": {}})
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
        write({"a": {}}, rograph)
        os.chmod(rodir, 0o555)
        if not os.access(rodir, os.W_OK):  # root bypasses the mode; the test is meaningless then
            try:
                res = run("start", "a", p=rograph)
                ok(res.returncode == 2 and res.stderr.count("\n") == 1 and "Traceback" not in res.stderr
                   and os.listdir(rodir) == ["graph.json"], "read-only dir: exit 2, one message, no temp file")
            finally:
                os.chmod(rodir, 0o755)
    print("selftest: PASS")
    return 0

def main(argv):
    cmd, path, rest = (argv + ["", ""])[1], (argv + ["", ""])[2], argv[3:]
    if cmd == "selftest" and not path:
        return selftest()
    limit = None
    if cmd == "ready" and len(rest) == 2 and rest[0] == "--max" and rest[1].isdigit():
        limit, rest = int(rest[1]), []
    if not path or cmd not in ("check", "ready", "show", *MOVES, "retry") \
            or bool(rest) != (cmd in MOVES or cmd == "retry"):
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
            if not errs and (cmd in MOVES or cmd == "retry"):
                errs, note = move(nodes, cmd, rest)
            if errs:
                print("\n".join(errs), file=sys.stderr)
                return 1
            if cmd in MOVES or cmd == "retry":
                fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump(graph, handle, indent=2)
                    os.replace(tmp, path)  # a crash never leaves half a graph
                finally:  # remove the temp on every failure path
                    os.path.exists(tmp) and os.unlink(tmp)
            print(note or "\n".join(ready(nodes, limit) if cmd == "ready" else show(nodes) if cmd == "show" else ["ok"]))
    except OSError as err:
        print(f"dag.py: {err}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
