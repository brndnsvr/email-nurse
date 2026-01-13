"""Calendar event retrieval from Apple Calendar.app."""

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

from email_nurse.applescript import AppleScriptError, escape_applescript_string, run_applescript
from email_nurse.calendar.calendars import (
    RECORD_SEP,
    UNIT_SEP,
    CalendarAppError,
    _check_calendar_running,
    _ensure_calendar_running,
)


@dataclass
class CalendarEvent:
    """Represents an event from Calendar.app."""

    id: str
    summary: str  # Event title
    description: str
    location: str | None
    start_date: datetime
    end_date: datetime
    all_day: bool
    calendar_name: str
    url: str | None  # Can contain message:// link
    recurrence_rule: str | None  # Recurrence info (read-only)

    @property
    def email_link(self) -> str | None:
        """Extract message:// URL from url or description if present."""
        # Check url field first
        if self.url and self.url.startswith("message://"):
            return self.url
        # Fallback: check description for message:// link
        if self.description:
            match = re.search(r"message://[<]?([^>\s]+)[>]?", self.description)
            return match.group(0) if match else None
        return None

    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes."""
        if self.all_day:
            return 24 * 60
        delta = self.end_date - self.start_date
        return int(delta.total_seconds() / 60)

    @property
    def duration_str(self) -> str:
        """Human-readable duration string."""
        minutes = self.duration_minutes
        if self.all_day:
            return "all day"
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        mins = minutes % 60
        if mins == 0:
            return f"{hours}h"
        return f"{hours}h {mins}m"

    @property
    def is_upcoming(self) -> bool:
        """Check if event is in the future."""
        return self.start_date > datetime.now()

    def __str__(self) -> str:
        if self.all_day:
            time_str = self.start_date.strftime("%Y-%m-%d") + " (all day)"
        else:
            time_str = self.start_date.strftime("%Y-%m-%d %H:%M")
        return f"{time_str}: {self.summary}"


def get_events(
    calendar_name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 100,
) -> list[CalendarEvent]:
    """
    Get events from Calendar.app.

    Args:
        calendar_name: Filter to specific calendar, or None for all.
        start_date: Start of date range (default: now).
        end_date: End of date range (default: 30 days from start).
        limit: Maximum number of events to retrieve.

    Returns:
        List of CalendarEvent objects, sorted by start_date.

    Raises:
        CalendarAppNotRunningError: If Calendar.app is not running.
        CalendarAppError: If the AppleScript fails.
    """
    # Ensure Calendar.app is running
    _ensure_calendar_running()

    # Default date range: now to 30 days from now
    if start_date is None:
        start_date = datetime.now()
    if end_date is None:
        end_date = start_date + timedelta(days=30)

    # Format dates for AppleScript
    start_str = start_date.strftime("%m/%d/%Y %H:%M:%S")
    end_str = end_date.strftime("%m/%d/%Y %H:%M:%S")

    if calendar_name:
        # Single calendar query
        cal_escaped = escape_applescript_string(calendar_name)
        script = f'''
        tell application "Calendar"
            set output to ""
            set RS to (ASCII character 30)  -- Record Separator
            set US to (ASCII character 31)  -- Unit Separator
            set eventCount to 0
            set maxEvents to {limit}

            set startFilter to date "{start_str}"
            set endFilter to date "{end_str}"

            set cal to calendar "{cal_escaped}"
            set calEvents to (events of cal whose start date >= startFilter and start date <= endFilter)

            repeat with evt in calEvents
                if eventCount >= maxEvents then exit repeat
                set eventCount to eventCount + 1

                set evtId to uid of evt
                set evtSummary to summary of evt
                if evtSummary is missing value then set evtSummary to ""

                set evtDesc to description of evt
                if evtDesc is missing value then set evtDesc to ""

                set evtLocation to location of evt
                if evtLocation is missing value then set evtLocation to ""

                set evtStart to start date of evt as string
                set evtEnd to end date of evt as string
                set evtAllDay to allday event of evt

                set evtUrl to url of evt
                if evtUrl is missing value then set evtUrl to ""

                set evtRecurrence to ""
                try
                    set evtRecurrence to recurrence of evt
                    if evtRecurrence is missing value then set evtRecurrence to ""
                end try

                -- Use "-" placeholder for empty strings (AppleScript strips empty strings at end)
                if evtUrl is "" then set evtUrl to "-"
                if evtRecurrence is "" then set evtRecurrence to "-"

                if output is not "" then set output to output & RS
                set output to output & evtId & US & evtSummary & US & evtDesc & US & evtLocation & US & evtStart & US & evtEnd & US & (evtAllDay as string) & US & "{cal_escaped}" & US & evtUrl & US & evtRecurrence
            end repeat

            return output
        end tell
        '''
    else:
        # All calendars - iterate through each
        script = f'''
        tell application "Calendar"
            set output to ""
            set RS to (ASCII character 30)  -- Record Separator
            set US to (ASCII character 31)  -- Unit Separator
            set eventCount to 0
            set maxEvents to {limit}

            set startFilter to date "{start_str}"
            set endFilter to date "{end_str}"

            repeat with cal in calendars
                if eventCount >= maxEvents then exit repeat

                set calName to name of cal
                set calEvents to (events of cal whose start date >= startFilter and start date <= endFilter)

                repeat with evt in calEvents
                    if eventCount >= maxEvents then exit repeat
                    set eventCount to eventCount + 1

                    set evtId to uid of evt
                    set evtSummary to summary of evt
                    if evtSummary is missing value then set evtSummary to ""

                    set evtDesc to description of evt
                    if evtDesc is missing value then set evtDesc to ""

                    set evtLocation to location of evt
                    if evtLocation is missing value then set evtLocation to ""

                    set evtStart to start date of evt as string
                    set evtEnd to end date of evt as string
                    set evtAllDay to allday event of evt

                    set evtUrl to url of evt
                    if evtUrl is missing value then set evtUrl to ""

                    set evtRecurrence to ""
                    try
                        set evtRecurrence to recurrence of evt
                        if evtRecurrence is missing value then set evtRecurrence to ""
                    end try

                    -- Use "-" placeholder for empty strings (AppleScript strips empty strings at end)
                    if evtUrl is "" then set evtUrl to "-"
                    if evtRecurrence is "" then set evtRecurrence to "-"

                    if output is not "" then set output to output & RS
                    set output to output & evtId & US & evtSummary & US & evtDesc & US & evtLocation & US & evtStart & US & evtEnd & US & (evtAllDay as string) & US & calName & US & evtUrl & US & evtRecurrence
                end repeat
            end repeat

            return output
        end tell
        '''

    try:
        # Calendar.app can be very slow with many events (10k+) - use 120s timeout
        result = run_applescript(script, timeout=120)
    except AppleScriptError as e:
        _check_calendar_running(str(e))
        raise CalendarAppError(str(e), e.script) from e

    if not result:
        return []

    events = []
    for record in result.split(RECORD_SEP):
        parts = record.split(UNIT_SEP)
        if len(parts) >= 10:
            events.append(
                CalendarEvent(
                    id=parts[0],
                    summary=parts[1],
                    description=parts[2],
                    location=parts[3] if parts[3] else None,
                    start_date=_parse_date(parts[4]) or datetime.now(),
                    end_date=_parse_date(parts[5]) or datetime.now(),
                    all_day=parts[6].lower() == "true",
                    calendar_name=parts[7],
                    url=parts[8] if parts[8] and parts[8] != "-" else None,
                    recurrence_rule=parts[9] if parts[9] and parts[9] != "-" else None,
                )
            )

    # Sort by start date
    events.sort(key=lambda e: e.start_date)
    return events


def get_events_today(calendar_name: str | None = None) -> list[CalendarEvent]:
    """
    Get all events scheduled for today.

    Args:
        calendar_name: Filter to specific calendar, or None for all.

    Returns:
        List of CalendarEvent objects for today, sorted by start time.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    return get_events(calendar_name=calendar_name, start_date=today, end_date=tomorrow)


