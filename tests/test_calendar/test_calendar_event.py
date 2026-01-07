"""Tests for CalendarEvent dataclass properties."""

from datetime import datetime

from email_nurse.calendar.events import CalendarEvent


def make_event(
    *,
    id: str = "evt-1",
    summary: str = "Test Event",
    description: str = "",
    location: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    all_day: bool = False,
    calendar_name: str = "Test",
    url: str | None = None,
    recurrence_rule: str | None = None,
) -> CalendarEvent:
    """Factory function for creating test events."""
    if start_date is None:
        start_date = datetime(2025, 1, 10, 10, 0, 0)
    if end_date is None:
        end_date = datetime(2025, 1, 10, 11, 0, 0)
    return CalendarEvent(
        id=id,
        summary=summary,
        description=description,
        location=location,
        start_date=start_date,
        end_date=end_date,
        all_day=all_day,
        calendar_name=calendar_name,
        url=url,
        recurrence_rule=recurrence_rule,
    )


class TestEmailLinkProperty:
    """Tests for the email_link property."""

    def test_url_field_with_message_scheme(self) -> None:
        """URL field with message:// should be returned directly."""
        event = make_event(url="message://<abc123@mail.com>")
        assert event.email_link == "message://<abc123@mail.com>"

    def test_url_field_non_message_scheme(self) -> None:
        """URL field with non-message scheme should fall back to description."""
        event = make_event(
            url="https://example.com",
            description="See message://<abc123@mail.com>",
        )
        # Falls back to description since URL is not message://
        assert event.email_link == "message://<abc123@mail.com>"

    def test_description_with_plain_message_link(self) -> None:
        """Message link in description without brackets."""
        event = make_event(description="Related email: message://abc123")
        assert event.email_link == "message://abc123"

    def test_description_with_bracketed_message_link(self) -> None:
        """Message link in description with angle brackets."""
        event = make_event(description="See <message://abc123@mail.com>")
        assert event.email_link == "message://abc123@mail.com>"

    def test_no_email_link(self) -> None:
        """No message link anywhere returns None."""
        event = make_event(
            url="https://example.com",
            description="Just a regular description",
        )
        assert event.email_link is None

    def test_empty_fields(self) -> None:
        """Empty URL and description returns None."""
        event = make_event(url=None, description="")
        assert event.email_link is None

    def test_url_takes_priority_over_description(self) -> None:
        """URL field message:// should take priority over description."""
        event = make_event(
            url="message://from-url",
            description="message://from-description",
        )
        assert event.email_link == "message://from-url"


class TestDurationMinutesProperty:
    """Tests for the duration_minutes property."""

    def test_all_day_event(self) -> None:
        """All-day event should return 24 * 60 minutes."""
        event = make_event(all_day=True)
        assert event.duration_minutes == 24 * 60  # 1440

    def test_one_hour_event(self) -> None:
        """One hour event."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 11, 0, 0),
        )
        assert event.duration_minutes == 60

    def test_90_minute_event(self) -> None:
        """90 minute event."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 11, 30, 0),
        )
        assert event.duration_minutes == 90

    def test_30_minute_event(self) -> None:
        """30 minute event."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 10, 30, 0),
        )
        assert event.duration_minutes == 30

    def test_zero_duration_event(self) -> None:
        """Zero duration event (start == end)."""
        same_time = datetime(2025, 1, 10, 10, 0, 0)
        event = make_event(start_date=same_time, end_date=same_time)
        assert event.duration_minutes == 0

    def test_multi_day_event(self) -> None:
        """Multi-day event."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 12, 10, 0, 0),
        )
        assert event.duration_minutes == 48 * 60  # 2 days


class TestDurationStrProperty:
    """Tests for the duration_str property."""

    def test_all_day_event(self) -> None:
        """All-day event should return 'all day'."""
        event = make_event(all_day=True)
        assert event.duration_str == "all day"

    def test_30_minutes(self) -> None:
        """30 minute duration."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 10, 30, 0),
        )
        assert event.duration_str == "30m"

    def test_45_minutes(self) -> None:
        """45 minute duration."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 10, 45, 0),
        )
        assert event.duration_str == "45m"

    def test_60_minutes(self) -> None:
        """60 minute duration should show as 1h."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 11, 0, 0),
        )
        assert event.duration_str == "1h"

    def test_90_minutes(self) -> None:
        """90 minute duration should show as 1h 30m."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 11, 30, 0),
        )
        assert event.duration_str == "1h 30m"

    def test_120_minutes(self) -> None:
        """120 minute duration should show as 2h."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 12, 0, 0),
        )
        assert event.duration_str == "2h"

    def test_150_minutes(self) -> None:
        """150 minute duration should show as 2h 30m."""
        event = make_event(
            start_date=datetime(2025, 1, 10, 10, 0, 0),
            end_date=datetime(2025, 1, 10, 12, 30, 0),
        )
        assert event.duration_str == "2h 30m"


class TestIsUpcomingProperty:
    """Tests for the is_upcoming property."""

    def test_future_event(self) -> None:
        """Future event should be upcoming."""
        event = make_event(start_date=datetime(2099, 1, 1, 10, 0, 0))
        assert event.is_upcoming is True

    def test_past_event(self) -> None:
        """Past event should not be upcoming."""
        event = make_event(start_date=datetime(2020, 1, 1, 10, 0, 0))
        assert event.is_upcoming is False


class TestStrMethod:
    """Tests for the __str__ method."""

    def test_regular_event_str(self) -> None:
        """Regular event string format."""
        event = make_event(
            summary="Team Meeting",
            start_date=datetime(2025, 1, 10, 14, 30, 0),
            all_day=False,
        )
        assert str(event) == "2025-01-10 14:30: Team Meeting"

    def test_all_day_event_str(self) -> None:
        """All-day event string format."""
        event = make_event(
            summary="Holiday",
            start_date=datetime(2025, 1, 10, 0, 0, 0),
            all_day=True,
        )
        assert str(event) == "2025-01-10 (all day): Holiday"
