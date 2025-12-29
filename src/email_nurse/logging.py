"""Logging infrastructure for email-nurse with per-account logs.

This module provides per-account logging to ~/Library/Logs/ with automatic rotation:
- email-nurse-error.log: Errors from all accounts (ERROR+ level only)
- email-nurse-{account}.log: Per-account activity logs

Usage:
    from email_nurse.logging import setup_logging, get_account_logger, get_error_logger

    # Initialize once at startup
    setup_logging()

    # Get logger for specific account
    logger = get_account_logger("iCloud")
    logger.info("Processing email...")

    # Errors also go to error log automatically
    logger.error("Something failed")  # Goes to both account log AND error log
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Default log directory (macOS standard location)
DEFAULT_LOG_DIR = Path.home() / "Library" / "Logs"

# Default rotation settings
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5MB
DEFAULT_BACKUP_COUNT = 3

# Module-level state
_loggers: dict[str, logging.Logger] = {}
_error_logger: logging.Logger | None = None
_log_dir: Path = DEFAULT_LOG_DIR
_max_bytes: int = DEFAULT_MAX_BYTES
_backup_count: int = DEFAULT_BACKUP_COUNT
_initialized: bool = False


class ErrorPropagatingHandler(logging.Handler):
    """Handler that propagates ERROR+ messages to the error logger."""

    def __init__(self, account: str) -> None:
        super().__init__(level=logging.ERROR)
        self.account = account

    def emit(self, record: logging.LogRecord) -> None:
        """Forward error records to the error logger with account context."""
        error_logger = get_error_logger()
        # Add account prefix to the message
        prefixed_record = logging.LogRecord(
            name=record.name,
            level=record.levelno,
            pathname=record.pathname,
            lineno=record.lineno,
            msg=f"[{self.account}] {record.getMessage()}",
            args=(),  # Already formatted via getMessage()
            exc_info=record.exc_info,
        )
        error_logger.handle(prefixed_record)


def setup_logging(
    log_dir: Path | None = None,
    log_level: str = "INFO",
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> None:
    """Initialize the logging system.

    Args:
        log_dir: Directory for log files (default: ~/Library/Logs)
        log_level: Minimum log level (default: INFO)
        max_bytes: Max size per log file before rotation (default: 5MB)
        backup_count: Number of backup files to keep (default: 3)
    """
    global _log_dir, _max_bytes, _backup_count, _initialized

    _log_dir = log_dir or DEFAULT_LOG_DIR
    _max_bytes = max_bytes or DEFAULT_MAX_BYTES
    _backup_count = backup_count if backup_count is not None else DEFAULT_BACKUP_COUNT

    # Ensure log directory exists
    _log_dir.mkdir(parents=True, exist_ok=True)

    # Configure the root email_nurse logger
    root_logger = logging.getLogger("email_nurse")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    _initialized = True


def get_error_logger() -> logging.Logger:
    """Get the shared error logger (ERROR+ level, all accounts).

    Returns:
        Logger that writes to email-nurse-error.log
    """
    global _error_logger

    if _error_logger is not None:
        return _error_logger

    if not _initialized:
        setup_logging()

    logger = logging.getLogger("email_nurse.errors")
    logger.setLevel(logging.ERROR)
    # Don't propagate to root to avoid duplicate messages
    logger.propagate = False

    # Check if handler already exists (avoid duplicates on re-init)
    if not logger.handlers:
        error_file = _log_dir / "email-nurse-error.log"
        handler = RotatingFileHandler(
            error_file,
            maxBytes=_max_bytes,
            backupCount=_backup_count,
        )
        handler.setLevel(logging.ERROR)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)

    _error_logger = logger
    return logger


def get_account_logger(account: str) -> logging.Logger:
    """Get or create a logger for a specific email account.

    Args:
        account: Name of the email account (e.g., "iCloud", "CSquare")

    Returns:
        Logger that writes to email-nurse-{account}.log
    """
    if account in _loggers:
        return _loggers[account]

    if not _initialized:
        setup_logging()

    # Sanitize account name for filename (replace non-alphanumeric with hyphen)
    safe_name = "".join(c if c.isalnum() else "-" for c in account)

    logger = logging.getLogger(f"email_nurse.account.{safe_name}")
    logger.setLevel(logging.INFO)
    # Don't propagate to avoid duplicate messages
    logger.propagate = False

    # Check if handlers already exist (avoid duplicates)
    if not logger.handlers:
        # Per-account file handler
        account_file = _log_dir / f"email-nurse-{safe_name}.log"
        file_handler = RotatingFileHandler(
            account_file,
            maxBytes=_max_bytes,
            backupCount=_backup_count,
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(file_handler)

        # Error propagation handler - sends ERROR+ to error log
        error_handler = ErrorPropagatingHandler(account)
        logger.addHandler(error_handler)

    _loggers[account] = logger
    return logger


def reset_logging() -> None:
    """Reset logging state (primarily for testing)."""
    global _loggers, _error_logger, _initialized

    # Close all handlers
    for logger in _loggers.values():
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

    if _error_logger:
        for handler in _error_logger.handlers[:]:
            handler.close()
            _error_logger.removeHandler(handler)

    _loggers = {}
    _error_logger = None
    _initialized = False
