"""Pytest fixtures for email-nurse tests."""

from datetime import datetime

import pytest

from email_nurse.mail.messages import EmailMessage


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
