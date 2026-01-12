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

**Direct event creation works** via AppleScript despite reports of issues on some macOS versions.
Events are created directly using Calendar.app's AppleScript interface without requiring third-party apps.

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
8. ✅ **Tests** - Unit tests for parsing (144 tests total)

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
│   └── actions.py               # create_event(), delete_event()
│
└── cli.py                       # Extended with reminders_app, calendar_app
```

---

## AI-Driven Calendar/Reminders Integration

**Status**: ✅ Complete
**Priority**: High

### Overview

The AI autopilot can now create Calendar events and Reminders based on email content.

**New EmailAction Types**:
- `create_reminder` - Extract deadlines, follow-ups, action items
- `create_event` - Extract meetings, conferences, events with dates

**Context Enrichment**:
The AI receives today's calendar and pending reminders as context when classifying emails, enabling smarter decisions.

**Files Modified**:
- `ai/base.py` - Added EmailAction enum values
- `ai/claude.py` - Updated prompt, datetime parsing
- `autopilot/models.py` - Added reminder/event fields to AutopilotDecision
- `autopilot/engine.py` - Added `_build_pim_context()`, action execution

---

## Balanced Reminder/Calendar Behavior with Override Support

**Status**: ✅ Complete
**Priority**: High

### Overview

Refined AI behavior for creating reminders and calendar events with sensible defaults and user-configurable overrides.

### Default Behavior (Conservative)

**Reminders**: Only created for emails with CLEAR, ACTIONABLE deadlines requiring user action.
- ✅ Good: "Payment due Jan 15", "RSVP by Friday", "Offer expires Dec 31"
- ❌ Bad: "We'll follow up next week", "Sale ends soon", general questions

**Calendar Events**: Only created for emails with SPECIFIC dates/times for meetings or events.
- ✅ Good: "Conference March 10-12", "Let's meet Thursday at 2pm", "Webinar on Jan 20 at 3pm"
- ❌ Bad: Calendar invites (Mail.app handles these), vague "sometime next month"

When uncertain, the AI prefers `flag` over creating a reminder/event.

### Override Behavior

User instructions in `autopilot.yaml` can adjust the threshold:
- `"create reminders liberally"` → Lower threshold, create for any date mention
- `"never create reminders/events"` → Respect completely
- Specific categories (e.g., `"reminders for bills"`) → Only create for matching emails

User instructions always take precedence over default behavior.

**Files Modified**:
- `ai/claude.py` - Updated prompt with default vs override behavior guidelines

---

## Deduplication for Reminders and Calendar Events

**Status**: ✅ Complete
**Priority**: High

### Overview

Prevent duplicate reminders and calendar events from being created when emails are reprocessed.

### Implementation

**Database Tracking**:
- `created_reminders` table - Tracks reminders created per email message ID
- `created_events` table - Tracks calendar events created per email message ID

**Processing Flow**:
1. Before creating a reminder/event, check if one already exists for this email
2. If exists, skip creation and log the duplicate detection
3. If new, create the reminder/event and record it in the database
4. Old tracking records are cleaned up based on `processed_retention_days`

**Database Methods**:
```python
# Reminder tracking
db.has_reminder_for_email(message_id) -> bool
db.get_reminder_for_email(message_id) -> dict | None
db.record_reminder_created(message_id, reminder_id, ...)
db.cleanup_old_reminder_records(retention_days) -> int

# Event tracking
db.has_event_for_email(message_id) -> bool
db.get_event_for_email(message_id) -> dict | None
db.record_event_created(message_id, event_id, ...)
db.cleanup_old_event_records(retention_days) -> int
```

**Files Modified**:
- `storage/database.py` - Added tracking tables and methods
- `autopilot/engine.py` - Added duplicate checks before creation, cleanup on run

---

## Unit Tests

**Status**: ✅ Complete
**Priority**: Medium

### Overview

Comprehensive unit tests for Calendar and Reminders modules. Test count: 144 tests.

### High-Priority Test Targets

| Function | Module | Why Critical |
|----------|--------|-------------|
| `_parse_date()` | Both | Handles 15+ AppleScript date formats |
| Separator parsing | Both | ASCII `\x1e`/`\x1f` record/unit splitting |
| `email_link` property | Both | Regex extraction of `message://` URLs |
| `priority_label` property | Reminders | Priority int → label boundary cases |
| `duration_str` property | Calendar | Time delta formatting |

