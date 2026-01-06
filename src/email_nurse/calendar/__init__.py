"""Apple Calendar.app integration via AppleScript."""

from email_nurse.calendar.actions import (
    create_event,
    create_event_from_email,
    delete_event,
)
from email_nurse.calendar.calendars import (
    Calendar,
    CalendarAppError,
    CalendarAppNotRunningError,
    get_calendar_names,
    get_calendars,
)
from email_nurse.calendar.events import (
    CalendarEvent,
    get_events,
    get_events_today,
)

__all__ = [
    # Data classes
    "Calendar",
    "CalendarEvent",
    # Error classes
    "CalendarAppError",
    "CalendarAppNotRunningError",
    # Read operations
    "get_calendars",
    "get_calendar_names",
    "get_events",
    "get_events_today",
    # Write operations
    "create_event",
    "create_event_from_email",
    "delete_event",
]
