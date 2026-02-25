"""Write operations for Apple Calendar.app.

Uses sysm CLI for event creation. AppleScript is kept for delete_event()
because sysm deletes by title (not UID), which is a different API.
"""

from datetime import datetime, timedelta

from email_nurse.applescript import AppleScriptError, escape_applescript_string, run_applescript
from email_nurse.calendar.calendars import CalendarAppError, _check_calendar_running
from email_nurse.mail.sysm import SysmError, create_event_sysm


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
    Create a calendar event via sysm.

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
        CalendarAppError: If event creation fails.
    """
    if end_date is None:
        end_date = start_date + timedelta(hours=1)

    # Format dates for sysm (ISO-ish format works)
    start_str = start_date.strftime("%Y-%m-%d %H:%M")
    end_str = end_date.strftime("%Y-%m-%d %H:%M")

    try:
        result = create_event_sysm(
            title=summary,
            start=start_str,
            end=end_str,
            calendar=calendar_name,
            location=location or None,
            notes=description or None,
            all_day=all_day,
        )
    except SysmError as e:
        raise CalendarAppError(str(e)) from e

    # Extract UID from sysm response
    return str(result.get("id", result.get("uid", "")))


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

    Uses AppleScript because sysm deletes by title (not UID).

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
