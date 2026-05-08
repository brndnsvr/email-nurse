# launchd Examples

Sanitized LaunchAgent plist templates for running email-nurse on macOS.

The supported install path is `scripts/install.sh`, which generates the
plists for you. These files are reference templates if you'd rather
install manually or adapt them.

## Files

| Plist | Purpose |
|-------|---------|
| `com.email-nurse.plist` | Scheduled autopilot, every 5 minutes |
| `com.email-nurse-digest.plist` | Daily HTML digest at 21:00 |
| `com.email-nurse-mail-restart.plist` | Mail.app restart helper, daily 04:00 |
| `com.email-nurse-backup.plist` | Daily autopilot.yaml backup at 03:00 |
| `com.email-nurse-watcher.plist` | Optional real-time watcher (off by default) |

## Manual install

`launchd` does not expand `$HOME` inside plists. Substitute your real
home directory before loading:

```bash
PLIST=com.email-nurse.plist
cp examples/launchd/$PLIST ~/Library/LaunchAgents/
sed -i '' "s|HOME_DIR|$HOME|g" ~/Library/LaunchAgents/$PLIST
launchctl load ~/Library/LaunchAgents/$PLIST
```

## Notes

- Labels use the `com.email-nurse[-suffix]` namespace. Pick something
  else if you have other agents already in that namespace.
- Logs land in `~/Library/Logs/`.
- The watcher is intentionally not loaded by `install.sh`; the
  every-5-minute scheduled run is usually enough.
