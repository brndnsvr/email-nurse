"""Tests for calendar list parsing (sysm-backed)."""

from unittest.mock import patch

import pytest

from email_nurse.calendar.calendars import Calendar, get_calendar_names, get_calendars


class TestGetCalendarsEmptyResults:
    """Tests for empty result handling."""

    @patch("email_nurse.calendar.calendars.get_calendars_sysm")
    def test_empty_list_returns_empty(self, mock_sysm: pytest.fixture) -> None:
        """Empty sysm result should return empty list."""
        mock_sysm.return_value = []
        result = get_calendars()
        assert result == []


class TestGetCalendarsRecordParsing:
    """Tests for record parsing logic."""

    @patch("email_nurse.calendar.calendars.get_calendars_sysm")
    def test_single_calendar_parsing(self, mock_sysm: pytest.fixture) -> None:
        """Single calendar should parse correctly."""
        mock_sysm.return_value = [
            {"id": "Work", "name": "Work", "description": "Work calendar", "writable": True}
        ]

        result = get_calendars()

        assert len(result) == 1
        cal = result[0]
        assert cal.id == "Work"
        assert cal.name == "Work"
        assert cal.description == "Work calendar"
        assert cal.writable is True

    @patch("email_nurse.calendar.calendars.get_calendars_sysm")
    def test_multiple_calendars_parsing(self, mock_sysm: pytest.fixture) -> None:
        """Multiple calendars should parse correctly."""
        mock_sysm.return_value = [
            {"id": "Work", "name": "Work", "description": "Work calendar", "writable": True},
            {"id": "Personal", "name": "Personal", "description": "", "writable": True},
            {"id": "Holidays", "name": "Holidays", "description": "Public holidays", "writable": False},
        ]

        result = get_calendars()

        assert len(result) == 3
        assert result[0].name == "Work"
        assert result[1].name == "Personal"
        assert result[2].name == "Holidays"


class TestGetCalendarsBooleanParsing:
    """Tests for boolean field parsing."""

    @pytest.mark.parametrize(
        "writable_val,expected",
        [
            (True, True),
            (False, False),
            (1, True),
            (0, False),
        ],
    )
    @patch("email_nurse.calendar.calendars.get_calendars_sysm")
    def test_writable_boolean_parsing(
        self, mock_sysm: pytest.fixture, writable_val, expected: bool
    ) -> None:
        """Writable boolean should parse correctly."""
        mock_sysm.return_value = [
            {"id": "Test", "name": "Test", "description": "", "writable": writable_val}
        ]

        result = get_calendars()

        assert len(result) == 1
        assert result[0].writable is expected


class TestGetCalendarsEmptyFields:
    """Tests for empty field handling."""

    @patch("email_nurse.calendar.calendars.get_calendars_sysm")
    def test_empty_description(self, mock_sysm: pytest.fixture) -> None:
        """Calendar with empty description should work."""
        mock_sysm.return_value = [
            {"id": "Personal", "name": "Personal", "description": "", "writable": True}
        ]

        result = get_calendars()

        assert len(result) == 1
        assert result[0].description == ""

    @patch("email_nurse.calendar.calendars.get_calendars_sysm")
    def test_missing_fields_use_defaults(self, mock_sysm: pytest.fixture) -> None:
        """Missing fields should use default values."""
        mock_sysm.return_value = [{"name": "Minimal"}]

        result = get_calendars()

        assert len(result) == 1
        assert result[0].name == "Minimal"
        assert result[0].description == ""
        assert result[0].writable is True


class TestCalendarDataclass:
    """Tests for Calendar dataclass."""

    def test_str_returns_name(self) -> None:
        """Calendar __str__ should return the name."""
        cal = Calendar(id="test", name="My Calendar", description="", writable=True)
        assert str(cal) == "My Calendar"


class TestGetCalendarNames:
    """Tests for get_calendar_names function."""

    @patch("email_nurse.calendar.calendars.get_calendar_names_sysm")
    def test_empty_result(self, mock_sysm: pytest.fixture) -> None:
        """Empty result should return empty list."""
        mock_sysm.return_value = []
        result = get_calendar_names()
        assert result == []

    @patch("email_nurse.calendar.calendars.get_calendar_names_sysm")
    def test_single_name(self, mock_sysm: pytest.fixture) -> None:
        """Single name should return single-item list."""
        mock_sysm.return_value = ["Work"]
        result = get_calendar_names()
        assert result == ["Work"]

    @patch("email_nurse.calendar.calendars.get_calendar_names_sysm")
    def test_multiple_names(self, mock_sysm: pytest.fixture) -> None:
        """Multiple names should be returned correctly."""
        mock_sysm.return_value = ["Work", "Personal", "Holidays"]
        result = get_calendar_names()
        assert result == ["Work", "Personal", "Holidays"]
