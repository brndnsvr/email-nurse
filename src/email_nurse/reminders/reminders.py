"""Reminder retrieval from Apple Reminders.app via sysm CLI."""

import re
import sys
from dataclasses import dataclass
from datetime import datetime

from email_nurse.mail.sysm import SysmError, get_reminders_sysm
from email_nurse.reminders.lists import (
    RECORD_SEP,
    UNIT_SEP,
    RemindersAppError,
)


@dataclass
class Reminder:
    """Represents a reminder from Reminders.app."""

    id: str
    name: str
    body: str  # Notes field (can contain email links)
    list_name: str
    due_date: datetime | None
    priority: int  # 0=none, 1=high, 5=medium, 9=low
    completed: bool
    creation_date: datetime | None

    @property
    def email_link(self) -> str | None:
        """Extract message:// URL from body if present."""
        if not self.body:
            return None
        # Match message://<message-id> pattern
        match = re.search(r"message://[<]?([^>\s]+)[>]?", self.body)
        return match.group(0) if match else None

    @property
    def priority_label(self) -> str:
        """Human-readable priority label."""
        if self.priority == 0:
            return "none"
        elif self.priority <= 3:
            return "high"
        elif self.priority <= 6:
            return "medium"
        else:
            return "low"

    def __str__(self) -> str:
        status = "[x]" if self.completed else "[ ]"
        due = f" (due {self.due_date.strftime('%Y-%m-%d')})" if self.due_date else ""
        return f"{status} {self.name}{due}"


def get_reminders(
    list_name: str | None = None,
    completed: bool | None = None,
    limit: int = 100,
) -> list[Reminder]:
    """
    Get reminders from Reminders.app via sysm.

    Args:
        list_name: Filter to specific list, or None for all lists.
        completed: True=completed only, False=incomplete only, None=all.
        limit: Maximum number of reminders to retrieve.

    Returns:
        List of Reminder objects.

    Raises:
        RemindersAppError: If the operation fails.
    """
    # sysm --all includes completed; without it, only incomplete are shown
    include_completed = completed is True or completed is None

    try:
        data = get_reminders_sysm(list_name, include_completed=include_completed)
    except SysmError as e:
        raise RemindersAppError(str(e)) from e

    reminders = []
    for item in data:
        is_completed = bool(item.get("completed", item.get("isCompleted", False)))

        # Apply completed filter
        if completed is True and not is_completed:
            continue
        if completed is False and is_completed:
            continue

        try:
            priority = int(item.get("priority", 0))
        except (ValueError, TypeError):
            priority = 0

        due_date = _parse_date(item.get("dueDate", item.get("due_date", "")))
        creation_date = _parse_date(item.get("creationDate", item.get("creation_date", "")))

        reminders.append(
            Reminder(
                id=str(item.get("id", "")),
                name=item.get("name", item.get("title", "")),
                body=item.get("body", item.get("notes", "")),
                list_name=item.get("list", item.get("listName", list_name or "")),
                due_date=due_date,
                priority=priority,
                completed=is_completed,
                creation_date=creation_date,
            )
        )

        if len(reminders) >= limit:
            break

    return reminders


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse a date string into a datetime object."""
    if not date_str or date_str == "missing value":
        return None

    # Try ISO 8601 first (most likely from sysm JSON)
    try:
        if date_str.endswith('Z'):
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return datetime.fromisoformat(date_str)
    except (ValueError, AttributeError):
        pass

    # AppleScript locale formats as fallback
    formats = [
        "%A, %B %d, %Y at %I:%M:%S %p",
        "%A, %B %d, %Y at %H:%M:%S",
        "%a, %b %d, %Y at %I:%M:%S %p",
        "%a, %b %d, %Y at %H:%M:%S",
        "%B %d, %Y at %I:%M:%S %p",
        "%B %d, %Y at %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %I:%M:%S %p",
        "%A, %B %d, %Y at %I:%M %p",
        "%Y-%m-%d %H:%M",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    print(
        f"Warning: Unrecognized date format in Reminders: {date_str!r}",
        file=sys.stderr,
    )
    return None
