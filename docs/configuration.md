# Configuration Guide

Email Nurse is an AI-powered email management tool for macOS Mail.app. This guide covers the configuration system, environment variables, and file locations.

## Table of Contents

- [Overview](#overview)
- [Configuration Directory](#configuration-directory)
- [Environment Variables](#environment-variables)
- [Configuration Files](#configuration-files)
  - [autopilot.yaml](#autopilotyaml) (Quick Rules, Inbox Aging)
- [Initial Setup](#initial-setup)
- [AI Provider Configuration](#ai-provider-configuration)
- [Processing Settings](#processing-settings)

## Overview

Email Nurse uses a combination of:
- **YAML configuration files** for rules and templates
- **Environment variables** for API keys and system settings
- **Command-line options** for runtime behavior

All configuration is designed to be version-controlled (except secrets) and portable across machines.

## Configuration Directory

Default location: `~/.config/email-nurse/`

Configuration directory structure:

```
~/.config/email-nurse/
├── rules.yaml           # Email processing rules
├── templates.yaml       # Reply templates
└── .env                 # Optional: environment variables
```

### Changing the Configuration Directory

Set via environment variable:

```bash
export EMAIL_NURSE_CONFIG_DIR=/path/to/config
```

The configuration directory will be created automatically on first run.

## Environment Variables

All environment variables use the `EMAIL_NURSE_` prefix.

### Core Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `EMAIL_NURSE_AI_PROVIDER` | string | `claude` | AI provider: `claude`, `openai`, or `ollama` |
| `EMAIL_NURSE_DRY_RUN` | bool | `true` | Default to dry-run mode (don't execute actions) |
| `EMAIL_NURSE_CONFIDENCE_THRESHOLD` | float | `0.7` | Minimum AI confidence (0.0-1.0) to auto-execute |
| `EMAIL_NURSE_LOG_LEVEL` | string | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### AI Provider Settings

#### Claude (Anthropic)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ANTHROPIC_API_KEY` | string | - | **Required**: Anthropic API key |
| `EMAIL_NURSE_CLAUDE_MODEL` | string | `claude-haiku-4-5-20251001` | Claude model to use |

Get your API key from: https://console.anthropic.com/

#### OpenAI

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENAI_API_KEY` | string | - | **Required**: OpenAI API key |
| `EMAIL_NURSE_OPENAI_MODEL` | string | `gpt-4o` | OpenAI model to use |

Get your API key from: https://platform.openai.com/

#### Ollama (Local Models)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `EMAIL_NURSE_OLLAMA_HOST` | string | `http://localhost:11434` | Ollama server URL |
| `EMAIL_NURSE_OLLAMA_MODEL` | string | `llama3.2` | Ollama model name |

Ollama must be installed and running. See: https://ollama.ai/

### Processing Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `EMAIL_NURSE_SYNC_INTERVAL_MINUTES` | int | `5` | Minutes between sync checks (≥1) |
| `EMAIL_NURSE_PROCESS_INTERVAL_MINUTES` | int | `1` | Minutes between processing runs (≥1) |
| `EMAIL_NURSE_WATCHER_INTERVAL` | int | `60` | Seconds between watcher processing cycles |
| `EMAIL_NURSE_WATCHER_CHECK_NEW_INTERVAL` | int | `300` | Seconds between checks for new messages |
| `EMAIL_NURSE_WATCHER_RUN_ON_START` | bool | `true` | Run immediate scan when watcher starts |

### Daily Reports

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `EMAIL_NURSE_REPORT_ENABLED` | bool | `true` | Enable daily activity reports |
| `EMAIL_NURSE_REPORT_RECIPIENT` | string | - | Email address to send reports to |
| `EMAIL_NURSE_REPORT_SENDER` | string | - | Sender email address for reports (must match account) |
| `EMAIL_NURSE_REPORT_TIME` | string | `21:00` | Time to send daily report (HH:MM, 24-hour format) |
| `EMAIL_NURSE_REPORT_ACCOUNT` | string | - | Mail.app account to send from (if using Mail.app) |

### SMTP Email Sending

Direct SMTP support allows sending emails without relying on Mail.app configuration. Particularly useful for Gmail and other providers.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `EMAIL_NURSE_SMTP_ENABLED` | bool | `false` | Use direct SMTP instead of Mail.app |
| `EMAIL_NURSE_SMTP_HOST` | string | - | SMTP server hostname (e.g., `smtp.gmail.com`) |
| `EMAIL_NURSE_SMTP_PORT` | int | `587` | SMTP port (587 for STARTTLS, 465 for SSL) |
| `EMAIL_NURSE_SMTP_USE_TLS` | bool | `true` | Use STARTTLS for connection |
| `EMAIL_NURSE_SMTP_USERNAME` | string | - | SMTP username (usually your email address) |
| `EMAIL_NURSE_SMTP_PASSWORD` | string | - | SMTP password or app-specific password |
| `EMAIL_NURSE_SMTP_FROM_ADDRESS` | string | - | From address (defaults to smtp_username if not set) |

**Gmail SMTP Setup:**

1. Generate an app-specific password at https://myaccount.google.com/apppasswords
2. Configure environment variables:

```bash
EMAIL_NURSE_SMTP_ENABLED=true
EMAIL_NURSE_SMTP_HOST=smtp.gmail.com
EMAIL_NURSE_SMTP_PORT=587
EMAIL_NURSE_SMTP_USE_TLS=true
EMAIL_NURSE_SMTP_USERNAME=you@gmail.com
EMAIL_NURSE_SMTP_PASSWORD=your_app_password
EMAIL_NURSE_SMTP_FROM_ADDRESS=you@gmail.com
```

**Note**: App-specific passwords are required for Gmail accounts with 2-Step Verification enabled.

### File Paths

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `EMAIL_NURSE_CONFIG_DIR` | path | `~/.config/email-nurse` | Configuration directory |
| `EMAIL_NURSE_RULES_FILE` | string | `rules.yaml` | Rules filename (relative to config_dir) |
| `EMAIL_NURSE_TEMPLATES_FILE` | string | `templates.yaml` | Templates filename (relative to config_dir) |
| `EMAIL_NURSE_LOG_FILE` | path | - | Optional log file path |

## Configuration Files

### rules.yaml

Defines email processing rules with conditions and actions.

**Location**: `~/.config/email-nurse/rules.yaml`

See [Rules Reference](./rules-reference.md) for complete documentation.

Basic structure:

```yaml
rules:
  - name: "Rule Name"
    description: "What this rule does"
    enabled: true
    priority: 100
    conditions:
      - type: sender_domain
        value: example.com
    action:
      action: move
      target_folder: "Example"
    stop_processing: true
```

### templates.yaml

Defines reply templates for auto-responding to emails.

**Location**: `~/.config/email-nurse/templates.yaml`

See [Templates Reference](./templates-reference.md) for complete documentation.

Basic structure:

```yaml
templates:
  template_name:
    description: "Template description"
    use_ai: true
    content: |
      Instructions for AI to generate reply...
```

### autopilot.yaml

Autopilot mode configuration for intelligent email processing.

**Location**: `~/.config/email-nurse/autopilot.yaml`

Basic structure:

```yaml
# Natural language instructions for the AI
instructions: |
  You are managing my email inbox. Follow these guidelines:
  1. Move newsletters to "Newsletters" folder
  2. Archive GitHub notifications
  3. Never delete emails from real people

# Mailboxes to process
mailboxes:
  - INBOX

# Accounts to process (empty = all enabled accounts)
accounts: []

# Central account for all move/archive operations (optional)
# When set, emails from other accounts move to folders on this account
main_account: iCloud

# Maximum age of emails to process
max_age_days: 30

# Sender/subject patterns to skip (substring match)
exclude_senders:
  - "noreply@yourbank.com"
exclude_subjects:
  - "Password Reset"
  - "2FA"

# Quick rules - processed BEFORE AI (instant, no API cost)
quick_rules:
  - name: "GitHub Notifications"
    match:
      sender_domain: ["github.com"]
    action: move
    folder: GitHub

  - name: "Marketing Spam"
    match:
      sender_contains: ["@marketing.example.com"]
    actions: [mark_read, delete]

# Inbox aging - auto-cleanup of stale emails
inbox_aging_enabled: false
inbox_stale_days: 30
needs_review_folder: "Needs Review"
needs_review_retention_days: 14

# Database cleanup (days to keep processed email records)
processed_retention_days: 90

# Per-account folder handling policies (optional)
account_settings:
  iCloud:
    folder_policy: auto_create    # auto-create folders via AppleScript
    notify_on_pending: false
  "Exchange Account":
    folder_policy: queue          # queue for manual creation
    notify_on_pending: true
```

#### Per-Account Folder Policies

Different email providers have different capabilities for folder creation. Exchange servers often have issues with AppleScript folder creation, while iCloud works well. The `account_settings` section lets you configure per-account behavior:

```yaml
account_settings:
  iCloud:
    folder_policy: auto_create
    notify_on_pending: false
  "My Exchange":
    folder_policy: queue
    notify_on_pending: true
```

**Folder policies:**
- `auto_create` - Create folders automatically via AppleScript (works well with iCloud)
- `queue` - Queue messages for manual folder creation (recommended for Exchange)
- `interactive` - Prompt user for each missing folder

**Workflow for queue policy:**
1. Autopilot detects a message needs folder "Projects/NewClient"
2. Since Exchange uses `queue` policy, message is saved to pending queue
3. At end of run, a macOS dialog shows folders needing creation
4. You manually create the folder in Outlook Web or Exchange Admin
5. Run `email-nurse autopilot retry-pending` to process queued messages

**CLI commands for pending folders:**
```bash
# List folders waiting for manual creation
email-nurse autopilot pending-folders

# Retry pending actions after creating folders
email-nurse autopilot retry-pending

# Retry only for specific account
email-nurse autopilot retry-pending --account "Exchange"
```

#### Quick Rules

Quick rules provide instant, deterministic matching before AI classification - saving API costs and processing time.

**Match conditions** (all specified conditions must match):
- `sender_contains`: List of substrings to match in sender
- `sender_domain`: List of email domains to match (e.g., `github.com`)
- `subject_contains`: List of substrings to match in subject

**Actions** (single or multiple):
- `delete` - Move to Trash
- `move` - Move to folder (requires `folder:` field)
- `archive` - Move to Archive
- `mark_read` - Mark as read
- `ignore` - Skip (don't pass to AI either)

```yaml
quick_rules:
  # Single action
  - name: "Archive newsletters"
    match:
      sender_contains: ["newsletter@"]
    action: archive

  # Multiple actions
  - name: "Spam cleanup"
    match:
      sender_domain: ["spamsite.com"]
    actions: [mark_read, delete]

  # Move to folder
  - name: "GitHub to folder"
    match:
      sender_domain: ["github.com"]
    action: move
    folder: GitHub
```

#### Inbox Aging

Automatically moves stale inbox emails to a review folder, then deletes them after a retention period.

```yaml
inbox_aging_enabled: true      # Enable the feature
inbox_stale_days: 30           # Days before email is "stale"
needs_review_folder: "Needs Review"  # Where stale emails go
needs_review_retention_days: 14      # Days in review before deletion
```

**Flow**: INBOX → (30 days) → Needs Review → (14 days) → Trash

## Initial Setup

### 1. Initialize Configuration

Run the initialization command to create the config directory and copy example files:

```bash
email-nurse init
```

This creates:
- `~/.config/email-nurse/` directory
- `rules.yaml` from example
- `templates.yaml` from example

### 2. Configure API Keys

Create a `.env` file in the config directory or set environment variables:

```bash
# For Claude
export ANTHROPIC_API_KEY=sk-ant-xxxxx

# For OpenAI
export OPENAI_API_KEY=sk-xxxxx

# For Ollama (no key needed, just ensure it's running)
ollama serve
```

### 3. Verify Configuration

Test your setup:

```bash
# List accounts
email-nurse accounts list

# List recent messages
email-nurse messages list --limit 5

# Test classification (dry run)
email-nurse messages classify --provider claude --dry-run
```

### 4. Customize Rules

Edit `~/.config/email-nurse/rules.yaml` to add your own rules:

```bash
# Edit with your preferred editor
$EDITOR ~/.config/email-nurse/rules.yaml

# Validate rules
email-nurse rules validate

# List configured rules
email-nurse rules list
```

### 5. Test Rules

Run in dry-run mode first to see what would happen:

```bash
# Process unread messages (dry run)
email-nurse process --dry-run

# Process all messages in inbox (dry run)
email-nurse process --mailbox Inbox --all --dry-run
```

### 6. Enable Auto-Processing

Once satisfied with rules, disable dry-run:

```bash
# Process for real
email-nurse process

# Or run as daemon
email-nurse daemon
```

## AI Provider Configuration

### Claude (Recommended)

Best for:
- Natural language understanding
- Complex classification logic
- High-quality reply generation

Setup:

```bash
export EMAIL_NURSE_AI_PROVIDER=claude
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

Available models:
- `claude-haiku-4-5-20251001` (default, fast and cost-effective)
- `claude-sonnet-4-5-20250929` (best balance of quality/speed)
- `claude-opus-4-5-20251101` (highest quality, slower)

### OpenAI

Best for:
- GPT-4 users
- Existing OpenAI workflows

Setup:

```bash
export EMAIL_NURSE_AI_PROVIDER=openai
export OPENAI_API_KEY=sk-xxxxx
```

Available models:
- `gpt-4o` (default, recommended)
- `gpt-4-turbo`
- `gpt-3.5-turbo` (faster, cheaper)

### Ollama (Local)

Best for:
- Privacy-conscious users
- No internet connection
- Free (no API costs)

Setup:

```bash
# Install Ollama
brew install ollama

# Pull a model
ollama pull llama3.2

# Start server
ollama serve

# Configure Email Nurse
export EMAIL_NURSE_AI_PROVIDER=ollama
export EMAIL_NURSE_OLLAMA_MODEL=llama3.2
```

Available models:
- `llama3.2` (default, 3B parameters)
- `llama3.1` (larger, better quality)
- `mistral` (fast, good quality)
- `phi3` (small, efficient)

### Switching Providers

You can switch providers at runtime:

```bash
# Use Claude
email-nurse process --provider claude

# Use OpenAI
email-nurse process --provider openai

# Use Ollama
email-nurse process --provider ollama
```

## Processing Settings

### Confidence Threshold

Controls how confident the AI must be before auto-executing an action:

```bash
# Conservative: only execute when very confident
export EMAIL_NURSE_CONFIDENCE_THRESHOLD=0.9

# Moderate: default
export EMAIL_NURSE_CONFIDENCE_THRESHOLD=0.7

# Aggressive: execute even with low confidence
export EMAIL_NURSE_CONFIDENCE_THRESHOLD=0.5
```

If confidence is below threshold, the email is left unprocessed (or flagged for manual review).

### Dry Run Mode

Always test new rules in dry-run mode first:

```bash
# Set default to dry-run
export EMAIL_NURSE_DRY_RUN=true

# Override at runtime
email-nurse process --no-dry-run
```

### Sync and Processing Intervals

For daemon mode, control how often Email Nurse checks for new messages:

```bash
# Check for new messages every 5 minutes
export EMAIL_NURSE_SYNC_INTERVAL_MINUTES=5

# Process messages every 1 minute
export EMAIL_NURSE_PROCESS_INTERVAL_MINUTES=1
```

## Daily Activity Reports

Email Nurse can automatically send daily HTML reports summarizing all email processing activity.

### Features

- **Beautiful HTML emails** with tables, color-coded entries, and responsive design
- **Summary statistics** showing total processed, actions taken, and error counts
- **Breakdown by folder** and **breakdown by account**
- **Detailed activity log** with timestamps, senders, subjects, and confidence scores
- **Automatic scheduling** via macOS LaunchAgent

### Configuration

Configure daily reports in your `.env` file:

```bash
# Enable reports and set recipient
EMAIL_NURSE_REPORT_ENABLED=true
EMAIL_NURSE_REPORT_RECIPIENT=you@example.com
EMAIL_NURSE_REPORT_TIME=21:00  # 9 PM

# Option 1: Use Mail.app (requires proper Mail.app setup)
EMAIL_NURSE_REPORT_ACCOUNT=iCloud
EMAIL_NURSE_REPORT_SENDER=you@icloud.com

# Option 2: Use SMTP (recommended - more reliable)
EMAIL_NURSE_SMTP_ENABLED=true
EMAIL_NURSE_SMTP_HOST=smtp.gmail.com
EMAIL_NURSE_SMTP_PORT=587
EMAIL_NURSE_SMTP_USERNAME=you@gmail.com
EMAIL_NURSE_SMTP_PASSWORD=your_app_password
EMAIL_NURSE_SMTP_FROM_ADDRESS=you@gmail.com
```

### Manual Report Generation

Generate and send a report manually:

```bash
# Send report for today
email-nurse autopilot report

# Send report for specific date
email-nurse autopilot report --date 2024-01-15

# Preview report without sending
email-nurse autopilot report --preview

# Send to different recipient
email-nurse autopilot report --to other@example.com
```

### Scheduled Reports with LaunchAgent

Set up automatic daily reports using macOS LaunchAgent:

1. **Create the LaunchAgent plist** at `~/Library/LaunchAgents/com.bss.email-nurse-report.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bss.email-nurse-report</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/email-nurse-report.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>21</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/email-nurse-report.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/email-nurse-report-error.log</string>
</dict>
</plist>
```

2. **Create the launcher script** at `/path/to/email-nurse-report.sh`:

```bash
#!/bin/bash
set -e

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Load environment from .env file
if [ -f "$HOME/.config/email-nurse/.env" ]; then
    set -a
    source "$HOME/.config/email-nurse/.env"
    set +a
fi

# Activate virtual environment
cd /path/to/email-nurse
source .venv/bin/activate

# Run report
uv run email-nurse autopilot report
```

3. **Load the LaunchAgent**:

```bash
# Make script executable
chmod +x /path/to/email-nurse-report.sh

# Load LaunchAgent
launchctl load ~/Library/LaunchAgents/com.bss.email-nurse-report.plist

# Verify it's loaded
launchctl list | grep email-nurse-report
```

4. **Test the setup**:

```bash
# Trigger immediately for testing
launchctl start com.bss.email-nurse-report

# Check logs
tail -f /tmp/email-nurse-report.log
```

### Report Contents

Each report includes:

1. **Header** - Date and branding
2. **Summary Section** - Total emails processed, breakdown by action type, error count
3. **By Folder** - Table showing email count per destination folder
4. **By Account** - Table showing email count per Mail.app account
5. **Detailed Activity Log** - Timestamped entries for each processed email with:
   - Time processed
   - Action taken (MOVE, ARCHIVE, DELETE, etc.)
   - Sender
   - Subject (truncated if long)
   - AI confidence score (if applicable)

### Troubleshooting Reports

**Report not sending:**

1. Check LaunchAgent is loaded: `launchctl list | grep email-nurse-report`
2. Check logs: `cat /tmp/email-nurse-report-error.log`
3. Test manually: `email-nurse autopilot report`
4. Verify SMTP credentials if using Gmail

**Mail.app authentication issues:**

If using Mail.app and emails fail to send, consider switching to SMTP:

```bash
# Disable Mail.app, enable SMTP
EMAIL_NURSE_SMTP_ENABLED=true
EMAIL_NURSE_SMTP_HOST=smtp.gmail.com
EMAIL_NURSE_SMTP_USERNAME=you@gmail.com
EMAIL_NURSE_SMTP_PASSWORD=your_app_password
```

**Empty reports:**

Reports show "No activity" if no emails were processed that day. This is normal if autopilot didn't run or no emails matched rules.

## Continuous Monitoring (Watcher Mode)

Run email-nurse continuously in the background with automatic processing:

```bash
# Start watcher (runs indefinitely)
email-nurse autopilot watch

# Configure intervals via environment variables
EMAIL_NURSE_WATCHER_INTERVAL=60           # Process every 60 seconds
EMAIL_NURSE_WATCHER_CHECK_NEW_INTERVAL=300  # Check for new messages every 5 minutes
EMAIL_NURSE_WATCHER_RUN_ON_START=true      # Run immediately on start
```

### Watcher LaunchAgent

Set up watcher as a LaunchAgent for automatic startup:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bss.email-nurse-watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/launch-autopilot.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/email-nurse-watcher.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/email-nurse-watcher-error.log</string>
</dict>
</plist>
```

## Best Practices

### 1. Start with Dry Run

Always test new configurations in dry-run mode:

```yaml
# .env
EMAIL_NURSE_DRY_RUN=true
```

### 2. Use Version Control

Track your configuration files (but not API keys):

```bash
cd ~/.config/email-nurse
git init
echo ".env" >> .gitignore
git add rules.yaml templates.yaml
git commit -m "Initial email-nurse configuration"
```

### 3. Incremental Rules

Start with simple, specific rules and add complexity gradually:

```yaml
# Start here: simple, safe rule
- name: "Archive Newsletters"
  conditions:
    - type: sender_domain
      value: newsletter.example.com
  action:
    action: archive

# Add later: more complex, AI-powered rules
- name: "AI Classification"
  use_ai: true
  # ...
```

### 4. Monitor Logs

Enable detailed logging during initial setup:

```bash
export EMAIL_NURSE_LOG_LEVEL=DEBUG
export EMAIL_NURSE_LOG_FILE=~/.config/email-nurse/email-nurse.log

# Tail logs in real-time
tail -f ~/.config/email-nurse/email-nurse.log
```

#### Log Viewer Utility

For scheduled/launchd runs, use the interactive log viewer:

```bash
./log-viewer.sh
```

This provides a menu to tail the main log, error log, or both simultaneously. Press `Ctrl+C` while viewing to return to the menu.

#### Log File Locations

Email Nurse uses per-account logging with automatic rotation:

```
~/Library/Logs/
├── email-nurse-error.log      # All errors (from all accounts)
├── email-nurse-iCloud.log     # Activity for iCloud account
├── email-nurse-CSquare.log    # Activity for CSquare account
└── email-nurse-{account}.log  # One log per account
```

**Log rotation:**
- Each log file rotates at 10 MB (configurable)
- Up to 5 backup files are kept (e.g., `email-nurse-iCloud.log.1`)
- Errors from any account are duplicated to `email-nurse-error.log` with `[account]` prefix

**Environment variables for logging:**

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_NURSE_LOG_DIR` | `~/Library/Logs` | Directory for log files |
| `EMAIL_NURSE_LOG_ROTATION_SIZE_MB` | `10` | Max log file size before rotation |
| `EMAIL_NURSE_LOG_BACKUP_COUNT` | `5` | Number of rotated backups to keep |

### 5. Test with Specific Mailboxes

Test on a subset of emails first:

```bash
# Process only a test folder
email-nurse process --mailbox "Test Folder" --dry-run

# Process single account
email-nurse process --account "work@example.com" --dry-run
```

### 6. Backup Before Changes

Backup configuration before making major changes:

```bash
cp ~/.config/email-nurse/rules.yaml ~/.config/email-nurse/rules.yaml.backup
```

### 7. Use Rule Priority

Organize rules by priority to control execution order:

```yaml
rules:
  # High priority: specific, important rules
  - name: "VIP Sender"
    priority: 10
    # ...

  # Medium priority: general categorization
  - name: "GitHub Notifications"
    priority: 50
    # ...

  # Low priority: catch-all rules
  - name: "AI Classification"
    priority: 999
    # ...
```

## Troubleshooting

### Configuration Not Found

```
Error: Configuration file not found
```

**Solution**: Run `email-nurse init` to create default configuration.

### API Key Issues

```
Error: Invalid API key
```

**Solution**: Verify your API key is set correctly:

```bash
echo $ANTHROPIC_API_KEY  # Should print your key
echo $OPENAI_API_KEY
```

### Mail.app Connection Issues

```
Error: Cannot connect to Mail.app
```

**Solution**:
1. Ensure Mail.app is running
2. Grant Terminal/iTerm2 automation permissions:
   - System Settings → Privacy & Security → Automation
   - Enable Terminal to control Mail

### Rules Not Working

```
No emails matched
```

**Solution**:
1. Validate rules: `email-nurse rules validate`
2. Check rule conditions match your emails
3. Enable debug logging: `EMAIL_NURSE_LOG_LEVEL=DEBUG`
4. Review rule priority and stop_processing settings

### Ollama Connection Failed

```
Error: Cannot connect to Ollama server
```

**Solution**:
1. Ensure Ollama is running: `ollama serve`
2. Verify host: `curl http://localhost:11434/api/tags`
3. Check firewall settings

## Next Steps

- [Rules Reference](./rules-reference.md) - Complete rules.yaml documentation
- [Templates Reference](./templates-reference.md) - Complete templates.yaml documentation
- [CLI Reference](./cli-reference.md) - Command-line interface guide (coming soon)
- [API Documentation](./api-reference.md) - Python API reference (coming soon)
