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


def _find_sysm() -> str | None:
    """Locate the sysm binary.

    Checks PATH first, then common user-local locations that may not
    be in launchd's restricted PATH.

    Returns:
        Full path to sysm binary, or None if not found
    """
    # Check PATH first
    path = shutil.which("sysm")
    if path:
        return path

    # Check common locations not in launchd's default PATH
    from pathlib import Path
    candidates = [
        Path.home() / "bin" / "sysm",
        Path.home() / ".local" / "bin" / "sysm",
        Path("/opt/homebrew/bin/sysm"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    return None


def is_sysm_available() -> bool:
    """Check if sysm binary is available.

    Returns:
        True if sysm is found, False otherwise
    """
    return _find_sysm() is not None


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
    sysm_path = _find_sysm()
    if not sysm_path:
        raise SysmNotFoundError("sysm binary not found on PATH or in ~/bin, ~/.local/bin, /opt/homebrew/bin")

    full_cmd = [sysm_path] + args
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
    """Parse date string from sysm.

    sysm returns dates in AppleScript's locale-dependent format:
    e.g., "Thursday, February 5, 2026 at 8:44:41 PM"

    Also handles ISO 8601 format as fallback.

    Args:
        date_str: Date string from sysm

    Returns:
        Parsed datetime or None if string is empty/None
    """
    if not date_str:
        return None

    try:
        # Try AppleScript locale format first (most common from sysm)
        # "Thursday, February 5, 2026 at 8:44:41 PM"
        return datetime.strptime(date_str, "%A, %B %d, %Y at %I:%M:%S %p")
    except (ValueError, AttributeError):
        pass

    try:
        # Try ISO 8601 with Z suffix
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
    - sysm "messageId" → EmailMessage.message_id (RFC 822 Message-ID)
    - sysm "subject" → EmailMessage.subject
    - sysm "from" → EmailMessage.sender
    - sysm "to" → EmailMessage.recipients (parsed from comma-separated)
    - sysm "dateReceived" → EmailMessage.date_received
    - sysm "dateSent" → EmailMessage.date_sent
    - sysm "isRead" → EmailMessage.is_read
    - sysm "mailbox" → EmailMessage.mailbox
    - sysm "accountName" → EmailMessage.account
    - sysm "content" → EmailMessage.content

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
        mailbox=data.get("mailbox", "INBOX"),
        account=data.get("accountName", ""),
        message_id=data.get("messageId", ""),
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

    # Parse messages — override mailbox from caller since sysm inbox
    # listing doesn't include it (avoids "INBOX" vs "Inbox" mismatch)
    messages = [parse_sysm_message(msg, content_loaded=False) for msg in data]
    for msg in messages:
        msg.mailbox = mailbox

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

    # Parse messages — override mailbox from caller since sysm inbox
    # listing doesn't include it (avoids "INBOX" vs "Inbox" mismatch)
    messages = [parse_sysm_message(msg, content_loaded=True) for msg in data]
    for msg in messages:
        msg.mailbox = mailbox

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
