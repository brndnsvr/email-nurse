"""Tests for the rule engine."""

import pytest

from email_nurse.ai.base import EmailAction
from email_nurse.mail.messages import EmailMessage
from email_nurse.rules.conditions import Condition, ConditionType
from email_nurse.rules.engine import Rule, RuleAction, RuleEngine


class TestRule:
    """Tests for individual rules."""

    def test_rule_matches_with_conditions(self, sample_email: EmailMessage) -> None:
        """Test rule matching with conditions."""
        rule = Rule(
            name="Test Rule",
            conditions=[
                Condition(type=ConditionType.SENDER_DOMAIN, value="example.com")
            ],
            action=RuleAction(action=EmailAction.FLAG),
        )
        assert rule.matches(sample_email) is True

    def test_disabled_rule_never_matches(self, sample_email: EmailMessage) -> None:
        """Test that disabled rules don't match."""
        rule = Rule(
            name="Disabled Rule",
            enabled=False,
            conditions=[
                Condition(type=ConditionType.SENDER_DOMAIN, value="example.com")
            ],
            action=RuleAction(action=EmailAction.FLAG),
        )
        assert rule.matches(sample_email) is False

    def test_rule_with_no_conditions_matches_all(
        self, sample_email: EmailMessage
    ) -> None:
        """Test that rule with no conditions matches all emails."""
        rule = Rule(
            name="Catch All",
            conditions=[],
            action=RuleAction(action=EmailAction.IGNORE),
        )
        assert rule.matches(sample_email) is True


class TestRuleEngine:
    """Tests for the rule engine."""

    def test_engine_priority_order(self) -> None:
        """Test that rules are processed in priority order."""
        engine = RuleEngine(
            rules=[
                Rule(
                    name="Low Priority",
                    priority=100,
                    conditions=[],
                    action=RuleAction(action=EmailAction.IGNORE),
                ),
                Rule(
                    name="High Priority",
                    priority=10,
                    conditions=[],
                    action=RuleAction(action=EmailAction.FLAG),
                ),
            ]
        )
        # Rules should be sorted by priority
        assert engine.rules[0].name == "High Priority"
        assert engine.rules[1].name == "Low Priority"

    def test_add_rule_maintains_order(self) -> None:
        """Test that adding a rule maintains priority order."""
        engine = RuleEngine()
        engine.add_rule(
            Rule(
                name="Later Added",
                priority=50,
                conditions=[],
                action=RuleAction(action=EmailAction.IGNORE),
            )
        )
        engine.add_rule(
            Rule(
                name="First Priority",
                priority=10,
                conditions=[],
                action=RuleAction(action=EmailAction.FLAG),
            )
        )
        assert engine.rules[0].name == "First Priority"

    def test_remove_rule(self) -> None:
        """Test rule removal."""
        engine = RuleEngine(
            rules=[
                Rule(
                    name="To Remove",
                    conditions=[],
                    action=RuleAction(action=EmailAction.IGNORE),
                )
            ]
        )
        assert engine.remove_rule("To Remove") is True
        assert len(engine.rules) == 0
        assert engine.remove_rule("Nonexistent") is False

    @pytest.mark.asyncio
    async def test_process_email_dry_run(self, sample_email: EmailMessage) -> None:
        """Test processing email in dry run mode."""
        engine = RuleEngine(
            rules=[
                Rule(
                    name="Flag All",
                    conditions=[],
                    action=RuleAction(action=EmailAction.FLAG),
                )
            ]
        )
        result = await engine.process_email(sample_email, dry_run=True)

        assert result is not None
        assert result.action == EmailAction.FLAG
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_no_matching_rules(self, sample_email: EmailMessage) -> None:
        """Test when no rules match."""
        engine = RuleEngine(
            rules=[
                Rule(
                    name="No Match",
                    conditions=[
                        Condition(
                            type=ConditionType.SENDER_DOMAIN, value="nomatch.com"
                        )
                    ],
                    action=RuleAction(action=EmailAction.FLAG),
                )
            ]
        )
        result = await engine.process_email(sample_email, dry_run=True)
        assert result is None

    @pytest.mark.asyncio
    async def test_stop_processing(self, sample_email: EmailMessage) -> None:
        """Test that stop_processing prevents further rule evaluation."""
        engine = RuleEngine(
            rules=[
                Rule(
                    name="First",
                    priority=10,
                    conditions=[],
                    action=RuleAction(action=EmailAction.FLAG),
                    stop_processing=True,
                ),
                Rule(
                    name="Second",
                    priority=20,
                    conditions=[],
                    action=RuleAction(action=EmailAction.DELETE),
                ),
            ]
        )
        result = await engine.process_email(sample_email, dry_run=True)

        # Should match first rule and stop
        assert result is not None
        assert result.action == EmailAction.FLAG
