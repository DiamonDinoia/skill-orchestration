#!/usr/bin/env python3
"""Merge a PR once every pull_request-event workflow run on its head commit succeeded.

Usage: merge-when-green.py <owner/repo> <pr>   (run as terminal background=true, notify=true)

Push-event runs on the same commit get cancelled when the PR runs start, and
`gh pr checks` lists those as failures. Only pull_request runs on the head SHA count.
A cancelled PR run (runner cancel, timeout) gets its failed jobs rerun once.
Exits 0 after a squash merge, 1 on a failed run (no merge), 2 on timeout.
"""
import json
import subprocess
import sys
import time

if len(sys.argv) != 3 or any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__)
    sys.exit(0)
repo, pr = sys.argv[1], sys.argv[2]
OK = {"success", "skipped", "neutral"}
rerun = set()


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


head = json.loads(gh("pr", "view", "-R", repo, pr, "--json", "headRefOid,headRefName"))
for _ in range(240):  # 240 * 60 s = 4 h
    runs = json.loads(gh("run", "list", "-R", repo, "-b", head["headRefName"], "-L", "100",
                         "--json", "databaseId,workflowName,event,status,conclusion,headSha"))
    runs = [r for r in runs if r["headSha"] == head["headRefOid"] and r["event"] == "pull_request"]
    for r in runs:
        if r["status"] == "completed" and r["conclusion"] == "cancelled" and r["databaseId"] not in rerun:
            gh("run", "rerun", "-R", repo, str(r["databaseId"]), "--failed")
            rerun.add(r["databaseId"])
            r["status"] = "rerun"
    bad = [r["workflowName"] for r in runs if r["status"] == "completed" and r["conclusion"] not in OK]
    pending = [r["workflowName"] for r in runs if r["status"] != "completed"]
    print(time.strftime("%H:%M"), f"runs={len(runs)} pending={pending} bad={bad}", flush=True)
    if bad:
        sys.exit(1)
    if runs and not pending:
        gh("pr", "merge", "-R", repo, pr, "--squash", "--delete-branch")
        print("merged", flush=True)
        sys.exit(0)
    time.sleep(60)
sys.exit(2)
