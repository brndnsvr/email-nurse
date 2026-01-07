"""Tests for reminder list parsing."""

from unittest.mock import patch

import pytest

from email_nurse.reminders.lists import ReminderList, get_list_names, get_lists

# Import separators from conftest
RECORD_SEP = "\x1e"
UNIT_SEP = "\x1f"


class TestGetListsEmptyResults:
    """Tests for empty result handling."""

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_empty_string_returns_empty_list(self, mock_run: pytest.fixture) -> None:
        """Empty string from AppleScript should return empty list."""
        mock_run.return_value = ""
        result = get_lists()
        assert result == []

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_none_returns_empty_list(self, mock_run: pytest.fixture) -> None:
        """None result should be handled as empty."""
        mock_run.return_value = None
        result = get_lists()
        assert result == []


class TestGetListsRecordParsing:
    """Tests for record parsing logic."""

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_single_list_parsing(self, mock_run: pytest.fixture) -> None:
        """Single list record should parse correctly."""
        # Fields: id, name, count
        list_data = UNIT_SEP.join(["list-123", "Work", "5"])
        mock_run.return_value = list_data

        result = get_lists()

        assert len(result) == 1
        lst = result[0]
        assert lst.id == "list-123"
        assert lst.name == "Work"
        assert lst.count == 5

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_multiple_lists_parsing(self, mock_run: pytest.fixture) -> None:
        """Multiple list records should parse correctly."""
        list1 = UNIT_SEP.join(["list-1", "Reminders", "10"])
        list2 = UNIT_SEP.join(["list-2", "Work", "5"])
        list3 = UNIT_SEP.join(["list-3", "Shopping", "0"])
        mock_run.return_value = RECORD_SEP.join([list1, list2, list3])

        result = get_lists()

        assert len(result) == 3
        assert result[0].name == "Reminders"
        assert result[0].count == 10
        assert result[1].name == "Work"
        assert result[1].count == 5
        assert result[2].name == "Shopping"
        assert result[2].count == 0

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_malformed_record_skipped(self, mock_run: pytest.fixture) -> None:
        """Records with fewer than 3 fields should be skipped."""
        good_list = UNIT_SEP.join(["list-1", "Good List", "5"])
        bad_list = UNIT_SEP.join(["list-2", "Bad List"])  # Only 2 fields
        mock_run.return_value = RECORD_SEP.join([good_list, bad_list])

        result = get_lists()

        assert len(result) == 1
        assert result[0].name == "Good List"


class TestGetListsCountParsing:
    """Tests for count field parsing."""

    @pytest.mark.parametrize(
        "count_str,expected",
        [
            ("0", 0),
            ("1", 1),
            ("10", 10),
            ("100", 100),
            ("1000", 1000),
        ],
    )
    @patch("email_nurse.reminders.lists.run_applescript")
    def test_valid_count_parsing(
        self, mock_run: pytest.fixture, count_str: str, expected: int
    ) -> None:
        """Valid count integers should parse correctly."""
        list_data = UNIT_SEP.join(["list-1", "Test", count_str])
        mock_run.return_value = list_data

        result = get_lists()

        assert len(result) == 1
        assert result[0].count == expected

    @pytest.mark.parametrize(
        "count_str",
        ["", "invalid", "abc"],
    )
    @patch("email_nurse.reminders.lists.run_applescript")
    def test_invalid_count_defaults_to_zero(
        self, mock_run: pytest.fixture, count_str: str
    ) -> None:
        """Non-numeric count values should default to 0."""
        list_data = UNIT_SEP.join(["list-1", "Test", count_str])
        mock_run.return_value = list_data

        result = get_lists()

        assert len(result) == 1
        assert result[0].count == 0

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_negative_count_parses_as_int(self, mock_run: pytest.fixture) -> None:
        """Negative count parses as int (code doesn't validate semantics)."""
        list_data = UNIT_SEP.join(["list-1", "Test", "-1"])
        mock_run.return_value = list_data

        result = get_lists()

        assert len(result) == 1
        # Note: -1 parses as valid int; semantic validation not done
        assert result[0].count == -1


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

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_empty_result(self, mock_run: pytest.fixture) -> None:
        """Empty result should return empty list."""
        mock_run.return_value = ""
        result = get_list_names()
        assert result == []

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_single_name(self, mock_run: pytest.fixture) -> None:
        """Single name should return single-item list."""
        mock_run.return_value = "Reminders"
        result = get_list_names()
        assert result == ["Reminders"]

    @patch("email_nurse.reminders.lists.run_applescript")
    def test_multiple_names(self, mock_run: pytest.fixture) -> None:
        """Multiple names should be split by record separator."""
        mock_run.return_value = RECORD_SEP.join(["Reminders", "Work", "Shopping"])
        result = get_list_names()
        assert result == ["Reminders", "Work", "Shopping"]
