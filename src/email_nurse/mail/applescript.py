"""AppleScript execution wrapper for Mail.app integration.

This module re-exports from the shared applescript package for backward
compatibility, while providing Mail-specific error classes.
"""

from email_nurse.applescript.base import (
    escape_applescript_string,
    run_applescript,
    run_applescript_json,
)
from email_nurse.applescript.errors import AppleScriptError, AppNotRunningError

__all__ = [
    "run_applescript",
    "run_applescript_json",
    "escape_applescript_string",
    "MailAppError",
    "MailAppNotRunningError",
]


class MailAppError(AppleScriptError):
    """Raised when a Mail.app AppleScript command fails."""

    pass


class MailAppNotRunningError(AppNotRunningError):
    """Raised when Mail.app is not running."""

    def __init__(self) -> None:
        super().__init__("Mail.app")
