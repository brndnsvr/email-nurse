"""AppleScript execution wrapper for Mail.app integration."""

import subprocess
from typing import Any


class MailAppError(Exception):
    """Raised when an AppleScript command fails."""

    def __init__(self, message: str, script: str | None = None) -> None:
        super().__init__(message)
        self.script = script


def run_applescript(script: str, *, timeout: int = 30) -> str:
    """
    Execute an AppleScript and return the output.

    Args:
        script: The AppleScript code to execute.
        timeout: Maximum seconds to wait for execution.

    Returns:
        The stdout from the AppleScript execution.

    Raises:
        MailAppError: If the script fails to execute.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise MailAppError(f"AppleScript timed out after {timeout}s", script) from e

    if result.returncode != 0:
        error_msg = result.stderr.strip() or "Unknown AppleScript error"
        raise MailAppError(error_msg, script)

    return result.stdout.strip()


def run_applescript_json(script: str, *, timeout: int = 30) -> Any:
    """
    Execute an AppleScript that returns JSON and parse it.

    The script should return a JSON-formatted string.

    Args:
        script: The AppleScript code to execute.
        timeout: Maximum seconds to wait for execution.

    Returns:
        Parsed JSON data from the script output.

    Raises:
        MailAppError: If the script fails or output isn't valid JSON.
    """
    import json

    output = run_applescript(script, timeout=timeout)

    if not output:
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        raise MailAppError(f"Invalid JSON output: {e}", script) from e


def escape_applescript_string(value: str) -> str:
    """Escape a string for safe inclusion in AppleScript."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
