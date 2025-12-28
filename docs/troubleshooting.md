# Troubleshooting Guide

This guide helps diagnose and fix common issues with Email Nurse.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [API Key Issues](#api-key-issues)
- [Model Errors](#model-errors)
- [Mail.app Issues](#mailapp-issues)
- [Processing Errors](#processing-errors)
- [Database Issues](#database-issues)
- [Log File Reference](#log-file-reference)

## Quick Diagnostics

### Check System Status

```bash
# Verify installation
email-nurse version

# List accounts (tests Mail.app connection)
email-nurse accounts list

# Check autopilot status
email-nurse autopilot status

# Run with maximum verbosity
email-nurse autopilot run --dry-run -vvv
```

### Verify API Key

```bash
# Test Claude API key directly
curl https://api.anthropic.com/v1/models \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01"
```

Expected output: JSON list of available models.

### Check Configuration

```bash
# View current .env
cat ~/.config/email-nurse/.env

# View autopilot config
cat ~/.config/email-nurse/autopilot.yaml
```

## API Key Issues

### Error: `authentication_error: invalid x-api-key`

**Symptoms:**
- All AI classifications fail
- ERROR entries in log for every email
- Quick rules still work (they don't use API)

**Causes:**
1. API key is expired or revoked
2. Key was copied incorrectly (extra whitespace, truncation)
3. Wrong environment variable name

**Solutions:**

1. **Get a new API key:**
   - Go to https://console.anthropic.com/settings/keys
   - Create a new key
   - Update `~/.config/email-nurse/.env`:
     ```bash
     EMAIL_NURSE_ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
     ```

2. **Check variable name:**
   The app looks for these (in order):
   - `EMAIL_NURSE_ANTHROPIC_API_KEY` (in .env with prefix)
   - `ANTHROPIC_API_KEY` (environment variable)

3. **Verify no extra characters:**
   ```bash
   # Check for trailing whitespace or newlines
   cat -A ~/.config/email-nurse/.env
   ```

### Error: `rate_limit_error`

**Symptoms:**
- Some classifications succeed, then failures
- Errors mention rate limits

**Solutions:**

1. **Increase delay between calls:**
   ```bash
   export EMAIL_NURSE_AUTOPILOT_RATE_LIMIT_DELAY=2.0
   ```

2. **Reduce batch size:**
   ```bash
   email-nurse autopilot run --limit 10
   ```

3. **Check Anthropic usage dashboard** for current limits.

## Model Errors

### Error: `model_not_found`

**Symptoms:**
- Error mentions invalid model name
- Classifications all fail

**Causes:**
- Model name is incorrect
- Model has been deprecated

**Solutions:**

1. **List available models:**
   ```bash
   curl https://api.anthropic.com/v1/models \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01"
   ```

2. **Use a valid model name:**
   ```bash
   # In ~/.config/email-nurse/.env
   EMAIL_NURSE_CLAUDE_MODEL=claude-haiku-4-5-20251001
   ```

3. **Current recommended models:**
   - `claude-haiku-4-5-20251001` (fast, cheap)
   - `claude-sonnet-4-5-20250929` (balanced)
   - `claude-opus-4-5-20251101` (highest quality)

### Slow Response Times

**Symptoms:**
- Classifications take 5+ seconds
- Timeouts on large batches

**Solutions:**

1. **Use a faster model:**
   ```bash
   EMAIL_NURSE_CLAUDE_MODEL=claude-haiku-4-5-20251001
   ```

2. **Reduce email content sent to AI:**
   Content is truncated at 4000 characters automatically.

3. **Use more quick rules:**
   Quick rules are instant (no API call).

## Mail.app Issues

### Error: `Cannot connect to Mail.app`

**Symptoms:**
- Account listing fails
- Message fetching fails
- Actions fail to execute

**Solutions:**

1. **Ensure Mail.app is running:**
   ```bash
   open -a "Mail"
   ```

2. **Grant automation permissions:**
   - System Settings → Privacy & Security → Automation
   - Find Terminal (or your terminal app)
   - Enable "Mail" checkbox

3. **Reset automation permissions:**
   ```bash
   tccutil reset AppleEvents
   ```
   Then run Email Nurse again and approve the permission prompt.

### Error: `AppleScript execution failed`

**Symptoms:**
- Specific actions fail (move, delete)
- Partial processing success

**Solutions:**

1. **Check folder names:**
   Folder names are case-sensitive and must exist:
   ```bash
   # List mailboxes for an account
   email-nurse messages list --account "iCloud" --mailbox "INBOX"
   ```

2. **Verify email still exists:**
   Emails may have been moved/deleted by another process.

3. **Check AppleScript directly:**
   ```bash
   osascript -e 'tell application "Mail" to get name of every account'
   ```

### Large Mailbox Timeouts

**Symptoms:**
- "AppleScript timed out after 180s" warnings
- Emails not being processed from accounts with large Inboxes (1000+ messages)
- Some accounts work fine, others fail

**Cause:**
Large mailboxes (e.g., Exchange accounts with 1000+ messages) can timeout during fetch because AppleScript must enumerate all messages.

**Solutions:**

1. **Archive old emails:**
   Reduce Inbox size by archiving emails older than 30-90 days.

2. **Process more frequently:**
   Smaller batches per run means fewer messages to enumerate.

3. **Enable `main_account` routing:**
   Route all emails to a central account with proper folder structure:
   ```yaml
   main_account: iCloud
   ```

### Folder Not Found

**Symptoms:**
- "Missing folder: FolderName" errors
- Actions queued instead of executed

**Solutions:**

1. **Use auto-create mode:**
   ```bash
   email-nurse autopilot run --auto-create
   ```

2. **Use interactive mode:**
   ```bash
   email-nurse autopilot run --interactive
   ```

3. **Create folder manually in Mail.app** before running.

## Processing Errors

### Emails Not Being Processed

**Symptoms:**
- "0 emails processed" in summary
- Emails appear unprocessed in Mail.app

**Causes:**
1. Emails already processed (in database)
2. Emails excluded by age or pattern
3. Wrong account/mailbox configuration

**Solutions:**

1. **Reset processed tracking:**
   ```bash
   # Clear all processed email records
   email-nurse autopilot reset --force

   # Clear only old records
   email-nurse autopilot reset --older-than 7
   ```

2. **Check exclusion patterns in `autopilot.yaml`:**
   ```yaml
   exclude_senders:
     - "security@"
   exclude_subjects:
     - "Password Reset"
   ```

3. **Verify account configuration:**
   ```yaml
   accounts:
     - iCloud
     - Gmail
   mailboxes:
     - INBOX
   ```

### Quick Rules Not Matching

**Symptoms:**
- Expected matches go to AI instead
- Rules appear correct but don't fire

**Debug steps:**

1. **Run with debug verbosity:**
   ```bash
   email-nurse autopilot run -vvv --dry-run
   ```

2. **Check match patterns:**
   ```yaml
   # Patterns are case-insensitive substrings
   match:
     sender_contains: ["newsletter@"]  # Matches "newsletter@example.com"
     sender_domain: ["github.com"]     # Matches "@github.com"
   ```

3. **Check rule order:**
   First matching rule wins. More specific rules should come first.

### AI Giving Wrong Classifications

**Symptoms:**
- Emails moved to wrong folders
- Unexpected actions taken

**Solutions:**

1. **Improve instructions in `autopilot.yaml`:**
   ```yaml
   instructions: |
     Be more specific:
     - Emails from linkedin.com → Social folder
     - NOT Career folder for LinkedIn jobs
   ```

2. **Add quick rules for known patterns:**
   Quick rules are deterministic and always correct.

3. **Adjust confidence threshold:**
   ```bash
   # Require higher confidence
   export EMAIL_NURSE_CONFIDENCE_THRESHOLD=0.9
   ```

4. **Review with dry-run:**
   ```bash
   email-nurse autopilot run --dry-run -vv
   ```

## Database Issues

### Database Locked

**Symptoms:**
- "database is locked" errors
- Concurrent access issues

**Solutions:**

1. **Ensure only one instance running:**
   ```bash
   pkill -f "email-nurse autopilot"
   ```

2. **Check for stale locks:**
   ```bash
   ls -la ~/.config/email-nurse/autopilot.db*
   # Remove -wal and -shm files if stale
   ```

### Database Corrupted

**Symptoms:**
- SQLite errors on every operation
- "malformed database" messages

**Solutions:**

1. **Backup and reset:**
   ```bash
   mv ~/.config/email-nurse/autopilot.db ~/.config/email-nurse/autopilot.db.bak
   # Database will be recreated on next run
   ```

2. **Try to recover:**
   ```bash
   sqlite3 ~/.config/email-nurse/autopilot.db ".recover" | sqlite3 autopilot-recovered.db
   ```

### Clear Mailbox Cache

**Symptoms:**
- Stale mailbox lists
- New folders not appearing

**Solutions:**

```bash
# Clear all cached mailbox lists
email-nurse autopilot clear-cache

# Clear for specific account
email-nurse autopilot clear-cache --account "iCloud"
```

## Log File Reference

### Log Locations

| Log Type | Location |
|----------|----------|
| LaunchAgent main | `~/Library/Logs/email-nurse.log` |
| LaunchAgent errors | `~/Library/Logs/email-nurse-error.log` |
| Manual runs | Console output |

### Using the Log Viewer

```bash
# Interactive log viewer
./log-viewer.sh
```

Options:
1. Tail main log
2. Tail error log
3. Tail both
4. Exit

### Log Entry Examples

**Successful processing:**
```
2025-12-27 10:32:20 - SUCCESS
Summary
  Emails fetched: 8
  Emails processed: 5
  Errors: 0
```

**Quick rule match:**
```
[RULE] MOVE (Career) LinkedIn Job Alerts <jobalerts@linkedin.com>
    "network engineer": Senior Network Engineer position
```

**AI classification:**
```
[AI] MOVE (Marketing) Newsletter <news@example.com>
    Weekly digest - Confidence: 0.92
```

**Error entry:**
```
ERROR Harper Auto Wash <harperautowash@support.rinsed.co>
    AI classification failed: authentication_error: invalid x-api-key
```

### Debug Mode

For maximum detail:

```bash
# Environment variable
export EMAIL_NURSE_LOG_LEVEL=DEBUG

# Or command line
email-nurse autopilot run -vvv
```

Debug output includes:
- Full email metadata
- API request/response details
- Rule matching traces
- Timing information

## Getting Help

### Collect Diagnostic Information

When reporting issues, include:

```bash
# Version
email-nurse version

# Configuration (redact API keys!)
cat ~/.config/email-nurse/autopilot.yaml

# Recent errors
tail -100 ~/Library/Logs/email-nurse-error.log

# System info
sw_vers
python3 --version
```

### Report Issues

File issues at: https://github.com/yourusername/email-nurse/issues

Include:
1. What you expected to happen
2. What actually happened
3. Steps to reproduce
4. Diagnostic information above

## Related Documentation

- [Configuration Guide](./configuration.md) - Settings and setup
- [AI Providers Guide](./ai-providers.md) - Provider configuration
- [Architecture Guide](./architecture.md) - System internals
