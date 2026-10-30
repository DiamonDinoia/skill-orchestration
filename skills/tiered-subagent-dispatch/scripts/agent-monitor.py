#!/usr/bin/env python3
"""Print one status line per delegate_task transcript every 10 minutes.

Usage: agent-monitor.py [--help]

Logs idle > 20 min are STALLED. DONE lines print once.
Stops after 4 h; relaunch if work runs longer.
"""
import glob, os, sys, time

if "-h" in sys.argv or "--help" in sys.argv:
    print(__doc__)
    sys.exit(0)

LIVE = os.path.expanduser("~/.hermes/cache/delegation/live")
end = time.time() + 4 * 3600
seen_final = set()
while time.time() < end:
    now = time.time()
    lines = []
    for f in sorted(glob.glob(f"{LIVE}/*/task-*.log"), key=os.path.getmtime):
        age = (now - os.path.getmtime(f)) / 60
        if age > 240:
            continue
        rows = open(f, errors="replace").read().strip().splitlines()
        last = rows[-1][:160] if rows else ""
        name = f[len(LIVE) + 1:]
        if " final " in last:
            if name in seen_final:
                continue
            seen_final.add(name)
            state = "DONE"
        else:
            state = "STALLED" if age > 20 else "running"
        lines.append(f"{state:8} {age:5.0f}m {name}: {last}")
    print(time.strftime("%H:%M"), "\n".join(lines) or "no active agents", flush=True)
    sys.stdout.flush()
    time.sleep(600)
