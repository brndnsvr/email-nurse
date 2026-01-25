"""Mail.app message actions - move, delete, reply, forward, etc."""

from dataclasses import dataclass
from difflib import SequenceMatcher

from email_nurse.mail.applescript import escape_applescript_string, run_applescript

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
    account_escaped = escape_applescript_string(account)
    script = f'''
    tell application "Mail"
        set output to ""
        set acct to account "{account_escaped}"
        set RS to (ASCII character 30)  -- Record Separator
        repeat with mbox in mailboxes of acct
            if output is not "" then set output to output & RS
            set output to output & name of mbox
        end repeat
        return output
    end tell
    '''
    result = run_applescript(script)
    return result.split(RECORD_SEP) if result else []


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


def create_mailbox(mailbox: str, account: str) -> bool:
    """
    Create a new mailbox in an account.

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


def _get_message_ref(message_id: str, source_mailbox: str | None, source_account: str | None) -> str:
    """Build AppleScript to reference a message efficiently."""
    if source_mailbox and source_account:
        mailbox_escaped = escape_applescript_string(source_mailbox)
        account_escaped = escape_applescript_string(source_account)
        return f'first message of mailbox "{mailbox_escaped}" of account "{account_escaped}" whose id is {message_id}'

    # Fallback: global search (slower)
    return f'first message whose id is {message_id}'


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

    Note: The mailbox must exist. Use create_mailbox() to create new folders.

    Args:
        message_id: The Mail.app message ID.
        target_mailbox: Name of the destination mailbox (must exist).
        target_account: Account for the target mailbox (if different from source).
        source_mailbox: Original mailbox (for faster lookup).
        source_account: Original account (for faster lookup).

    Returns:
        True if the move was successful.
    """
    mailbox_escaped = escape_applescript_string(target_mailbox)
    msg_ref = _get_message_ref(message_id, source_mailbox, source_account)

    # Determine which account to use for the target mailbox
    # LOCAL_ACCOUNT_KEY ("__local__") means route to local "On My Mac" mailboxes
    if target_account == LOCAL_ACCOUNT_KEY:
        account_escaped = None  # Local folder - no account qualifier
    elif target_account:
        account_escaped = escape_applescript_string(target_account)
    elif source_account:
        account_escaped = escape_applescript_string(source_account)
    else:
        account_escaped = None

    if account_escaped:
        script = f'''
        tell application "Mail"
            set msg to {msg_ref}
            move msg to mailbox "{mailbox_escaped}" of account "{account_escaped}"
        end tell
        '''
    else:
        script = f'''
        tell application "Mail"
            set msg to {msg_ref}
            move msg to mailbox "{mailbox_escaped}"
        end tell
        '''

    run_applescript(script)
    return True


@dataclass
class PendingMove:
    """Represents a pending move operation for batch processing."""

    message_id: str
    target_mailbox: str
    target_account: str | None
    source_mailbox: str | None
    source_account: str | None


