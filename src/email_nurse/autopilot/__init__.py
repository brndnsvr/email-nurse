"""Autopilot mode for AI-native email processing."""

from email_nurse.autopilot.config import AutopilotConfig, load_autopilot_config
from email_nurse.autopilot.engine import AutopilotEngine
from email_nurse.autopilot.watcher import WatcherEngine
from email_nurse.autopilot.models import (
    AutopilotDecision,
    AutopilotRunResult,
    LowConfidenceAction,
    OutboundPolicy,
    PendingAction,
    ProcessResult,
)

__all__ = [
    "AutopilotConfig",
    "AutopilotEngine",
    "WatcherEngine",
    "load_autopilot_config",
    "AutopilotDecision",
    "AutopilotRunResult",
    "LowConfidenceAction",
    "OutboundPolicy",
    "PendingAction",
    "ProcessResult",
]
