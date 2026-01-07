"""Tests for reminder parsing."""

from datetime import datetime
from unittest.mock import patch

import pytest

from email_nurse.reminders.reminders import get_reminders

# Import separators from conftest
RECORD_SEP = "\x1e"
UNIT_SEP = "\x1f"


class TestGetRemindersEmptyResults:
    """Tests for empty result handling."""

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_empty_string_returns_empty_list(self, mock_run: pytest.fixture) -> None:
        """Empty string from AppleScript should return empty list."""
        mock_run.return_value = ""
        result = get_reminders()
        assert result == []

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_none_returns_empty_list(self, mock_run: pytest.fixture) -> None:
        """None result should be handled as empty."""
        mock_run.return_value = None
        result = get_reminders()
        assert result == []


class TestGetRemindersRecordParsing:
    """Tests for record parsing logic."""

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_single_reminder_parsing(self, mock_run: pytest.fixture) -> None:
        """Single reminder record should parse correctly."""
        # Fields: id, name, body, list_name, due_date, priority, completed, creation_date
        rem_data = UNIT_SEP.join([
            "rem-123",
            "Review PR",
            "See the PR for details",
            "Work",
            "2025-01-10 17:00:00",
            "1",
            "false",
            "2025-01-09 09:00:00",
        ])
        mock_run.return_value = rem_data

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

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_multiple_reminders_parsing(self, mock_run: pytest.fixture) -> None:
        """Multiple reminder records should parse correctly."""
        rem1 = UNIT_SEP.join([
            "rem-1", "Task 1", "", "Work", "2025-01-10 10:00:00",
            "1", "false", "2025-01-09 09:00:00",
        ])
        rem2 = UNIT_SEP.join([
            "rem-2", "Task 2", "", "Personal", "2025-01-11 14:00:00",
            "5", "false", "2025-01-09 10:00:00",
        ])
        mock_run.return_value = RECORD_SEP.join([rem1, rem2])

        result = get_reminders()

        assert len(result) == 2
        assert result[0].id == "rem-1"
        assert result[0].name == "Task 1"
        assert result[1].id == "rem-2"
        assert result[1].name == "Task 2"

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_malformed_record_skipped(self, mock_run: pytest.fixture) -> None:
        """Records with fewer than 8 fields should be skipped."""
        good_rem = UNIT_SEP.join([
            "rem-1", "Good Task", "", "Work", "2025-01-10 10:00:00",
            "1", "false", "2025-01-09 09:00:00",
        ])
        bad_rem = UNIT_SEP.join(["rem-2", "Bad Task"])  # Only 2 fields
        mock_run.return_value = RECORD_SEP.join([good_rem, bad_rem])

        result = get_reminders()

        assert len(result) == 1
        assert result[0].id == "rem-1"


class TestGetRemindersPriorityParsing:
    """Tests for priority field parsing."""

    @pytest.mark.parametrize(
        "priority_str,expected",
        [
            ("0", 0),
            ("1", 1),
            ("5", 5),
            ("9", 9),
        ],
    )
    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_valid_priority_parsing(
        self, mock_run: pytest.fixture, priority_str: str, expected: int
    ) -> None:
        """Valid priority integers should parse correctly."""
        rem_data = UNIT_SEP.join([
            "rem-1", "Task", "", "Work", "",
            priority_str, "false", "2025-01-09 09:00:00",
        ])
        mock_run.return_value = rem_data

        result = get_reminders()

        assert len(result) == 1
        assert result[0].priority == expected

    @pytest.mark.parametrize(
        "priority_str",
        ["", "invalid", "abc"],
    )
    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_invalid_priority_defaults_to_zero(
        self, mock_run: pytest.fixture, priority_str: str
    ) -> None:
        """Non-numeric priority values should default to 0."""
        rem_data = UNIT_SEP.join([
            "rem-1", "Task", "", "Work", "",
            priority_str, "false", "2025-01-09 09:00:00",
        ])
        mock_run.return_value = rem_data

        result = get_reminders()

        assert len(result) == 1
        assert result[0].priority == 0

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_negative_priority_parses_as_int(self, mock_run: pytest.fixture) -> None:
        """Negative priority parses as int (code doesn't validate semantics)."""
        rem_data = UNIT_SEP.join([
            "rem-1", "Task", "", "Work", "",
            "-1", "false", "2025-01-09 09:00:00",
        ])
        mock_run.return_value = rem_data

        result = get_reminders()

        assert len(result) == 1
        # Note: -1 parses as valid int; semantic validation not done
        assert result[0].priority == -1


class TestGetRemindersBooleanParsing:
    """Tests for boolean field parsing."""

    @pytest.mark.parametrize(
        "completed_str,expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("", False),
            ("invalid", False),
        ],
    )
    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_completed_boolean_parsing(
        self, mock_run: pytest.fixture, completed_str: str, expected: bool
    ) -> None:
        """Completed boolean should parse case-insensitively."""
        rem_data = UNIT_SEP.join([
            "rem-1", "Task", "", "Work", "",
            "0", completed_str, "2025-01-09 09:00:00",
        ])
        mock_run.return_value = rem_data

        result = get_reminders()

        assert len(result) == 1
        assert result[0].completed is expected


class TestGetRemindersOptionalFields:
    """Tests for optional field handling."""

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_empty_due_date(self, mock_run: pytest.fixture) -> None:
        """Empty due date should become None."""
        rem_data = UNIT_SEP.join([
            "rem-1", "Task", "", "Work", "",  # empty due_date
            "0", "false", "2025-01-09 09:00:00",
        ])
        mock_run.return_value = rem_data

        result = get_reminders()

        assert len(result) == 1
        assert result[0].due_date is None

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_empty_body(self, mock_run: pytest.fixture) -> None:
        """Empty body should be empty string."""
        rem_data = UNIT_SEP.join([
            "rem-1", "Task", "", "Work", "2025-01-10 10:00:00",
            "0", "false", "2025-01-09 09:00:00",
        ])
        mock_run.return_value = rem_data

        result = get_reminders()

        assert len(result) == 1
        assert result[0].body == ""


class TestGetRemindersDateParsing:
    """Tests for date field parsing within reminders."""

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_both_dates_parsed(self, mock_run: pytest.fixture) -> None:
        """Both due_date and creation_date should be parsed."""
        rem_data = UNIT_SEP.join([
            "rem-1", "Task", "", "Work",
            "Friday, January 10, 2025 at 5:00:00 PM",
            "1", "false",
            "Thursday, January 9, 2025 at 9:00:00 AM",
        ])
        mock_run.return_value = rem_data

        result = get_reminders()

        assert len(result) == 1
        assert result[0].due_date == datetime(2025, 1, 10, 17, 0, 0)
        assert result[0].creation_date == datetime(2025, 1, 9, 9, 0, 0)

    @patch("email_nurse.reminders.reminders.run_applescript")
    def test_unparseable_due_date_becomes_none(self, mock_run: pytest.fixture) -> None:
        """Unparseable due_date should become None."""
        rem_data = UNIT_SEP.join([
            "rem-1", "Task", "", "Work", "not a date",
            "1", "false", "2025-01-09 09:00:00",
        ])
        mock_run.return_value = rem_data

        result = get_reminders()

        assert len(result) == 1
        assert result[0].due_date is None
