"""Tests for reminder deduplication."""

import pytest

from email_nurse.storage.database import AutopilotDatabase


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    return AutopilotDatabase(db_path)


class TestReminderTracking:
    """Tests for reminder tracking in database."""

    def test_has_reminder_for_email_false_when_none(self, temp_db):
        """has_reminder_for_email returns False when no reminder exists."""
        assert temp_db.has_reminder_for_email("nonexistent-id") is False

    def test_has_reminder_for_email_true_after_recording(self, temp_db):
        """has_reminder_for_email returns True after recording."""
        temp_db.record_reminder_created(
            message_id="test-123",
            reminder_id="rem-456",
            reminder_name="Test Reminder",
            reminder_list="Work",
        )
        assert temp_db.has_reminder_for_email("test-123") is True

    def test_has_reminder_for_email_false_for_different_id(self, temp_db):
        """has_reminder_for_email returns False for different message_id."""
        temp_db.record_reminder_created(
            message_id="test-123",
            reminder_id="rem-456",
            reminder_name="Test Reminder",
            reminder_list="Work",
        )
        assert temp_db.has_reminder_for_email("other-id") is False

    def test_get_reminder_for_email_returns_none_when_none(self, temp_db):
        """get_reminder_for_email returns None when no reminder exists."""
        assert temp_db.get_reminder_for_email("nonexistent-id") is None

    def test_get_reminder_for_email_returns_details(self, temp_db):
        """get_reminder_for_email returns full reminder details."""
        temp_db.record_reminder_created(
            message_id="test-123",
            reminder_id="rem-456",
            reminder_name="Test Reminder",
            reminder_list="Work",
        )
        result = temp_db.get_reminder_for_email("test-123")
        assert result is not None
        assert result["message_id"] == "test-123"
        assert result["reminder_id"] == "rem-456"
        assert result["reminder_name"] == "Test Reminder"
        assert result["reminder_list"] == "Work"
        assert "created_at" in result

    def test_record_reminder_created_updates_existing(self, temp_db):
        """Recording again updates the existing record (INSERT OR REPLACE)."""
        temp_db.record_reminder_created(
            message_id="test-123",
            reminder_id="rem-old",
            reminder_name="Old Name",
            reminder_list="Work",
        )
        temp_db.record_reminder_created(
            message_id="test-123",
            reminder_id="rem-new",
            reminder_name="New Name",
            reminder_list="Personal",
        )
        result = temp_db.get_reminder_for_email("test-123")
        assert result["reminder_id"] == "rem-new"
        assert result["reminder_name"] == "New Name"
        assert result["reminder_list"] == "Personal"

    def test_multiple_emails_tracked_independently(self, temp_db):
        """Each email's reminder is tracked independently."""
        temp_db.record_reminder_created(
            message_id="email-1",
            reminder_id="rem-1",
            reminder_name="Reminder 1",
            reminder_list="Work",
        )
        temp_db.record_reminder_created(
            message_id="email-2",
            reminder_id="rem-2",
            reminder_name="Reminder 2",
            reminder_list="Personal",
        )

        assert temp_db.has_reminder_for_email("email-1") is True
        assert temp_db.has_reminder_for_email("email-2") is True

        result1 = temp_db.get_reminder_for_email("email-1")
        result2 = temp_db.get_reminder_for_email("email-2")

        assert result1["reminder_name"] == "Reminder 1"
        assert result2["reminder_name"] == "Reminder 2"

    def test_cleanup_old_reminder_records_returns_count(self, temp_db):
        """cleanup_old_reminder_records returns deletion count."""
        temp_db.record_reminder_created(
            message_id="test-123",
            reminder_id="rem-456",
            reminder_name="Test",
            reminder_list="Work",
        )
        # Cleanup with very high retention should delete nothing
        deleted = temp_db.cleanup_old_reminder_records(9999)
        assert deleted == 0

    def test_table_created_on_init(self, tmp_path):
        """Verify the created_reminders table exists after init."""
        import sqlite3

        db_path = tmp_path / "test.db"
        AutopilotDatabase(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='created_reminders'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "created_reminders"
