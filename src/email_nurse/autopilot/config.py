"""Autopilot configuration loader."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class QuickRule(BaseModel):
    """A deterministic rule that runs before AI classification."""

    name: str = Field(description="Human-readable rule name")
    match: dict[str, list[str]] = Field(
        description="Match conditions: sender_contains, subject_contains, sender_domain"
    )
    action: Literal["delete", "move", "archive", "mark_read", "ignore"] = Field(
        description="Action to take when rule matches"
    )
    folder: str | None = Field(
        default=None, description="Target folder for 'move' action"
    )


class AutopilotConfig(BaseModel):
    """Autopilot configuration from YAML."""

    enabled: bool = Field(default=True, description="Whether autopilot is enabled")
    instructions: str = Field(
        description="Natural language instructions for email handling"
    )
    mailboxes: list[str] = Field(
        default=["INBOX"], description="Mailboxes to process"
    )
    accounts: list[str] | None = Field(
        default=None, description="Specific accounts to process (None = all)"
    )
    exclude_senders: list[str] = Field(
        default_factory=list, description="Sender patterns to never auto-process"
    )
    exclude_subjects: list[str] = Field(
        default_factory=list, description="Subject patterns to never auto-process"
    )
    max_age_days: int = Field(
        default=7, ge=1, description="Don't process emails older than this"
    )
    main_account: str | None = Field(
        default=None,
        description="Central account for all move/archive operations (e.g., 'iCloud'). "
        "When set, emails from other accounts will be moved to folders on this account.",
    )
    quick_rules: list[QuickRule] = Field(
        default_factory=list,
        description="Deterministic rules that run before AI classification",
    )


def load_autopilot_config(path: Path) -> AutopilotConfig | None:
    """
    Load autopilot configuration from a YAML file.

    Args:
        path: Path to the autopilot.yaml file.

    Returns:
        AutopilotConfig if file exists and is valid, None otherwise.
    """
    if not path.exists():
        return None

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    # Get the autopilot section
    autopilot_data = data.get("autopilot", data)

    # Handle the case where instructions might be under a nested key
    if "instructions" not in autopilot_data and "autopilot" in data:
        autopilot_data = data["autopilot"]

    return AutopilotConfig(**autopilot_data)


def save_autopilot_config(path: Path, config: AutopilotConfig) -> None:
    """
    Save autopilot configuration to a YAML file.

    Args:
        path: Path to save the configuration.
        config: AutopilotConfig to save.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {"autopilot": config.model_dump(exclude_none=True)}

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


DEFAULT_INSTRUCTIONS = """Handle my email according to these preferences:

## Newsletters and Marketing
- Newsletters and digests: archive, mark as read
- Marketing/promotional emails: archive
- Unsubscribe confirmations: delete

## Notifications
- GitHub notifications: move to "GitHub" folder, mark as read
- CI/CD notifications: move to "GitHub" folder
- Calendar invites: leave in inbox, flag if it's a new meeting request

## Personal and Work
- Direct emails from colleagues: leave in inbox
- Emails where I'm CC'd only: archive unless urgent
- Meeting follow-ups: leave in inbox

## Automated/Transactional
- Order confirmations: move to "Receipts" folder
- Shipping notifications: move to "Receipts" folder
- Password reset emails: leave in inbox (security sensitive)

## Default Behavior
- When uncertain about an email's category: leave in inbox (ignore action)
- Express confidence honestly - use lower confidence when unsure
- Never delete personal emails or anything that looks unique/important
- Flag emails that seem important but don't match any category
"""
