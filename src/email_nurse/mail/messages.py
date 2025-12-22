"""Mail.app message retrieval and parsing."""

from dataclasses import dataclass
from datetime import datetime

from email_nurse.mail.applescript import escape_applescript_string, run_applescript


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

    script = f'''
    tell application "Mail"
        set output to ""
        set msgList to (messages of {mailbox_ref} {read_filter})
        set msgCount to count of msgList
        if msgCount > {limit} then set msgCount to {limit}

        repeat with i from 1 to msgCount
            set msg to item i of msgList
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

            -- Build record with ||| as record separator and ::: as field separator
            if output is not "" then set output to output & "|||"
            set output to output & msgId & ":::" & msgMessageId & ":::" & msgSubject & ":::" & msgSender & ":::" & recipList & ":::" & msgDateReceived & ":::" & msgDateSent & ":::" & msgContent & ":::" & msgRead & ":::" & msgMailbox & ":::" & msgAccount
        end repeat

        return output
    end tell
    '''

    result = run_applescript(script, timeout=120)  # Longer timeout for large mailboxes
    if not result:
        return []

    messages = []
    for msg_str in result.split("|||"):
        parts = msg_str.split(":::")
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

        return "{message_id}" & ":::" & msgMessageId & ":::" & msgSubject & ":::" & msgSender & ":::" & recipList & ":::" & msgDateReceived & ":::" & msgDateSent & ":::" & msgContent & ":::" & msgRead & ":::" & msgMailbox & ":::" & msgAccount
    end tell
    '''

    try:
        result = run_applescript(script, timeout=30)
    except Exception:
        return None

    if not result:
        return None

    parts = result.split(":::")
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


def _parse_date(date_str: str) -> datetime | None:
    """Parse an AppleScript date string into a datetime object."""
    if not date_str or date_str == "missing value":
        return None

    # AppleScript returns dates like "Friday, December 20, 2024 at 10:30:00 AM"
    formats = [
        "%A, %B %d, %Y at %I:%M:%S %p",
        "%A, %B %d, %Y at %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None
