"""Tests for reminder parsing (sysm-backed)."""

from datetime import datetime
from unittest.mock import patch

import pytest

from email_nurse.reminders.reminders import get_reminders


class TestGetRemindersEmptyResults:
    """Tests for empty result handling."""

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_empty_list_returns_empty(self, mock_sysm: pytest.fixture) -> None:
        """Empty sysm result should return empty list."""
        mock_sysm.return_value = []
        result = get_reminders()
        assert result == []


class TestGetRemindersRecordParsing:
    """Tests for record parsing logic."""

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_single_reminder_parsing(self, mock_sysm: pytest.fixture) -> None:
        """Single reminder should parse correctly."""
        mock_sysm.return_value = [{
            "id": "rem-123",
            "name": "Review PR",
            "notes": "See the PR for details",
            "list": "Work",
            "dueDate": "2025-01-10T17:00:00",
            "priority": 1,
            "completed": False,
            "creationDate": "2025-01-09T09:00:00",
        }]

        result = get_reminders()

        assert len(result) == 1
        rem = result[0]
        assert rem.id == "rem-123"
        assert rem.name == "Review PR"
        assert rem.body == "See the PR for details"
        assert rem.list_name == "Work"
        assert rem.due_date == datetime(2025, 1, 10, 17, 0, 0)
        assert rem.priority == 1
        assert rem.completed is False
        assert rem.creation_date == datetime(2025, 1, 9, 9, 0, 0)

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_multiple_reminders_parsing(self, mock_sysm: pytest.fixture) -> None:
        """Multiple reminders should parse correctly."""
        mock_sysm.return_value = [
            {"id": "rem-1", "name": "Task 1", "notes": "", "list": "Work",
             "dueDate": "2025-01-10T10:00:00", "priority": 1, "completed": False,
             "creationDate": "2025-01-09T09:00:00"},
            {"id": "rem-2", "name": "Task 2", "notes": "", "list": "Personal",
             "dueDate": "2025-01-11T14:00:00", "priority": 5, "completed": False,
             "creationDate": "2025-01-09T10:00:00"},
        ]

        result = get_reminders()

        assert len(result) == 2
        assert result[0].id == "rem-1"
        assert result[0].name == "Task 1"
        assert result[1].id == "rem-2"
        assert result[1].name == "Task 2"


class TestGetRemindersPriorityParsing:
    """Tests for priority field parsing."""

    @pytest.mark.parametrize(
        "priority_val,expected",
        [
            (0, 0),
            (1, 1),
            (5, 5),
            (9, 9),
        ],
    )
    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_valid_priority_parsing(
        self, mock_sysm: pytest.fixture, priority_val: int, expected: int
    ) -> None:
        """Valid priority integers should parse correctly."""
        mock_sysm.return_value = [{
            "id": "rem-1", "name": "Task", "notes": "", "list": "Work",
            "dueDate": "", "priority": priority_val, "completed": False,
            "creationDate": "2025-01-09T09:00:00",
        }]

        result = get_reminders()

        assert len(result) == 1
        assert result[0].priority == expected

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_missing_priority_defaults_to_zero(self, mock_sysm: pytest.fixture) -> None:
        """Missing priority should default to 0."""
        mock_sysm.return_value = [{
            "id": "rem-1", "name": "Task", "notes": "", "list": "Work",
            "completed": False, "creationDate": "2025-01-09T09:00:00",
        }]

        result = get_reminders()

        assert len(result) == 1
        assert result[0].priority == 0


class TestGetRemindersBooleanParsing:
    """Tests for boolean field parsing."""

    @pytest.mark.parametrize(
        "completed_val,expected",
        [
            (True, True),
            (False, False),
            (1, True),
            (0, False),
        ],
    )
    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_completed_boolean_parsing(
        self, mock_sysm: pytest.fixture, completed_val, expected: bool
    ) -> None:
        """Completed boolean should parse correctly."""
        mock_sysm.return_value = [{
            "id": "rem-1", "name": "Task", "notes": "", "list": "Work",
            "dueDate": "", "priority": 0, "completed": completed_val,
            "creationDate": "2025-01-09T09:00:00",
        }]

        result = get_reminders()

        assert len(result) == 1
        assert result[0].completed is expected


