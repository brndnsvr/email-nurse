"""Unit tests for sysm wrapper module."""

import json
from subprocess import CalledProcessError, TimeoutExpired
from unittest.mock import patch

import pytest

from email_nurse.mail.sysm import (
    SysmError,
    SysmNotFoundError,
    SysmTimeoutError,
    is_sysm_available,
    load_message_content_sysm,
    parse_sysm_message,
    run_sysm,
    run_sysm_json,
    get_messages_metadata_sysm,
    get_messages_sysm,
    _parse_date,
    _parse_recipients,
)


class TestIsSysmAvailable:
    """Tests for is_sysm_available()."""

    @patch("email_nurse.mail.sysm.shutil.which")
    def test_sysm_found(self, mock_which):
        """Test when sysm is found on PATH."""
        mock_which.return_value = "/usr/local/bin/sysm"
        assert is_sysm_available() is True
        mock_which.assert_called_once_with("sysm")

    @patch("email_nurse.mail.sysm.shutil.which")
    def test_sysm_not_found(self, mock_which):
        """Test when sysm is not found on PATH."""
        mock_which.return_value = None
        assert is_sysm_available() is False
        mock_which.assert_called_once_with("sysm")


class TestRunSysm:
    """Tests for run_sysm()."""

    @patch("email_nurse.mail.sysm.is_sysm_available")
    @patch("email_nurse.mail.sysm.subprocess.run")
    def test_success(self, mock_run, mock_available):
        """Test successful sysm command execution."""
        mock_available.return_value = True
        mock_run.return_value.stdout = "test output"
        mock_run.return_value.returncode = 0

        result = run_sysm(["mail", "inbox", "--json"])

        assert result == "test output"
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["sysm", "mail", "inbox", "--json"]

    @patch("email_nurse.mail.sysm.is_sysm_available")
    def test_binary_not_found(self, mock_available):
        """Test error when sysm binary not found."""
        mock_available.return_value = False

        with pytest.raises(SysmNotFoundError, match="sysm binary not found"):
            run_sysm(["mail", "inbox"])

    @patch("email_nurse.mail.sysm.is_sysm_available")
    @patch("email_nurse.mail.sysm.subprocess.run")
    def test_command_error(self, mock_run, mock_available):
        """Test error handling for failed command."""
        mock_available.return_value = True
        mock_run.side_effect = CalledProcessError(
            returncode=1,
            cmd=["sysm", "mail", "inbox"],
            stderr="command failed"
        )

        with pytest.raises(SysmError, match="exit code 1"):
            run_sysm(["mail", "inbox"])

    @patch("email_nurse.mail.sysm.is_sysm_available")
    @patch("email_nurse.mail.sysm.subprocess.run")
    def test_timeout(self, mock_run, mock_available):
        """Test timeout handling."""
        mock_available.return_value = True
        mock_run.side_effect = TimeoutExpired(
            cmd=["sysm", "mail", "inbox"],
            timeout=30
        )

        with pytest.raises(SysmTimeoutError, match="timed out after 30s"):
            run_sysm(["mail", "inbox"], timeout=30)


class TestRunSysmJson:
    """Tests for run_sysm_json()."""

    @patch("email_nurse.mail.sysm.run_sysm")
    def test_valid_json_dict(self, mock_run):
        """Test parsing valid JSON dict."""
        mock_run.return_value = '{"id": "123", "subject": "test"}'

        result = run_sysm_json(["mail", "inbox", "--json"])

        assert result == {"id": "123", "subject": "test"}

    @patch("email_nurse.mail.sysm.run_sysm")
    def test_valid_json_list(self, mock_run):
        """Test parsing valid JSON list."""
        mock_run.return_value = '[{"id": "1"}, {"id": "2"}]'

        result = run_sysm_json(["mail", "inbox", "--json"])

        assert result == [{"id": "1"}, {"id": "2"}]

    @patch("email_nurse.mail.sysm.run_sysm")
    def test_invalid_json(self, mock_run):
        """Test error on invalid JSON."""
        mock_run.return_value = "not json"

        with pytest.raises(SysmError, match="Failed to parse sysm JSON"):
            run_sysm_json(["mail", "inbox", "--json"])


