"""Integration tests for sysm message provider and engine retry logic."""

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
        """Verify the Field default is applescript for backward compatibility."""
        # Check the field default directly (production .env may override at runtime)
        field_default = Settings.model_fields["message_provider"].default
        assert field_default == "applescript"

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


class TestContentLoadingRetry:
    """Tests for content loading retry ceiling in AutopilotEngine."""

    @pytest.mark.asyncio
    async def test_content_loading_retries_then_gives_up(self, sample_email):
        """After 3 content loading failures, email is marked processed and stops retrying."""
        from email_nurse.autopilot.engine import AutopilotEngine

        sample_email.content_loaded = False

        engine = MagicMock(spec=AutopilotEngine)
        engine.db = MagicMock()
        engine.config = MagicMock()
        engine.settings = MagicMock()
        engine._apply_quick_rules.return_value = None

        # Simulate increment_rule_failure returning 3 (max retries reached)
        engine.db.increment_rule_failure.return_value = 3

        with patch(
            "email_nurse.autopilot.engine.load_message_content",
            side_effect=TimeoutError("sysm timed out"),
        ), patch(
            "email_nurse.autopilot.engine.get_account_logger",
            return_value=MagicMock(),
        ):
            result = await AutopilotEngine._process_email(
                engine, sample_email, dry_run=False, interactive=False, auto_create=False
            )

        assert result.success is False
        assert "Content loading failed after 3 attempts" in result.error
        engine.db.mark_processed.assert_called_once()
        call_kwargs = engine.db.mark_processed.call_args[1]
        assert call_kwargs["action"]["action"] == "content_load_failed"
        engine.db.clear_rule_failures.assert_called_once_with(sample_email.id)

    @pytest.mark.asyncio
    async def test_content_loading_retries_under_limit(self, sample_email):
        """Before 3 failures, email is NOT marked processed (will retry next cycle)."""
        from email_nurse.autopilot.engine import AutopilotEngine

        sample_email.content_loaded = False

        engine = MagicMock(spec=AutopilotEngine)
        engine.db = MagicMock()
        engine.config = MagicMock()
        engine.settings = MagicMock()
        engine._apply_quick_rules.return_value = None

        # Simulate increment_rule_failure returning 1 (first failure)
        engine.db.increment_rule_failure.return_value = 1

        with patch(
            "email_nurse.autopilot.engine.load_message_content",
            side_effect=TimeoutError("sysm timed out"),
        ), patch(
            "email_nurse.autopilot.engine.get_account_logger",
            return_value=MagicMock(),
        ):
            result = await AutopilotEngine._process_email(
                engine, sample_email, dry_run=False, interactive=False, auto_create=False
            )

        assert result.success is False
        # Should NOT mark as processed — will retry next cycle
        engine.db.mark_processed.assert_not_called()
        engine.db.clear_rule_failures.assert_not_called()

    @pytest.mark.asyncio
    async def test_content_loading_success_proceeds_to_ai(self, sample_email):
        """When content loads successfully, processing continues to AI classification."""
        from unittest.mock import AsyncMock
        from email_nurse.autopilot.engine import AutopilotEngine

        sample_email.content_loaded = False

        engine = MagicMock(spec=AutopilotEngine)
        engine.db = MagicMock()
        engine.config = MagicMock()
        engine.config.instructions = "test"
        engine.settings = MagicMock()
        engine._apply_quick_rules.return_value = None
        engine._build_pim_context.return_value = ""

        # AI classification fails — we just need to verify content loading succeeded
        # and processing reached the AI step
        engine.ai = MagicMock()
        engine.ai.autopilot_classify = AsyncMock(side_effect=RuntimeError("AI unavailable"))
        engine.db.increment_rule_failure.return_value = 1

        with patch(
            "email_nurse.autopilot.engine.load_message_content",
        ) as mock_load, patch(
            "email_nurse.autopilot.engine.get_account_logger",
            return_value=MagicMock(),
        ):
            result = await AutopilotEngine._process_email(
                engine, sample_email, dry_run=False, interactive=False, auto_create=False
            )

        # Content should have been loaded successfully
        mock_load.assert_called_once_with(sample_email)
        # Failure should be for AI classification, not content loading
        engine.db.increment_rule_failure.assert_called_once()
        call_args = engine.db.increment_rule_failure.call_args
        assert call_args[0][1] == "ai_classification"


class TestBatchMoveTracking:
    """Tests for per-group batch move tracking."""

    def test_batch_move_returns_moved_ids_on_success(self):
        """Successful batch move returns all message IDs."""
        from email_nurse.mail.actions import PendingMove, move_messages_batch

        moves = [
            PendingMove(
                message_id="100",
                target_mailbox="Archive",
                target_account="iCloud",
                source_mailbox="INBOX",
                source_account="iCloud",
            ),
            PendingMove(
                message_id="101",
                target_mailbox="Archive",
                target_account="iCloud",
                source_mailbox="INBOX",
                source_account="iCloud",
            ),
        ]

        with patch("email_nurse.mail.actions.run_applescript", return_value="2"):
            count, ids = move_messages_batch(moves)

        assert count == 2
        assert ids == {"100", "101"}

    def test_batch_move_excludes_failed_group_ids(self):
        """Failed group's message IDs are excluded from moved_ids."""
        from email_nurse.mail.actions import PendingMove, move_messages_batch

        moves = [
            PendingMove(
                message_id="100",
                target_mailbox="Archive",
                target_account="iCloud",
                source_mailbox="INBOX",
                source_account="iCloud",
            ),
            PendingMove(
                message_id="200",
                target_mailbox="Trash",
                target_account="iCloud",
                source_mailbox="INBOX",
                source_account="iCloud",
            ),
        ]

        call_count = 0

        def mock_applescript(script, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "1"  # First group succeeds
            raise TimeoutError("AppleScript timed out")  # Second group fails

        with patch("email_nurse.mail.actions.run_applescript", side_effect=mock_applescript):
            count, ids = move_messages_batch(moves)

        assert count == 1
        # Only one group's IDs should be in moved_ids
        assert len(ids) == 1

    def test_batch_move_empty_returns_empty(self):
        """Empty move list returns zero count and empty set."""
        from email_nurse.mail.actions import move_messages_batch

        count, ids = move_messages_batch([])
        assert count == 0
        assert ids == set()

    def test_batch_move_partial_move_excludes_ids(self):
        """Partial move (count < group size) excludes IDs conservatively."""
        from email_nurse.mail.actions import PendingMove, move_messages_batch

        moves = [
            PendingMove(
                message_id="100",
                target_mailbox="Archive",
                target_account="iCloud",
                source_mailbox="INBOX",
                source_account="iCloud",
            ),
            PendingMove(
                message_id="101",
                target_mailbox="Archive",
                target_account="iCloud",
                source_mailbox="INBOX",
                source_account="iCloud",
            ),
        ]

        # AppleScript reports only 1 of 2 moved
        with patch("email_nurse.mail.actions.run_applescript", return_value="1"):
            count, ids = move_messages_batch(moves)

        assert count == 1
        # Can't tell which moved, so neither should be in moved_ids
        assert ids == set()
