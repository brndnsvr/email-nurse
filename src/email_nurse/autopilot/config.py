"""Autopilot configuration loader."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

# Type alias for rule actions
RuleAction = Literal["delete", "move", "archive", "mark_read", "ignore"]

# Type alias for folder handling policies
FolderPolicy = Literal["auto_create", "queue", "interactive"]


class AccountSettings(BaseModel):
    """Per-account settings for folder handling and notifications."""

    folder_policy: FolderPolicy = Field(
        default="queue",
        description="How to handle missing folders: auto_create, queue, or interactive",
    )
    notify_on_pending: bool = Field(
        default=True,
        description="Show AppleScript notification when folders are queued for creation",
    )


class FolderRetentionRule(BaseModel):
    """Per-folder retention policy for automatic email purging."""

    folder: str = Field(description="Folder name to apply retention to")
    retention_days: int = Field(ge=1, description="Days before emails are deleted to Trash")
    account: str | None = Field(
        default=None,
        description="Specific account (None = use main_account)",
    )


class QuickRule(BaseModel):
    """A deterministic rule that runs before AI classification."""

    name: str = Field(description="Human-readable rule name")
    match: dict[str, list[str]] = Field(
        description="Match conditions: sender_contains, subject_contains, sender_domain"
    )
    action: RuleAction | None = Field(
        default=None,
        description="Single action (use 'actions' for multiple)",
    )
    actions: list[RuleAction] | None = Field(
        default=None,
        description="List of actions to execute in order",
    )
    folder: str | None = Field(
        default=None, description="Target folder for 'move' action"
    )

    @model_validator(mode="after")
    def validate_actions(self) -> "QuickRule":
        """Ensure either action or actions is provided, not both."""
        if self.action is None and self.actions is None:
            raise ValueError("Either 'action' or 'actions' must be provided")
        if self.action is not None and self.actions is not None:
            raise ValueError("Cannot specify both 'action' and 'actions'")
        return self

    def get_actions(self) -> list[RuleAction]:
        """Get list of actions to execute."""
        if self.actions is not None:
            return self.actions
        if self.action is not None:
            return [self.action]
        return []


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
    local_folders: list[str] = Field(
        default_factory=list,
        description="Folders that route to local 'On My Mac' mailboxes instead of account folders. "
        "Messages matching rules for these folders will be moved to local storage regardless of source account.",
    )
    quick_rules: list[QuickRule] = Field(
        default_factory=list,
        description="Deterministic rules that run before AI classification",
    )

    # Inbox aging settings
    inbox_aging_enabled: bool = Field(
        default=False,
        description="Enable automatic aging of stale inbox emails",
    )
    inbox_stale_days: int = Field(
        default=30,
        ge=1,
        description="Days before an email is considered stale and moved to Needs Review",
    )
    needs_review_folder: str = Field(
        default="Needs Review",
        description="Folder to move stale emails to",
    )
    needs_review_retention_days: int = Field(
        default=14,
        ge=1,
        description="Days in Needs Review before auto-deletion to Trash",
    )

    # Processed email tracking retention
    processed_retention_days: int = Field(
        default=365,
        ge=1,
        description="Days to retain processed email records before auto-cleanup",
    )

    # Per-account settings
    account_settings: dict[str, AccountSettings] = Field(
        default_factory=dict,
        description="Per-account settings for folder handling (keyed by account name)",
    )

    # Per-folder retention rules
    folder_retention_rules: list[FolderRetentionRule] = Field(
        default_factory=list,
        description="Per-folder retention policies for automatic purging to Trash",
    )

    def get_folder_policy(self, account: str) -> FolderPolicy:
        """Get folder policy for an account, with fallback to default 'queue'.

        Args:
            account: Account name to look up.

        Returns:
            The folder policy for this account.
        """
        if account in self.account_settings:
            return self.account_settings[account].folder_policy
        return "queue"  # Safe default - don't auto-create

    def should_notify(self, account: str) -> bool:
        """Check if account should receive AppleScript notifications.

        Args:
            account: Account name to look up.

        Returns:
            True if notifications should be shown for this account.
        """
        if account in self.account_settings:
            return self.account_settings[account].notify_on_pending
        return True  # Default to notifying


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