def move_messages_batch(moves: list[PendingMove]) -> int:
    """
    Move multiple messages in batched AppleScript calls.

    Groups messages by (target_mailbox, target_account) and executes one
    AppleScript call per group. This is much faster than individual moves.

    Args:
        moves: List of PendingMove objects.

    Returns:
        Number of messages successfully moved.
    """
    if not moves:
        return 0

    # Group moves by target (mailbox, account) for batch processing
    from collections import defaultdict

    groups: dict[tuple[str, str | None], list[PendingMove]] = defaultdict(list)
    for move in moves:
        key = (move.target_mailbox, move.target_account)
        groups[key].append(move)

    total_moved = 0

    for (target_mailbox, target_account), group_moves in groups.items():
        mailbox_escaped = escape_applescript_string(target_mailbox)

        # Build message references - group by source mailbox/account for efficiency
        # Messages from same source can be referenced more efficiently
        source_groups: dict[tuple[str | None, str | None], list[str]] = defaultdict(list)
        for m in group_moves:
            source_key = (m.source_mailbox, m.source_account)
            source_groups[source_key].append(m.message_id)

        # Determine target account for AppleScript
        if target_account == LOCAL_ACCOUNT_KEY:
            account_escaped = None
        elif target_account:
            account_escaped = escape_applescript_string(target_account)
        else:
            # Use first source account as fallback
            first_move = group_moves[0]
            if first_move.source_account:
                account_escaped = escape_applescript_string(first_move.source_account)
            else:
                account_escaped = None

        # Build AppleScript for this batch
        if account_escaped:
            target_ref = f'mailbox "{mailbox_escaped}" of account "{account_escaped}"'
        else:
            target_ref = f'mailbox "{mailbox_escaped}"'

        # Build message list and move in one script
        msg_id_list = [m.message_id for m in group_moves]
        msg_ids_str = "{" + ", ".join(msg_id_list) + "}"

        # For same-source batches, use optimized lookup
        # For mixed sources, use global lookup (slower but works)
        if len(source_groups) == 1:
            (src_mailbox, src_account) = list(source_groups.keys())[0]
            if src_mailbox and src_account:
                src_mailbox_escaped = escape_applescript_string(src_mailbox)
                src_account_escaped = escape_applescript_string(src_account)
                script = f'''
                tell application "Mail"
                    set targetBox to {target_ref}
                    set srcBox to mailbox "{src_mailbox_escaped}" of account "{src_account_escaped}"
                    set msgIds to {msg_ids_str}
                    set movedCount to 0
                    repeat with msgId in msgIds
                        try
                            set msg to first message of srcBox whose id is msgId
                            move msg to targetBox
                            set movedCount to movedCount + 1
                        end try
                    end repeat
                    return movedCount
                end tell
                '''
            else:
                # Global lookup fallback
                script = f'''
                tell application "Mail"
                    set targetBox to {target_ref}
                    set msgIds to {msg_ids_str}
                    set movedCount to 0
                    repeat with msgId in msgIds
                        try
                            set msg to first message whose id is msgId
                            move msg to targetBox
                            set movedCount to movedCount + 1
                        end try
                    end repeat
                    return movedCount
                end tell
                '''
        else:
            # Mixed sources - use global lookup
            script = f'''
            tell application "Mail"
                set targetBox to {target_ref}
                set msgIds to {msg_ids_str}
                set movedCount to 0
                repeat with msgId in msgIds
                    try
                        set msg to first message whose id is msgId
                        move msg to targetBox
                        set movedCount to movedCount + 1
                    end try
                end repeat
                return movedCount
            end tell
            '''

        try:
            result = run_applescript(script, timeout=120)
            if result:
                total_moved += int(result)
            else:
                total_moved += len(group_moves)  # Assume success if no error
        except Exception:
            # Continue with other groups even if one fails
            pass

    return total_moved


def delete_message(
    message_id: str,
    *,
    permanent: bool = False,
    source_mailbox: str | None = None,
    source_account: str | None = None,
) -> bool:
    """
    Delete a message (move to Trash or permanently delete).

    Args:
        message_id: The Mail.app message ID.
        permanent: If True, permanently delete. Otherwise move to Trash.
        source_mailbox: Original mailbox (for faster lookup).
        source_account: Original account (for faster lookup).

    Returns:
        True if the delete was successful.
    """
    msg_ref = _get_message_ref(message_id, source_mailbox, source_account)

    if permanent:
        script = f'''
        tell application "Mail"
            set msg to {msg_ref}
            delete msg
        end tell
        '''
    else:
        # Find trash by common names since "trash mailbox of account" doesn't work
        script = f'''
        tell application "Mail"
            set msg to {msg_ref}
            set msgAcct to account of mailbox of msg

            -- Search for trash mailbox by common names
            set trashNames to {{"Trash", "Deleted Messages", "[Gmail]/Trash", "Deleted Items"}}
            set trashMbox to missing value

            repeat with trashName in trashNames
                try
                    set trashMbox to mailbox trashName of msgAcct
                    exit repeat
                end try
            end repeat

            if trashMbox is missing value then
                error "Could not find trash mailbox"
            end if

            move msg to trashMbox
        end tell
        '''

    run_applescript(script)
    return True


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
        source_mailbox: Original mailbox (for faster lookup).
        source_account: Original account (for faster lookup).

    Returns:
        True if successful.
    """
    msg_ref = _get_message_ref(message_id, source_mailbox, source_account)
    read_value = "true" if read else "false"
    script = f'''
    tell application "Mail"
        set msg to {msg_ref}
        set read status of msg to {read_value}
    end tell
    '''

    run_applescript(script)
    return True


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
        source_mailbox: Original mailbox (for faster lookup).
        source_account: Original account (for faster lookup).

    Returns:
        True if successful.
    """
    msg_ref = _get_message_ref(message_id, source_mailbox, source_account)
    flag_value = "true" if flagged else "false"
    script = f'''
    tell application "Mail"
        set msg to {msg_ref}
        set flagged status of msg to {flag_value}
    end tell
    '''

    run_applescript(script)
    return True


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
        source_mailbox: Original mailbox (for faster lookup).
        source_account: Original account (for faster lookup).

    Returns:
        True if the reply was created/sent successfully.
    """
    msg_ref = _get_message_ref(message_id, source_mailbox, source_account)
    content_escaped = escape_applescript_string(reply_content)
    reply_cmd = "reply" if not reply_all else "reply msg with properties {reply to all:true}"

    if send_immediately:
        script = f'''
        tell application "Mail"
            set msg to {msg_ref}
            set replyMsg to {reply_cmd} msg
            set content of replyMsg to "{content_escaped}"
            send replyMsg
        end tell
        '''
    else:
        script = f'''
        tell application "Mail"
            set msg to {msg_ref}
            set replyMsg to {reply_cmd} msg
            set content of replyMsg to "{content_escaped}"
            -- Leave draft open for review
        end tell
        '''

    run_applescript(script)
    return True


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

    Args:
        message_id: The Mail.app message ID.
        to_addresses: List of email addresses to forward to.
        additional_content: Optional text to prepend to the forwarded message.
        send_immediately: If True, send immediately.
        source_mailbox: Original mailbox (for faster lookup).
        source_account: Original account (for faster lookup).

    Returns:
        True if successful.
    """
    msg_ref = _get_message_ref(message_id, source_mailbox, source_account)
    content_escaped = escape_applescript_string(additional_content)
    addresses_str = ", ".join(f'"{addr}"' for addr in to_addresses)

    send_action = "send fwdMsg" if send_immediately else "-- Draft created"

    script = f'''
    tell application "Mail"
        set msg to {msg_ref}
        set fwdMsg to forward msg

        -- Add recipients
        repeat with addr in {{{addresses_str}}}
            make new to recipient at end of to recipients of fwdMsg with properties {{address:addr}}
        end repeat

        -- Prepend additional content if provided
        if "{content_escaped}" is not "" then
            set content of fwdMsg to "{content_escaped}" & return & return & content of fwdMsg
        end if

        {send_action}
    end tell
    '''

    run_applescript(script)
    return True


