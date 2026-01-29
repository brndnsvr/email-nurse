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

**Disabled (do not enable):**
- `com.bss.email-nurse-watcher` — Real-time polling watcher (disabled intentionally)

The watcher is disabled by design. Only the 5-minute scheduled autopilot should run.
