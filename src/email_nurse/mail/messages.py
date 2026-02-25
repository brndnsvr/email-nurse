"""Mail.app message retrieval and parsing.

Uses sysm CLI as the sole provider for message retrieval.
AppleScript is only used for load_message_headers() (sysm gap).
"""

import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime

from email_nurse.config import Settings
from email_nurse.mail.applescript import escape_applescript_string, run_applescript
from email_nurse.mail.sysm import (
    get_inbox_count_sysm,
    get_messages_metadata_sysm,
    get_messages_sysm,
    load_message_content_sysm,
)
from email_nurse.performance_tracker import get_tracker

logger = logging.getLogger(__name__)

# ASCII control characters for parsing AppleScript output
# These are virtually never found in email content, unlike "|||" or ":::"
RECORD_SEP = "\x1e"  # ASCII 30 - Record Separator
UNIT_SEP = "\x1f"  # ASCII 31 - Unit Separator


@dataclass
class EmailMessage:
    """Represents an email message from Mail.app."""

    id: str
    message_id: str
    subject: str
    sender: str
    recipients: list[str]
    date_received: datetime | None
    date_sent: datetime | None
    content: str
    is_read: bool
    mailbox: str
    account: str
    content_loaded: bool = True  # False when fetched via get_messages_metadata()
    headers: str = ""
    headers_loaded: bool = False

    @property
    def preview(self) -> str:
        """Get a short preview of the message content."""
        content = self.content[:200].replace("\n", " ").strip()
        return f"{content}..." if len(self.content) > 200 else content


