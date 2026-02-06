"""Integration tests for sysm message provider."""

from unittest.mock import MagicMock, patch

import pytest

from email_nurse.config import Settings
from email_nurse.mail.messages import (
    get_messages,
    get_messages_metadata,
    load_message_content,
)
from email_nurse.mail.sysm import SysmError


class TestAppleScriptMode:
    """Tests for applescript provider mode (never calls sysm)."""

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_get_messages_metadata_never_calls_sysm(self, mock_applescript, mock_settings):
        """Verify applescript mode never attempts sysm calls."""
        settings = Settings()
        settings.message_provider = "applescript"
        mock_settings.return_value = settings

        # Mock AppleScript response
        mock_applescript.return_value = ""

        result = get_messages_metadata(limit=10)

        # Should call AppleScript
        assert mock_applescript.called
        # Should NOT import or call sysm
        assert result == []

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_get_messages_never_calls_sysm(self, mock_applescript, mock_settings):
        """Verify applescript mode for get_messages."""
        settings = Settings()
        settings.message_provider = "applescript"
        mock_settings.return_value = settings

        mock_applescript.return_value = ""

        result = get_messages(limit=10)

        assert mock_applescript.called
        assert result == []

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_load_message_content_never_calls_sysm(self, mock_applescript, mock_settings, sample_email):
        """Verify applescript mode for load_message_content."""
        settings = Settings()
        settings.message_provider = "applescript"
        mock_settings.return_value = settings

        mock_applescript.return_value = "Content loaded via AppleScript"
        sample_email.content_loaded = False

        result = load_message_content(sample_email)

        assert mock_applescript.called
        assert result == "Content loaded via AppleScript"


class TestSysmMode:
    """Tests for sysm provider mode (never falls back to AppleScript)."""

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_get_messages_metadata_never_calls_applescript(self, mock_applescript, mock_sysm, mock_settings):
        """Verify sysm mode never falls back to AppleScript."""
        settings = Settings()
        settings.message_provider = "sysm"
        mock_settings.return_value = settings

        mock_sysm.return_value = []

        result = get_messages_metadata(limit=10)

        # Should call sysm
        assert mock_sysm.called
        # Should NOT call AppleScript
        assert not mock_applescript.called
        assert result == []

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_get_messages_never_calls_applescript(self, mock_applescript, mock_sysm, mock_settings):
        """Verify sysm mode for get_messages."""
        settings = Settings()
        settings.message_provider = "sysm"
        mock_settings.return_value = settings

        mock_sysm.return_value = []

        result = get_messages(limit=10)

        assert mock_sysm.called
        assert not mock_applescript.called
        assert result == []

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_sysm_mode_raises_on_error(self, mock_applescript, mock_sysm, mock_settings, sample_email):
        """Verify sysm mode raises errors instead of falling back."""
        settings = Settings()
        settings.message_provider = "sysm"
        mock_settings.return_value = settings

        mock_sysm.side_effect = SysmError("sysm failed")
        sample_email.content_loaded = False

        # Should raise error, not fall back to AppleScript
        with pytest.raises(SysmError, match="sysm failed"):
            load_message_content(sample_email)

        # AppleScript should never be called
        assert not mock_applescript.called


