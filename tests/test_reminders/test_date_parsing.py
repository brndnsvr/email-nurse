"""Tests for date parsing in reminders module."""

from datetime import datetime

import pytest

from email_nurse.reminders.reminders import _parse_date


class TestParseDateEmptyInputs:
    """Tests for empty/missing value handling."""

    def test_empty_string_returns_none(self) -> None:
        """Empty string should return None."""
        assert _parse_date("") is None

    def test_missing_value_returns_none(self) -> None:
        """AppleScript 'missing value' sentinel should return None."""
        assert _parse_date("missing value") is None


class TestParseDateUSFormats:
    """Tests for US English locale date formats."""

    @pytest.mark.parametrize(
        "date_str,expected",
        [
            # Full US format with AM/PM
            (
                "Friday, December 20, 2024 at 10:30:00 AM",
                datetime(2024, 12, 20, 10, 30, 0),
            ),
            (
                "Monday, January 6, 2025 at 3:45:00 PM",
                datetime(2025, 1, 6, 15, 45, 0),
            ),
            # Full US format with 24-hour time
            (
                "Friday, December 20, 2024 at 22:30:00",
                datetime(2024, 12, 20, 22, 30, 0),
            ),
            # Abbreviated format with AM/PM
            (
                "Fri, Dec 20, 2024 at 10:30:00 AM",
                datetime(2024, 12, 20, 10, 30, 0),
            ),
            (
                "Mon, Jan 6, 2025 at 3:45:00 PM",
                datetime(2025, 1, 6, 15, 45, 0),
            ),
            # Abbreviated format with 24-hour time
            (
                "Fri, Dec 20, 2024 at 22:30:00",
                datetime(2024, 12, 20, 22, 30, 0),
            ),
            # Without day name
            (
                "December 20, 2024 at 10:30:00 AM",
                datetime(2024, 12, 20, 10, 30, 0),
            ),
            (
                "December 20, 2024 at 22:30:00",
                datetime(2024, 12, 20, 22, 30, 0),
            ),
            # Without seconds
            (
                "Friday, December 20, 2024 at 10:30 AM",
                datetime(2024, 12, 20, 10, 30, 0),
            ),
        ],
    )
    def test_us_date_formats(self, date_str: str, expected: datetime) -> None:
        """Test various US English date formats."""
        result = _parse_date(date_str)
        assert result == expected


class TestParseDateISOFormats:
    """Tests for ISO 8601 date formats."""

    @pytest.mark.parametrize(
        "date_str,expected",
        [
            # Full ISO with T separator
            ("2024-12-20T10:30:00", datetime(2024, 12, 20, 10, 30, 0)),
            ("2025-01-06T15:45:30", datetime(2025, 1, 6, 15, 45, 30)),
            # ISO with space separator
            ("2024-12-20 22:30:00", datetime(2024, 12, 20, 22, 30, 0)),
            ("2025-01-06 08:00:00", datetime(2025, 1, 6, 8, 0, 0)),
            # Date only (reminders without time)
            ("2024-12-20", datetime(2024, 12, 20, 0, 0, 0)),
            ("2025-01-06", datetime(2025, 1, 6, 0, 0, 0)),
            # Without seconds
            ("2024-12-20 22:30", datetime(2024, 12, 20, 22, 30, 0)),
        ],
    )
    def test_iso_date_formats(self, date_str: str, expected: datetime) -> None:
        """Test ISO 8601 date formats."""
        result = _parse_date(date_str)
        assert result == expected


class TestParseDateNumericFormats:
    """Tests for numeric date formats (US and European)."""

    @pytest.mark.parametrize(
        "date_str,expected",
        [
            # US numeric (MM/DD/YYYY) - unambiguous when day > 12
            ("12/20/2024 22:30:00", datetime(2024, 12, 20, 22, 30, 0)),
            # US numeric with AM/PM
            ("12/20/2024 10:30:00 PM", datetime(2024, 12, 20, 22, 30, 0)),
            # European numeric (DD/MM/YYYY) - unambiguous when day > 12
            ("20/12/2024 22:30:00", datetime(2024, 12, 20, 22, 30, 0)),
            ("25/01/2025 08:00:00", datetime(2025, 1, 25, 8, 0, 0)),
            # European with AM/PM
            ("20/12/2024 10:30:00 PM", datetime(2024, 12, 20, 22, 30, 0)),
            # Note: Ambiguous dates like "01/06/2025" are not tested as
            # the result depends on parser order (US vs European first)
        ],
    )
    def test_numeric_date_formats(self, date_str: str, expected: datetime) -> None:
        """Test numeric date formats."""
        result = _parse_date(date_str)
        assert result == expected


class TestParseDateInvalidInputs:
    """Tests for invalid/unrecognized date formats."""

    @pytest.mark.parametrize(
        "date_str",
        [
            "not a date",
            "tomorrow",
            "2024-13-45",  # Invalid month/day
            "abc123",
            "12:30:00",  # Time only
        ],
    )
    def test_invalid_formats_return_none(self, date_str: str) -> None:
        """Invalid formats should return None (with warning printed)."""
        result = _parse_date(date_str)
        assert result is None


class TestParseDateEdgeCases:
    """Edge case tests for date parsing."""

    def test_midnight(self) -> None:
        """Test midnight time (00:00:00)."""
        result = _parse_date("2024-12-20 00:00:00")
        assert result == datetime(2024, 12, 20, 0, 0, 0)

    def test_end_of_day(self) -> None:
        """Test end of day time (23:59:59)."""
        result = _parse_date("2024-12-20 23:59:59")
        assert result == datetime(2024, 12, 20, 23, 59, 59)

    def test_noon_am_pm(self) -> None:
        """Test noon with AM/PM format."""
        result = _parse_date("Friday, December 20, 2024 at 12:00:00 PM")
        assert result == datetime(2024, 12, 20, 12, 0, 0)

    def test_midnight_am_pm(self) -> None:
        """Test midnight with AM/PM format."""
        result = _parse_date("Friday, December 20, 2024 at 12:00:00 AM")
        assert result == datetime(2024, 12, 20, 0, 0, 0)

    def test_leap_year_date(self) -> None:
        """Test February 29 on a leap year."""
        result = _parse_date("2024-02-29")
        assert result == datetime(2024, 2, 29, 0, 0, 0)

    def test_year_boundary(self) -> None:
        """Test New Year's Eve/Day."""
        assert _parse_date("2024-12-31 23:59:59") == datetime(2024, 12, 31, 23, 59, 59)
        assert _parse_date("2025-01-01 00:00:00") == datetime(2025, 1, 1, 0, 0, 0)
