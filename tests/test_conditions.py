"""Tests for rule conditions."""

import pytest

from email_nurse.mail.messages import EmailMessage
from email_nurse.rules.conditions import Condition, ConditionGroup, ConditionType


class TestSenderConditions:
    """Tests for sender-based conditions."""

    def test_sender_contains(self, sample_email: EmailMessage) -> None:
        """Test sender_contains condition."""
        condition = Condition(type=ConditionType.SENDER_CONTAINS, value="example")
        assert condition.matches(sample_email) is True

        condition = Condition(type=ConditionType.SENDER_CONTAINS, value="other")
        assert condition.matches(sample_email) is False

    def test_sender_contains_case_insensitive(self, sample_email: EmailMessage) -> None:
        """Test case-insensitive sender matching."""
        condition = Condition(
            type=ConditionType.SENDER_CONTAINS, value="EXAMPLE", case_sensitive=False
        )
        assert condition.matches(sample_email) is True

    def test_sender_domain(self, sample_email: EmailMessage) -> None:
        """Test sender_domain condition."""
        condition = Condition(type=ConditionType.SENDER_DOMAIN, value="example.com")
        assert condition.matches(sample_email) is True

        condition = Condition(type=ConditionType.SENDER_DOMAIN, value="other.com")
        assert condition.matches(sample_email) is False

    def test_sender_regex(self, sample_email: EmailMessage) -> None:
        """Test sender_regex condition."""
        condition = Condition(type=ConditionType.SENDER_REGEX, value=r".*@example\.com$")
        assert condition.matches(sample_email) is True


class TestSubjectConditions:
    """Tests for subject-based conditions."""

    def test_subject_contains(self, sample_email: EmailMessage) -> None:
        """Test subject_contains condition."""
        condition = Condition(type=ConditionType.SUBJECT_CONTAINS, value="test")
        assert condition.matches(sample_email) is True

    def test_subject_starts_with(self, sample_email: EmailMessage) -> None:
        """Test subject_starts_with condition."""
        condition = Condition(type=ConditionType.SUBJECT_STARTS_WITH, value="test")
        assert condition.matches(sample_email) is True

        condition = Condition(type=ConditionType.SUBJECT_STARTS_WITH, value="subject")
        assert condition.matches(sample_email) is False

    def test_subject_regex(self, newsletter_email: EmailMessage) -> None:
        """Test subject_regex with newsletter pattern."""
        condition = Condition(type=ConditionType.SUBJECT_REGEX, value=r"newsletter", )
        assert condition.matches(newsletter_email) is True


class TestBodyConditions:
    """Tests for body/content-based conditions."""

    def test_body_contains(self, newsletter_email: EmailMessage) -> None:
        """Test body_contains condition."""
        condition = Condition(type=ConditionType.BODY_CONTAINS, value="unsubscribe")
        assert condition.matches(newsletter_email) is True

    def test_body_regex(self, spam_email: EmailMessage) -> None:
        """Test body_regex condition."""
        condition = Condition(type=ConditionType.BODY_REGEX, value=r"(?i)lottery|winner")
        assert condition.matches(spam_email) is True


class TestNegation:
    """Tests for negated conditions."""

    def test_negated_condition(self, sample_email: EmailMessage) -> None:
        """Test that negate inverts the result."""
        # Normal: matches
        condition = Condition(type=ConditionType.SENDER_DOMAIN, value="example.com")
        assert condition.matches(sample_email) is True

        # Negated: doesn't match
        condition = Condition(
            type=ConditionType.SENDER_DOMAIN, value="example.com", negate=True
        )
        assert condition.matches(sample_email) is False


class TestConditionGroup:
    """Tests for condition groups with AND/OR logic."""

    def test_and_group(self, newsletter_email: EmailMessage) -> None:
        """Test AND logic in condition group."""
        group = ConditionGroup(
            conditions=[
                Condition(type=ConditionType.SUBJECT_CONTAINS, value="newsletter"),
                Condition(type=ConditionType.BODY_CONTAINS, value="unsubscribe"),
            ],
            operator="and",
        )
        assert group.matches(newsletter_email) is True

    def test_or_group(self, sample_email: EmailMessage) -> None:
        """Test OR logic in condition group."""
        group = ConditionGroup(
            conditions=[
                Condition(type=ConditionType.SUBJECT_CONTAINS, value="newsletter"),
                Condition(type=ConditionType.SUBJECT_CONTAINS, value="test"),
            ],
            operator="or",
        )
        assert group.matches(sample_email) is True

    def test_empty_group_matches(self, sample_email: EmailMessage) -> None:
        """Test that empty group matches everything."""
        group = ConditionGroup(conditions=[], operator="and")
        assert group.matches(sample_email) is True
