"""Reminder list retrieval from Apple Reminders.app via sysm CLI."""

from dataclasses import dataclass

from email_nurse.applescript import AppleScriptError, AppNotRunningError
from email_nurse.mail.sysm import SysmError, get_reminder_lists_sysm


class RemindersAppError(AppleScriptError):
    """Raised when a Reminders.app operation fails."""

    pass


class RemindersAppNotRunningError(AppNotRunningError):
    """Raised when Reminders.app is not running."""

    def __init__(self) -> None:
        super().__init__("Reminders")


# ASCII control characters kept for backward compat with any test fixtures
RECORD_SEP = "\x1e"  # ASCII 30 - Record Separator
UNIT_SEP = "\x1f"  # ASCII 31 - Unit Separator


@dataclass
class ReminderList:
    """Represents a reminder list from Reminders.app."""

    id: str
    name: str
    count: int  # Number of incomplete reminders

    def __str__(self) -> str:
        return f"{self.name} ({self.count} items)"


def _check_reminders_running(error_msg: str) -> None:
    """Check if error indicates Reminders.app is not running."""
    if "-600" in error_msg or "not running" in error_msg.lower():
        raise RemindersAppNotRunningError()


def get_lists(include_counts: bool = False) -> list[ReminderList]:
    """
    Get all reminder lists from Reminders.app via sysm.

    Args:
        include_counts: If True, include incomplete reminder counts.
                        Note: sysm may or may not include counts in JSON.

    Returns:
        List of ReminderList objects.

    Raises:
        RemindersAppError: If the operation fails.
    """
    try:
        data = get_reminder_lists_sysm()
    except SysmError as e:
        raise RemindersAppError(str(e)) from e

    lists = []
    for item in data:
        name = item.get("name", "")
        list_id = item.get("id", name)
        count = int(item.get("count", item.get("reminderCount", 0)))
        lists.append(
            ReminderList(
                id=str(list_id),
                name=name,
                count=count,
            )
        )

    return lists


def get_list_names() -> list[str]:
    """
    Get just the names of all reminder lists via sysm.

    Returns:
        List of reminder list names.

    Raises:
        RemindersAppError: If the operation fails.
    """
    try:
        data = get_reminder_lists_sysm()
    except SysmError as e:
        raise RemindersAppError(str(e)) from e

    return [item.get("name", "") for item in data if item.get("name")]
