# Waves

`scripts/waves.py` turns a plan into wave groups, a critical path and tier hints. Run it from this skill directory. The groups are a plan view only. Dispatch each unit when its own dependencies are done; do not wait for a whole group. The ready rule lives in skill `parallel`, SKILL.md.

Write `plan.json` as one object with a `units` list. Each unit carries `name`, `files`, optional `depends` and `cost` (intern 1, junior 2, senior 3, principal 4). `depends` defaults to `[]`, `cost` to 1.

```json
{"units": [{"name": "a", "files": ["x.py"]}, {"name": "b", "files": ["y.py"], "depends": ["a"], "cost": 3}]}
```

    python3 scripts/waves.py plan.json

Exit codes: 0 prints the waves and the critical path. Exit 1 means `--selftest` failed. Exit 2 means a dependency cycle. Exit 3 means a file overlap. Exit 4 means bad input. Exit 2 or 3: fix the split. Exit 4: fix `plan.json`. Exit 1: fix `waves.py`, the selftest failed.

The render marks each unit `(critical)` or `(slack)`.
