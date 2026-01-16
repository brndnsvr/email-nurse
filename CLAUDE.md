# email-nurse Project Instructions

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
