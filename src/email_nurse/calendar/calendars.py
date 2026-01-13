"""Calendar retrieval from Apple Calendar.app."""

from dataclasses import dataclass

from email_nurse.applescript import AppleScriptError, AppNotRunningError, run_applescript

# ASCII control characters for parsing AppleScript output
RECORD_SEP = "\x1e"  # ASCII 30 - Record Separator
UNIT_SEP = "\x1f"  # ASCII 31 - Unit Separator


class CalendarAppError(AppleScriptError):
    """Raised when a Calendar.app AppleScript command fails."""

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
    Get all calendars from Calendar.app.

    Returns:
        List of Calendar objects.

    Raises:
        CalendarAppNotRunningError: If Calendar.app is not running.
        CalendarAppError: If the AppleScript fails.
    """
    script = '''
    tell application "Calendar"
        set output to ""
        set RS to (ASCII character 30)  -- Record Separator
        set US to (ASCII character 31)  -- Unit Separator

        repeat with cal in calendars
            set calName to name of cal
            -- Calendar.app doesn't expose uid for calendars - use name as ID
            set calId to calName

            -- Description may be missing
            set calDesc to ""
            try
                set calDesc to description of cal
                if calDesc is missing value then set calDesc to ""
            on error
                set calDesc to ""
            end try

            set calWritable to writable of cal

            if output is not "" then set output to output & RS
            set output to output & calId & US & calName & US & calDesc & US & (calWritable as string)
        end repeat

        return output
    end tell
    '''

    try:
        # Calendar.app is native (not Catalyst) - 30s should be plenty
        result = run_applescript(script, timeout=30)
    except AppleScriptError as e:
        _check_calendar_running(str(e))
        raise CalendarAppError(str(e), e.script) from e

    if not result:
        return []

    calendars = []
    for record in result.split(RECORD_SEP):
        parts = record.split(UNIT_SEP)
        if len(parts) >= 4:
            calendars.append(
                Calendar(
                    id=parts[0],
                    name=parts[1],
                    description=parts[2],
                    writable=parts[3].lower() == "true",
                )
            )

    return calendars


def get_calendar_names() -> list[str]:
    """
    Get just the names of all calendars.

    This is faster than get_calendars() when you only need names.

    Returns:
        List of calendar names.
    """
    script = '''
    tell application "Calendar"
        set output to ""
        set RS to (ASCII character 30)

        repeat with cal in calendars
            if output is not "" then set output to output & RS
            set output to output & name of cal
        end repeat

        return output
    end tell
    '''

    try:
        result = run_applescript(script, timeout=30)
    except AppleScriptError as e:
        _check_calendar_running(str(e))
        raise CalendarAppError(str(e), e.script) from e

    if not result:
        return []

    return result.split(RECORD_SEP)