class TestParseDateAndRecipients:
    """Tests for date and recipient parsing helpers."""

    def test_parse_date_iso8601_with_z(self):
        """Test parsing ISO 8601 date with Z suffix."""
        result = _parse_date("2025-01-20T10:30:00Z")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 20
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_date_iso8601_without_z(self):
        """Test parsing ISO 8601 date without Z suffix."""
        result = _parse_date("2025-01-20T10:30:00")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 20

    def test_parse_date_none(self):
        """Test parsing None date."""
        assert _parse_date(None) is None

    def test_parse_date_empty(self):
        """Test parsing empty date."""
        assert _parse_date("") is None

    def test_parse_date_invalid(self):
        """Test parsing invalid date."""
        result = _parse_date("not a date")
        assert result is None

    def test_parse_recipients_single(self):
        """Test parsing single recipient."""
        result = _parse_recipients("user@example.com")
        assert result == ["user@example.com"]

    def test_parse_recipients_multiple(self):
        """Test parsing multiple recipients."""
        result = _parse_recipients("user1@example.com, user2@example.com")
        assert result == ["user1@example.com", "user2@example.com"]

    def test_parse_recipients_with_whitespace(self):
        """Test parsing recipients with extra whitespace."""
        result = _parse_recipients("user1@example.com ,  user2@example.com  ")
        assert result == ["user1@example.com", "user2@example.com"]

    def test_parse_recipients_none(self):
        """Test parsing None recipients."""
        assert _parse_recipients(None) == []

    def test_parse_recipients_empty(self):
        """Test parsing empty recipients."""
        assert _parse_recipients("") == []


class TestParseSysmMessage:
    """Tests for parse_sysm_message()."""

    def test_parse_full_message(self):
        """Test parsing complete sysm message."""
        data = {
            "id": "12345",
            "subject": "Test Subject",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "dateReceived": "2025-01-20T10:30:00Z",
            "dateSent": "2025-01-20T10:25:00Z",
            "content": "Test body",
            "isRead": False,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        }

        result = parse_sysm_message(data, content_loaded=True)

        assert result.id == "12345"
        assert result.subject == "Test Subject"
        assert result.sender == "sender@example.com"
        assert result.recipients == ["recipient@example.com"]
        assert result.content == "Test body"
        assert result.is_read is False
        assert result.mailbox == "INBOX"
        assert result.account == "Test Account"
        assert result.message_id == ""  # sysm doesn't provide this
        assert result.content_loaded is True

    def test_parse_metadata_only(self):
        """Test parsing message without content."""
        data = {
            "id": "12345",
            "subject": "Test",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "dateReceived": "2025-01-20T10:30:00Z",
            "dateSent": "2025-01-20T10:25:00Z",
            "isRead": True,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        }

        result = parse_sysm_message(data, content_loaded=False)

        assert result.id == "12345"
        assert result.content == ""
        assert result.content_loaded is False

    def test_parse_multiple_recipients(self):
        """Test parsing message with multiple recipients."""
        data = {
            "id": "12345",
            "subject": "Test",
            "from": "sender@example.com",
            "to": "user1@example.com, user2@example.com",
            "dateReceived": "2025-01-20T10:30:00Z",
            "dateSent": "2025-01-20T10:25:00Z",
            "isRead": False,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        }

        result = parse_sysm_message(data, content_loaded=False)

        assert result.recipients == ["user1@example.com", "user2@example.com"]

    def test_parse_missing_fields(self):
        """Test parsing message with missing optional fields."""
        data = {
            "id": "12345"
        }

        result = parse_sysm_message(data, content_loaded=False)

        assert result.id == "12345"
        assert result.subject == ""
        assert result.sender == ""
        assert result.recipients == []
        assert result.date_received is None
        assert result.date_sent is None