class TestGetRemindersOptionalFields:
    """Tests for optional field handling."""

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_empty_due_date(self, mock_sysm: pytest.fixture) -> None:
        """Empty due date should become None."""
        mock_sysm.return_value = [{
            "id": "rem-1", "name": "Task", "notes": "", "list": "Work",
            "dueDate": "", "priority": 0, "completed": False,
            "creationDate": "2025-01-09T09:00:00",
        }]

        result = get_reminders()

        assert len(result) == 1
        assert result[0].due_date is None

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_empty_body(self, mock_sysm: pytest.fixture) -> None:
        """Empty body should be empty string."""
        mock_sysm.return_value = [{
            "id": "rem-1", "name": "Task", "notes": "", "list": "Work",
            "dueDate": "2025-01-10T10:00:00", "priority": 0, "completed": False,
            "creationDate": "2025-01-09T09:00:00",
        }]

        result = get_reminders()

        assert len(result) == 1
        assert result[0].body == ""


class TestGetRemindersDateParsing:
    """Tests for date field parsing within reminders."""

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_both_dates_parsed(self, mock_sysm: pytest.fixture) -> None:
        """Both due_date and creation_date should be parsed."""
        mock_sysm.return_value = [{
            "id": "rem-1", "name": "Task", "notes": "", "list": "Work",
            "dueDate": "2025-01-10T17:00:00",
            "priority": 1, "completed": False,
            "creationDate": "2025-01-09T09:00:00",
        }]

        result = get_reminders()

        assert len(result) == 1
        assert result[0].due_date == datetime(2025, 1, 10, 17, 0, 0)
        assert result[0].creation_date == datetime(2025, 1, 9, 9, 0, 0)

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_unparseable_due_date_becomes_none(self, mock_sysm: pytest.fixture) -> None:
        """Unparseable due_date should become None."""
        mock_sysm.return_value = [{
            "id": "rem-1", "name": "Task", "notes": "", "list": "Work",
            "dueDate": "not a date",
            "priority": 1, "completed": False,
            "creationDate": "2025-01-09T09:00:00",
        }]

        result = get_reminders()

        assert len(result) == 1
        assert result[0].due_date is None


class TestGetRemindersCompletedFilter:
    """Tests for completed filter behavior."""

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_completed_true_filters_incomplete(self, mock_sysm: pytest.fixture) -> None:
        """completed=True should only return completed reminders."""
        mock_sysm.return_value = [
            {"id": "rem-1", "name": "Done", "completed": True, "list": "Work"},
            {"id": "rem-2", "name": "Not Done", "completed": False, "list": "Work"},
        ]

        result = get_reminders(completed=True)

        assert len(result) == 1
        assert result[0].name == "Done"

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_completed_false_filters_complete(self, mock_sysm: pytest.fixture) -> None:
        """completed=False should only return incomplete reminders."""
        mock_sysm.return_value = [
            {"id": "rem-1", "name": "Done", "completed": True, "list": "Work"},
            {"id": "rem-2", "name": "Not Done", "completed": False, "list": "Work"},
        ]

        result = get_reminders(completed=False)

        assert len(result) == 1
        assert result[0].name == "Not Done"

    @patch("email_nurse.reminders.reminders.get_reminders_sysm")
    def test_completed_none_returns_all(self, mock_sysm: pytest.fixture) -> None:
        """completed=None should return all reminders."""
        mock_sysm.return_value = [
            {"id": "rem-1", "name": "Done", "completed": True, "list": "Work"},
            {"id": "rem-2", "name": "Not Done", "completed": False, "list": "Work"},
        ]

        result = get_reminders(completed=None)

        assert len(result) == 2
