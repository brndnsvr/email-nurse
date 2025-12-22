"""Condition definitions for rule matching."""

import re
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from email_nurse.mail.messages import EmailMessage


class ConditionType(str, Enum):
    """Types of conditions for matching emails."""

    SENDER_CONTAINS = "sender_contains"
    SENDER_EQUALS = "sender_equals"
    SENDER_DOMAIN = "sender_domain"
    SENDER_REGEX = "sender_regex"

    SUBJECT_CONTAINS = "subject_contains"
    SUBJECT_EQUALS = "subject_equals"
    SUBJECT_REGEX = "subject_regex"
    SUBJECT_STARTS_WITH = "subject_starts_with"

    BODY_CONTAINS = "body_contains"
    BODY_REGEX = "body_regex"

    RECIPIENT_CONTAINS = "recipient_contains"
    RECIPIENT_EQUALS = "recipient_equals"

    MAILBOX_EQUALS = "mailbox_equals"
    ACCOUNT_EQUALS = "account_equals"

    IS_READ = "is_read"
    IS_UNREAD = "is_unread"

    # AI-powered conditions
    AI_CLASSIFY = "ai_classify"


class Condition(BaseModel):
    """A single condition for matching emails."""

    type: ConditionType
    value: Any = Field(description="Value to match against")
    case_sensitive: bool = Field(default=False, description="Case-sensitive matching")
    negate: bool = Field(default=False, description="Invert the condition result")

    def matches(self, email: "EmailMessage") -> bool:
        """
        Check if the email matches this condition.

        Args:
            email: The email to check.

        Returns:
            True if the condition matches.
        """
        result = self._evaluate(email)
        return not result if self.negate else result

    def _evaluate(self, email: "EmailMessage") -> bool:
        """Evaluate the condition against an email."""
        value = self.value
        if not self.case_sensitive and isinstance(value, str):
            value = value.lower()

        match self.type:
            # Sender conditions
            case ConditionType.SENDER_CONTAINS:
                sender = email.sender if self.case_sensitive else email.sender.lower()
                return value in sender

            case ConditionType.SENDER_EQUALS:
                sender = email.sender if self.case_sensitive else email.sender.lower()
                return sender == value

            case ConditionType.SENDER_DOMAIN:
                # Extract domain from sender email
                if "@" in email.sender:
                    domain = email.sender.split("@")[-1].strip(">").lower()
                    return domain == value.lower()
                return False

            case ConditionType.SENDER_REGEX:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return bool(re.search(str(self.value), email.sender, flags))

            # Subject conditions
            case ConditionType.SUBJECT_CONTAINS:
                subject = email.subject if self.case_sensitive else email.subject.lower()
                return value in subject

            case ConditionType.SUBJECT_EQUALS:
                subject = email.subject if self.case_sensitive else email.subject.lower()
                return subject == value

            case ConditionType.SUBJECT_REGEX:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return bool(re.search(str(self.value), email.subject, flags))

            case ConditionType.SUBJECT_STARTS_WITH:
                subject = email.subject if self.case_sensitive else email.subject.lower()
                return subject.startswith(value)

            # Body conditions
            case ConditionType.BODY_CONTAINS:
                content = email.content if self.case_sensitive else email.content.lower()
                return value in content

            case ConditionType.BODY_REGEX:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return bool(re.search(str(self.value), email.content, flags))

            # Recipient conditions
            case ConditionType.RECIPIENT_CONTAINS:
                for recip in email.recipients:
                    r = recip if self.case_sensitive else recip.lower()
                    if value in r:
                        return True
                return False

            case ConditionType.RECIPIENT_EQUALS:
                for recip in email.recipients:
                    r = recip if self.case_sensitive else recip.lower()
                    if r == value:
                        return True
                return False

            # Mailbox/Account conditions
            case ConditionType.MAILBOX_EQUALS:
                mailbox = email.mailbox if self.case_sensitive else email.mailbox.lower()
                return mailbox == value

            case ConditionType.ACCOUNT_EQUALS:
                account = email.account if self.case_sensitive else email.account.lower()
                return account == value

            # Status conditions
            case ConditionType.IS_READ:
                return email.is_read

            case ConditionType.IS_UNREAD:
                return not email.is_read

            # AI condition (evaluated separately by the engine)
            case ConditionType.AI_CLASSIFY:
                return True  # Always matches; actual AI check in engine

            case _:
                return False


class ConditionGroup(BaseModel):
    """A group of conditions combined with AND/OR logic."""

    conditions: list[Condition] = Field(default_factory=list)
    operator: str = Field(default="and", pattern="^(and|or)$")

    def matches(self, email: "EmailMessage") -> bool:
        """Check if the email matches the condition group."""
        if not self.conditions:
            return True

        if self.operator == "and":
            return all(c.matches(email) for c in self.conditions)
        else:  # or
            return any(c.matches(email) for c in self.conditions)
