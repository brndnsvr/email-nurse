"""Shared AppleScript execution infrastructure for macOS app integrations."""

from email_nurse.applescript.base import (
    escape_applescript_string,
    run_applescript,
    run_applescript_json,
)
from email_nurse.applescript.errors import (
    AppleScriptError,
    AppNotRunningError,
)

__all__ = [
    "run_applescript",
    "run_applescript_json",
    "escape_applescript_string",
    "AppleScriptError",
    "AppNotRunningError",
]
