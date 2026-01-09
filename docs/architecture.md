# Architecture Guide

This document describes the internal architecture of Email Nurse for developers and contributors.

## Project Structure

```
src/email_nurse/
├── __init__.py              # Package version
├── cli.py                   # Typer CLI commands (~1900 lines)
├── config.py                # Pydantic settings and YAML config loading
│
├── ai/                      # AI Provider Implementations
│   ├── base.py              # Abstract AIProvider interface
│   ├── claude.py            # Anthropic Claude implementation
│   ├── openai.py            # OpenAI GPT implementation
│   └── ollama.py            # Local Ollama implementation
│
├── applescript/             # AppleScript Execution Layer
│   ├── base.py              # AppleScript runner utility
│   └── errors.py            # AppleScript-specific exceptions
│
├── autopilot/               # Intelligent Email Processing
│   ├── config.py            # AutopilotConfig, QuickRule models
│   ├── engine.py            # AutopilotEngine (~1200 lines)
│   ├── models.py            # AutopilotDecision, ProcessResult
│   ├── reports.py           # Daily activity report generation
│   └── watcher.py           # Continuous monitoring mode
│
├── calendar/                # Calendar.app Integration
│   ├── calendars.py         # Calendar dataclass, get_calendars()
│   ├── events.py            # CalendarEvent dataclass, get_events()
│   └── actions.py           # create_event(), delete_event()
│
├── mail/                    # Mail.app Integration
│   ├── accounts.py          # Account discovery and sync
│   ├── actions.py           # Email actions (move, delete, flag)
│   ├── applescript.py       # Mail-specific AppleScript commands
│   └── messages.py          # EmailMessage model, fetching
│
├── reminders/               # Reminders.app Integration
│   ├── lists.py             # Reminder list management
│   ├── reminders.py         # Individual reminder operations
│   └── actions.py           # create_reminder(), complete_reminder()
│
├── rules/                   # Rule-Based Processing
│   ├── conditions.py        # Condition types and matching
│   └── engine.py            # RuleEngine evaluation
│
├── storage/                 # Persistence Layer
│   └── database.py          # SQLite database for autopilot state
│
└── templates/               # Reply Templates
    └── manager.py           # Template loading and rendering
```

## Module Responsibilities

### `cli.py` - Command Line Interface

Entry point for all user interactions. Uses Typer for CLI framework.

**Key command groups:**
- `accounts` - List and sync email accounts
- `messages` - View and classify messages
- `autopilot` - Run intelligent processing
- `reminders` - Apple Reminders integration
- `calendar` - Apple Calendar integration
- `rules` - Manage processing rules

### `config.py` - Configuration Management

Centralized settings using Pydantic v2 Settings.

**Configuration hierarchy (highest to lowest priority):**
1. Environment variables with `EMAIL_NURSE_` prefix
2. User config: `~/.config/email-nurse/.env`
3. Project `.env` file
4. Default values in Settings class

**Key settings:**
```python
Settings.anthropic_api_key   # API key for Claude
Settings.claude_model        # Default: claude-haiku-4-5-20251001
Settings.confidence_threshold # 0.7 default
Settings.autopilot_config_path # Path to autopilot.yaml
```

### `ai/` - AI Provider Layer

Abstract interface for AI classification with multiple implementations.

**Base interface (`ai/base.py`):**
```python
class AIProvider(ABC):
    async def classify_email(email, context) -> EmailClassification
    async def autopilot_classify(email, instructions) -> AutopilotDecision
    async def generate_reply(email, template, context) -> str
    async def is_available() -> bool
```

**Implementations:**
- `ClaudeProvider` - Uses Anthropic SDK, lazy-loads client
- `OpenAIProvider` - Uses OpenAI SDK
- `OllamaProvider` - HTTP client to local Ollama server

### `autopilot/` - Intelligent Processing Engine

The core email processing logic.

**Processing flow:**
```
1. AutopilotEngine.run()
   ├── Fetch unprocessed emails from Mail.app
   ├── For each email:
   │   ├── Check exclude patterns (skip security emails)
   │   ├── Try quick_rules (instant, no API cost)
   │   │   └── First match wins → execute action
   │   ├── If no quick_rule match:
   │   │   └── Call AI provider → get decision
   │   ├── Execute action or queue for approval
   │   └── Mark email as processed in database
   ├── Run inbox aging (if enabled)
   └── Return summary statistics
```

**Key classes:**
- `AutopilotEngine` - Orchestrates processing
- `AutopilotConfig` - Parsed autopilot.yaml
- `QuickRule` - Fast pattern matching rule
- `AutopilotDecision` - AI classification result

### `mail/` - Mail.app Integration

All communication with Mail.app via AppleScript.

**`messages.py`:**
- `EmailMessage` dataclass with all email properties
- `get_messages()` - Fetch from mailbox
- `get_message_by_id()` - Fetch specific message

**`actions.py`:**
- `move_message()`, `delete_message()`, `archive_message()`
- `mark_read()`, `mark_unread()`
- `flag_message()`, `unflag_message()`

