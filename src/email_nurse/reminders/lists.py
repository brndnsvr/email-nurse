"""Reminder list retrieval from Apple Reminders.app."""

from dataclasses import dataclass

from email_nurse.applescript import AppleScriptError, AppNotRunningError, run_applescript

# ASCII control character for parsing AppleScript output
RECORD_SEP = "\x1e"  # ASCII 30 - Record Separator
UNIT_SEP = "\x1f"  # ASCII 31 - Unit Separator


class RemindersAppError(AppleScriptError):
    """Raised when a Reminders.app AppleScript command fails."""

    pass


class RemindersAppNotRunningError(AppNotRunningError):
    """Raised when Reminders.app is not running."""

    def __init__(self) -> None:
        super().__init__("Reminders")


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
    Get all reminder lists from Reminders.app.

    Args:
        include_counts: If True, include incomplete reminder counts (slower).
                        If False, count will be 0 for all lists (faster).

    Returns:
        List of ReminderList objects.

    Raises:
        RemindersAppNotRunningError: If Reminders.app is not running.
        RemindersAppError: If the AppleScript fails.

    Note:
        Counting reminders in large lists can be extremely slow due to
        Reminders.app (Catalyst) performance. Set include_counts=False
        for faster results when counts aren't needed.
    """
    if include_counts:
        # Slower query that counts incomplete items per list
        # Can timeout on lists with many items
        script = '''
        tell application "Reminders"
            set output to ""
            set RS to (ASCII character 30)  -- Record Separator
            set US to (ASCII character 31)  -- Unit Separator

            repeat with reminderList in lists
                set listId to id of reminderList
                set listName to name of reminderList
                -- Count incomplete reminders only (slow for large lists!)
                set incompleteCount to count of (reminders of reminderList whose completed is false)

                if output is not "" then set output to output & RS
                set output to output & listId & US & listName & US & (incompleteCount as string)
            end repeat

            return output
        end tell
        '''
    else:
        # Faster query without counts
        script = '''
        tell application "Reminders"
            set output to ""
            set RS to (ASCII character 30)  -- Record Separator
            set US to (ASCII character 31)  -- Unit Separator

            repeat with reminderList in lists
                set listId to id of reminderList
                set listName to name of reminderList

                if output is not "" then set output to output & RS
                set output to output & listId & US & listName & US & "0"
            end repeat

            return output
        end tell
        '''

    try:
        # Even the fast query can be slow - use 60s timeout
        result = run_applescript(script, timeout=60)
    except AppleScriptError as e:
        _check_reminders_running(str(e))
        raise RemindersAppError(str(e), e.script) from e

    if not result:
        return []

    lists = []
    for record in result.split(RECORD_SEP):
        parts = record.split(UNIT_SEP)
        if len(parts) >= 3:
            try:
                count = int(parts[2])
            except ValueError:
                count = 0
            lists.append(
                ReminderList(
                    id=parts[0],
                    name=parts[1],
                    count=count,
                )
            )

    return lists


def get_list_names() -> list[str]:
    """
    Get just the names of all reminder lists.

    This is faster than get_lists() when you only need names.

    Returns:
        List of reminder list names.
    """
    script = '''
    tell application "Reminders"
        set output to ""
        set RS to (ASCII character 30)

        repeat with reminderList in lists
            if output is not "" then set output to output & RS
            set output to output & name of reminderList
        end repeat

        return output
    end tell
    '''

    try:
        result = run_applescript(script, timeout=60)
    except AppleScriptError as e:
        _check_reminders_running(str(e))
        raise RemindersAppError(str(e), e.script) from e

    if not result:
        return []

    return result.split(RECORD_SEP)
