"""Tests for secondary action support in autopilot."""

from email_nurse.ai.base import EmailAction
from email_nurse.autopilot.models import AutopilotDecision


class TestAutopilotDecisionSecondary:
    """Tests for AutopilotDecision secondary action fields."""

    def test_secondary_action_defaults_none(self) -> None:
        """Secondary action should default to None."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
        )
        assert decision.secondary_action is None
        assert decision.secondary_target_folder is None

    def test_secondary_action_can_be_set(self) -> None:
        """Secondary action can be set to valid EmailAction."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.CREATE_REMINDER,
            reminder_name="Follow up",
        )
        assert decision.secondary_action == EmailAction.CREATE_REMINDER

    def test_secondary_target_folder_for_move(self) -> None:
        """Secondary MOVE should use secondary_target_folder."""
        decision = AutopilotDecision(
            action=EmailAction.FLAG,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.MOVE,
            secondary_target_folder="Important",
        )
        assert decision.secondary_action == EmailAction.MOVE
        assert decision.secondary_target_folder == "Important"

    def test_is_pim_action_true_for_primary_reminder(self) -> None:
        """is_pim_action should return True if primary is PIM action."""
        decision = AutopilotDecision(
            action=EmailAction.CREATE_REMINDER,
            confidence=0.9,
            reasoning="Test",
            reminder_name="Test reminder",
        )
        assert decision.is_pim_action is True

    def test_is_pim_action_true_for_secondary_reminder(self) -> None:
        """is_pim_action should return True if secondary is PIM action."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.CREATE_REMINDER,
            reminder_name="Follow up",
        )
        assert decision.is_pim_action is True

    def test_is_pim_action_true_for_secondary_event(self) -> None:
        """is_pim_action should return True if secondary is CREATE_EVENT."""
        from datetime import datetime

        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.CREATE_EVENT,
            event_summary="Meeting",
            event_start=datetime.now(),
        )
        assert decision.is_pim_action is True

    def test_is_pim_action_false_for_non_pim(self) -> None:
        """is_pim_action should return False if neither action is PIM."""
        decision = AutopilotDecision(
            action=EmailAction.MOVE,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.MARK_READ,
            target_folder="Archive",
        )
        assert decision.is_pim_action is False

    def test_has_invalid_secondary_for_reply(self) -> None:
        """has_invalid_secondary should detect REPLY as secondary."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.REPLY,
        )
        assert decision.has_invalid_secondary is True

    def test_has_invalid_secondary_for_forward(self) -> None:
        """has_invalid_secondary should detect FORWARD as secondary."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.FORWARD,
        )
        assert decision.has_invalid_secondary is True

    def test_has_invalid_secondary_false_for_valid(self) -> None:
        """has_invalid_secondary should return False for valid secondary."""
        decision = AutopilotDecision(
            action=EmailAction.FLAG,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.ARCHIVE,
        )
        assert decision.has_invalid_secondary is False

    def test_has_invalid_secondary_false_for_none(self) -> None:
        """has_invalid_secondary should return False when no secondary action."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
        )
        assert decision.has_invalid_secondary is False

    def test_common_combination_archive_reminder(self) -> None:
        """Test common combination: archive + create_reminder."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.85,
            reasoning="Archive and set reminder to follow up",
            secondary_action=EmailAction.CREATE_REMINDER,
            reminder_name="Follow up on invoice",
        )
        assert decision.action == EmailAction.ARCHIVE
        assert decision.secondary_action == EmailAction.CREATE_REMINDER
        assert decision.is_pim_action is True
        assert decision.has_invalid_secondary is False

    def test_common_combination_move_mark_read(self) -> None:
        """Test common combination: move + mark_read."""
        decision = AutopilotDecision(
            action=EmailAction.MOVE,
            confidence=0.9,
            reasoning="Sort newsletter and mark as read",
            target_folder="Newsletters",
            secondary_action=EmailAction.MARK_READ,
        )
        assert decision.action == EmailAction.MOVE
        assert decision.secondary_action == EmailAction.MARK_READ
        assert decision.target_folder == "Newsletters"

    def test_common_combination_event_archive(self) -> None:
        """Test common combination: create_event + archive."""
        from datetime import datetime

        decision = AutopilotDecision(
            action=EmailAction.CREATE_EVENT,
            confidence=0.9,
            reasoning="Create calendar event and archive",
            event_summary="Conference Call",
            event_start=datetime(2025, 1, 20, 14, 0),
            secondary_action=EmailAction.ARCHIVE,
        )
        assert decision.action == EmailAction.CREATE_EVENT
        assert decision.secondary_action == EmailAction.ARCHIVE
        assert decision.is_pim_action is True


class TestSecondaryActionSerialization:
    """Test that secondary action fields serialize correctly."""

    def test_model_dump_includes_secondary_action(self) -> None:
        """model_dump should include secondary_action when set."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
            secondary_action=EmailAction.CREATE_REMINDER,
            reminder_name="Follow up",
        )
        data = decision.model_dump()
        assert data["secondary_action"] == EmailAction.CREATE_REMINDER
        assert data["secondary_target_folder"] is None

    def test_model_dump_excludes_none_secondary(self) -> None:
        """model_dump should include None for secondary_action when not set."""
        decision = AutopilotDecision(
            action=EmailAction.ARCHIVE,
            confidence=0.9,
            reasoning="Test",
        )
        data = decision.model_dump()
        assert data["secondary_action"] is None
        assert data["secondary_target_folder"] is None