def get_messages(
    mailbox: str = "INBOX",
    account: str | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list[EmailMessage]:
    """
    Retrieve messages from a mailbox with content via sysm.

    Args:
        mailbox: Name of the mailbox (default: INBOX).
        account: Specific account name, or None for all accounts.
        limit: Maximum number of messages to retrieve.
        unread_only: If True, only retrieve unread messages.

    Returns:
        List of EmailMessage objects.
    """
    settings = Settings()
    provider = settings.message_provider
    if provider not in ("sysm", "hybrid"):
        logger.info("message_provider=%s is deprecated, using sysm", provider)

    return get_messages_sysm(mailbox, account, limit, unread_only)


def get_messages_metadata(
    mailbox: str = "INBOX",
    account: str | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list[EmailMessage]:
    """
    Retrieve messages from a mailbox WITHOUT content (metadata only) via sysm.

    This is significantly faster than get_messages() because fetching
    message content is the primary bottleneck.

    Args:
        mailbox: Name of the mailbox (default: INBOX).
        account: Specific account name, or None for all accounts.
        limit: Maximum number of messages to retrieve.
        unread_only: If True, only retrieve unread messages.

    Returns:
        List of EmailMessage objects with content_loaded=False.
        Call load_message_content() to fetch content when needed.
    """
    settings = Settings()
    provider = settings.message_provider
    if provider not in ("sysm", "hybrid"):
        logger.info("message_provider=%s is deprecated, using sysm", provider)

    tracker = get_tracker()
    start_time = time.time()
    messages: list[EmailMessage] = []

    try:
        messages = get_messages_metadata_sysm(mailbox, account, limit, unread_only)
        return messages
    finally:
        duration = time.time() - start_time
        from email_nurse.performance_tracker import OperationMetric
        tracker.log_metric(OperationMetric(
            timestamp=datetime.now().isoformat(),
            operation="fetch_messages",
            provider="sysm",
            duration_seconds=round(duration, 3),
            message_count=len(messages),
            account=account or "all",
            mailbox=mailbox,
            success=True,
            metadata={"limit": limit, "unread_only": unread_only}
        ))


def load_message_content(email: EmailMessage) -> str:
    """
    Load the content for a message that was fetched via get_messages_metadata().

    Uses sysm for content loading.

    This updates the email object in-place AND returns the content.

    Args:
        email: EmailMessage with content_loaded=False

    Returns:
        The message content string.
        Also sets email.content and email.content_loaded=True.
    """
    if email.content_loaded:
        return email.content

    return load_message_content_sysm(email)


def load_message_headers(email: EmailMessage) -> str:
    """
    Load raw RFC headers for a message via AppleScript.

    This updates the email object in-place AND returns the headers.
    Always uses AppleScript since sysm doesn't support header retrieval.

    Args:
        email: EmailMessage to load headers for.

    Returns:
        The raw headers string.
        Also sets email.headers and email.headers_loaded=True.
    """
    if email.headers_loaded:
        return email.headers

    mailbox_escaped = escape_applescript_string(email.mailbox)
    account_escaped = escape_applescript_string(email.account)

    script = f'''
    tell application "Mail"
        set msg to first message of mailbox "{mailbox_escaped}" of account "{account_escaped}" whose id is {email.id}
        set msgHeaders to ""
        try
            set msgHeaders to all headers of msg
        end try
        return msgHeaders
    end tell
    '''

    try:
        headers = run_applescript(script, timeout=30) or ""
    except Exception:
        headers = ""

    email.headers = headers
    email.headers_loaded = True
    return headers


def get_message_by_id(message_id: str) -> EmailMessage | None:
    """
    Retrieve a specific message by its ID.

    Args:
        message_id: The Mail.app message ID.

    Returns:
        EmailMessage if found, None otherwise.
    """
    from email_nurse.mail.sysm import run_sysm_json, SysmError

    try:
        data = run_sysm_json(["mail", "read", str(message_id), "--json"])
        if isinstance(data, list):
            data = data[0] if data else None
        if not data:
            return None

        from email_nurse.mail.sysm import parse_sysm_message
        return parse_sysm_message(data, content_loaded=True)
    except SysmError:
        return None


def get_inbox_count(account: str, mailbox: str = "INBOX") -> int:
    """
    Get message count for a mailbox via sysm.

    Args:
        account: Account name to check.
        mailbox: Mailbox name (default: INBOX).

    Returns:
        Number of messages in the mailbox, or 0 on error.
    """
    return get_inbox_count_sysm(account, mailbox)


def _parse_date(date_str: str) -> datetime | None:
    """Parse an AppleScript date string into a datetime object.

    Handles various formats that AppleScript may return depending on
    the user's locale and system settings.
    """
    if not date_str or date_str == "missing value":
        return None

    # AppleScript returns dates in various formats depending on locale
    formats = [
        # US English locale formats
        "%A, %B %d, %Y at %I:%M:%S %p",  # Friday, December 20, 2024 at 10:30:00 AM
        "%A, %B %d, %Y at %H:%M:%S",  # Friday, December 20, 2024 at 22:30:00
        # Abbreviated day/month names
        "%a, %b %d, %Y at %I:%M:%S %p",  # Fri, Dec 20, 2024 at 10:30:00 AM
        "%a, %b %d, %Y at %H:%M:%S",  # Fri, Dec 20, 2024 at 22:30:00
        # Without day name
        "%B %d, %Y at %I:%M:%S %p",  # December 20, 2024 at 10:30:00 AM
        "%B %d, %Y at %H:%M:%S",  # December 20, 2024 at 22:30:00
        # ISO 8601 variants
        "%Y-%m-%d %H:%M:%S",  # 2024-12-20 22:30:00
        "%Y-%m-%dT%H:%M:%S",  # 2024-12-20T22:30:00
        "%Y-%m-%d",  # 2024-12-20
        # European-style formats
        "%d/%m/%Y %H:%M:%S",  # 20/12/2024 22:30:00
        "%d/%m/%Y %I:%M:%S %p",  # 20/12/2024 10:30:00 PM
        # US-style numeric
        "%m/%d/%Y %H:%M:%S",  # 12/20/2024 22:30:00
        "%m/%d/%Y %I:%M:%S %p",  # 12/20/2024 10:30:00 PM
        # Without seconds
        "%A, %B %d, %Y at %I:%M %p",  # Friday, December 20, 2024 at 10:30 AM
        "%Y-%m-%d %H:%M",  # 2024-12-20 22:30
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Log unrecognized format for debugging (only once per unique format)
    print(
        f"Warning: Unrecognized date format: {date_str!r}",
        file=sys.stderr,
    )
    return None
