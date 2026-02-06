"""sysm CLI wrapper for faster message retrieval.

This module provides functions to interact with the sysm CLI tool for retrieving
email messages from Mail.app. Testing shows sysm is 44-51% faster than AppleScript
for message retrieval operations.

Performance benchmarks:
- 10 messages: 1.14s (sysm) vs 2.05s (AppleScript) = 44% faster
- 50 messages: 5.09s (sysm) vs 10.5s (AppleScript) = 51% faster
"""

import json
import logging
import shutil
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from email_nurse.mail.messages import EmailMessage

logger = logging.getLogger(__name__)


class SysmError(Exception):
    """Raised when sysm command fails."""

    def __init__(self, message: str, command: list[str] | None = None):
        super().__init__(message)
        self.command = command


class SysmNotFoundError(SysmError):
    """Raised when sysm binary is not found."""


class SysmTimeoutError(SysmError):
    """Raised when sysm times out."""


def is_sysm_available() -> bool:
    """Check if sysm binary is available on PATH.

    Returns:
        True if sysm is found, False otherwise
    """
    return shutil.which("sysm") is not None


def run_sysm(args: list[str], timeout: int = 30) -> str:
    """Execute sysm CLI command and return stdout.

    Args:
        args: Command arguments (e.g., ["mail", "inbox", "--json"])
        timeout: Command timeout in seconds

    Returns:
        Command stdout as string

    Raises:
        SysmNotFoundError: If sysm binary not found
        SysmTimeoutError: If command times out
        SysmError: If command fails
    """
    if not is_sysm_available():
        raise SysmNotFoundError("sysm binary not found on PATH")

    full_cmd = ["sysm"] + args
    logger.debug(f"Running sysm command: {' '.join(full_cmd)}")

    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True
        )
        return result.stdout
    except subprocess.TimeoutExpired as e:
        raise SysmTimeoutError(f"sysm command timed out after {timeout}s", full_cmd) from e
    except subprocess.CalledProcessError as e:
        raise SysmError(
            f"sysm command failed with exit code {e.returncode}: {e.stderr}",
            full_cmd
        ) from e
    except Exception as e:
        raise SysmError(f"sysm command failed: {e}", full_cmd) from e


