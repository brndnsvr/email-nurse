"""Application configuration management."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="EMAIL_NURSE_",
        env_file=[
            ".env",  # Project-level defaults (lower priority)
            Path.home() / ".config" / "email-nurse" / ".env",  # User config (higher priority)
        ],
        env_file_encoding="utf-8",
    )

    # AI Provider settings
    ai_provider: Literal["claude", "openai", "ollama"] = Field(
        default="claude", description="Default AI provider to use"
    )

    # Claude settings
    anthropic_api_key: str | None = Field(
        default=None, description="Anthropic API key"
    )
    claude_model: str = Field(
        default="claude-haiku-4-5-20251001", description="Claude model to use"
    )

    # OpenAI settings
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="OpenAI model to use")

    # Ollama settings
    ollama_host: str = Field(
        default="http://localhost:11434", description="Ollama server URL"
    )
    ollama_model: str = Field(default="llama3.2", description="Ollama model to use")

    # Processing settings
    confidence_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum confidence to auto-execute"
    )
    dry_run: bool = Field(
        default=True, description="Default to dry-run mode (don't execute actions)"
    )

    # Sync settings
    sync_interval_minutes: int = Field(
        default=5, ge=1, description="Minutes between sync checks"
    )
    process_interval_minutes: int = Field(
        default=1, ge=1, description="Minutes between processing runs"
    )

    # Paths
    config_dir: Path = Field(
        default=Path.home() / ".config" / "email-nurse",
        description="Configuration directory",
    )
    rules_file: str = Field(default="rules.yaml", description="Rules config filename")
    templates_file: str = Field(
        default="templates.yaml", description="Templates config filename"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Path | None = Field(default=None, description="Log file path (deprecated)")
    log_dir: Path = Field(
        default=Path.home() / "Library" / "Logs",
        description="Directory for log files (per-account logs written here)",
    )
    log_rotation_size_mb: int = Field(
        default=5, ge=1, description="Max size per log file in MB before rotation"
    )
    log_backup_count: int = Field(
        default=3, ge=0, description="Number of rotated log files to keep"
    )

    # Autopilot settings
    autopilot_enabled: bool = Field(
        default=False, description="Enable autopilot mode"
    )
    autopilot_config_file: str = Field(
        default="autopilot.yaml", description="Autopilot configuration filename"
    )
    low_confidence_action: Literal["flag_for_review", "skip", "queue_for_approval"] = Field(
        default="queue_for_approval",
        description="Action when AI confidence is below threshold",
    )
    outbound_policy: Literal["require_approval", "allow_high_confidence", "full_autopilot"] = Field(
        default="allow_high_confidence",
        description="Policy for outbound actions (reply/forward)",
    )
    outbound_confidence_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for auto-sending outbound messages",
    )
    autopilot_batch_size: int = Field(
        default=50, ge=1, description="Number of emails to process per autopilot run"
    )
    autopilot_rate_limit_delay: float = Field(
        default=1.0, ge=0.0, description="Delay between AI API calls (seconds)"
    )
    mailbox_cache_ttl_minutes: int = Field(
        default=60, ge=1, description="Minutes to cache mailbox list before refreshing"
    )

    # Watcher settings (for hybrid trigger mode)
    poll_interval_seconds: int = Field(
        default=30, ge=5, description="Seconds between inbox count checks"
    )
    post_scan_interval_minutes: int = Field(
        default=10, ge=1, description="Minutes to wait after any scan before next scheduled scan"
    )
    watcher_startup_scan: bool = Field(
        default=True, description="Run immediate scan when watcher starts"
    )

    @property
    def rules_path(self) -> Path:
        """Full path to rules file."""
        return self.config_dir / self.rules_file

    @property
    def templates_path(self) -> Path:
        """Full path to templates file."""
        return self.config_dir / self.templates_file

    @property
    def autopilot_config_path(self) -> Path:
        """Full path to autopilot config file."""
        return self.config_dir / self.autopilot_config_file

    @property
    def database_path(self) -> Path:
        """Path to SQLite database for autopilot state."""
        return self.config_dir / "autopilot.db"

    def ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)


def load_rules(path: Path) -> list[dict]:
    """Load rules from a YAML file."""
    if not path.exists():
        return []

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    return data.get("rules", [])


def save_rules(path: Path, rules: list[dict]) -> None:
    """Save rules to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        yaml.dump({"rules": rules}, f, default_flow_style=False, sort_keys=False)