### Test Architecture

```
tests/
├── test_calendar/
│   ├── test_events_parsing.py    # Date parsing, separator parsing
│   ├── test_calendar_event.py    # Dataclass properties
│   └── test_actions.py           # Event creation (mocked)
├── test_reminders/
│   ├── test_reminders_parsing.py # Date parsing, priority mapping
│   ├── test_reminder.py          # Dataclass properties
│   └── test_actions.py           # Reminder creation (mocked)
```

### Key Insight

Most parsing can be tested without mocking AppleScript - pass mock output strings directly to parsing functions.

**Result**: 144 tests total

---

## AI Behavior Tuning

**Status**: ✅ Complete
**Priority**: High (quick win)

### Overview

Added section 9 to `autopilot.yaml` instructions with guidance for reminders:
- Create reminders for deadlines, follow-ups, action items, specific senders
- Exclusions for certain domains (support tickets) and vague deadlines
- Calendar events disabled (user prefers manual control)

**Location**: `deploy/config/autopilot.yaml`

---

## Secondary Actions

**Status**: ✅ Complete
**Priority**: Medium

### Overview

AI can now recommend multiple actions per email (e.g., "archive AND create reminder").

### Implementation

**Option A - Secondary Action Field** was implemented:
```python
class AutopilotDecision(BaseModel):
    action: EmailAction              # Primary action
    secondary_action: EmailAction | None = None
    secondary_target_folder: str | None = None
```

### Design Decisions

- **Confidence**: Secondary inherits primary confidence (single judgment)
- **Error handling**: If secondary fails, primary still succeeds
- **Outbound policy**: REPLY/FORWARD/DELETE not allowed as secondary actions
- **Deduplication**: Existing checks apply to secondary CREATE_REMINDER/CREATE_EVENT

### Changes Made

1. ✅ Updated `AutopilotDecision` model with `secondary_action` and `secondary_target_folder`
2. ✅ Updated AI prompts (Claude + OpenAI) to explain secondary actions
3. ✅ Added `_execute_secondary_action()` method to engine
4. ✅ Updated `is_pim_action` property to check secondary
5. ✅ Added `has_invalid_secondary` property for validation

### Common Combinations

- `archive` + `create_reminder` - Archive but remind to follow up
- `move` + `mark_read` - Sort and mark read
- `create_event` + `archive` - Extract event, archive original
- `flag` + `move` - Flag and move to folder

---

## Daily Digest Enhancement

**Status**: ✅ Complete
**Priority**: Medium

### Overview

Enhanced daily email reports to include tomorrow's schedule and pending reminders.

### Implemented Sections

**Tomorrow's Schedule**:
- Lists calendar events for the next day (time, summary, location)
- All-day events shown separately
- Data source: `get_events()` with tomorrow's date range

**Pending Reminders** (up to 10 shown):
- Sorted by due date (overdue first, then upcoming, then no-date)
- Overdue items highlighted in red
- Due today items highlighted in blue
- Data source: `get_reminders(completed=False)`

**Email Activity**:
- Total processed count with action breakdown
- By-folder and by-account summaries
- Detailed activity log with timestamps

### Edge Cases Handled

- Calendar/Reminders app not running: gracefully skips section
- No events scheduled: shows "No events scheduled for tomorrow"
- No pending reminders: shows "All caught up!"
- More than 10 reminders: shows "... and X more"

**Files Modified**: `src/email_nurse/autopilot/reports.py`

---

## Future Ideas (Parking Lot)

Potential enhancements for future consideration:

- ~~**Smart Duplicate Detection**~~ - ✅ Implemented (see Deduplication section above)
- **General `run` Command** - The `email-nurse run --once` command is a placeholder for a simpler processing mode. Consider whether this is needed given `autopilot run` covers the use case.
- **Recurring Pattern Learning** - Learn from user's manual corrections
- **Priority Inference** - Set reminder priority based on email urgency signals
- **Calendar Conflict Detection** - Warn if proposed event conflicts with existing
- **Snooze Integration** - Support snoozing reminders via CLI
- **Natural Language Dates** - Parse "next Tuesday" style relative dates
