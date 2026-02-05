# email-nurse Project Instructions

## Dev + Prod Parity

This repo powers the user's daily driver email triage AI agent. Generic questions ("are we...", "is the app...", "do we have...") **and** change requests ("add a quick-rule for...", "update the system prompt to...") apply to **both**:
1. **Dev repo** — the source code in this directory
2. **Production** — the installed binaries and configs at `~/.config/email-nurse/` that run via launchd

When answering questions, check both locations as needed. When making changes (adding quick-rules, modifying prompts, updating configs, etc.), ensure they propagate to production per the sync policies below.

## Config Files

**Production configs** live at `~/.config/email-nurse/` and are read by the launchd services. Changes take effect on the next run (no restart required).

| Config File | Location | Notes |
|-------------|----------|-------|
| autopilot.yaml | `~/.config/email-nurse/autopilot.yaml` | Production only (example in repo at `deploy/config/autopilot.example.yaml`) |
| rules.yaml | `~/.config/email-nurse/rules.yaml` | Sync with `deploy/config/rules.yaml` if needed |
| templates.yaml | `~/.config/email-nurse/templates.yaml` | Sync with `deploy/config/templates.yaml` if needed |

**autopilot.yaml** contains personal quick-rules and AI instructions - edit directly in production, no repo sync needed.

## Production Runtime

**Active launchd services:**
- `com.bss.email-nurse` — Scheduled autopilot, runs every **5 minutes** (`StartInterval: 300`)
- `com.bss.email-nurse-digest` — Daily digest email
- `com.bss.email-nurse-mail-restart` — Mail.app restart service, checks daily at 4am but only executes every 3 days

**Disabled (do not enable):**
- `com.bss.email-nurse-watcher` — Real-time polling watcher (disabled intentionally)

The watcher is disabled by design. Only the 5-minute scheduled autopilot should run.

## Project Task Tracking

This project uses a markdown-based task system in `.tasks/TASKS.md`.

**Quick Reference:**
- All tasks: `.tasks/TASKS.md`
- Task IDs: T-001, T-002, etc. (never renumber)
- Next ID: Top of TASKS.md

**Workflow:**
- Check Inflight section before starting work
- Create tasks for non-trivial work (>15 min or worth tracking)
- Move tasks between sections as work progresses
- Add log entries for decisions, blockers, or progress worth noting
- Update the Updated date when modifying a task
- Reference task IDs in commits: `T-XXX: description`
- Branch naming: `t-XXX-short-description`

**Labels:** bug, feature, refactor, docs, infra, automation

**Triage Inbox regularly** - move items to proper lanes or delete.