class TestGetMessagesMetadataSysm:
    """Tests for get_messages_metadata_sysm()."""

    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_single_message(self, mock_run_json):
        """Test retrieving single message metadata."""
        mock_run_json.return_value = {
            "id": "12345",
            "subject": "Test",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "dateReceived": "2025-01-20T10:30:00Z",
            "dateSent": "2025-01-20T10:25:00Z",
            "isRead": False,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        }

        result = get_messages_metadata_sysm(limit=10)

        assert len(result) == 1
        assert result[0].id == "12345"
        assert result[0].content_loaded is False

    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_multiple_messages(self, mock_run_json):
        """Test retrieving multiple messages metadata."""
        mock_run_json.return_value = [
            {"id": "1", "subject": "First", "from": "a@ex.com", "to": "b@ex.com",
             "dateReceived": "2025-01-20T10:00:00Z", "dateSent": "2025-01-20T09:55:00Z",
             "isRead": False, "mailbox": "INBOX", "accountName": "Test"},
            {"id": "2", "subject": "Second", "from": "c@ex.com", "to": "d@ex.com",
             "dateReceived": "2025-01-20T11:00:00Z", "dateSent": "2025-01-20T10:55:00Z",
             "isRead": True, "mailbox": "INBOX", "accountName": "Test"}
        ]

        result = get_messages_metadata_sysm(limit=50)

        assert len(result) == 2
        assert result[0].id == "1"
        assert result[1].id == "2"
        assert all(not msg.content_loaded for msg in result)

    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_with_account_filter(self, mock_run_json):
        """Test retrieving messages with account filter."""
        mock_run_json.return_value = []

        get_messages_metadata_sysm(account="Work", limit=10)

        # Verify --account flag was passed
        call_args = mock_run_json.call_args[0][0]
        assert "--account" in call_args
        assert "Work" in call_args

    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_unread_only(self, mock_run_json):
        """Test retrieving unread messages only."""
        mock_run_json.return_value = []

        get_messages_metadata_sysm(unread_only=True, limit=10)

        # Verify "unread" command was used
        call_args = mock_run_json.call_args[0][0]
        assert "unread" in call_args


class TestGetMessagesSysm:
    """Tests for get_messages_sysm()."""

    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_with_content(self, mock_run_json):
        """Test retrieving messages with content."""
        mock_run_json.return_value = [{
            "id": "12345",
            "subject": "Test",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "dateReceived": "2025-01-20T10:30:00Z",
            "dateSent": "2025-01-20T10:25:00Z",
            "content": "Full message content here",
            "isRead": False,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        }]

        result = get_messages_sysm(limit=10)

        assert len(result) == 1
        assert result[0].content == "Full message content here"
        assert result[0].content_loaded is True

        # Verify --with-content flag was passed
        call_args = mock_run_json.call_args[0][0]
        assert "--with-content" in call_args


class TestLoadMessageContentSysm:
    """Tests for load_message_content_sysm()."""

    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_load_content(self, mock_run_json, sample_email):
        """Test loading content for a message."""
        mock_run_json.return_value = {
            "id": "12345",
            "content": "Loaded content"
        }

        sample_email.content = ""
        sample_email.content_loaded = False

        result = load_message_content_sysm(sample_email)

        assert result == "Loaded content"
        assert sample_email.content == "Loaded content"
        assert sample_email.content_loaded is True

    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_load_content_list_response(self, mock_run_json, sample_email):
        """Test loading content when sysm returns a list."""
        mock_run_json.return_value = [{
            "id": "12345",
            "content": "Content from list"
        }]

        sample_email.content = ""
        sample_email.content_loaded = False

        result = load_message_content_sysm(sample_email)

        assert result == "Content from list"
        assert sample_email.content == "Content from list"
        assert sample_email.content_loaded is True

    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_load_empty_content(self, mock_run_json, sample_email):
        """Test loading when content is missing."""
        mock_run_json.return_value = {"id": "12345"}

        sample_email.content = ""
        sample_email.content_loaded = False

        result = load_message_content_sysm(sample_email)

        assert result == ""
        assert sample_email.content == ""
        assert sample_email.content_loaded is True
