# email-nurse Project Instructions

## Dev + Prod Parity

This repo powers the user's daily driver email triage AI agent. Generic questions ("are we...", "is the app...", "do we have...") **and** change requests ("add a quick-rule for...", "update the system prompt to...") apply to **both**:
1. **Dev repo** — the source code in this directory
2. **Production** — the installed binaries and configs at `~/.config/email-nurse/` that run via launchd

When answering questions, check both locations as needed. When making changes (adding quick-rules, modifying prompts, updating configs, etc.), ensure they propagate to production per the sync policies below.

## Config File Sync Requirement

When editing config files, always sync between the repo and production locations.

| Config File | Repo Location | Production Location |
|-------------|---------------|---------------------|
| autopilot.yaml | `/Users/bss/code/email-nurse/deploy/config/autopilot.yaml` | `~/.config/email-nurse/autopilot.yaml` |
| rules.yaml | `/Users/bss/code/email-nurse/deploy/config/rules.yaml` | `~/.config/email-nurse/rules.yaml` |
| templates.yaml | `/Users/bss/code/email-nurse/deploy/config/templates.yaml` | `~/.config/email-nurse/templates.yaml` |

### Sync Policy: Merge First

Before editing configs, always check for differences between repo and production:
```bash
diff /Users/bss/code/email-nurse/deploy/config/<file> ~/.config/email-nurse/<file>
```

**If files differ:**
1. Attempt to merge changes from both locations
2. If merge is straightforward (non-conflicting changes), apply the merge
3. If merge conflicts exist or intent is unclear, **ASK THE USER** before proceeding

**After editing any config in the repo, copy to production:**
```bash
cp /Users/bss/code/email-nurse/deploy/config/<file> ~/.config/email-nurse/<file>
```

The running launchd services read from `~/.config/email-nurse/` and will pick up changes on the next run (no restart required).

## Production Runtime

**Active launchd services:**
- `com.bss.email-nurse` — Scheduled autopilot, runs every **5 minutes** (`StartInterval: 300`)
- `com.bss.email-nurse-digest` — Daily digest email

**Disabled (do not enable):**
- `com.bss.email-nurse-watcher` — Real-time polling watcher (disabled intentionally)

The watcher is disabled by design. Only the 5-minute scheduled autopilot should run.
