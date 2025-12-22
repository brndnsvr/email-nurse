"""Rule engine for processing emails against defined rules."""

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from email_nurse.ai.base import EmailAction, EmailClassification
from email_nurse.rules.conditions import Condition, ConditionGroup

if TYPE_CHECKING:
    from email_nurse.ai.base import AIProvider
    from email_nurse.mail.messages import EmailMessage


class RuleAction(BaseModel):
    """Action to take when a rule matches."""

    action: EmailAction
    target_folder: str | None = None
    target_account: str | None = None
    reply_template: str | None = None
    forward_to: list[str] | None = None


class Rule(BaseModel):
    """A single rule for processing emails."""

    name: str = Field(description="Human-readable rule name")
    description: str | None = Field(default=None, description="Rule description")
    enabled: bool = Field(default=True, description="Whether the rule is active")
    priority: int = Field(default=100, description="Lower number = higher priority")
    stop_processing: bool = Field(
        default=True, description="Stop processing more rules if this matches"
    )

    # Conditions - can use simple list or grouped conditions
    conditions: list[Condition] = Field(default_factory=list)
    condition_groups: list[ConditionGroup] = Field(default_factory=list)
    match_all: bool = Field(
        default=True, description="True=AND all conditions, False=OR"
    )

    # Action to take
    action: RuleAction

    # Optional: use AI for classification instead of/in addition to rules
    use_ai: bool = Field(default=False, description="Use AI to classify this email")
    ai_context: str | None = Field(
        default=None, description="Additional context for AI classification"
    )

    def matches(self, email: "EmailMessage") -> bool:
        """
        Check if an email matches this rule's conditions.

        Args:
            email: The email to check.

        Returns:
            True if all/any conditions match (based on match_all).
        """
        if not self.enabled:
            return False

        # Evaluate individual conditions
        condition_results = [c.matches(email) for c in self.conditions]

        # Evaluate condition groups
        group_results = [g.matches(email) for g in self.condition_groups]

        all_results = condition_results + group_results

        if not all_results:
            return True  # No conditions = always match

        if self.match_all:
            return all(all_results)
        else:
            return any(all_results)


class RuleEngine:
    """Engine for processing emails against rules."""

    def __init__(
        self,
        rules: list[Rule] | None = None,
        ai_provider: "AIProvider | None" = None,
    ) -> None:
        """
        Initialize the rule engine.

        Args:
            rules: List of rules to process.
            ai_provider: AI provider for AI-based classification.
        """
        self.rules = sorted(rules or [], key=lambda r: r.priority)
        self.ai_provider = ai_provider

    def add_rule(self, rule: Rule) -> None:
        """Add a rule and re-sort by priority."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name."""
        original_count = len(self.rules)
        self.rules = [r for r in self.rules if r.name != name]
        return len(self.rules) < original_count

    async def process_email(
        self,
        email: "EmailMessage",
        *,
        dry_run: bool = False,
    ) -> EmailClassification | None:
        """
        Process an email against all rules.

        Args:
            email: The email to process.
            dry_run: If True, don't execute actions, just return what would happen.

        Returns:
            EmailClassification if a rule matched, None otherwise.
        """
        for rule in self.rules:
            if not rule.matches(email):
                continue

            # Rule matched
            if rule.use_ai and self.ai_provider:
                # Use AI for classification
                classification = await self.ai_provider.classify_email(
                    email, context=rule.ai_context
                )

                if not dry_run:
                    await self._execute_action(email, classification)

                return classification

            # Use rule's defined action
            classification = EmailClassification(
                action=rule.action.action,
                confidence=1.0,  # Rule-based = 100% confidence
                target_folder=rule.action.target_folder,
                target_account=rule.action.target_account,
                reply_template=rule.action.reply_template,
                forward_to=rule.action.forward_to,
                reasoning=f"Matched rule: {rule.name}",
            )

            if not dry_run:
                await self._execute_action(email, classification)

            if rule.stop_processing:
                return classification

        return None

    async def _execute_action(
        self,
        email: "EmailMessage",
        classification: EmailClassification,
    ) -> None:
        """Execute the action from a classification."""
        from email_nurse.mail.actions import (
            delete_message,
            flag_message,
            forward_message,
            mark_as_read,
            move_message,
            reply_to_message,
        )

        match classification.action:
            case EmailAction.MOVE:
                if classification.target_folder:
                    move_message(
                        email.id,
                        classification.target_folder,
                        classification.target_account,
                    )

            case EmailAction.DELETE:
                delete_message(email.id)

            case EmailAction.ARCHIVE:
                move_message(email.id, "Archive")

            case EmailAction.MARK_READ:
                mark_as_read(email.id, read=True)

            case EmailAction.MARK_UNREAD:
                mark_as_read(email.id, read=False)

            case EmailAction.FLAG:
                flag_message(email.id, flagged=True)

            case EmailAction.UNFLAG:
                flag_message(email.id, flagged=False)

            case EmailAction.REPLY:
                if classification.reply_template and self.ai_provider:
                    reply_content = await self.ai_provider.generate_reply(
                        email, classification.reply_template
                    )
                    reply_to_message(email.id, reply_content, send_immediately=False)

            case EmailAction.FORWARD:
                if classification.forward_to:
                    forward_message(
                        email.id,
                        classification.forward_to,
                        send_immediately=False,
                    )

            case EmailAction.IGNORE:
                pass  # Do nothing

    async def classify_all(
        self,
        emails: list["EmailMessage"],
        *,
        dry_run: bool = True,
    ) -> list[tuple["EmailMessage", EmailClassification | None]]:
        """
        Classify a batch of emails.

        Args:
            emails: List of emails to process.
            dry_run: If True, don't execute actions.

        Returns:
            List of (email, classification) tuples.
        """
        results = []
        for email in emails:
            classification = await self.process_email(email, dry_run=dry_run)
            results.append((email, classification))
        return results
