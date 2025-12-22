"""Base AI provider interface and shared types."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from email_nurse.autopilot.models import AutopilotDecision
    from email_nurse.mail.messages import EmailMessage


class EmailAction(str, Enum):
    """Actions that can be taken on an email."""

    MOVE = "move"
    DELETE = "delete"
    ARCHIVE = "archive"
    MARK_READ = "mark_read"
    MARK_UNREAD = "mark_unread"
    FLAG = "flag"
    UNFLAG = "unflag"
    REPLY = "reply"
    FORWARD = "forward"
    IGNORE = "ignore"


class EmailClassification(BaseModel):
    """Result of AI classification of an email."""

    action: EmailAction = Field(description="The recommended action to take")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score for the recommendation"
    )
    category: str | None = Field(
        default=None, description="Category label (e.g., 'newsletter', 'invoice', 'spam')"
    )
    target_folder: str | None = Field(
        default=None, description="Target folder for move actions"
    )
    target_account: str | None = Field(
        default=None, description="Target account for cross-account moves"
    )
    reply_template: str | None = Field(
        default=None, description="Template name for reply actions"
    )
    forward_to: list[str] | None = Field(
        default=None, description="Addresses for forward actions"
    )
    reasoning: str = Field(description="Brief explanation of the decision")


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def classify_email(
        self,
        email: "EmailMessage",
        context: str | None = None,
    ) -> EmailClassification:
        """
        Classify an email and recommend an action.

        Args:
            email: The email message to classify.
            context: Optional additional context (rules, user preferences).

        Returns:
            EmailClassification with recommended action and reasoning.
        """
        ...

    @abstractmethod
    async def generate_reply(
        self,
        email: "EmailMessage",
        template: str,
        context: str | None = None,
    ) -> str:
        """
        Generate a reply to an email based on a template.

        Args:
            email: The email to reply to.
            template: Template content or instructions for the reply.
            context: Optional additional context.

        Returns:
            Generated reply text.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the AI provider is available and properly configured."""
        ...

    @abstractmethod
    async def autopilot_classify(
        self,
        email: "EmailMessage",
        instructions: str,
    ) -> "AutopilotDecision":
        """
        Classify an email using natural language instructions (autopilot mode).

        This method is designed for AI-native processing where the AI interprets
        the user's preferences and decides both the category and action.

        Args:
            email: The email message to classify.
            instructions: User's natural language preferences for email handling.

        Returns:
            AutopilotDecision with action, confidence, reasoning, and any
            action-specific fields (target_folder, reply_content, etc.).
        """
        ...
