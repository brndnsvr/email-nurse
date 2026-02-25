"""Tests for reminder list parsing (sysm-backed)."""

from unittest.mock import patch

import pytest

from email_nurse.reminders.lists import ReminderList, get_list_names, get_lists


class TestGetListsEmptyResults:
    """Tests for empty result handling."""

    @patch("email_nurse.reminders.lists.get_reminder_lists_sysm")
    def test_empty_list_returns_empty(self, mock_sysm: pytest.fixture) -> None:
        """Empty sysm result should return empty list."""
        mock_sysm.return_value = []
        result = get_lists()
        assert result == []


class TestGetListsRecordParsing:
    """Tests for record parsing logic."""

    @patch("email_nurse.reminders.lists.get_reminder_lists_sysm")
    def test_single_list_parsing(self, mock_sysm: pytest.fixture) -> None:
        """Single list should parse correctly."""
        mock_sysm.return_value = [
            {"id": "list-123", "name": "Work", "count": 5}
        ]

        result = get_lists()

        assert len(result) == 1
        lst = result[0]
        assert lst.id == "list-123"
        assert lst.name == "Work"
        assert lst.count == 5

    @patch("email_nurse.reminders.lists.get_reminder_lists_sysm")
    def test_multiple_lists_parsing(self, mock_sysm: pytest.fixture) -> None:
        """Multiple lists should parse correctly."""
        mock_sysm.return_value = [
            {"id": "list-1", "name": "Reminders", "count": 10},
            {"id": "list-2", "name": "Work", "count": 5},
            {"id": "list-3", "name": "Shopping", "count": 0},
        ]

        result = get_lists()

        assert len(result) == 3
        assert result[0].name == "Reminders"
        assert result[0].count == 10
        assert result[1].name == "Work"
        assert result[1].count == 5
        assert result[2].name == "Shopping"
        assert result[2].count == 0


class TestGetListsCountParsing:
    """Tests for count field parsing."""

    @pytest.mark.parametrize(
        "count_val,expected",
        [
            (0, 0),
            (1, 1),
            (10, 10),
            (100, 100),
            (1000, 1000),
        ],
    )
    @patch("email_nurse.reminders.lists.get_reminder_lists_sysm")
    def test_valid_count_parsing(
        self, mock_sysm: pytest.fixture, count_val: int, expected: int
    ) -> None:
        """Valid count integers should parse correctly."""
        mock_sysm.return_value = [{"id": "list-1", "name": "Test", "count": count_val}]

        result = get_lists()

        assert len(result) == 1
        assert result[0].count == expected

    @patch("email_nurse.reminders.lists.get_reminder_lists_sysm")
    def test_missing_count_defaults_to_zero(self, mock_sysm: pytest.fixture) -> None:
        """Missing count should default to 0."""
        mock_sysm.return_value = [{"id": "list-1", "name": "Test"}]

        result = get_lists()

        assert len(result) == 1
        assert result[0].count == 0


class TestReminderListDataclass:
    """Tests for ReminderList dataclass."""

    def test_str_returns_name_with_count(self) -> None:
        """ReminderList __str__ should return name with count."""
        lst = ReminderList(id="test", name="Work", count=5)
        assert str(lst) == "Work (5 items)"

    def test_str_zero_count(self) -> None:
        """ReminderList __str__ with zero count."""
        lst = ReminderList(id="test", name="Empty List", count=0)
        assert str(lst) == "Empty List (0 items)"


class TestGetListNames:
    """Tests for get_list_names function."""

    @patch("email_nurse.reminders.lists.get_reminder_lists_sysm")
    def test_empty_result(self, mock_sysm: pytest.fixture) -> None:
        """Empty result should return empty list."""
        mock_sysm.return_value = []
        result = get_list_names()
        assert result == []

    @patch("email_nurse.reminders.lists.get_reminder_lists_sysm")
    def test_single_name(self, mock_sysm: pytest.fixture) -> None:
        """Single name should return single-item list."""
        mock_sysm.return_value = [{"id": "list-1", "name": "Reminders"}]
        result = get_list_names()
        assert result == ["Reminders"]

    @patch("email_nurse.reminders.lists.get_reminder_lists_sysm")
    def test_multiple_names(self, mock_sysm: pytest.fixture) -> None:
        """Multiple names should be returned correctly."""
        mock_sysm.return_value = [
            {"id": "list-1", "name": "Reminders"},
            {"id": "list-2", "name": "Work"},
            {"id": "list-3", "name": "Shopping"},
        ]
        result = get_list_names()
        assert result == ["Reminders", "Work", "Shopping"]
