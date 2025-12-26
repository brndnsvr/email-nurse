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
| `EMAIL_NURSE_CLAUDE_MODEL` | string | `claude-sonnet-4-20250514` | Claude model to use |

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
- `claude-sonnet-4-20250514` (default, best balance)
- `claude-opus-4-20250514` (highest quality, slower)
- `claude-haiku-3-20240307` (fastest, cheaper)

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

Log files location (when using launchd):
- Main log: `~/Library/Logs/email-nurse.log`
- Error log: `~/Library/Logs/email-nurse-error.log`

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
