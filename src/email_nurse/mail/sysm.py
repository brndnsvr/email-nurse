"""sysm CLI wrapper for Mail.app, Calendar, Reminders, and notifications.

This module provides functions to interact with the sysm CLI tool, replacing
AppleScript for all supported operations. sysm has its own TCC grant and is
not affected by the osascript -1743 automation permission loss.

Covers: mail actions/queries, calendar, reminders, notifications.
AppleScript is still used for gaps noted in each section.
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

    Uses ``sysm mail search --after`` instead of ``sysm mail inbox`` to
    avoid enumerating the full mailbox, which causes AppleScript timeouts
    on large inboxes.

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
    if unread_only:
        cmd = ["mail", "unread", "--limit", str(limit), "--json"]
        if account:
            cmd.extend(["--account", account])
        data = run_sysm_json(cmd)
    else:
        # Try inbox listing first. If it times out (common with large
        # inboxes), fall back to search with a date filter which is
        # index-backed and doesn't enumerate the full mailbox.
        cmd = ["mail", "inbox", "--limit", str(limit), "--json"]
        if account:
            cmd.extend(["--account", account])
        try:
            data = run_sysm_json(cmd)
        except SysmTimeoutError:
            logger.info(
                "Inbox listing timed out, falling back to search"
            )
            from datetime import datetime, timedelta
            after_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            cmd = ["mail", "search", "--after", after_date,
                   "--limit", str(limit), "--json"]
            if account:
                cmd.extend(["--account", account])
            data = run_sysm_json(cmd)

    # Convert to list if single message returned as dict
    if isinstance(data, dict):
        data = [data]

    # Parse messages — override mailbox from caller since sysm search
    # doesn't filter by mailbox (avoids "INBOX" vs "Inbox" mismatch)
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


# ---------------------------------------------------------------------------
# Mail actions
# ---------------------------------------------------------------------------


def move_message_sysm(
    message_id: str,
    target_mailbox: str,
    target_account: str | None = None,
) -> bool:
    """Move a message to a different mailbox via sysm.

    Args:
        message_id: The Mail.app message ID.
        target_mailbox: Name of the destination mailbox.
        target_account: Account for the target mailbox (optional).

    Returns:
        True if the move was successful.
    """
    cmd = ["mail", "move", str(message_id), target_mailbox]
    if target_account:
        cmd.extend(["--account", target_account])
    run_sysm(cmd, timeout=30)
    return True


def move_messages_batch_sysm(
    moves: list,
) -> tuple[int, set[str]]:
    """Move multiple messages via sequential sysm calls.

    Args:
        moves: List of PendingMove objects (from actions.py).

    Returns:
        Tuple of (total_moved_count, set of successfully moved message IDs).
    """
    if not moves:
        return 0, set()

    total_moved = 0
    moved_ids: set[str] = set()

    for move in moves:
        try:
            # Determine account: use target_account, fall back to source_account
            account = move.target_account
            if account == "__local__":
                account = None
            elif not account:
                account = move.source_account

            move_message_sysm(move.message_id, move.target_mailbox, account)
            total_moved += 1
            moved_ids.add(move.message_id)
        except SysmError as e:
            logger.error(f"sysm move failed for message {move.message_id} -> {move.target_mailbox}: {e}")

    return total_moved, moved_ids


def delete_message_sysm(message_id: str) -> bool:
    """Delete a message via sysm (moves to Trash).

    Args:
        message_id: The Mail.app message ID.

    Returns:
        True if the delete was successful.
    """
    run_sysm(["mail", "delete", str(message_id), "--force"], timeout=30)
    return True


def mark_as_read_sysm(message_id: str, *, read: bool = True) -> bool:
    """Mark a message as read or unread via sysm.

    Args:
        message_id: The Mail.app message ID.
        read: True to mark as read, False to mark as unread.

    Returns:
        True if successful.
    """
    flag = "--read" if read else "--unread"
    run_sysm(["mail", "mark", str(message_id), flag], timeout=30)
    return True


def flag_message_sysm(message_id: str, *, flagged: bool = True) -> bool:
    """Flag or unflag a message via sysm.

    Args:
        message_id: The Mail.app message ID.
        flagged: True to flag, False to unflag.

    Returns:
        True if successful.
    """
    flag = "--flag" if flagged else "--unflag"
    run_sysm(["mail", "flag", str(message_id), flag], timeout=30)
    return True


def reply_to_message_sysm(
    message_id: str,
    body: str,
    *,
    reply_all: bool = False,
    send: bool = False,
) -> bool:
    """Reply to a message via sysm.

    Args:
        message_id: The Mail.app message ID.
        body: Reply body text.
        reply_all: If True, reply to all recipients.
        send: If True, send immediately.

    Returns:
        True if successful.
    """
    cmd = ["mail", "reply", str(message_id), "--body", body]
    if reply_all:
        cmd.append("--all")
    if send:
        cmd.append("--send")
    run_sysm(cmd, timeout=30)
    return True


def forward_message_sysm(
    message_id: str,
    to: str,
    *,
    body: str = "",
    send: bool = False,
) -> bool:
    """Forward a message via sysm.

    Args:
        message_id: The Mail.app message ID.
        to: Recipient email address.
        body: Optional body text to include.
        send: If True, send immediately.

    Returns:
        True if successful.
    """
    cmd = ["mail", "forward", str(message_id), "--to", to]
    if body:
        cmd.extend(["--body", body])
    if send:
        cmd.append("--send")
    run_sysm(cmd, timeout=30)
    return True


def compose_email_sysm(
    to: str,
    subject: str,
    body: str,
    *,
    account: str | None = None,
    html_body: str | None = None,
    send: bool = True,
) -> bool:
    """Compose and send an email via sysm.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Plain text body.
        account: Account to send from (optional).
        html_body: HTML body (optional).
        send: If True, send immediately (adds --force to skip prompt).

    Returns:
        True if successful.
    """
    cmd = ["mail", "send", "--to", to, "--subject", subject, "--body", body]
    if html_body:
        cmd.extend(["--html-body", html_body])
    if account:
        cmd.extend(["--account", account])
    if send:
        cmd.append("--force")
    run_sysm(cmd, timeout=30)
    return True


# ---------------------------------------------------------------------------
# Mail queries
# ---------------------------------------------------------------------------


def get_accounts_sysm() -> list[dict]:
    """Get all configured email accounts via sysm.

    Returns:
        List of account dicts with keys from sysm JSON output.
    """
    data = run_sysm_json(["mail", "accounts", "--json"], timeout=15)
    if isinstance(data, dict):
        data = [data]
    return data


def get_mailboxes_sysm(account: str | None = None) -> list[dict]:
    """Get mailboxes via sysm.

    Args:
        account: Filter by account name (optional).

    Returns:
        List of mailbox dicts from sysm JSON output.
    """
    cmd = ["mail", "mailboxes", "--json"]
    if account:
        cmd.extend(["--account", account])
    data = run_sysm_json(cmd, timeout=15)
    if isinstance(data, dict):
        data = [data]
    return data


def get_inbox_count_sysm(account: str, mailbox: str = "INBOX") -> int:
    """Get message count for a mailbox via sysm.

    Fetches the mailbox list and extracts messageCount for the target mailbox.

    Args:
        account: Account name.
        mailbox: Mailbox name (default: INBOX).

    Returns:
        Number of messages, or 0 on error.
    """
    try:
        mailboxes = get_mailboxes_sysm(account)
        for mbox in mailboxes:
            if mbox.get("name", "").upper() == mailbox.upper():
                return int(mbox.get("messageCount", mbox.get("unreadCount", 0)))
        return 0
    except (SysmError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def get_calendars_sysm() -> list[dict]:
    """Get all calendars via sysm.

    Returns:
        List of calendar dicts from sysm JSON output.
    """
    data = run_sysm_json(["calendar", "calendars", "--json"], timeout=15)
    if isinstance(data, dict):
        data = [data]
    return data


def get_calendar_names_sysm() -> list[str]:
    """Get just the names of all calendars via sysm.

    Returns:
        List of calendar names.
    """
    calendars = get_calendars_sysm()
    return [cal.get("name", "") for cal in calendars if cal.get("name")]


def create_event_sysm(
    title: str,
    start: str,
    *,
    end: str | None = None,
    calendar: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    all_day: bool = False,
) -> dict:
    """Create a calendar event via sysm.

    Args:
        title: Event title.
        start: Start date/time string (e.g., "2026-02-25 14:00").
        end: End date/time string (optional, defaults to start + 1hr).
        calendar: Calendar name (optional).
        location: Event location (optional).
        notes: Event notes (optional).
        all_day: Whether this is an all-day event.

    Returns:
        Dict with created event details from sysm JSON output.
    """
    cmd = ["calendar", "add", title, "--start", start, "--json"]
    if end:
        cmd.extend(["--end", end])
    if calendar:
        cmd.extend(["--calendar", calendar])
    if location:
        cmd.extend(["--location", location])
    if notes:
        cmd.extend(["--notes", notes])
    if all_day:
        cmd.append("--all-day")
    data = run_sysm_json(cmd, timeout=30)
    return data if isinstance(data, dict) else (data[0] if data else {})


def get_events_sysm(
    date: str,
    *,
    end_date: str | None = None,
    calendar: str | None = None,
) -> list[dict]:
    """Get calendar events for a date/range via sysm.

    Args:
        date: Date string (e.g., "2026-02-25", "tomorrow").
        end_date: End date for range query (optional).
        calendar: Filter by calendar name (optional).

    Returns:
        List of event dicts.
    """
    cmd = ["calendar", "list", date, "--json"]
    if end_date:
        cmd.extend(["--end-date", end_date])
    if calendar:
        cmd.extend(["--calendar", calendar])
    data = run_sysm_json(cmd, timeout=30)
    if isinstance(data, dict):
        data = [data]
    return data


def get_events_today_sysm() -> list[dict]:
    """Get today's calendar events via sysm.

    Returns:
        List of event dicts.
    """
    data = run_sysm_json(["calendar", "today", "--json"], timeout=15)
    if isinstance(data, dict):
        data = [data]
    return data


def delete_event_sysm(title: str) -> bool:
    """Delete a calendar event by title via sysm.

    Note: sysm deletes by title, not UID. This is a different API than
    the AppleScript version which uses event UID.

    Args:
        title: Event title to delete.

    Returns:
        True if successful.
    """
    run_sysm(["calendar", "delete", title, "--force"], timeout=30)
    return True


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


def get_reminder_lists_sysm() -> list[dict]:
    """Get all reminder lists via sysm.

    Returns:
        List of reminder list dicts from sysm JSON output.
    """
    data = run_sysm_json(["reminders", "lists", "--json"], timeout=30)
    if isinstance(data, dict):
        data = [data]
    return data


def get_reminders_sysm(
    list_name: str | None = None,
    *,
    include_completed: bool = False,
) -> list[dict]:
    """Get reminders via sysm.

    Args:
        list_name: Filter to specific list (optional).
        include_completed: If True, include completed reminders.

    Returns:
        List of reminder dicts.
    """
    cmd = ["reminders", "list"]
    if list_name:
        cmd.append(list_name)
    if include_completed:
        cmd.append("--all")
    cmd.append("--json")
    data = run_sysm_json(cmd, timeout=60)
    if isinstance(data, dict):
        data = [data]
    return data


def create_reminder_sysm(
    task: str,
    *,
    list_name: str | None = None,
    due: str | None = None,
    notes: str | None = None,
    priority: int = 0,
) -> dict:
    """Create a reminder via sysm.

    Args:
        task: Reminder text.
        list_name: Target list name (optional, defaults to "Reminders").
        due: Due date string (optional).
        notes: Notes text (optional).
        priority: Priority (0=none, 1=high, 5=medium, 9=low).

    Returns:
        Dict with created reminder details from sysm JSON output.
    """
    cmd = ["reminders", "add", task]
    if list_name:
        cmd.extend(["--list", list_name])
    if due:
        cmd.extend(["--due", due])
    if notes:
        cmd.extend(["--notes", notes])
    if priority > 0:
        cmd.extend(["--priority", str(priority)])
    cmd.append("--json")
    data = run_sysm_json(cmd, timeout=60)
    return data if isinstance(data, dict) else (data[0] if data else {})


def complete_reminder_sysm(name: str) -> bool:
    """Complete a reminder by name via sysm.

    Note: sysm completes by name, not ID. This is a different API than
    the AppleScript version which uses reminder ID.

    Args:
        name: Reminder name to complete.

    Returns:
        True if successful.
    """
    run_sysm(["reminders", "complete", name], timeout=30)
    return True


def delete_reminder_sysm(reminder_id: str) -> bool:
    """Delete a reminder by ID via sysm.

    Args:
        reminder_id: The reminder ID.

    Returns:
        True if successful.
    """
    run_sysm(["reminders", "delete", reminder_id, "--force"], timeout=30)
    return True


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def notify_sysm(
    title: str,
    body: str,
    *,
    subtitle: str | None = None,
) -> bool:
    """Send a macOS notification via sysm.

    Args:
        title: Notification title.
        body: Notification body text.
        subtitle: Optional subtitle.

    Returns:
        True if successful, False on error.
    """
    cmd = ["notify", "send", title, body]
    if subtitle:
        cmd.extend(["--subtitle", subtitle])
    try:
        run_sysm(cmd, timeout=10)
        return True
    except SysmError:
        return False
