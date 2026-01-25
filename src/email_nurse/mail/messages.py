"""Mail.app message retrieval and parsing."""

import sys
from dataclasses import dataclass
from datetime import datetime

from email_nurse.mail.applescript import escape_applescript_string, run_applescript

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
    Retrieve messages from a mailbox.

    Args:
        mailbox: Name of the mailbox (default: INBOX).
        account: Specific account name, or None for all accounts.
        limit: Maximum number of messages to retrieve.
        unread_only: If True, only retrieve unread messages.

    Returns:
        List of EmailMessage objects.
    """
    mailbox_escaped = escape_applescript_string(mailbox)

    if account:
        account_escaped = escape_applescript_string(account)
        mailbox_ref = f'mailbox "{mailbox_escaped}" of account "{account_escaped}"'
    else:
        mailbox_ref = f'mailbox "{mailbox_escaped}"'

    read_filter = "whose read status is false" if unread_only else ""

    # Use lazy iteration with early exit to avoid timeout on large mailboxes.
    # The previous approach (set msgList to all messages, then limit) timed out
    # because AppleScript enumerated all messages upfront. This approach iterates
    # lazily and exits after 'limit' messages are processed.
    script = f'''
    tell application "Mail"
        set output to ""
        set RS to (ASCII character 30)  -- Record Separator
        set US to (ASCII character 31)  -- Unit Separator
        set i to 0

        repeat with msg in (messages of {mailbox_ref} {read_filter})
            -- Early exit after limit reached (avoids full enumeration)
            set i to i + 1
            if i > {limit} then exit repeat

            set msgId to id of msg as string
            set msgMessageId to message id of msg
            set msgSubject to subject of msg
            set msgSender to sender of msg
            set msgDateReceived to date received of msg as string
            set msgDateSent to date sent of msg as string
            set msgRead to read status of msg
            set msgMailbox to name of mailbox of msg
            set msgAccount to name of account of mailbox of msg

            -- Get recipients
            set recipList to ""
            repeat with recip in recipients of msg
                if recipList is not "" then set recipList to recipList & ","
                set recipList to recipList & (address of recip)
            end repeat

            -- Get content (first 5000 chars to avoid huge payloads)
            set msgContent to ""
            try
                set msgContent to content of msg
                if length of msgContent > 5000 then
                    set msgContent to text 1 thru 5000 of msgContent
                end if
            end try

            -- Build record with ASCII control chars as delimiters
            if output is not "" then set output to output & RS
            set output to output & msgId & US & msgMessageId & US & msgSubject & US & msgSender & US & recipList & US & msgDateReceived & US & msgDateSent & US & msgContent & US & msgRead & US & msgMailbox & US & msgAccount
        end repeat

        return output
    end tell
    '''

    result = run_applescript(script, timeout=600)  # 10 min timeout for large mailboxes
    if not result:
        return []

    messages = []
    for msg_str in result.split(RECORD_SEP):
        parts = msg_str.split(UNIT_SEP)
        if len(parts) >= 11:
            messages.append(
                EmailMessage(
                    id=parts[0],
                    message_id=parts[1],
                    subject=parts[2],
                    sender=parts[3],
                    recipients=parts[4].split(",") if parts[4] else [],
                    date_received=_parse_date(parts[5]),
                    date_sent=_parse_date(parts[6]),
                    content=parts[7],
                    is_read=parts[8].lower() == "true",
                    mailbox=parts[9],
                    account=parts[10],
                )
            )

    return messages


def get_messages_metadata(
    mailbox: str = "INBOX",
    account: str | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list[EmailMessage]:
    """
    Retrieve messages from a mailbox WITHOUT content (metadata only).

    This is significantly faster than get_messages() because fetching
    message content is the primary bottleneck in AppleScript/Mail.app
    communication.

    Args:
        mailbox: Name of the mailbox (default: INBOX).
        account: Specific account name, or None for all accounts.
        limit: Maximum number of messages to retrieve.
        unread_only: If True, only retrieve unread messages.

    Returns:
        List of EmailMessage objects with content_loaded=False.
        Call load_message_content() to fetch content when needed.
    """
    mailbox_escaped = escape_applescript_string(mailbox)

    if account:
        account_escaped = escape_applescript_string(account)
        mailbox_ref = f'mailbox "{mailbox_escaped}" of account "{account_escaped}"'
    else:
        mailbox_ref = f'mailbox "{mailbox_escaped}"'

    read_filter = "whose read status is false" if unread_only else ""

    # Metadata-only fetch - NO content extraction
    script = f'''
    tell application "Mail"
        set output to ""
        set RS to (ASCII character 30)  -- Record Separator
        set US to (ASCII character 31)  -- Unit Separator
        set i to 0

        repeat with msg in (messages of {mailbox_ref} {read_filter})
            -- Early exit after limit reached
            set i to i + 1
            if i > {limit} then exit repeat

            set msgId to id of msg as string
            set msgMessageId to message id of msg
            set msgSubject to subject of msg
            set msgSender to sender of msg
            set msgDateReceived to date received of msg as string
            set msgDateSent to date sent of msg as string
            set msgRead to read status of msg
            set msgMailbox to name of mailbox of msg
            set msgAccount to name of account of mailbox of msg

            -- Get recipients
            set recipList to ""
            repeat with recip in recipients of msg
                if recipList is not "" then set recipList to recipList & ","
                set recipList to recipList & (address of recip)
            end repeat

            -- NO content extraction - this is the key performance optimization

            -- Build record with ASCII control chars as delimiters
            if output is not "" then set output to output & RS
            set output to output & msgId & US & msgMessageId & US & msgSubject & US & msgSender & US & recipList & US & msgDateReceived & US & msgDateSent & US & msgRead & US & msgMailbox & US & msgAccount
        end repeat

        return output
    end tell
    '''

    result = run_applescript(script, timeout=120)  # Shorter timeout - metadata is fast
    if not result:
        return []

    messages = []
    for msg_str in result.split(RECORD_SEP):
        parts = msg_str.split(UNIT_SEP)
        if len(parts) >= 10:
            messages.append(
                EmailMessage(
                    id=parts[0],
                    message_id=parts[1],
                    subject=parts[2],
                    sender=parts[3],
                    recipients=parts[4].split(",") if parts[4] else [],
                    date_received=_parse_date(parts[5]),
                    date_sent=_parse_date(parts[6]),
                    content="",  # Not loaded
                    is_read=parts[7].lower() == "true",
                    mailbox=parts[8],
                    account=parts[9],
                    content_loaded=False,  # Mark as not loaded
                )
            )

    return messages


def load_message_content(email: EmailMessage) -> str:
    """
    Load the content for a message that was fetched via get_messages_metadata().

    This updates the email object in-place AND returns the content.

    Args:
        email: EmailMessage with content_loaded=False

    Returns:
        The message content (first 5000 chars).
        Also sets email.content and email.content_loaded=True.
    """
    if email.content_loaded:
        return email.content

    mailbox_escaped = escape_applescript_string(email.mailbox)
    account_escaped = escape_applescript_string(email.account)

    script = f'''
    tell application "Mail"
        set msg to first message of mailbox "{mailbox_escaped}" of account "{account_escaped}" whose id is {email.id}
        set msgContent to ""
        try
            set msgContent to content of msg
            if length of msgContent > 5000 then
                set msgContent to text 1 thru 5000 of msgContent
            end if
        end try
        return msgContent
    end tell
    '''

    try:
        content = run_applescript(script, timeout=30) or ""
    except Exception:
        content = ""

    email.content = content
    email.content_loaded = True
    return content


def get_message_by_id(message_id: str) -> EmailMessage | None:
    """
    Retrieve a specific message by its ID.

    Args:
        message_id: The Mail.app message ID.

    Returns:
        EmailMessage if found, None otherwise.
    """
    script = f'''
    tell application "Mail"
        set msg to first message whose id is {message_id}
        set msgMessageId to message id of msg
        set msgSubject to subject of msg
        set msgSender to sender of msg
        set msgDateReceived to date received of msg as string
        set msgDateSent to date sent of msg as string
        set msgRead to read status of msg
        set msgMailbox to name of mailbox of msg
        set msgAccount to name of account of mailbox of msg

        set recipList to ""
        repeat with recip in recipients of msg
            if recipList is not "" then set recipList to recipList & ","
            set recipList to recipList & (address of recip)
        end repeat

        set msgContent to ""
        try
            set msgContent to content of msg
        end try

        -- Use ASCII Unit Separator (31) as delimiter to avoid content collisions
        set US to (ASCII character 31)
        return "{message_id}" & US & msgMessageId & US & msgSubject & US & msgSender & US & recipList & US & msgDateReceived & US & msgDateSent & US & msgContent & US & msgRead & US & msgMailbox & US & msgAccount
    end tell
    '''

    try:
        result = run_applescript(script, timeout=30)
    except Exception:
        return None

    if not result:
        return None

    parts = result.split(UNIT_SEP)
    if len(parts) >= 11:
        return EmailMessage(
            id=parts[0],
            message_id=parts[1],
            subject=parts[2],
            sender=parts[3],
            recipients=parts[4].split(",") if parts[4] else [],
            date_received=_parse_date(parts[5]),
            date_sent=_parse_date(parts[6]),
            content=parts[7],
            is_read=parts[8].lower() == "true",
            mailbox=parts[9],
            account=parts[10],
        )

    return None


def get_inbox_count(account: str, mailbox: str = "INBOX") -> int:
    """
    Get message count for a mailbox (O(1) - just reads count property).

    This is much faster than get_messages() as it doesn't enumerate messages.
    Used by the watcher for efficient polling.

    Args:
        account: Account name to check.
        mailbox: Mailbox name (default: INBOX).

    Returns:
        Number of messages in the mailbox, or 0 on error.
    """
    account_escaped = escape_applescript_string(account)
    mailbox_escaped = escape_applescript_string(mailbox)

    script = f'''
    tell application "Mail"
        return count of messages of mailbox "{mailbox_escaped}" of account "{account_escaped}"
    end tell
    '''

    try:
        result = run_applescript(script, timeout=10)
        return int(result) if result else 0
    except (ValueError, Exception):
        return 0


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
