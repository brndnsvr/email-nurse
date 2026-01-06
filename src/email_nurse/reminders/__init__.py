"""Apple Reminders.app integration via AppleScript."""

from email_nurse.reminders.actions import (
    complete_reminder,
    create_reminder,
    create_reminder_from_email,
    delete_reminder,
    uncomplete_reminder,
)
from email_nurse.reminders.lists import ReminderList, get_lists
from email_nurse.reminders.reminders import Reminder, get_reminders

__all__ = [
    # Data classes
    "ReminderList",
    "Reminder",
    # Read operations
    "get_lists",
    "get_reminders",
    # Write operations
    "create_reminder",
    "create_reminder_from_email",
    "complete_reminder",
    "uncomplete_reminder",
    "delete_reminder",
]
