"""Reminder retrieval from Apple Reminders.app.

Performance Note:
    Reminders.app is a Catalyst app (iPad app running on macOS), which makes
    AppleScript interactions extremely slow. Lists with thousands of items
    (e.g., 3000+ reminders) may timeout. Recommend specifying a list_name
    when calling get_reminders() for better performance.
"""

import re
import sys
from dataclasses import dataclass
from datetime import datetime

from email_nurse.applescript import AppleScriptError, escape_applescript_string, run_applescript
from email_nurse.reminders.lists import (
    RECORD_SEP,
    UNIT_SEP,
    RemindersAppError,
    _check_reminders_running,
)


@dataclass
class Reminder:
    """Represents a reminder from Reminders.app."""

    id: str
    name: str
    body: str  # Notes field (can contain email links)
    list_name: str
    due_date: datetime | None
    priority: int  # 0=none, 1=high, 5=medium, 9=low
    completed: bool
    creation_date: datetime | None

    @property
    def email_link(self) -> str | None:
        """Extract message:// URL from body if present."""
        if not self.body:
            return None
        # Match message://<message-id> pattern
        match = re.search(r"message://[<]?([^>\s]+)[>]?", self.body)
        return match.group(0) if match else None

    @property
    def priority_label(self) -> str:
        """Human-readable priority label."""
        if self.priority == 0:
            return "none"
        elif self.priority <= 3:
            return "high"
        elif self.priority <= 6:
            return "medium"
        else:
            return "low"

    def __str__(self) -> str:
        status = "[x]" if self.completed else "[ ]"
        due = f" (due {self.due_date.strftime('%Y-%m-%d')})" if self.due_date else ""
        return f"{status} {self.name}{due}"


def get_reminders(
    list_name: str | None = None,
    completed: bool | None = None,
    limit: int = 100,
) -> list[Reminder]:
    """
    Get reminders from Reminders.app.

    Args:
        list_name: Filter to specific list, or None for all lists.
        completed: True=completed only, False=incomplete only, None=all.
        limit: Maximum number of reminders to retrieve.

    Returns:
        List of Reminder objects.

    Raises:
        RemindersAppNotRunningError: If Reminders.app is not running.
        RemindersAppError: If the AppleScript fails.
    """
    # Build completion filter
    if completed is True:
        completion_filter = "whose completed is true"
    elif completed is False:
        completion_filter = "whose completed is false"
    else:
        completion_filter = ""

    # Build list filter
    if list_name:
        list_escaped = escape_applescript_string(list_name)
        list_ref = f'list "{list_escaped}"'
        reminder_ref = f"reminders of {list_ref} {completion_filter}"
    else:
        # All lists - need to iterate
        reminder_ref = None

    if reminder_ref:
        # Single list query - more efficient
        script = f'''
        tell application "Reminders"
            set output to ""
            set RS to (ASCII character 30)  -- Record Separator
            set US to (ASCII character 31)  -- Unit Separator
            set reminderCount to 0
            set maxReminders to {limit}

            repeat with r in ({reminder_ref})
                if reminderCount >= maxReminders then exit repeat
                set reminderCount to reminderCount + 1

                set rId to id of r
                set rName to name of r
                set rBody to body of r
                if rBody is missing value then set rBody to ""
                set rList to name of container of r
                set rPriority to priority of r
                set rCompleted to completed of r
                set rCreated to creation date of r

                -- Get due date (can be missing)
                set rDue to ""
                try
                    set rDue to due date of r as string
                end try

                if output is not "" then set output to output & RS
                set output to output & rId & US & rName & US & rBody & US & rList & US & rDue & US & (rPriority as string) & US & (rCompleted as string) & US & (rCreated as string)
            end repeat

            return output
        end tell
        '''
    else:
        # All lists - iterate through each
        script = f'''
        tell application "Reminders"
            set output to ""
            set RS to (ASCII character 30)  -- Record Separator
            set US to (ASCII character 31)  -- Unit Separator
            set reminderCount to 0
            set maxReminders to {limit}

            repeat with reminderList in lists
                if reminderCount >= maxReminders then exit repeat

                repeat with r in (reminders of reminderList {completion_filter})
                    if reminderCount >= maxReminders then exit repeat
                    set reminderCount to reminderCount + 1

                    set rId to id of r
                    set rName to name of r
                    set rBody to body of r
                    if rBody is missing value then set rBody to ""
                    set rList to name of container of r
                    set rPriority to priority of r
                    set rCompleted to completed of r
                    set rCreated to creation date of r

                    -- Get due date (can be missing)
                    set rDue to ""
                    try
                        set rDue to due date of r as string
                    end try

                    if output is not "" then set output to output & RS
                    set output to output & rId & US & rName & US & rBody & US & rList & US & rDue & US & (rPriority as string) & US & (rCompleted as string) & US & (rCreated as string)
                end repeat
            end repeat

            return output
        end tell
        '''

    try:
        # Reminders.app is slow - use 90s timeout for large lists
        result = run_applescript(script, timeout=90)
    except AppleScriptError as e:
        _check_reminders_running(str(e))
        raise RemindersAppError(str(e), e.script) from e

    if not result:
        return []

    reminders = []
    for record in result.split(RECORD_SEP):
        parts = record.split(UNIT_SEP)
        if len(parts) >= 8:
            try:
                priority = int(parts[5])
            except ValueError:
                priority = 0

            reminders.append(
                Reminder(
                    id=parts[0],
                    name=parts[1],
                    body=parts[2],
                    list_name=parts[3],
                    due_date=_parse_date(parts[4]),
                    priority=priority,
                    completed=parts[6].lower() == "true",
                    creation_date=_parse_date(parts[7]),
                )
            )

    return reminders


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
        f"Warning: Unrecognized date format in Reminders: {date_str!r}",
        file=sys.stderr,
    )
    return None
