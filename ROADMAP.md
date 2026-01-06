# email-nurse Roadmap

This document outlines planned features and integrations for email-nurse.

---

## Apple Reminders Integration

**Status**: ✅ Complete (Phase 1.0 + 1.2)
**Priority**: High

### Overview

Add AppleScript integration for Apple Reminders app, enabling:
- Creating reminders linked back to emails via `message://` URL scheme
- Viewing and managing reminders from the CLI

### Phase 1.0: Read Operations ✅

**Data Model**:
```python
@dataclass
class Reminder:
    id: str
    name: str
    body: str                    # Notes (stores email links)
    list_name: str
    due_date: datetime | None
    priority: int                # 0=none, 1=high, 5=medium, 9=low
    completed: bool
    creation_date: datetime | None
```

**Functions**:
- `get_lists() -> list[ReminderList]` - Get all reminder lists
- `get_reminders(list_name?, completed?) -> list[Reminder]` - Get reminders

**CLI Commands**:
```bash
email-nurse reminders list              # List all reminder lists
email-nurse reminders show <list>       # Show reminders in a list
email-nurse reminders incomplete        # All incomplete reminders
```

### Phase 1.2: Write Operations ✅

**Functions** (implemented in `reminders/actions.py`):
```python
def create_reminder(name, list_name="Reminders", body=None, due_date=None, priority=0) -> str
def create_reminder_from_email(message_id, name, list_name, due_date, subject, sender) -> str
def complete_reminder(reminder_id, list_name) -> bool
def uncomplete_reminder(reminder_id, list_name) -> bool
def delete_reminder(reminder_id, list_name) -> bool
```

**CLI Commands**:
```bash
email-nurse reminders create <name> [--list] [--body] [--due] [--priority]
email-nurse reminders complete <id> --list <list>
email-nurse reminders delete <id> --list <list> [--force]
```

### Known Limitations

- **Subtasks NOT accessible** via AppleScript (top-level only)
- **Tags NOT accessible** via AppleScript
- **Performance is SLOW** (Catalyst app) - use 60s+ timeouts

---

## Apple Calendar Integration

**Status**: ✅ Complete (Phase 1.0 + 1.2)
**Priority**: Medium

### Overview

Add AppleScript integration for Apple Calendar app, enabling:
- Creating calendar events linked back to emails
- Viewing upcoming events from the CLI

### Implementation Notes

**Direct event creation works** on this system despite reports of issues on macOS Sequoia.
The `parse sentence` command (mentioned in some workarounds) is actually a Fantastical feature, not Calendar.app.

### Phase 1.0: Read Operations ✅

**Data Model**:
```python
@dataclass
class CalendarEvent:
    id: str
    summary: str                 # Event title
    description: str
    location: str | None
    start_date: datetime
    end_date: datetime
    all_day: bool
    calendar_name: str
    url: str | None              # Can contain message:// link
    recurrence_rule: str | None  # Recurrence info (read-only)
```

**Functions** (implemented in `calendar/calendars.py` and `calendar/events.py`):
- `get_calendars() -> list[Calendar]` - Get all calendars
- `get_calendar_names() -> list[str]` - Get calendar names (fast)
- `get_events(calendar?, start_date?, end_date?, limit?) -> list[CalendarEvent]`
- `get_events_today(calendar?) -> list[CalendarEvent]`

**CLI Commands**:
```bash
email-nurse calendar list               # List all calendars
email-nurse calendar events             # Upcoming events (30 days)
email-nurse calendar today              # Today's events
```

### Phase 1.2: Write Operations ✅

**Functions** (implemented in `calendar/actions.py`):
```python
def create_event(summary, start_date, end_date?, calendar_name?, location?, description?, all_day?) -> str
def create_event_from_email(summary, start_date, message_id, calendar_name?, end_date?, subject?, sender?) -> str
def delete_event(event_id, calendar_name) -> bool
```

**CLI Commands**:
```bash
email-nurse calendar create <summary> --start <datetime> [--end] [--calendar] [--location] [--all-day]
```

### Known Limitations

- **Calendar.app doesn't expose uid** for calendars - uses `name` as identifier
- **Recurring events** have limited AppleScript support (read-only)
- **Performance can be slow** when querying many calendars - use 90s timeout

---

## Email Linking via `message://` URL

Both Reminders and Calendar events can link back to the original email:

```python
# Reminders: Store in body field
body = f"From email: message://<{email.message_id}>\nSubject: {email.subject}"

# Calendar: Store in url field (or description as fallback)
url = f"message://<{email.message_id}>"
```

Clicking the `message://` URL in Reminders or Calendar opens the email in Mail.app.

---

## Implementation Order

1. ✅ **Shared infrastructure** - `applescript/` module (extract from mail/)
2. ✅ **Reminders read** - lists.py, reminders.py
3. ✅ **Reminders CLI** - list, show, incomplete commands
4. ✅ **Calendar read** - calendars.py, events.py
5. ✅ **Calendar CLI** - list, events, today commands
6. ✅ **Reminders write** - actions.py (create, complete, delete)
7. ✅ **Calendar write** - actions.py (create_event, delete_event)
8. ⬜ **Tests** - Unit tests for parsing, integration tests for live calls

---

## Module Structure

```
src/email_nurse/
├── applescript/                 # Shared AppleScript infrastructure
│   ├── __init__.py
│   ├── base.py                  # run_applescript(), escape_applescript_string()
│   └── errors.py                # AppleScriptError, AppNotRunningError
│
├── mail/                        # Existing (updated imports)
│   └── applescript.py           # Re-export from applescript/base
│
├── reminders/                   # NEW
│   ├── __init__.py
│   ├── lists.py                 # ReminderList dataclass, get_lists()
│   ├── reminders.py             # Reminder dataclass, get_reminders()
│   └── actions.py               # create_reminder(), complete_reminder()
│
├── calendar/                    # NEW
│   ├── __init__.py
│   ├── calendars.py             # Calendar dataclass, get_calendars()
│   ├── events.py                # CalendarEvent dataclass, get_events()
│   └── actions.py               # create_event() via parse_sentence
│
└── cli.py                       # Extended with reminders_app, calendar_app
```
