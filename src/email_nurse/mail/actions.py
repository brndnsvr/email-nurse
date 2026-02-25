"""Mail.app message actions - move, delete, reply, forward, etc.

Uses sysm CLI for all supported operations. AppleScript is only used for
create_mailbox(), create_local_mailbox(), and get_local_mailboxes() (sysm gaps).
"""

import logging
from dataclasses import dataclass
from difflib import SequenceMatcher

from email_nurse.mail.applescript import escape_applescript_string, run_applescript
from email_nurse.mail.sysm import (
    compose_email_sysm,
    delete_message_sysm,
    flag_message_sysm,
    forward_message_sysm,
    get_mailboxes_sysm,
    mark_as_read_sysm,
    move_message_sysm,
    move_messages_batch_sysm,
    reply_to_message_sysm,
)

logger = logging.getLogger(__name__)

# ASCII control character for parsing AppleScript output
# Virtually never found in mailbox names, preventing parse errors
RECORD_SEP = "\x1e"  # ASCII 30 - Record Separator

# Virtual Gmail mailboxes that can't be referenced directly in AppleScript
VIRTUAL_MAILBOXES = {
    "All Mail",
    "[Gmail]/All Mail",
    "Important",
    "Starred",
}

# Sentinel value to indicate local "On My Mac" mailbox routing
# When passed as target_account, the move will use no account qualifier
LOCAL_ACCOUNT_KEY = "__local__"


def get_all_mailboxes(account: str) -> list[str]:
    """
    Get all mailbox names for an account.

    Args:
        account: The account name (e.g., "iCloud", "Google").

    Returns:
        List of mailbox names.
    """
    mailboxes = get_mailboxes_sysm(account)
    return [mbox.get("name", "") for mbox in mailboxes if mbox.get("name")]


def find_similar_mailbox(target: str, existing: list[str], threshold: float = 0.6) -> str | None:
    """
    Find a similar mailbox name using fuzzy matching.

    Args:
        target: The target mailbox name to match.
        existing: List of existing mailbox names.
        threshold: Minimum similarity ratio (0.0 to 1.0) to consider a match.

    Returns:
        The most similar existing mailbox name, or None if no good match.
    """
    target_lower = target.lower()
    best_match = None
    best_ratio = 0.0

    for mailbox in existing:
        # Check for exact match first (case-insensitive)
        if mailbox.lower() == target_lower:
            return mailbox

        # Calculate similarity ratio
        ratio = SequenceMatcher(None, target_lower, mailbox.lower()).ratio()
        if ratio > best_ratio and ratio >= threshold:
            best_ratio = ratio
            best_match = mailbox

    return best_match


# --- AppleScript-only operations (sysm gaps) ---


def create_mailbox(mailbox: str, account: str) -> bool:
    """
    Create a new mailbox in an account.

    Uses AppleScript (sysm has no mailbox creation support).

    Args:
        mailbox: Name of the mailbox to create.
        account: Account to create the mailbox in.

    Returns:
        True if successful.
    """
    mailbox_escaped = escape_applescript_string(mailbox)
    account_escaped = escape_applescript_string(account)
    script = f'''
    tell application "Mail"
        set targetAcct to account "{account_escaped}"
        make new mailbox with properties {{name:"{mailbox_escaped}"}} at targetAcct
    end tell
    '''
    run_applescript(script)
    return True


def get_local_mailboxes() -> list[str]:
    """
    Get all local 'On My Mac' mailbox names.

    Uses AppleScript (sysm has no local-only mailbox filter).

    Returns:
        List of local mailbox names.
    """
    script = '''
    tell application "Mail"
        set output to ""
        set RS to (ASCII character 30)  -- Record Separator
        repeat with mbox in mailboxes
            if account of mbox is missing value then
                if output is not "" then set output to output & RS
                set output to output & name of mbox
            end if
        end repeat
        return output
    end tell
    '''
    result = run_applescript(script)
    # Handle empty string case - don't return [''] for empty results
    if not result or not result.strip():
        return []
    return result.split(RECORD_SEP)