def get_mailboxes(account_name: str | None = None) -> list[str]:
    """
    Get list of mailbox names for an account.

    Args:
        account_name: Specific account, or None for all accounts.

    Returns:
        List of mailbox names.
    """
    if account_name:
        account_escaped = escape_applescript_string(account_name)
        script = f'''
        tell application "Mail"
            set output to ""
            set RS to (ASCII character 30)  -- Record Separator
            set mboxes to mailboxes of account "{account_escaped}"
            repeat with mbox in mboxes
                if output is not "" then set output to output & RS
                set output to output & name of mbox
            end repeat
            return output
        end tell
        '''
    else:
        script = '''
        tell application "Mail"
            set output to ""
            set RS to (ASCII character 30)  -- Record Separator
            repeat with acct in accounts
                set mboxes to mailboxes of acct
                repeat with mbox in mboxes
                    if output is not "" then set output to output & RS
                    set output to output & name of mbox & " (" & name of acct & ")"
                end repeat
            end repeat
            return output
        end tell
        '''

    result = run_applescript(script)
    return result.split(RECORD_SEP) if result else []


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
    Compose and optionally send a new email via Mail.app.

    Args:
        to_address: Recipient email address.
        subject: Email subject line.
        content: Plain text email body (newlines preserved).
        from_account: Account to send from (uses first enabled if not specified).
        sender_address: Specific sender email address (must match account).
        send_immediately: If True, send immediately; if False, leave as draft.

    Returns:
        True if successful, False otherwise.
    """
    import tempfile

    # Import here to avoid circular import
    from email_nurse.mail.accounts import get_accounts

    subject_escaped = escape_applescript_string(subject)
    to_escaped = escape_applescript_string(to_address)

    # Use first enabled account if not specified
    if from_account is None:
        accounts = get_accounts()
        enabled = [a for a in accounts if a.enabled]
        if not enabled:
            raise ValueError("No enabled email accounts found")
        from_account = enabled[0].name

    send_cmd = "send newMsg" if send_immediately else ""

    # Get sender address - use specific address if provided, otherwise first from account
    account_escaped = escape_applescript_string(from_account)
    sender_escaped = escape_applescript_string(sender_address) if sender_address else None

    # Write content to temp file to avoid AppleScript escaping issues
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Build message properties - sender is optional
        # If sender_address is specified, include it; otherwise let Mail use default
        if sender_escaped:
            msg_props = f'{{subject:"{subject_escaped}", content:msgContent, visible:false, sender:"{sender_escaped}"}}'
        else:
            msg_props = f'{{subject:"{subject_escaped}", content:msgContent, visible:false}}'

        script = f'''
        set filePath to POSIX file "{temp_path}"
        set msgContent to read filePath as text
        tell application "Mail"
            set newMsg to make new outgoing message with properties {msg_props}
            tell newMsg
                make new to recipient at end of to recipients with properties {{address:"{to_escaped}"}}
            end tell
            {send_cmd}
        end tell
        '''
        run_applescript(script, timeout=30)
        return True
    finally:
        # Clean up temp file
        import os
        os.unlink(temp_path)


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
