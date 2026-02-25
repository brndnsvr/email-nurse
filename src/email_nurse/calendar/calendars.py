"""Calendar retrieval from Apple Calendar.app via sysm CLI."""

from dataclasses import dataclass

from email_nurse.applescript import AppleScriptError, AppNotRunningError
from email_nurse.mail.sysm import SysmError, get_calendars_sysm, get_calendar_names_sysm

# ASCII control characters for parsing AppleScript output (used by events.py)
RECORD_SEP = "\x1e"  # ASCII 30 - Record Separator
UNIT_SEP = "\x1f"  # ASCII 31 - Unit Separator


class CalendarAppError(AppleScriptError):
    """Raised when a Calendar.app operation fails."""

    pass


class CalendarAppNotRunningError(AppNotRunningError):
    """Raised when Calendar.app is not running."""

    def __init__(self) -> None:
        super().__init__("Calendar")


@dataclass
class Calendar:
    """Represents a calendar from Calendar.app."""

    id: str
    name: str
    description: str
    writable: bool

    def __str__(self) -> str:
        return self.name


def _check_calendar_running(error_msg: str) -> None:
    """Check if error indicates Calendar.app is not running."""
    if "-600" in error_msg or "not running" in error_msg.lower():
        raise CalendarAppNotRunningError()


def _ensure_calendar_running() -> None:
    """Launch Calendar.app if not running and wait for it to be ready."""
    import subprocess
    import time

    # Check if running
    result = subprocess.run(["pgrep", "-x", "Calendar"], capture_output=True)
    if result.returncode == 0:
        return  # Already running

    # Launch Calendar.app using open command (more reliable than AppleScript)
    subprocess.run(["open", "-a", "Calendar"], check=True)
    time.sleep(2)  # Give it time to fully initialize


def get_calendars() -> list[Calendar]:
    """
    Get all calendars from Calendar.app via sysm.

    Returns:
        List of Calendar objects.

    Raises:
        CalendarAppError: If the operation fails.
    """
    try:
        data = get_calendars_sysm()
    except SysmError as e:
        raise CalendarAppError(str(e)) from e

    calendars = []
    for cal in data:
        name = cal.get("name", "")
        calendars.append(
            Calendar(
                id=cal.get("id", name),
                name=name,
                description=cal.get("description", ""),
                writable=bool(cal.get("writable", True)),
            )
        )

    return calendars


def get_calendar_names() -> list[str]:
    """
    Get just the names of all calendars via sysm.

    Returns:
        List of calendar names.

    Raises:
        CalendarAppError: If the operation fails.
    """
    try:
        return get_calendar_names_sysm()
    except SysmError as e:
        raise CalendarAppError(str(e)) from e