def create_local_mailbox(mailbox: str) -> bool:
    """
    Create a new local 'On My Mac' mailbox.

    Uses AppleScript (sysm has no mailbox creation support).

    Args:
        mailbox: Name of the mailbox to create.

    Returns:
        True if successful.
    """
    mailbox_escaped = escape_applescript_string(mailbox)
    script = f'''
    tell application "Mail"
        make new mailbox with properties {{name:"{mailbox_escaped}"}}
    end tell
    '''
    run_applescript(script)
    return True


# --- sysm-backed operations ---


def move_message(
    message_id: str,
    target_mailbox: str,
    target_account: str | None = None,
    *,
    source_mailbox: str | None = None,
    source_account: str | None = None,
) -> bool:
    """
    Move a message to a different mailbox.

    Args:
        message_id: The Mail.app message ID.
        target_mailbox: Name of the destination mailbox (must exist).
        target_account: Account for the target mailbox (if different from source).
        source_mailbox: Original mailbox (unused, kept for signature compat).
        source_account: Original account (used as fallback for target_account).

    Returns:
        True if the move was successful.
    """
    # Determine account: LOCAL_ACCOUNT_KEY means no account
    if target_account == LOCAL_ACCOUNT_KEY:
        account = None
    elif target_account:
        account = target_account
    elif source_account:
        account = source_account
    else:
        account = None

    return move_message_sysm(message_id, target_mailbox, account)


@dataclass
class PendingMove:
    """Represents a pending move operation for batch processing."""

    message_id: str
    target_mailbox: str
    target_account: str | None
    source_mailbox: str | None
    source_account: str | None


def move_messages_batch(moves: list[PendingMove]) -> tuple[int, set[str]]:
    """
    Move multiple messages via sysm.

    Args:
        moves: List of PendingMove objects.

    Returns:
        Tuple of (total_moved_count, set of successfully moved message IDs).
    """
    return move_messages_batch_sysm(moves)


def delete_message(
    message_id: str,
    *,
    permanent: bool = False,
    source_mailbox: str | None = None,
    source_account: str | None = None,
) -> bool:
    """
    Delete a message (move to Trash).

    Args:
        message_id: The Mail.app message ID.
        permanent: Unused (sysm always moves to Trash).
        source_mailbox: Unused, kept for signature compat.
        source_account: Unused, kept for signature compat.

    Returns:
        True if the delete was successful.
    """
    return delete_message_sysm(message_id)


def mark_as_read(
    message_id: str,
    *,
    read: bool = True,
    source_mailbox: str | None = None,
    source_account: str | None = None,
) -> bool:
    """
    Mark a message as read or unread.

    Args:
        message_id: The Mail.app message ID.
        read: True to mark as read, False to mark as unread.
        source_mailbox: Unused, kept for signature compat.
        source_account: Unused, kept for signature compat.

    Returns:
        True if successful.
    """
    return mark_as_read_sysm(message_id, read=read)


def flag_message(
    message_id: str,
    *,
    flagged: bool = True,
    source_mailbox: str | None = None,
    source_account: str | None = None,
) -> bool:
    """
    Flag or unflag a message.

    Args:
        message_id: The Mail.app message ID.
        flagged: True to flag, False to unflag.
        source_mailbox: Unused, kept for signature compat.
        source_account: Unused, kept for signature compat.

    Returns:
        True if successful.
    """
    return flag_message_sysm(message_id, flagged=flagged)


def reply_to_message(
    message_id: str,
    reply_content: str,
    *,
    reply_all: bool = False,
    send_immediately: bool = False,
    source_mailbox: str | None = None,
    source_account: str | None = None,
) -> bool:
    """
    Create a reply to a message.

    Args:
        message_id: The Mail.app message ID.
        reply_content: The body text of the reply.
        reply_all: If True, reply to all recipients.
        send_immediately: If True, send the reply immediately.
        source_mailbox: Unused, kept for signature compat.
        source_account: Unused, kept for signature compat.

    Returns:
        True if the reply was created/sent successfully.
    """
    return reply_to_message_sysm(
        message_id, reply_content, reply_all=reply_all, send=send_immediately
    )


