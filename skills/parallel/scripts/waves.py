#!/usr/bin/env python3
"""Turn a parallel-skill plan into wave groups (a plan view), a critical path and tier hints.

Usage: waves.py plan.json | waves.py --selftest

plan.json: {"units": [{"name": str, "files": [str, ...], "depends": [name, ...], "cost": number}, ...]}
`depends` defaults to [], `cost` to 1.

Exit codes: 0 plan accepted; 2 dependency cycle; 3 file overlap; 4 bad input.
Stdlib only, python3 >= 3.9.
"""

import json
import sys
from graphlib import TopologicalSorter

CYCLE, OVERLAP, BAD_INPUT = 2, 3, 4


class PlanError(Exception):
    """A rejected plan; `code` is the process exit code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def parse_units(data):
    """Validate raw JSON; return (costs, files, depends, order)."""
    units = data.get("units") if isinstance(data, dict) else None
    if not isinstance(units, list):
        raise PlanError(BAD_INPUT, "bad input: expected an object with a 'units' list")
    costs, files, depends, order = {}, {}, {}, []
    for index, unit in enumerate(units):
        if not isinstance(unit, dict) or not isinstance(unit.get("name"), str):
            raise PlanError(BAD_INPUT, f"bad input: unit {index} has no string 'name'")
        name = unit["name"]
        if name in costs:
            raise PlanError(BAD_INPUT, f"bad input: duplicate unit name '{name}'")
        if not isinstance(unit.get("files"), list):
            raise PlanError(BAD_INPUT, f"bad input: unit '{name}' has no 'files' list")
        costs[name] = unit.get("cost", 1)
        files[name] = unit["files"]
        depends[name] = unit.get("depends", [])
        order.append(name)
    for name in order:
        for dep in depends[name]:
            if dep not in costs:
                raise PlanError(
                    BAD_INPUT, f"bad input: '{name}' depends on unknown name '{dep}'"
                )
    return costs, files, depends, order


def check_overlap(files):
    """Reject a file path owned by more than one unit; explicit depends is no excuse."""
    owners = {}
    for name, paths in files.items():
        for path in set(paths):
            owners.setdefault(path, []).append(name)
    shared = {path: units for path, units in owners.items() if len(units) > 1}
    if shared:
        detail = "\n".join(
            f"overlap: '{path}' in units: {', '.join(sorted(units))}"
            for path, units in sorted(shared.items())
        )
        raise PlanError(OVERLAP, detail)


def find_cycle(depends):
    """DFS with a path stack; return one witness cycle [a, ..., a] or None."""
    state = {}  # name -> True once fully explored; absent = unvisited
    stack = []

    def visit(node):
        state[node] = False  # on the current path
        stack.append(node)
        for dep in depends[node]:
            if state.get(dep) is False:
                return stack[stack.index(dep) :] + [dep]
            if dep not in state:
                cycle = visit(dep)
                if cycle:
                    return cycle
        stack.pop()
        state[node] = True
        return None

    for node in depends:
        if node not in state:
            cycle = visit(node)
            if cycle:
                return cycle
    return None


def compute_waves(depends):
    """Group units into waves by dependency depth; a plan view, not a dispatch barrier."""
    sorter = TopologicalSorter(depends)
    sorter.prepare()
    waves = []
    while sorter.is_active():
        wave = sorted(sorter.get_ready())
        waves.append(wave)
        sorter.done(*wave)
    return waves


def critical_path(costs, depends, order):
    """Longest path by summed cost. Ties keep the earliest-defined unit; max() picks the
    first maximal item, so scanning `depends` lists and `order` in declaration order decides."""
    if not order:
        return [], 0
    dist, parent = {}, {}
    for name in TopologicalSorter(depends).static_order():
        parent[name] = max(depends[name], key=lambda dep: dist[dep], default=None)
        dist[name] = costs[name] + (dist[parent[name]] if parent[name] is not None else 0)
    end = max(order, key=lambda name: dist[name])
    path = []
    while end is not None:
        path.append(end)
        end = parent[end]
    path.reverse()
    return path, dist[path[-1]]


def analyze(data):
    """Return (exit_code, message); exit 0 carries the result dict instead of a message."""
    try:
        costs, files, depends, order = parse_units(data)
        check_overlap(files)
    except PlanError as err:
        return err.code, str(err)
    cycle = find_cycle(depends)
    if cycle:
        return CYCLE, f"cycle: {' -> '.join(cycle)}"
    waves = compute_waves(depends)
    path, total = critical_path(costs, depends, order)
    return 0, {"waves": waves, "path": path, "cost": total, "order": order}


def render(result):
    critical = set(result["path"])
    lines = ["waves:"]
    for index, wave in enumerate(result["waves"]):
        lines.append(f"wave {index}: {' '.join(wave)}")
    lines.append(f"critical path (cost {result['cost']}): {' -> '.join(result['path'])}")
    for name in result["order"]:
        lines.append(f"{name} ({'critical' if name in critical else 'slack'})")
    return "\n".join(lines)


def _selftest_cases():
    diamond = {
        "units": [
            {"name": "a", "files": ["a"]},
            {"name": "b", "files": ["b"], "depends": ["a"]},
            {"name": "c", "files": ["c"], "depends": ["a"]},
            {"name": "d", "files": ["d"], "depends": ["b", "c"]},
        ]
    }
    unequal = {
        "units": [
            {"name": "a", "files": ["a"], "cost": 5},
            {"name": "b", "files": ["b"], "depends": ["a"]},
            {"name": "c", "files": ["c"], "depends": ["a"], "cost": 1},
        ]
    }
    cyclic = {
        "units": [
            {"name": "a", "files": ["a"], "depends": ["b"]},
            {"name": "b", "files": ["b"], "depends": ["a"]},
        ]
    }
    overlap = {
        "units": [
            {"name": "a", "files": ["shared", "a-only"]},
            {"name": "b", "files": ["shared"]},
        ]
    }
    unknown = {"units": [{"name": "a", "files": ["a"], "depends": ["ghost"]}]}

    def diamond_case():
        code, result = analyze(diamond)
        assert code == 0, f"exit {code}: {result}"
        assert result["waves"] == [["a"], ["b", "c"], ["d"]], result["waves"]
        assert len(result["path"]) == 3 and result["cost"] == 3, result

    def unequal_case():
        # Both branches sum to 6 (a=5 + default 1); the earliest-defined unit, b, wins the tie.
        code, result = analyze(unequal)
        assert code == 0, f"exit {code}: {result}"
        assert "b" in result["path"], result["path"]

    def cycle_case():
        code, message = analyze(cyclic)
        assert code == CYCLE, f"exit {code}: {message}"
        assert "a -> b -> a" in message, message

    def overlap_case():
        code, message = analyze(overlap)
        assert code == OVERLAP, f"exit {code}: {message}"
        assert "'shared' in units: a, b" in message, message

    def unknown_case():
        code, message = analyze(unknown)
        assert code == BAD_INPUT, f"exit {code}: {message}"
        assert "ghost" in message, message

    return [diamond_case, unequal_case, cycle_case, overlap_case, unknown_case]


def selftest():
    cases = _selftest_cases()
    failures = 0
    for case in cases:
        try:
            case()
        except AssertionError as err:
            failures += 1
            print(f"selftest {case.__name__}: FAIL ({err})")
    total = len(cases)
    status = "PASS" if not failures else "FAIL"
    print(f"selftest: {total - failures}/{total} {status}")
    return 0 if not failures else 1


def main(argv):
    if len(argv) != 2:
        print(f"usage: {argv[0]} plan.json | --selftest", file=sys.stderr)
        return BAD_INPUT
    if argv[1] == "--selftest":
        return selftest()
    try:
        with open(argv[1], encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as err:
        print(f"bad input: {argv[1]}: {err}", file=sys.stderr)
        return BAD_INPUT
    code, payload = analyze(data)
    if code:
        print(payload, file=sys.stderr)
        return code
    print(render(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
