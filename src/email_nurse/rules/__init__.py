"""Rule engine for email processing."""

from email_nurse.rules.conditions import Condition, ConditionType
from email_nurse.rules.engine import Rule, RuleEngine

__all__ = [
    "Condition",
    "ConditionType",
    "Rule",
    "RuleEngine",
]
