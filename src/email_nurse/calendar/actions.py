"""Write operations for Apple Calendar.app.

This module provides functions to create calendar events via AppleScript
integration with macOS Calendar.app.

Note: Direct event creation may not work on all macOS versions/configurations.
If it fails, see: https://mjtsai.com/blog/2024/10/23/the-sad-state-of-mac-calendar-scripting/
"""

from datetime import datetime, timedelta

from email_nurse.applescript import AppleScriptError, escape_applescript_string, run_applescript
from email_nurse.calendar.calendars import CalendarAppError, _check_calendar_running


def create_event(
    summary: str,
    start_date: datetime,
    end_date: datetime | None = None,
    calendar_name: str = "Calendar",
    location: str = "",
    description: str = "",
    all_day: bool = False,
) -> str:
    """
    Create a calendar event.

    Args:
        summary: Event title.
        start_date: Event start date/time.
        end_date: Event end date/time (default: start + 1 hour).
        calendar_name: Target calendar name.
        location: Event location.
        description: Event notes/description.
        all_day: Whether this is an all-day event.

    Returns:
        The UID of the created event.

    Raises:
        CalendarAppNotRunningError: If Calendar.app is not running.
        CalendarAppError: If event creation fails.

    Example:
        >>> from datetime import datetime, timedelta
        >>> start = datetime.now() + timedelta(days=1, hours=14)
        >>> event_id = create_event(
        ...     "Team Meeting",
        ...     start_date=start,
        ...     calendar_name="Work",
        ...     location="Conference Room A",
        ... )
    """
    if end_date is None:
        end_date = start_date + timedelta(hours=1)

    summary_escaped = escape_applescript_string(summary)
    cal_escaped = escape_applescript_string(calendar_name)

    # Format dates for AppleScript
    start_str = start_date.strftime("%m/%d/%Y %H:%M:%S")
    end_str = end_date.strftime("%m/%d/%Y %H:%M:%S")

    # Build properties
    props = [
        f'summary:"{summary_escaped}"',
        f'start date:date "{start_str}"',
        f'end date:date "{end_str}"',
    ]

    if all_day:
        props.append("allday event:true")

    if location:
        location_escaped = escape_applescript_string(location)
        props.append(f'location:"{location_escaped}"')

    if description:
        desc_escaped = escape_applescript_string(description)
        props.append(f'description:"{desc_escaped}"')

    props_str = ", ".join(props)

    script = f'''
    tell application "Calendar"
        set theCal to calendar "{cal_escaped}"
        set newEvent to make new event at end of events of theCal with properties {{{props_str}}}
        return uid of newEvent
    end tell
    '''

    try:
        result = run_applescript(script, timeout=30)
    except AppleScriptError as e:
        _check_calendar_running(str(e))
        raise CalendarAppError(str(e), e.script) from e

    return result.strip()


def create_event_from_email(
    summary: str,
    start_date: datetime,
    message_id: str,
    calendar_name: str = "Calendar",
    end_date: datetime | None = None,
    subject: str = "",
    sender: str = "",
) -> str:
    """
    Create a calendar event linked to an email.

    The email reference is stored in the event description with a
    message:// URL that opens the email in Mail.app when clicked.

    Args:
        summary: Event title.
        start_date: Event start date/time.
        message_id: Mail.app message ID to reference.
        calendar_name: Target calendar name.
        end_date: Event end date/time.
        subject: Email subject for context.
        sender: Email sender for context.

    Returns:
        The UID of the created event.

    Example:
        >>> from datetime import datetime, timedelta
        >>> start = datetime.now() + timedelta(days=1, hours=14)
        >>> event_id = create_event_from_email(
        ...     "Follow up meeting",
        ...     start_date=start,
        ...     message_id="abc123@example.com",
        ...     subject="Project Update",
        ...     sender="bob@example.com",
        ... )
    """
    # Build description with email context
    desc_parts = []

    if subject:
        desc_parts.append(f"Re: {subject}")
    if sender:
        desc_parts.append(f"From: {sender}")

    # Add message:// link
    msg_url = f"message://<{message_id}>"
    desc_parts.append(f"Email: {msg_url}")

    description = "\n".join(desc_parts)

    return create_event(
        summary=summary,
        start_date=start_date,
        end_date=end_date,
        calendar_name=calendar_name,
        description=description,
    )


def delete_event(event_id: str, calendar_name: str) -> bool:
    """
    Delete a calendar event.

    Args:
        event_id: The event UID to delete.
        calendar_name: Name of the calendar containing the event.

    Returns:
        True if successful.

    Raises:
        CalendarAppNotRunningError: If Calendar.app is not running.
        CalendarAppError: If deletion fails.
    """
    cal_escaped = escape_applescript_string(calendar_name)
    event_id_escaped = escape_applescript_string(event_id)

    script = f'''
    tell application "Calendar"
        set theCal to calendar "{cal_escaped}"
        set theEvent to first event of theCal whose uid is "{event_id_escaped}"
        delete theEvent
    end tell
    '''

    try:
        run_applescript(script, timeout=30)
    except AppleScriptError as e:
        _check_calendar_running(str(e))
        raise CalendarAppError(str(e), e.script) from e

    return True