class TestHybridMode:
    """Tests for hybrid provider mode (tries sysm, falls back to AppleScript)."""

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_uses_sysm_when_available(self, mock_applescript, mock_sysm, mock_settings):
        """Verify hybrid mode uses sysm when it succeeds."""
        settings = Settings()
        settings.message_provider = "hybrid"
        mock_settings.return_value = settings

        mock_sysm.return_value = [{
            "id": "12345",
            "subject": "Test",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "dateReceived": "2025-01-20T10:30:00Z",
            "dateSent": "2025-01-20T10:25:00Z",
            "isRead": False,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        }]

        result = get_messages_metadata(limit=10)

        # Should call sysm
        assert mock_sysm.called
        # Should NOT call AppleScript (sysm succeeded)
        assert not mock_applescript.called
        assert len(result) == 1
        assert result[0].id == "12345"

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_falls_back_on_error(self, mock_applescript, mock_sysm, mock_settings):
        """Verify hybrid mode falls back to AppleScript on sysm error."""
        settings = Settings()
        settings.message_provider = "hybrid"
        mock_settings.return_value = settings

        # sysm fails
        mock_sysm.side_effect = SysmError("sysm failed")
        # AppleScript succeeds
        mock_applescript.return_value = ""

        result = get_messages_metadata(limit=10)

        # Both should be called
        assert mock_sysm.called
        assert mock_applescript.called
        # Should return AppleScript result
        assert result == []

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_falls_back_on_timeout(self, mock_applescript, mock_sysm, mock_settings):
        """Verify hybrid mode falls back on timeout."""
        settings = Settings()
        settings.message_provider = "hybrid"
        mock_settings.return_value = settings

        from email_nurse.mail.sysm import SysmTimeoutError

        # sysm times out
        mock_sysm.side_effect = SysmTimeoutError("timed out")
        # AppleScript succeeds
        mock_applescript.return_value = ""

        result = get_messages_metadata(limit=10)

        assert mock_sysm.called
        assert mock_applescript.called
        assert result == []

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_load_content_fallback(self, mock_applescript, mock_sysm, mock_settings, sample_email):
        """Verify hybrid mode falls back for load_message_content."""
        settings = Settings()
        settings.message_provider = "hybrid"
        mock_settings.return_value = settings

        # sysm fails
        mock_sysm.side_effect = SysmError("sysm failed")
        # AppleScript succeeds
        mock_applescript.return_value = "AppleScript content"
        sample_email.content_loaded = False

        result = load_message_content(sample_email)

        assert mock_sysm.called
        assert mock_applescript.called
        assert result == "AppleScript content"
        assert sample_email.content == "AppleScript content"
        assert sample_email.content_loaded is True


class TestProviderConfiguration:
    """Tests for provider configuration."""

    def test_default_provider_is_applescript(self):
        """Verify default provider is applescript for backward compatibility."""
        settings = Settings()
        assert settings.message_provider == "applescript"

    def test_sysm_timeout_defaults(self):
        """Verify sysm timeout defaults."""
        settings = Settings()
        assert settings.sysm_timeout == 30
        assert settings.sysm_fallback_timeout == 5

    @patch.dict("os.environ", {"EMAIL_NURSE_MESSAGE_PROVIDER": "sysm"})
    def test_provider_from_environment(self):
        """Verify provider can be set via environment variable."""
        settings = Settings()
        assert settings.message_provider == "sysm"


class TestEndToEnd:
    """End-to-end tests with realistic scenarios."""

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    def test_sysm_full_workflow(self, mock_sysm, mock_settings):
        """Test full workflow with sysm provider."""
        settings = Settings()
        settings.message_provider = "sysm"
        mock_settings.return_value = settings

        # Mock metadata retrieval
        mock_sysm.return_value = [{
            "id": "12345",
            "subject": "Test Email",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "dateReceived": "2025-01-20T10:30:00Z",
            "dateSent": "2025-01-20T10:25:00Z",
            "isRead": False,
            "mailbox": "INBOX",
            "accountName": "Test Account"
        }]

        # Get metadata
        messages = get_messages_metadata(limit=10)
        assert len(messages) == 1
        assert messages[0].content_loaded is False

        # Mock content loading
        mock_sysm.return_value = {
            "id": "12345",
            "content": "Full email content"
        }

        # Load content
        content = load_message_content(messages[0])
        assert content == "Full email content"
        assert messages[0].content_loaded is True

    @patch("email_nurse.mail.messages.Settings")
    @patch("email_nurse.mail.sysm.run_sysm_json")
    @patch("email_nurse.mail.messages.run_applescript")
    def test_hybrid_graceful_degradation(self, mock_applescript, mock_sysm, mock_settings):
        """Test hybrid mode gracefully degrades to AppleScript."""
        settings = Settings()
        settings.message_provider = "hybrid"
        mock_settings.return_value = settings

        # sysm fails for metadata
        mock_sysm.side_effect = SysmError("sysm not available")

        # AppleScript provides fallback (empty result for simplicity)
        mock_applescript.return_value = ""

        # Should succeed with AppleScript
        messages = get_messages_metadata(limit=10)
        assert messages == []
        assert mock_sysm.called
        assert mock_applescript.called
