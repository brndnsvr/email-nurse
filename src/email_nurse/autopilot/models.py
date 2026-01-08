"""Data models for autopilot mode."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from email_nurse.ai.base import EmailAction


class LowConfidenceAction(str, Enum):
    """Action to take when AI confidence is below threshold."""

    FLAG_FOR_REVIEW = "flag_for_review"
    SKIP = "skip"
    QUEUE_FOR_APPROVAL = "queue_for_approval"


class OutboundPolicy(str, Enum):
    """Policy for outbound actions (reply/forward)."""

    REQUIRE_APPROVAL = "require_approval"
    ALLOW_HIGH_CONFIDENCE = "allow_high_confidence"
    FULL_AUTOPILOT = "full_autopilot"


class AutopilotDecision(BaseModel):
    """AI decision for an email in autopilot mode."""

    action: EmailAction = Field(description="The action to take")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score for this decision"
    )
    reasoning: str = Field(description="Brief explanation of the decision")
    category: str | None = Field(
        default=None, description="Category label (e.g., 'newsletter', 'personal')"
    )
    target_folder: str | None = Field(
        default=None, description="Target folder for move actions"
    )
    target_account: str | None = Field(
        default=None, description="Target account for cross-account moves"
    )
    reply_content: str | None = Field(
        default=None, description="Generated reply content for reply actions"
    )
    forward_to: list[str] | None = Field(
        default=None, description="Email addresses for forward actions"
    )
    # Reminder fields (for CREATE_REMINDER action)
    reminder_name: str | None = Field(
        default=None, description="Reminder title/name"
    )
    reminder_due: datetime | None = Field(
        default=None, description="Due date for the reminder"
    )
    reminder_list: str | None = Field(
        default=None, description="Target reminder list (default: Reminders)"
    )
    # Calendar event fields (for CREATE_EVENT action)
    event_summary: str | None = Field(
        default=None, description="Calendar event title"
    )
    event_start: datetime | None = Field(
        default=None, description="Event start date/time"
    )
    event_end: datetime | None = Field(
        default=None, description="Event end date/time (optional)"
    )
    event_calendar: str | None = Field(
        default=None, description="Target calendar (default: Calendar)"
    )
    event_all_day: bool = Field(
        default=False, description="Whether this is an all-day event"
    )

    @property
    def is_outbound(self) -> bool:
        """Check if this action involves sending a message."""
        return self.action in (EmailAction.REPLY, EmailAction.FORWARD)

    @property
    def is_destructive(self) -> bool:
        """Check if this action is destructive (hard to undo)."""
        return self.action == EmailAction.DELETE

    @property
    def is_pim_action(self) -> bool:
        """Check if this action creates a PIM (Personal Information Manager) item."""
        return self.action in (EmailAction.CREATE_REMINDER, EmailAction.CREATE_EVENT)


class PendingAction(BaseModel):
    """An action awaiting user approval."""

    id: int = Field(description="Unique action ID")
    message_id: str = Field(description="Mail.app message ID")
    email_summary: str = Field(description="Subject + sender for display")
    proposed_action: AutopilotDecision = Field(description="The proposed action")
    confidence: float = Field(description="AI confidence score")
    reasoning: str = Field(description="AI reasoning")
    created_at: datetime = Field(description="When queued")
    status: str = Field(default="pending", description="pending/approved/rejected")


class ProcessResult(BaseModel):
    """Result of processing a single email."""

    message_id: str = Field(description="Mail.app message ID")
    success: bool = Field(default=True, description="Whether processing succeeded")
    action: str | None = Field(default=None, description="Action taken")
    target_folder: str | None = Field(
        default=None, description="Target folder for move/archive actions"
    )
    skipped: bool = Field(default=False, description="Whether email was skipped")
    queued: bool = Field(default=False, description="Whether action was queued")
    reason: str | None = Field(default=None, description="Reason for skip/queue/failure")
    error: str | None = Field(default=None, description="Error message if failed")
    rule_matched: str | None = Field(
        default=None, description="Name of quick rule if matched (None = AI classified)"
    )


class AutopilotRunResult(BaseModel):
    """Summary of an autopilot run."""

    started_at: datetime = Field(description="When run started")
    completed_at: datetime = Field(description="When run completed")
    emails_fetched: int = Field(default=0, description="Total emails fetched")
    emails_processed: int = Field(default=0, description="Emails processed")
    emails_skipped: int = Field(default=0, description="Emails skipped")
    actions_executed: int = Field(default=0, description="Actions executed")
    actions_queued: int = Field(default=0, description="Actions queued for approval")
    errors: int = Field(default=0, description="Processing errors")
    dry_run: bool = Field(default=False, description="Was this a dry run")

    @property
    def duration_seconds(self) -> float:
        """Get run duration in seconds."""
        return (self.completed_at - self.started_at).total_seconds()


class AgingResult(BaseModel):
    """Summary of inbox aging checks."""

    moved_to_review: int = Field(default=0, description="Emails moved to Needs Review")
    deleted_from_review: int = Field(default=0, description="Emails deleted from Needs Review")
    retention_deleted: int = Field(default=0, description="Emails deleted by folder retention rules")
    errors: int = Field(default=0, description="Errors during aging")
