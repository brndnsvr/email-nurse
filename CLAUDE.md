# email-nurse Project Instructions

## Config File Sync Requirement

When editing config files, always sync between the repo and production locations.

| Config File | Repo Location | Production Location |
|-------------|---------------|---------------------|
| autopilot.yaml | `/Users/bss/code/email-nurse/deploy/config/autopilot.yaml` | `~/.config/email-nurse/autopilot.yaml` |
| rules.yaml | `/Users/bss/code/email-nurse/deploy/config/rules.yaml` | `~/.config/email-nurse/rules.yaml` |
| templates.yaml | `/Users/bss/code/email-nurse/deploy/config/templates.yaml` | `~/.config/email-nurse/templates.yaml` |

After editing any config in the repo, copy to production:
```bash
cp /Users/bss/code/email-nurse/deploy/config/<file> ~/.config/email-nurse/<file>
```

The running launchd services read from `~/.config/email-nurse/` and will pick up changes on the next run (no restart required).