def _parse_date(date_str: str) -> datetime | None:
    """Parse an AppleScript date string into a datetime object."""
    if not date_str or date_str == "missing value":
        return None

    # AppleScript returns dates in various formats depending on locale
    formats = [
        # US English locale formats
        "%A, %B %d, %Y at %I:%M:%S %p",  # Friday, December 20, 2024 at 10:30:00 AM
        "%A, %B %d, %Y at %H:%M:%S",  # Friday, December 20, 2024 at 22:30:00
        # Abbreviated day/month names
        "%a, %b %d, %Y at %I:%M:%S %p",  # Fri, Dec 20, 2024 at 10:30:00 AM
        "%a, %b %d, %Y at %H:%M:%S",  # Fri, Dec 20, 2024 at 22:30:00
        # Without day name
        "%B %d, %Y at %I:%M:%S %p",  # December 20, 2024 at 10:30:00 AM
        "%B %d, %Y at %H:%M:%S",  # December 20, 2024 at 22:30:00
        # ISO 8601 variants
        "%Y-%m-%d %H:%M:%S",  # 2024-12-20 22:30:00
        "%Y-%m-%dT%H:%M:%S",  # 2024-12-20T22:30:00
        "%Y-%m-%d",  # 2024-12-20
        # European-style formats
        "%d/%m/%Y %H:%M:%S",  # 20/12/2024 22:30:00
        "%d/%m/%Y %I:%M:%S %p",  # 20/12/2024 10:30:00 PM
        # US-style numeric
        "%m/%d/%Y %H:%M:%S",  # 12/20/2024 22:30:00
        "%m/%d/%Y %I:%M:%S %p",  # 12/20/2024 10:30:00 PM
        # Without seconds
        "%A, %B %d, %Y at %I:%M %p",  # Friday, December 20, 2024 at 10:30 AM
        "%Y-%m-%d %H:%M",  # 2024-12-20 22:30
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Log unrecognized format for debugging
    print(
        f"Warning: Unrecognized date format in Calendar: {date_str!r}",
        file=sys.stderr,
    )
    return None
