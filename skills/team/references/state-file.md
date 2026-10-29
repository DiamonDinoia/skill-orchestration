# State file template

The state file of one run uses this shape. The manager keeps it self-contained.

```markdown
### Goal
What, why, the expected end state.

### Deliverables
- [ ] D1: <statement>; check: <shell command, non-zero exit on failure>

### Dispatch preferences
- Engineers: dispatched | inline

### Integration
- Branch: team/integration
- Checkout: <path of the integration worktree>

### Pool
| Role | Specialty |
|------|-----------|

### Split
| # | Subproblem | Role | Scope | Check | Depends on | Status |
|---|------------|------|-------|-------|------------|--------|

### Rounds
| Round | Event | Accepted findings | Rejected findings |
|-------|-------|-------------------|-------------------|

### Verification
Build and test: <shell command, non-zero exit on failure>

### Notes
Decisions, escalation resolutions, review findings.
```
