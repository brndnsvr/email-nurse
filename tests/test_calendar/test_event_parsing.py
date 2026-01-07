"""Tests for calendar event parsing."""

from datetime import datetime
from unittest.mock import patch

import pytest

from email_nurse.calendar.events import get_events

# Import separators from conftest
RECORD_SEP = "\x1e"
UNIT_SEP = "\x1f"


class TestGetEventsEmptyResults:
    """Tests for empty result handling."""

    @patch("email_nurse.calendar.events.run_applescript")
    def test_empty_string_returns_empty_list(self, mock_run: pytest.fixture) -> None:
        """Empty string from AppleScript should return empty list."""
        mock_run.return_value = ""
        result = get_events()
        assert result == []

    @patch("email_nurse.calendar.events.run_applescript")
    def test_none_returns_empty_list(self, mock_run: pytest.fixture) -> None:
        """None result should be handled as empty."""
        mock_run.return_value = None
        result = get_events()
        assert result == []


class TestGetEventsRecordParsing:
    """Tests for record parsing logic."""

    @patch("email_nurse.calendar.events.run_applescript")
    def test_single_event_parsing(self, mock_run: pytest.fixture) -> None:
        """Single event record should parse correctly."""
        event_data = UNIT_SEP.join([
            "evt-123",
            "Team Meeting",
            "Weekly standup",
            "Room A",
            "2025-01-10 10:00:00",
            "2025-01-10 11:00:00",
            "false",
            "Work",
            "",
            "",
        ])
        mock_run.return_value = event_data

        result = get_events()

        assert len(result) == 1
        event = result[0]
        assert event.id == "evt-123"
        assert event.summary == "Team Meeting"
        assert event.description == "Weekly standup"
        assert event.location == "Room A"
        assert event.start_date == datetime(2025, 1, 10, 10, 0, 0)
        assert event.end_date == datetime(2025, 1, 10, 11, 0, 0)
        assert event.all_day is False
        assert event.calendar_name == "Work"
        assert event.url is None
        assert event.recurrence_rule is None

    @patch("email_nurse.calendar.events.run_applescript")
    def test_multiple_events_parsing(self, mock_run: pytest.fixture) -> None:
        """Multiple event records should parse correctly."""
        event1 = UNIT_SEP.join([
            "evt-1", "Meeting 1", "", "", "2025-01-10 10:00:00",
            "2025-01-10 11:00:00", "false", "Work", "", "",
        ])
        event2 = UNIT_SEP.join([
            "evt-2", "Meeting 2", "", "", "2025-01-10 14:00:00",
            "2025-01-10 15:00:00", "false", "Work", "", "",
        ])
        mock_run.return_value = RECORD_SEP.join([event1, event2])

        result = get_events()

        assert len(result) == 2
        assert result[0].id == "evt-1"
        assert result[1].id == "evt-2"

    @patch("email_nurse.calendar.events.run_applescript")
    def test_malformed_record_skipped(self, mock_run: pytest.fixture) -> None:
        """Records with fewer than 10 fields should be skipped."""
        good_event = UNIT_SEP.join([
            "evt-1", "Good Event", "", "", "2025-01-10 10:00:00",
            "2025-01-10 11:00:00", "false", "Work", "", "",
        ])
        bad_event = UNIT_SEP.join(["evt-2", "Bad Event"])  # Only 2 fields
        mock_run.return_value = RECORD_SEP.join([good_event, bad_event])

        result = get_events()

        assert len(result) == 1
        assert result[0].id == "evt-1"


class TestGetEventsBooleanParsing:
    """Tests for boolean field parsing."""

    @pytest.mark.parametrize(
        "all_day_str,expected",
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
    @patch("email_nurse.calendar.events.run_applescript")
    def test_all_day_boolean_parsing(
        self, mock_run: pytest.fixture, all_day_str: str, expected: bool
    ) -> None:
        """All-day boolean should parse case-insensitively."""
        event_data = UNIT_SEP.join([
            "evt-1", "Event", "", "", "2025-01-10",
            "2025-01-10", all_day_str, "Work", "", "",
        ])
        mock_run.return_value = event_data

        result = get_events()

        assert len(result) == 1
        assert result[0].all_day is expected


class TestGetEventsOptionalFields:
    """Tests for optional field handling."""

    @patch("email_nurse.calendar.events.run_applescript")
    def test_empty_optional_fields_become_none(self, mock_run: pytest.fixture) -> None:
        """Empty strings for optional fields should become None."""
        event_data = UNIT_SEP.join([
            "evt-1", "Event", "", "",  # empty description and location
            "2025-01-10 10:00:00", "2025-01-10 11:00:00",
            "false", "Work", "", "",  # empty url and recurrence
        ])
        mock_run.return_value = event_data

        result = get_events()

        assert len(result) == 1
        assert result[0].location is None
        assert result[0].url is None
        assert result[0].recurrence_rule is None
        # description stays as empty string (not optional in same way)
        assert result[0].description == ""

    @patch("email_nurse.calendar.events.run_applescript")
    def test_url_field_preserved(self, mock_run: pytest.fixture) -> None:
        """Non-empty URL field should be preserved."""
        event_data = UNIT_SEP.join([
            "evt-1", "Event", "", "",
            "2025-01-10 10:00:00", "2025-01-10 11:00:00",
            "false", "Work", "message://<abc123>", "",
        ])
        mock_run.return_value = event_data

        result = get_events()

        assert result[0].url == "message://<abc123>"

    @patch("email_nurse.calendar.events.run_applescript")
    def test_recurrence_field_preserved(self, mock_run: pytest.fixture) -> None:
        """Non-empty recurrence field should be preserved."""
        event_data = UNIT_SEP.join([
            "evt-1", "Event", "", "",
            "2025-01-10 10:00:00", "2025-01-10 11:00:00",
            "false", "Work", "", "FREQ=WEEKLY;INTERVAL=1",
        ])
        mock_run.return_value = event_data

        result = get_events()

        assert result[0].recurrence_rule == "FREQ=WEEKLY;INTERVAL=1"


class TestGetEventsSorting:
    """Tests for event sorting behavior."""

    @patch("email_nurse.calendar.events.run_applescript")
    def test_events_sorted_by_start_date(self, mock_run: pytest.fixture) -> None:
        """Events should be returned sorted by start_date."""
        # Return events out of order
        event_later = UNIT_SEP.join([
            "evt-1", "Later", "", "", "2025-01-10 14:00:00",
            "2025-01-10 15:00:00", "false", "Work", "", "",
        ])
        event_earlier = UNIT_SEP.join([
            "evt-2", "Earlier", "", "", "2025-01-10 10:00:00",
            "2025-01-10 11:00:00", "false", "Work", "", "",
        ])
        mock_run.return_value = RECORD_SEP.join([event_later, event_earlier])

        result = get_events()

        assert len(result) == 2
        assert result[0].summary == "Earlier"
        assert result[1].summary == "Later"


class TestGetEventsDateParsing:
    """Tests for date field parsing within events."""

    @patch("email_nurse.calendar.events.run_applescript")
    def test_unparseable_dates_fallback_to_now(self, mock_run: pytest.fixture) -> None:
        """Events with unparseable dates should fallback to now."""
        event_data = UNIT_SEP.join([
            "evt-1", "Event", "", "",
            "not a date", "also not a date",
            "false", "Work", "", "",
        ])
        mock_run.return_value = event_data

        result = get_events()

        assert len(result) == 1
        # Should have datetime values (now), not None
        assert result[0].start_date is not None
        assert result[0].end_date is not None
