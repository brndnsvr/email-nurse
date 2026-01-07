"""Tests for calendar list parsing."""

from unittest.mock import patch

import pytest

from email_nurse.calendar.calendars import Calendar, get_calendar_names, get_calendars

# Import separators from conftest
RECORD_SEP = "\x1e"
UNIT_SEP = "\x1f"


class TestGetCalendarsEmptyResults:
    """Tests for empty result handling."""

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_empty_string_returns_empty_list(self, mock_run: pytest.fixture) -> None:
        """Empty string from AppleScript should return empty list."""
        mock_run.return_value = ""
        result = get_calendars()
        assert result == []

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_none_returns_empty_list(self, mock_run: pytest.fixture) -> None:
        """None result should be handled as empty."""
        mock_run.return_value = None
        result = get_calendars()
        assert result == []


class TestGetCalendarsRecordParsing:
    """Tests for record parsing logic."""

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_single_calendar_parsing(self, mock_run: pytest.fixture) -> None:
        """Single calendar record should parse correctly."""
        cal_data = UNIT_SEP.join(["Work", "Work", "Work calendar", "true"])
        mock_run.return_value = cal_data

        result = get_calendars()

        assert len(result) == 1
        cal = result[0]
        assert cal.id == "Work"
        assert cal.name == "Work"
        assert cal.description == "Work calendar"
        assert cal.writable is True

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_multiple_calendars_parsing(self, mock_run: pytest.fixture) -> None:
        """Multiple calendar records should parse correctly."""
        cal1 = UNIT_SEP.join(["Work", "Work", "Work calendar", "true"])
        cal2 = UNIT_SEP.join(["Personal", "Personal", "", "true"])
        cal3 = UNIT_SEP.join(["Holidays", "Holidays", "Public holidays", "false"])
        mock_run.return_value = RECORD_SEP.join([cal1, cal2, cal3])

        result = get_calendars()

        assert len(result) == 3
        assert result[0].name == "Work"
        assert result[1].name == "Personal"
        assert result[2].name == "Holidays"

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_malformed_record_skipped(self, mock_run: pytest.fixture) -> None:
        """Records with fewer than 4 fields should be skipped."""
        good_cal = UNIT_SEP.join(["Work", "Work", "Description", "true"])
        bad_cal = UNIT_SEP.join(["Bad", "Calendar"])  # Only 2 fields
        mock_run.return_value = RECORD_SEP.join([good_cal, bad_cal])

        result = get_calendars()

        assert len(result) == 1
        assert result[0].name == "Work"


class TestGetCalendarsBooleanParsing:
    """Tests for boolean field parsing."""

    @pytest.mark.parametrize(
        "writable_str,expected",
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
    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_writable_boolean_parsing(
        self, mock_run: pytest.fixture, writable_str: str, expected: bool
    ) -> None:
        """Writable boolean should parse case-insensitively."""
        cal_data = UNIT_SEP.join(["Test", "Test", "", writable_str])
        mock_run.return_value = cal_data

        result = get_calendars()

        assert len(result) == 1
        assert result[0].writable is expected


class TestGetCalendarsEmptyFields:
    """Tests for empty field handling."""

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_empty_description(self, mock_run: pytest.fixture) -> None:
        """Calendar with empty description should work."""
        cal_data = UNIT_SEP.join(["Personal", "Personal", "", "true"])
        mock_run.return_value = cal_data

        result = get_calendars()

        assert len(result) == 1
        assert result[0].description == ""


class TestCalendarDataclass:
    """Tests for Calendar dataclass."""

    def test_str_returns_name(self) -> None:
        """Calendar __str__ should return the name."""
        cal = Calendar(id="test", name="My Calendar", description="", writable=True)
        assert str(cal) == "My Calendar"


class TestGetCalendarNames:
    """Tests for get_calendar_names function."""

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_empty_result(self, mock_run: pytest.fixture) -> None:
        """Empty result should return empty list."""
        mock_run.return_value = ""
        result = get_calendar_names()
        assert result == []

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_single_name(self, mock_run: pytest.fixture) -> None:
        """Single name should return single-item list."""
        mock_run.return_value = "Work"
        result = get_calendar_names()
        assert result == ["Work"]

    @patch("email_nurse.calendar.calendars.run_applescript")
    def test_multiple_names(self, mock_run: pytest.fixture) -> None:
        """Multiple names should be split by record separator."""
        mock_run.return_value = RECORD_SEP.join(["Work", "Personal", "Holidays"])
        result = get_calendar_names()
        assert result == ["Work", "Personal", "Holidays"]
