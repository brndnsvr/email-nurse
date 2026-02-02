# Task Tracking System

Lightweight markdown-based task tracking for email-nurse.

## Files

- `TASKS.md` - Main kanban board with all active tasks
- `archive/` - Monthly archives of completed tasks (e.g., `2025-02.md`)

## Task Format

### Full Task

```markdown
### T-XXX: Title

> **Created:** YYYY-MM-DD | **Updated:** YYYY-MM-DD
> **Labels:** infra, automation, bug, feature, refactor, docs

Description here.

- [ ] Subtask one
- [x] Subtask two (completed)

#### Log
- YYYY-MM-DD: Note about progress, decisions, blockers
```

### Minimal Task (for small items)

```markdown
### T-XXX: Title

> **Created:** YYYY-MM-DD

One-liner description.
```

### Blocked Task

```markdown
### T-XXX: Title

> **Created:** YYYY-MM-DD | **Updated:** YYYY-MM-DD
> **Blocked-by:** T-YYY or "waiting on vendor response"

Description.
```

## Lanes

| Lane | Purpose | WIP Limit |
|------|---------|-----------|
| **Inbox** | Quick captures, triage regularly | None |
| **Inflight** | Active work | ~3 tasks |
| **Next** | Ready to start or blocked | None |
| **Backlog** | Prioritized future work (top = highest) | None |
| **Done** | Completed tasks | Archive monthly |

## Labels

| Label | Description |
|-------|-------------|
| `bug` | Something broken |
| `feature` | New functionality |
| `refactor` | Code improvement without behavior change |
| `docs` | Documentation updates |
| `infra` | Infrastructure, CI/CD, deployment |
| `automation` | Automation improvements |

## Conventions

- **Task IDs**: Sequential `T-001`, `T-002`, etc. Never renumber existing IDs.
- **Next ID**: Tracked at the top of TASKS.md. Increment when creating new tasks.
- **Descriptions**: Concise but actionable.
- **Subtasks**: Use checkboxes for multi-step work.
- **Logs**: Capture decisions, blockers, and context for future reference.
- **Backlog order**: Priority (top = highest).
- **Blocked tasks**: Stay in Next with `Blocked-by` field.
- **Small fixes**: Items under ~15 minutes with obvious scope don't need tasks.
- **Archiving**: Move Done section to `archive/YYYY-MM.md` monthly or when it gets long.

## Git Integration

- Reference task IDs in commits: `T-XXX: description`
- Branch naming: `t-XXX-short-description`
