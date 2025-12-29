"""AppleScript notifications for email-nurse pending folder alerts."""

from email_nurse.applescript.base import escape_applescript_string, run_applescript


def notify_pending_folders(
    pending_items: list[dict],
    title: str = "Email Nurse - Folders Needed",
) -> bool:
    """Show a macOS dialog about folders that need to be created.

    Args:
        pending_items: List of dicts with keys:
            - pending_folder: str - folder name
            - pending_account: str - account name
            - message_count: int - number of messages waiting
            - sample_messages: list[dict] with sender, subject, date (optional)
        title: Dialog title.

    Returns:
        True if dialog was shown successfully, False on error.
    """
    if not pending_items:
        return True

    # Build the message content with line breaks as literal \n for AppleScript
    lines = ["The following folders need to be created:\\n"]

    for item in pending_items:
        folder = item["pending_folder"]
        account = item["pending_account"]
        count = item["message_count"]

        lines.append(f"\\n--- {folder} ({account}) ---")
        lines.append(f"{count} message(s) waiting")

        # Show sample messages if provided
        samples = item.get("sample_messages", [])
        for msg in samples[:3]:
            sender = msg.get("sender", "Unknown")[:30]
            subject = msg.get("subject", "No subject")[:40]
            date = msg.get("date", "")
            lines.append(f"  - {sender}: {subject}")
            if date:
                lines.append(f"    ({date})")

    lines.append("\\n\\nCreate folders via Outlook/Mail, then run:")
    lines.append("  email-nurse autopilot retry-pending")

    # Join with literal \n for AppleScript string
    message = "\\n".join(lines)
    message_escaped = escape_applescript_string(message)
    title_escaped = escape_applescript_string(title)

    # Use display dialog for a modal alert that requires user attention
    script = f'''
    tell application "System Events"
        display dialog "{message_escaped}" with title "{title_escaped}" buttons {{"OK"}} default button "OK" with icon caution
    end tell
    '''

    try:
        run_applescript(script, timeout=120)  # Long timeout - user may read
        return True
    except Exception:
        # Don't fail the run if notification fails
        return False


def notify_simple(
    message: str,
    title: str = "Email Nurse",
    subtitle: str | None = None,
) -> bool:
    """Show a simple macOS notification banner.

    This uses Notification Center and doesn't block - the notification
    appears briefly and then goes to the notification drawer.

    Args:
        message: Notification body text.
        title: Notification title.
        subtitle: Optional subtitle line.

    Returns:
        True if notification was shown, False on error.
    """
    message_escaped = escape_applescript_string(message)
    title_escaped = escape_applescript_string(title)

    if subtitle:
        subtitle_escaped = escape_applescript_string(subtitle)
        script = f'''
        display notification "{message_escaped}" with title "{title_escaped}" subtitle "{subtitle_escaped}"
        '''
    else:
        script = f'''
        display notification "{message_escaped}" with title "{title_escaped}"
        '''

    try:
        run_applescript(script, timeout=10)
        return True
    except Exception:
        return False


def notify_folders_summary(
    folder_count: int,
    message_count: int,
    account: str | None = None,
) -> bool:
    """Show a brief notification about pending folders.

    This is a non-blocking banner notification, useful for background
    daemon runs where a full dialog would be intrusive.

    Args:
        folder_count: Number of folders needing creation.
        message_count: Total messages waiting across all folders.
        account: Specific account name, or None for multiple accounts.

    Returns:
        True if notification was shown, False on error.
    """
    if account:
        subtitle = f"on {account}"
    else:
        subtitle = "across accounts"

    message = f"{folder_count} folder(s) need creation, {message_count} message(s) waiting"

    return notify_simple(
        message=message,
        title="Email Nurse - Action Needed",
        subtitle=subtitle,
    )
