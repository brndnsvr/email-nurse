"""Write operations for Apple Reminders.app.

Uses sysm CLI for create and delete operations. AppleScript is kept for
complete_reminder() and uncomplete_reminder() because sysm completes by
name (not ID), which is a different API.
"""

from datetime import datetime

from email_nurse.applescript import AppleScriptError, escape_applescript_string, run_applescript
from email_nurse.mail.sysm import SysmError, create_reminder_sysm, delete_reminder_sysm
from email_nurse.reminders.lists import RemindersAppError, _check_reminders_running


def create_reminder(
    name: str,
    list_name: str = "Reminders",
    body: str = "",
    due_date: datetime | None = None,
    priority: int = 0,
) -> str:
    """
    Create a new reminder in Reminders.app via sysm.

    Args:
        name: The reminder title.
        list_name: Name of the list to add the reminder to (default: "Reminders").
        body: Optional notes/body text for the reminder.
        due_date: Optional due date for the reminder.
        priority: Priority level (0=none, 1=high, 5=medium, 9=low).

    Returns:
        The ID of the newly created reminder.

    Raises:
        RemindersAppError: If the operation fails.
    """
    due_str = None
    if due_date:
        due_str = due_date.strftime("%Y-%m-%d %H:%M")

    try:
        result = create_reminder_sysm(
            task=name,
            list_name=list_name,
            due=due_str,
            notes=body or None,
            priority=priority,
        )
    except SysmError as e:
        raise RemindersAppError(str(e)) from e

    return str(result.get("id", ""))


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


# --- AppleScript-only operations (sysm gaps) ---


def complete_reminder(reminder_id: str, list_name: str) -> bool:
    """
    Mark a reminder as completed.

    Uses AppleScript because sysm completes by name (not ID).

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
        set completed of targetReminder to true
    end tell
    '''

    try:
        run_applescript(script, timeout=60)
    except AppleScriptError as e:
        _check_reminders_running(str(e))
        raise RemindersAppError(str(e), e.script) from e

    return True


def uncomplete_reminder(reminder_id: str, list_name: str) -> bool:
    """
    Mark a completed reminder as incomplete.

    Uses AppleScript (sysm has no uncomplete equivalent).

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
    Delete a reminder from Reminders.app via sysm.

    Args:
        reminder_id: The unique ID of the reminder.
        list_name: The name of the list containing the reminder (unused by sysm).

    Returns:
        True if successful.

    Raises:
        RemindersAppError: If the operation fails.
    """
    try:
        return delete_reminder_sysm(reminder_id)
    except SysmError as e:
        raise RemindersAppError(str(e)) from e