def run_sysm_json(args: list[str], timeout: int = 30) -> dict | list[dict]:
    """Execute sysm and parse JSON output.

    Args:
        args: Command arguments (must include --json flag)
        timeout: Command timeout in seconds

    Returns:
        Parsed JSON object (dict or list of dicts)

    Raises:
        SysmError: If JSON parsing fails or command fails
    """
    stdout = run_sysm(args, timeout)

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise SysmError(f"Failed to parse sysm JSON output: {e}") from e


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse date string from sysm (ISO 8601 format).

    sysm returns dates in ISO 8601 format (e.g., "2025-01-20T10:30:00Z").

    Args:
        date_str: Date string from sysm

    Returns:
        Parsed datetime or None if string is empty/None
    """
    if not date_str:
        return None

    try:
        # Handle both with and without timezone
        if date_str.endswith('Z'):
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return datetime.fromisoformat(date_str)
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse date '{date_str}': {e}")
        return None


def _parse_recipients(recipients_str: str | None) -> list[str]:
    """Parse recipients string from sysm.

    sysm may return a comma-separated string for multiple recipients.

    Args:
        recipients_str: Recipients string from sysm (e.g., "a@ex.com, b@ex.com")

    Returns:
        List of email addresses
    """
    if not recipients_str:
        return []

    # Split on comma and strip whitespace
    return [addr.strip() for addr in recipients_str.split(',') if addr.strip()]


def parse_sysm_message(data: dict, content_loaded: bool = True) -> "EmailMessage":
    """Convert sysm JSON message to EmailMessage dataclass.

    Field mapping:
    - sysm "id" → EmailMessage.id
    - sysm "subject" → EmailMessage.subject
    - sysm "from" → EmailMessage.sender
    - sysm "to" → EmailMessage.recipients (parsed from comma-separated)
    - sysm "dateReceived" → EmailMessage.date_received
    - sysm "dateSent" → EmailMessage.date_sent
    - sysm "isRead" → EmailMessage.is_read
    - sysm "mailbox" → EmailMessage.mailbox
    - sysm "accountName" → EmailMessage.account
    - sysm "content" → EmailMessage.content
    - EmailMessage.message_id = "" (sysm doesn't provide RFC 822 Message-ID)

    Args:
        data: JSON object from sysm
        content_loaded: Whether content is included in data

    Returns:
        EmailMessage instance
    """
    from email_nurse.mail.messages import EmailMessage

    return EmailMessage(
        id=str(data.get("id", "")),
        subject=data.get("subject", ""),
        sender=data.get("from", ""),
        recipients=_parse_recipients(data.get("to")),
        date_received=_parse_date(data.get("dateReceived")),
        date_sent=_parse_date(data.get("dateSent")),
        content=data.get("content", "") if content_loaded else "",
        is_read=bool(data.get("isRead", False)),
        mailbox=data.get("mailbox", ""),
        account=data.get("accountName", ""),
        message_id="",  # sysm doesn't provide RFC 822 Message-ID
        content_loaded=content_loaded
    )


def get_messages_metadata_sysm(
    mailbox: str = "INBOX",
    account: str | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list["EmailMessage"]:
    """Retrieve message metadata using sysm (no content).

    Args:
        mailbox: Mailbox name (default: "INBOX")
        account: Account name filter (optional)
        limit: Maximum number of messages to retrieve
        unread_only: If True, only retrieve unread messages

    Returns:
        List of EmailMessage objects with metadata only (content_loaded=False)

    Raises:
        SysmError: If sysm command fails
    """
    # Build command
    if unread_only:
        cmd = ["mail", "unread"]
    else:
        cmd = ["mail", "inbox"]

    cmd.extend(["--limit", str(limit), "--json"])

    if account:
        cmd.extend(["--account", account])

    # Execute and parse
    data = run_sysm_json(cmd)

    # Convert to list if single message returned as dict
    if isinstance(data, dict):
        data = [data]

    # Parse messages
    messages = [parse_sysm_message(msg, content_loaded=False) for msg in data]

    logger.info(f"Retrieved {len(messages)} message(s) metadata via sysm from {mailbox}")
    return messages


def get_messages_sysm(
    mailbox: str = "INBOX",
    account: str | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list["EmailMessage"]:
    """Retrieve messages with content using sysm.

    Args:
        mailbox: Mailbox name (default: "INBOX")
        account: Account name filter (optional)
        limit: Maximum number of messages to retrieve
        unread_only: If True, only retrieve unread messages

    Returns:
        List of EmailMessage objects with content loaded

    Raises:
        SysmError: If sysm command fails
    """
    # Build command
    if unread_only:
        cmd = ["mail", "unread"]
    else:
        cmd = ["mail", "inbox"]

    cmd.extend(["--with-content", "--limit", str(limit), "--json"])

    if account:
        cmd.extend(["--account", account])

    # Execute and parse
    data = run_sysm_json(cmd)

    # Convert to list if single message returned as dict
    if isinstance(data, dict):
        data = [data]

    # Parse messages
    messages = [parse_sysm_message(msg, content_loaded=True) for msg in data]

    logger.info(f"Retrieved {len(messages)} message(s) with content via sysm from {mailbox}")
    return messages


def load_message_content_sysm(email: "EmailMessage") -> str:
    """Load content for a message using sysm.

    Args:
        email: EmailMessage to load content for

    Returns:
        Message content string

    Raises:
        SysmError: If sysm command fails
    """
    cmd = ["mail", "read", email.id, "--json"]
    data = run_sysm_json(cmd)

    # Handle single message response
    if isinstance(data, dict):
        content = data.get("content", "")
    else:
        # If list, take first item
        content = data[0].get("content", "") if data else ""

    # Update email object in-place
    email.content = content
    email.content_loaded = True

    logger.debug(f"Loaded content for message {email.id} via sysm ({len(content)} chars)")
    return content