def forward_message(
    message_id: str,
    to_addresses: list[str],
    additional_content: str = "",
    *,
    send_immediately: bool = False,
    source_mailbox: str | None = None,
    source_account: str | None = None,
) -> bool:
    """
    Forward a message to one or more recipients.

    Note: sysm only supports a single --to address. For multiple recipients,
    we forward to the first address only.

    Args:
        message_id: The Mail.app message ID.
        to_addresses: List of email addresses to forward to.
        additional_content: Optional text to prepend to the forwarded message.
        send_immediately: If True, send immediately.
        source_mailbox: Unused, kept for signature compat.
        source_account: Unused, kept for signature compat.

    Returns:
        True if successful.
    """
    if not to_addresses:
        return False

    # sysm forward only supports single --to; forward to first address
    return forward_message_sysm(
        message_id,
        to_addresses[0],
        body=additional_content,
        send=send_immediately,
    )


def get_mailboxes(account_name: str | None = None) -> list[str]:
    """
    Get list of mailbox names for an account.

    Args:
        account_name: Specific account, or None for all accounts.

    Returns:
        List of mailbox names.
    """
    mailboxes = get_mailboxes_sysm(account_name)
    if account_name:
        return [mbox.get("name", "") for mbox in mailboxes if mbox.get("name")]
    else:
        # When no account specified, include account context like the old format
        result = []
        for mbox in mailboxes:
            name = mbox.get("name", "")
            acct = mbox.get("account", mbox.get("accountName", ""))
            if name:
                result.append(f"{name} ({acct})" if acct else name)
        return result


def compose_email(
    to_address: str,
    subject: str,
    content: str,
    *,
    from_account: str | None = None,
    sender_address: str | None = None,
    send_immediately: bool = True,
) -> bool:
    """
    Compose and optionally send a new email via sysm.

    Args:
        to_address: Recipient email address.
        subject: Email subject line.
        content: Plain text email body (newlines preserved).
        from_account: Account to send from (uses first enabled if not specified).
        sender_address: Specific sender email address (unused by sysm).
        send_immediately: If True, send immediately; if False, leave as draft.

    Returns:
        True if successful, False otherwise.
    """
    return compose_email_sysm(
        to_address,
        subject,
        content,
        account=from_account,
        send=send_immediately,
    )


def send_email_smtp(
    to_address: str,
    subject: str,
    content: str,
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    from_address: str | None = None,
    use_tls: bool = True,
    html_content: str | None = None,
) -> bool:
    """
    Send email using direct SMTP connection (bypasses Mail.app).

    Args:
        to_address: Recipient email address.
        subject: Email subject line.
        content: Plain text email body.
        smtp_host: SMTP server hostname (e.g., smtp.gmail.com).
        smtp_port: SMTP server port (587 for STARTTLS, 465 for SSL).
        smtp_username: SMTP username (usually your email address).
        smtp_password: SMTP password (use app-specific password for Gmail).
        from_address: From address (defaults to smtp_username if not specified).
        use_tls: Use STARTTLS for connection (default True).
        html_content: Optional HTML version of the email body.

    Returns:
        True if email was sent successfully, False otherwise.

    Raises:
        Various SMTP exceptions if sending fails.
    """
    import smtplib
    from email.message import EmailMessage

    # Default from_address to smtp_username
    sender = from_address or smtp_username

    # Create email message
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(content)

    # Add HTML alternative if provided
    if html_content:
        msg.add_alternative(html_content, subtype="html")

    try:
        # Connect to SMTP server
        if use_tls:
            # Use STARTTLS (port 587)
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            # Use SSL (port 465)
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
            server.ehlo()

        # Authenticate
        server.login(smtp_username, smtp_password)

        # Send email
        server.send_message(msg)
        server.quit()
        return True

    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(f"SMTP authentication failed: {e}") from e
    except smtplib.SMTPException as e:
        raise RuntimeError(f"SMTP error: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to send email: {e}") from e
