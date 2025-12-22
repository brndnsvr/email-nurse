"""Mail.app interface layer via AppleScript."""

from email_nurse.mail.accounts import get_accounts, sync_account
from email_nurse.mail.actions import (
    delete_message,
    forward_message,
    mark_as_read,
    move_message,
    reply_to_message,
)
from email_nurse.mail.applescript import MailAppError, run_applescript
from email_nurse.mail.messages import get_messages

__all__ = [
    "MailAppError",
    "run_applescript",
    "get_accounts",
    "sync_account",
    "get_messages",
    "move_message",
    "delete_message",
    "mark_as_read",
    "forward_message",
    "reply_to_message",
]
