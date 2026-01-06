"""Write operations for Apple Reminders.app.

This module provides functions to create, complete, and delete reminders
via AppleScript integration with macOS Reminders.app.

Performance Note:
    Reminders.app is a Catalyst app (iPad app running on macOS), which makes
    AppleScript interactions slower than native apps. Write operations
    typically complete in 1-5 seconds.
"""

from datetime import datetime

from email_nurse.applescript import AppleScriptError, escape_applescript_string, run_applescript
from email_nurse.reminders.lists import RemindersAppError, _check_reminders_running


def create_reminder(
    name: str,
    list_name: str = "Reminders",
    body: str = "",
    due_date: datetime | None = None,
    priority: int = 0,
) -> str:
    """
    Create a new reminder in Reminders.app.

    Args:
        name: The reminder title.
        list_name: Name of the list to add the reminder to (default: "Reminders").
        body: Optional notes/body text for the reminder.
        due_date: Optional due date for the reminder.
        priority: Priority level (0=none, 1=high, 5=medium, 9=low).

    Returns:
        The ID of the newly created reminder.

    Raises:
        RemindersAppNotRunningError: If Reminders.app is not running.
        RemindersAppError: If the AppleScript fails.

    Example:
        >>> reminder_id = create_reminder(
        ...     "Call Bob",
        ...     list_name="Work",
        ...     due_date=datetime(2025, 1, 15, 9, 0),
        ...     priority=1,  # high
        ... )
    """
    name_escaped = escape_applescript_string(name)
    list_escaped = escape_applescript_string(list_name)

    # Build properties dictionary
    props = [f'name:"{name_escaped}"']

    if body:
        body_escaped = escape_applescript_string(body)
        props.append(f'body:"{body_escaped}"')

    if priority > 0:
        props.append(f"priority:{priority}")

    if due_date:
        # AppleScript date format: "month/day/year hour:minute:second"
        due_str = due_date.strftime("%m/%d/%Y %H:%M:%S")
        props.append(f'due date:date "{due_str}"')

    props_str = ", ".join(props)

    script = f'''
    tell application "Reminders"
        set newReminder to make new reminder with properties {{{props_str}}} at list "{list_escaped}"
        return id of newReminder
    end tell
    '''

    try:
        # Reminders.app (Catalyst) is slow - use 60s timeout
        result = run_applescript(script, timeout=60)
    except AppleScriptError as e:
        _check_reminders_running(str(e))
        raise RemindersAppError(str(e), e.script) from e

    return result.strip()


def create_reminder_from_email(
    message_id: str,
    name: str,
    list_name: str = "Reminders",
    due_date: datetime | None = None,
    subject: str = "",
    sender: str = "",
) -> str:
    """
    Create a reminder linked to an email via message:// URL.

    The reminder's body will contain a clickable link that opens
    the email in Mail.app when clicked.

    Args:
        message_id: The Mail.app message ID to link to.
        name: The reminder title.
        list_name: Name of the list to add the reminder to.
        due_date: Optional due date for the reminder.
        subject: Optional email subject for context in the body.
        sender: Optional email sender for context in the body.

    Returns:
        The ID of the newly created reminder.

    Raises:
        RemindersAppNotRunningError: If Reminders.app is not running.
        RemindersAppError: If the AppleScript fails.

    Example:
        >>> reminder_id = create_reminder_from_email(
        ...     message_id="12345",
        ...     name="Reply to Bob's email",
        ...     list_name="Work",
        ...     subject="Q4 Budget Review",
        ...     sender="bob@example.com",
        ... )
    """
    # Build body with message link
    body_parts = [f"From email: message://<{message_id}>"]
    if sender:
        body_parts.append(f"From: {sender}")
    if subject:
        body_parts.append(f"Subject: {subject}")

    body = "\n".join(body_parts)

    return create_reminder(
        name=name,
        list_name=list_name,
        body=body,
        due_date=due_date,
        priority=0,
    )


def complete_reminder(reminder_id: str, list_name: str) -> bool:
    """
    Mark a reminder as completed.

    Args:
        reminder_id: The unique ID of the reminder.
        list_name: The name of the list containing the reminder.

    Returns:
        True if successful.

    Raises:
        RemindersAppNotRunningError: If Reminders.app is not running.
        RemindersAppError: If the AppleScript fails (e.g., reminder not found).

    Example:
        >>> complete_reminder("x-apple-reminder://ABC123", "Work")
        True
    """
    list_escaped = escape_applescript_string(list_name)
    id_escaped = escape_applescript_string(reminder_id)

    script = f'''
    tell application "Reminders"
        set targetList to list "{list_escaped}"
        set targetReminder to first reminder of targetList whose id is "{id_escaped}"
        set completed of targetReminder to true
    end tell
    '''

    try:
        # Reminders.app (Catalyst) is slow - use 60s timeout
        run_applescript(script, timeout=60)
    except AppleScriptError as e:
        _check_reminders_running(str(e))
        raise RemindersAppError(str(e), e.script) from e

    return True


def uncomplete_reminder(reminder_id: str, list_name: str) -> bool:
    """
    Mark a completed reminder as incomplete.

    Args:
        reminder_id: The unique ID of the reminder.
        list_name: The name of the list containing the reminder.

    Returns:
        True if successful.

    Raises:
        RemindersAppNotRunningError: If Reminders.app is not running.
        RemindersAppError: If the AppleScript fails.
    """
    list_escaped = escape_applescript_string(list_name)
    id_escaped = escape_applescript_string(reminder_id)

    script = f'''
    tell application "Reminders"
        set targetList to list "{list_escaped}"
        set targetReminder to first reminder of targetList whose id is "{id_escaped}"
        set completed of targetReminder to false
    end tell
    '''

    try:
        run_applescript(script, timeout=60)
    except AppleScriptError as e:
        _check_reminders_running(str(e))
        raise RemindersAppError(str(e), e.script) from e

    return True


def delete_reminder(reminder_id: str, list_name: str) -> bool:
    """
    Delete a reminder from Reminders.app.

    Warning:
        This permanently deletes the reminder. It cannot be undone.

    Args:
        reminder_id: The unique ID of the reminder.
        list_name: The name of the list containing the reminder.

    Returns:
        True if successful.

    Raises:
        RemindersAppNotRunningError: If Reminders.app is not running.
        RemindersAppError: If the AppleScript fails (e.g., reminder not found).

    Example:
        >>> delete_reminder("x-apple-reminder://ABC123", "Work")
        True
    """
    list_escaped = escape_applescript_string(list_name)
    id_escaped = escape_applescript_string(reminder_id)

    script = f'''
    tell application "Reminders"
        set targetList to list "{list_escaped}"
        set targetReminder to first reminder of targetList whose id is "{id_escaped}"
        delete targetReminder
    end tell
    '''

    try:
        run_applescript(script, timeout=60)
    except AppleScriptError as e:
        _check_reminders_running(str(e))
        raise RemindersAppError(str(e), e.script) from e

    return True
