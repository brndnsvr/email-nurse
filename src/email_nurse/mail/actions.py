"""Mail.app message actions - move, delete, reply, forward, etc."""

from email_nurse.mail.applescript import escape_applescript_string, run_applescript


def move_message(
    message_id: str,
    target_mailbox: str,
    target_account: str | None = None,
) -> bool:
    """
    Move a message to a different mailbox.

    Args:
        message_id: The Mail.app message ID.
        target_mailbox: Name of the destination mailbox.
        target_account: Account for the target mailbox (if different from source).

    Returns:
        True if the move was successful.
    """
    mailbox_escaped = escape_applescript_string(target_mailbox)

    if target_account:
        account_escaped = escape_applescript_string(target_account)
        target_ref = f'mailbox "{mailbox_escaped}" of account "{account_escaped}"'
    else:
        target_ref = f'mailbox "{mailbox_escaped}"'

    script = f'''
    tell application "Mail"
        set msg to first message whose id is {message_id}
        move msg to {target_ref}
    end tell
    '''

    run_applescript(script)
    return True


def delete_message(message_id: str, *, permanent: bool = False) -> bool:
    """
    Delete a message (move to Trash or permanently delete).

    Args:
        message_id: The Mail.app message ID.
        permanent: If True, permanently delete. Otherwise move to Trash.

    Returns:
        True if the delete was successful.
    """
    if permanent:
        script = f'''
        tell application "Mail"
            set msg to first message whose id is {message_id}
            delete msg
        end tell
        '''
    else:
        script = f'''
        tell application "Mail"
            set msg to first message whose id is {message_id}
            set acct to account of mailbox of msg
            move msg to trash mailbox of acct
        end tell
        '''

    run_applescript(script)
    return True


def mark_as_read(message_id: str, *, read: bool = True) -> bool:
    """
    Mark a message as read or unread.

    Args:
        message_id: The Mail.app message ID.
        read: True to mark as read, False to mark as unread.

    Returns:
        True if successful.
    """
    read_value = "true" if read else "false"
    script = f'''
    tell application "Mail"
        set msg to first message whose id is {message_id}
        set read status of msg to {read_value}
    end tell
    '''

    run_applescript(script)
    return True


def flag_message(message_id: str, *, flagged: bool = True) -> bool:
    """
    Flag or unflag a message.

    Args:
        message_id: The Mail.app message ID.
        flagged: True to flag, False to unflag.

    Returns:
        True if successful.
    """
    flag_value = "true" if flagged else "false"
    script = f'''
    tell application "Mail"
        set msg to first message whose id is {message_id}
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
) -> bool:
    """
    Create a reply to a message.

    Args:
        message_id: The Mail.app message ID.
        reply_content: The body text of the reply.
        reply_all: If True, reply to all recipients.
        send_immediately: If True, send the reply immediately.

    Returns:
        True if the reply was created/sent successfully.
    """
    content_escaped = escape_applescript_string(reply_content)
    reply_cmd = "reply" if not reply_all else "reply msg with properties {reply to all:true}"

    if send_immediately:
        script = f'''
        tell application "Mail"
            set msg to first message whose id is {message_id}
            set replyMsg to {reply_cmd} msg
            set content of replyMsg to "{content_escaped}"
            send replyMsg
        end tell
        '''
    else:
        script = f'''
        tell application "Mail"
            set msg to first message whose id is {message_id}
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
) -> bool:
    """
    Forward a message to one or more recipients.

    Args:
        message_id: The Mail.app message ID.
        to_addresses: List of email addresses to forward to.
        additional_content: Optional text to prepend to the forwarded message.
        send_immediately: If True, send immediately.

    Returns:
        True if successful.
    """
    content_escaped = escape_applescript_string(additional_content)
    addresses_str = ", ".join(f'"{addr}"' for addr in to_addresses)

    send_action = "send fwdMsg" if send_immediately else "-- Draft created"

    script = f'''
    tell application "Mail"
        set msg to first message whose id is {message_id}
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
            set mboxes to mailboxes of account "{account_escaped}"
            repeat with mbox in mboxes
                if output is not "" then set output to output & "|||"
                set output to output & name of mbox
            end repeat
            return output
        end tell
        '''
    else:
        script = '''
        tell application "Mail"
            set output to ""
            repeat with acct in accounts
                set mboxes to mailboxes of acct
                repeat with mbox in mboxes
                    if output is not "" then set output to output & "|||"
                    set output to output & name of mbox & " (" & name of acct & ")"
                end repeat
            end repeat
            return output
        end tell
        '''

    result = run_applescript(script)
    return result.split("|||") if result else []
