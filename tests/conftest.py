"""Pytest fixtures for email-nurse tests."""

import json
from datetime import datetime
from subprocess import CompletedProcess

import pytest

from email_nurse.mail.messages import EmailMessage

# ASCII control characters used by AppleScript output
RECORD_SEP = "\x1e"  # ASCII 30 - Record Separator
UNIT_SEP = "\x1f"  # ASCII 31 - Unit Separator


# --- Calendar Fixtures ---


@pytest.fixture
def sample_calendar_output() -> str:
    """Sample AppleScript output for calendars (4 fields each)."""
    # Fields: id, name, description, writable
    cal1 = UNIT_SEP.join(["Work", "Work", "Work calendar", "true"])
    cal2 = UNIT_SEP.join(["Personal", "Personal", "", "true"])
    cal3 = UNIT_SEP.join(["Holidays", "Holidays", "Public holidays", "false"])
    return RECORD_SEP.join([cal1, cal2, cal3])


@pytest.fixture
def sample_event_output() -> str:
    """Sample AppleScript output for events (10 fields each)."""
    # Fields: id, summary, description, location, start, end, all_day, calendar, url, recurrence
    event1 = UNIT_SEP.join([
        "evt-1",
        "Team Meeting",
        "Weekly standup",
        "Conference Room A",
        "Friday, January 10, 2025 at 10:00:00 AM",
        "Friday, January 10, 2025 at 11:00:00 AM",
        "false",
        "Work",
        "",
        "",
    ])
    event2 = UNIT_SEP.join([
        "evt-2",
        "Birthday Party",
        "message://<abc123@mail.com>",
        "Home",
        "Saturday, January 11, 2025 at 2:00:00 PM",
        "Saturday, January 11, 2025 at 6:00:00 PM",
        "false",
        "Personal",
        "",
        "",
    ])
    event3 = UNIT_SEP.join([
        "evt-3",
        "Company Holiday",
        "",
        "",
        "2025-01-20",
        "2025-01-20",
        "true",
        "Work",
        "",
        "",
    ])
    return RECORD_SEP.join([event1, event2, event3])


# --- Reminders Fixtures ---


@pytest.fixture
def sample_reminder_output() -> str:
    """Sample AppleScript output for reminders (8 fields each)."""
    # Fields: id, name, body, list_name, due_date, priority, completed, creation_date
    rem1 = UNIT_SEP.join([
        "rem-1",
        "Review PR",
        "From email: message://<pr123@github.com>",
        "Work",
        "Friday, January 10, 2025 at 5:00:00 PM",
        "1",
        "false",
        "Thursday, January 9, 2025 at 9:00:00 AM",
    ])
    rem2 = UNIT_SEP.join([
        "rem-2",
        "Buy groceries",
        "",
        "Personal",
        "",
        "0",
        "false",
        "Wednesday, January 8, 2025 at 3:00:00 PM",
    ])
    rem3 = UNIT_SEP.join([
        "rem-3",
        "Call dentist",
        "Schedule checkup",
        "Personal",
        "2025-01-15",
        "5",
        "true",
        "2025-01-01T10:00:00",
    ])
    return RECORD_SEP.join([rem1, rem2, rem3])


@pytest.fixture
def sample_list_output() -> str:
    """Sample AppleScript output for reminder lists (3 fields each)."""
    # Fields: id, name, count
    list1 = UNIT_SEP.join(["list-1", "Reminders", "5"])
    list2 = UNIT_SEP.join(["list-2", "Work", "12"])
    list3 = UNIT_SEP.join(["list-3", "Shopping", "0"])
    return RECORD_SEP.join([list1, list2, list3])


@pytest.fixture
def sample_email() -> EmailMessage:
    """Create a sample email for testing."""
    return EmailMessage(
        id="12345",
        message_id="<abc123@example.com>",
        subject="Test Subject",
        sender="sender@example.com",
        recipients=["recipient@example.com"],
        date_received=datetime.now(),
        date_sent=datetime.now(),
        content="This is a test email body.",
        is_read=False,
        mailbox="INBOX",
        account="Test Account",
    )


@pytest.fixture
def newsletter_email() -> EmailMessage:
    """Create a newsletter-like email for testing."""
    return EmailMessage(
        id="12346",
        message_id="<news123@newsletter.com>",
        subject="Weekly Newsletter - December Edition",
        sender="newsletter@company.com",
        recipients=["user@example.com"],
        date_received=datetime.now(),
        date_sent=datetime.now(),
        content="Check out our latest updates! Click here to unsubscribe.",
        is_read=False,
        mailbox="INBOX",
        account="Test Account",
    )


@pytest.fixture
def spam_email() -> EmailMessage:
    """Create a spam-like email for testing."""
    return EmailMessage(
        id="12347",
        message_id="<spam456@spammer.net>",
        subject="URGENT: You're a WINNER! Claim your Bitcoin NOW!!!",
        sender="prince@nigeria.spam",
        recipients=["victim@example.com"],
        date_received=datetime.now(),
        date_sent=datetime.now(),
        content="Congratulations! You have won the lottery!",
        is_read=False,
        mailbox="INBOX",
        account="Test Account",
    )


# --- sysm Fixtures ---


@pytest.fixture
def sysm_single_message_json():
    """Sample JSON response from sysm for a single message."""
    return json.dumps({
        "id": "12345",
        "messageId": "abc123@example.com",
        "subject": "Test Subject",
        "from": "sender@example.com",
        "to": "recipient@example.com",
        "dateReceived": "Monday, January 20, 2025 at 10:30:00 AM",
        "dateSent": "Monday, January 20, 2025 at 10:25:00 AM",
        "content": "Test email body",
        "isRead": False,
        "mailbox": "INBOX",
        "accountName": "Test Account"
    })


@pytest.fixture
def sysm_multiple_messages_json():
    """Sample JSON response from sysm for multiple messages."""
    return json.dumps([
        {
            "id": "12345",
            "messageId": "abc123@example.com",
            "subject": "First Email",
            "from": "sender1@example.com",
            "to": "recipient@example.com",
            "dateReceived": "Monday, January 20, 2025 at 10:30:00 AM",
            "dateSent": "Monday, January 20, 2025 at 10:25:00 AM",
            "content": "First message",
            "isRead": False,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        },
        {
            "id": "12346",
            "messageId": "def456@example.com",
            "subject": "Second Email",
            "from": "sender2@example.com",
            "to": "recipient@example.com, cc@example.com",
            "dateReceived": "Monday, January 20, 2025 at 11:00:00 AM",
            "dateSent": "Monday, January 20, 2025 at 10:55:00 AM",
            "content": "Second message",
            "isRead": True,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        }
    ])


@pytest.fixture
def mock_sysm_success(sysm_single_message_json):
    """Mock successful sysm subprocess call."""
    def _mock(*args, **kwargs):
        return CompletedProcess(
            args=args[0] if args else [],
            returncode=0,
            stdout=sysm_single_message_json,
            stderr=""
        )
    return _mock


@pytest.fixture
def mock_sysm_failure():
    """Mock failed sysm subprocess call."""
    def _mock(*args, **kwargs):
        from subprocess import CalledProcessError
        raise CalledProcessError(
            returncode=1,
            cmd=args[0] if args else [],
            output="",
            stderr="sysm: command failed"
        )
    return _mock


@pytest.fixture
def mock_sysm_timeout():
    """Mock sysm subprocess timeout."""
    def _mock(*args, **kwargs):
        from subprocess import TimeoutExpired
        raise TimeoutExpired(
            cmd=args[0] if args else [],
            timeout=30
        )
    return _mock
