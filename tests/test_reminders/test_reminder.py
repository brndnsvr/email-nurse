"""Tests for Reminder dataclass properties."""

from datetime import datetime

import pytest

from email_nurse.reminders.reminders import Reminder


def make_reminder(
    *,
    id: str = "rem-1",
    name: str = "Test Reminder",
    body: str = "",
    list_name: str = "Reminders",
    due_date: datetime | None = None,
    priority: int = 0,
    completed: bool = False,
    creation_date: datetime | None = None,
) -> Reminder:
    """Factory function for creating test reminders."""
    return Reminder(
        id=id,
        name=name,
        body=body,
        list_name=list_name,
        due_date=due_date,
        priority=priority,
        completed=completed,
        creation_date=creation_date,
    )


class TestEmailLinkProperty:
    """Tests for the email_link property."""

    def test_plain_message_link_in_body(self) -> None:
        """Plain message:// link in body."""
        reminder = make_reminder(body="From email: message://abc123")
        assert reminder.email_link == "message://abc123"

    def test_bracketed_message_link_in_body(self) -> None:
        """Message link with angle brackets in body."""
        reminder = make_reminder(body="See <message://abc123@mail.com>")
        assert reminder.email_link == "message://abc123@mail.com>"

    def test_message_link_with_special_chars(self) -> None:
        """Message link with special characters."""
        reminder = make_reminder(body="Ref: message://<abc-123_456@mail.example.com>")
        assert reminder.email_link == "message://<abc-123_456@mail.example.com>"

    def test_message_link_at_start(self) -> None:
        """Message link at the start of body."""
        reminder = make_reminder(body="message://abc123 is the reference")
        assert reminder.email_link == "message://abc123"

    def test_message_link_at_end(self) -> None:
        """Message link at the end of body."""
        reminder = make_reminder(body="Reference: message://abc123")
        assert reminder.email_link == "message://abc123"

    def test_no_message_link(self) -> None:
        """No message link in body returns None."""
        reminder = make_reminder(body="Just a regular note")
        assert reminder.email_link is None

    def test_empty_body(self) -> None:
        """Empty body returns None."""
        reminder = make_reminder(body="")
        assert reminder.email_link is None

    def test_https_link_not_matched(self) -> None:
        """HTTPS links should not be matched as email links."""
        reminder = make_reminder(body="See https://example.com for details")
        assert reminder.email_link is None

    def test_multiple_message_links_returns_first(self) -> None:
        """Multiple message links should return the first one."""
        reminder = make_reminder(
            body="First: message://abc123 Second: message://def456"
        )
        assert reminder.email_link == "message://abc123"


class TestPriorityLabelProperty:
    """Tests for the priority_label property."""

    def test_priority_0_is_none(self) -> None:
        """Priority 0 should return 'none'."""
        reminder = make_reminder(priority=0)
        assert reminder.priority_label == "none"

    @pytest.mark.parametrize("priority", [1, 2, 3])
    def test_priority_1_to_3_is_high(self, priority: int) -> None:
        """Priority 1-3 should return 'high'."""
        reminder = make_reminder(priority=priority)
        assert reminder.priority_label == "high"

    @pytest.mark.parametrize("priority", [4, 5, 6])
    def test_priority_4_to_6_is_medium(self, priority: int) -> None:
        """Priority 4-6 should return 'medium'."""
        reminder = make_reminder(priority=priority)
        assert reminder.priority_label == "medium"

    @pytest.mark.parametrize("priority", [7, 8, 9])
    def test_priority_7_to_9_is_low(self, priority: int) -> None:
        """Priority 7-9 should return 'low'."""
        reminder = make_reminder(priority=priority)
        assert reminder.priority_label == "low"

    def test_priority_10_is_low(self) -> None:
        """Priority 10+ should return 'low'."""
        reminder = make_reminder(priority=10)
        assert reminder.priority_label == "low"


class TestStrMethod:
    """Tests for the __str__ method."""

    def test_incomplete_reminder_str(self) -> None:
        """Incomplete reminder string format."""
        reminder = make_reminder(name="Buy milk", completed=False)
        assert str(reminder) == "[ ] Buy milk"

    def test_completed_reminder_str(self) -> None:
        """Completed reminder string format."""
        reminder = make_reminder(name="Buy milk", completed=True)
        assert str(reminder) == "[x] Buy milk"

    def test_reminder_with_due_date_str(self) -> None:
        """Reminder with due date string format."""
        reminder = make_reminder(
            name="Submit report",
            completed=False,
            due_date=datetime(2025, 1, 15, 17, 0, 0),
        )
        assert str(reminder) == "[ ] Submit report (due 2025-01-15)"

    def test_completed_reminder_with_due_date_str(self) -> None:
        """Completed reminder with due date string format."""
        reminder = make_reminder(
            name="Submit report",
            completed=True,
            due_date=datetime(2025, 1, 15, 17, 0, 0),
        )
        assert str(reminder) == "[x] Submit report (due 2025-01-15)"

    def test_reminder_no_due_date_str(self) -> None:
        """Reminder without due date should not show date."""
        reminder = make_reminder(name="Someday task", completed=False, due_date=None)
        assert str(reminder) == "[ ] Someday task"


class TestReminderEquality:
    """Tests for reminder comparison."""

    def test_reminders_with_same_data_are_equal(self) -> None:
        """Two reminders with same data should be equal."""
        due = datetime(2025, 1, 10, 17, 0, 0)
        created = datetime(2025, 1, 9, 9, 0, 0)
        rem1 = make_reminder(
            id="rem-1",
            name="Task",
            body="Note",
            list_name="Work",
            due_date=due,
            priority=1,
            completed=False,
            creation_date=created,
        )
        rem2 = make_reminder(
            id="rem-1",
            name="Task",
            body="Note",
            list_name="Work",
            due_date=due,
            priority=1,
            completed=False,
            creation_date=created,
        )
        assert rem1 == rem2

    def test_reminders_with_different_id_not_equal(self) -> None:
        """Two reminders with different IDs should not be equal."""
        rem1 = make_reminder(id="rem-1")
        rem2 = make_reminder(id="rem-2")
        assert rem1 != rem2