**`accounts.py`:**
- `get_accounts()` - List all Mail.app accounts
- `sync_account()` - Trigger mailbox sync

### `storage/database.py` - SQLite Persistence

Tracks processing state across runs.

**Tables:**
- `processed_emails` - IDs of emails already handled
- `pending_actions` - Actions awaiting approval
- `action_history` - Log of executed actions
- `mailbox_cache` - Cached mailbox lists

**Key methods:**
```python
db.is_processed(message_id) -> bool
db.mark_processed(message_id)
db.add_pending_action(email, decision) -> int
db.get_pending_actions(limit) -> list
```

## Data Flow

### Email Classification Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Mail.app   │────▶│  Autopilot  │────▶│  AI Provider │
│  (emails)   │     │   Engine    │     │  (classify)  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Execute   │
                    │   Action    │
                    └─────────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
             ┌──────────┐  ┌─────────────┐
             │ Mail.app │  │  Database   │
             │ (action) │  │ (log/queue) │
             └──────────┘  └─────────────┘
```

### Configuration Loading Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Environment │────▶│  Pydantic   │────▶│  Settings   │
│  Variables  │     │  Settings   │     │   Object    │
└─────────────┘     └─────────────┘     └─────────────┘
                           ▲
                           │
                    ┌──────┴──────┐
                    │  .env files │
                    │ (user/proj) │
                    └─────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│autopilot.yml│────▶│  YAML Load  │────▶│ Autopilot   │
│             │     │             │     │  Config     │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Key Design Decisions

### 1. Lazy Client Initialization

AI clients are lazily initialized to avoid import overhead and allow graceful degradation:

```python
@property
def client(self) -> anthropic.Anthropic:
    if self._client is None:
        import anthropic
        self._client = anthropic.Anthropic(api_key=self.api_key)
    return self._client
```

### 2. Quick Rules Before AI

Quick rules provide instant pattern matching without API calls:

```python
# In AutopilotEngine._process_email()
for rule in self.config.quick_rules:
    if rule.matches(email):
        return self._execute_quick_rule(rule, email)

# Only call AI if no quick rule matched
decision = await self.ai.autopilot_classify(email, instructions)
```

### 3. AppleScript Error Handling

All AppleScript calls are wrapped with timeout and error handling:

```python
def run_applescript(script: str, timeout: float = 30.0) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        # Handle errors...
    except subprocess.TimeoutExpired:
        raise AppleScriptTimeout(f"Script timed out after {timeout}s")
```

### 4. Confidence-Based Action Execution

Actions are only auto-executed when AI confidence meets threshold:

```python
if decision.confidence >= settings.confidence_threshold:
    await self._execute_action(decision)
else:
    db.add_pending_action(email, decision)
```

## Database Schema

```sql
CREATE TABLE processed_emails (
    message_id TEXT PRIMARY KEY,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    email_summary TEXT,
    proposed_action JSON,
    confidence REAL,
    reasoning TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE action_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT,
    action TEXT,
    source TEXT,  -- 'quick_rule', 'ai', 'manual'
    details JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE mailbox_cache (
    account TEXT,
    mailbox TEXT,
    cached_at TIMESTAMP,
    PRIMARY KEY (account, mailbox)
);

CREATE TABLE watcher_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pid INTEGER,
    started_at TIMESTAMP,
    last_inbox_count INTEGER,
    last_check_at TIMESTAMP
);

CREATE TABLE pending_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    folder TEXT NOT NULL,
    message_id TEXT,
    proposed_action JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account, folder, message_id)
);
```

## Extending Email Nurse

### Adding a New AI Provider

1. Create `ai/newprovider.py`:
```python
from email_nurse.ai.base import AIProvider, EmailClassification

class NewProvider(AIProvider):
    async def classify_email(self, email, context=None):
        # Implementation...
        return EmailClassification(...)

    async def autopilot_classify(self, email, instructions):
        # Implementation...

    async def is_available(self):
        # Check connectivity...
```

2. Add to CLI provider selection in `cli.py`
3. Add settings in `config.py`

### Adding a New Action Type

1. Add to `EmailAction` enum in `ai/base.py`
2. Implement execution in `autopilot/engine.py:_execute_action()`
3. Add AppleScript commands in `mail/actions.py`
4. Update documentation

### Adding a New Condition Type

1. Add condition class in `rules/conditions.py`
2. Register in condition factory
3. Update rules-reference.md documentation

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=email_nurse

# Run specific module tests
pytest tests/test_autopilot.py -v
```

## Performance Considerations

- **AppleScript calls are slow** (~50-100ms each). Batch operations where possible.
- **AI API calls have latency** (~500ms-2s). Use quick_rules to minimize.
- **Large mailboxes** can timeout. Use pagination with `limit` parameter.
- **SQLite is single-writer**. Database operations are fast but serialized.

## Related Documentation

- [Configuration Guide](./configuration.md) - Settings and environment setup
- [AI Providers Guide](./ai-providers.md) - Provider implementation details
- [Troubleshooting Guide](./troubleshooting.md) - Common issues and solutions
