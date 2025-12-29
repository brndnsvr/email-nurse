"""SQLite database for autopilot state tracking."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator


def _safe_json_loads(data: str | None, default: Any = None) -> Any:
    """Safely parse JSON, returning default on error."""
    if not data:
        return default
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError) as e:
        # Log but don't crash - return default for corrupted data
        import sys
        print(f"Warning: Failed to parse JSON in database: {e}", file=sys.stderr)
        return default


class AutopilotDatabase:
    """SQLite database for tracking processed emails and pending actions."""

    def __init__(self, db_path: Path) -> None:
        """
        Initialize the database connection.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._ensure_schema()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        """Create database tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connection() as conn:
            conn.executescript("""
                -- Track which emails have been processed
                CREATE TABLE IF NOT EXISTS processed_emails (
                    message_id TEXT PRIMARY KEY,
                    mailbox TEXT NOT NULL,
                    account TEXT NOT NULL,
                    subject TEXT,
                    sender TEXT,
                    processed_at TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    confidence REAL NOT NULL
                );

                -- Queue for actions awaiting user approval
                CREATE TABLE IF NOT EXISTS pending_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    email_summary TEXT NOT NULL,
                    proposed_action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reasoning TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    resolved_at TEXT
                );

                -- Audit log for all actions taken
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    details TEXT
                );

                -- Cache for mailbox lists (avoid slow AppleScript on every run)
                CREATE TABLE IF NOT EXISTS mailbox_cache (
                    account TEXT PRIMARY KEY,
                    mailboxes TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                );

                -- Track when emails were first seen (for inbox aging)
                CREATE TABLE IF NOT EXISTS email_first_seen (
                    message_id TEXT PRIMARY KEY,
                    mailbox TEXT NOT NULL,
                    account TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL
                );

                -- Indexes for common queries
                CREATE INDEX IF NOT EXISTS idx_processed_at
                    ON processed_emails(processed_at);
                CREATE INDEX IF NOT EXISTS idx_pending_status
                    ON pending_actions(status);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                    ON audit_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_first_seen_at
                    ON email_first_seen(first_seen_at);
            """)

            # Migration: Add folder-pending columns to pending_actions
            cursor = conn.execute("PRAGMA table_info(pending_actions)")
            existing_columns = {row["name"] for row in cursor.fetchall()}

            if "pending_folder" not in existing_columns:
                conn.execute(
                    "ALTER TABLE pending_actions ADD COLUMN pending_folder TEXT"
                )
            if "pending_account" not in existing_columns:
                conn.execute(
                    "ALTER TABLE pending_actions ADD COLUMN pending_account TEXT"
                )
            if "action_type" not in existing_columns:
                conn.execute(
                    "ALTER TABLE pending_actions ADD COLUMN action_type TEXT DEFAULT 'general'"
                )

            # Index for folder-pending queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending_folder
                ON pending_actions(pending_folder, pending_account)
                WHERE pending_folder IS NOT NULL
            """)

    # ─── Processed Emails ─────────────────────────────────────────────────

    def is_processed(self, message_id: str) -> bool:
        """Check if an email has already been processed."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_emails WHERE message_id = ?",
                (message_id,),
            )
            return cursor.fetchone() is not None

    def get_processed_ids(self, limit: int = 10000) -> set[str]:
        """Get set of processed message IDs for efficient filtering."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT message_id FROM processed_emails ORDER BY processed_at DESC LIMIT ?",
                (limit,),
            )
            return {row["message_id"] for row in cursor.fetchall()}

    def mark_processed(
        self,
        message_id: str,
        mailbox: str,
        account: str,
        subject: str,
        sender: str,
        action: dict[str, Any],
        confidence: float,
    ) -> None:
        """Mark an email as processed."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_emails
                (message_id, mailbox, account, subject, sender, processed_at, action_taken, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    mailbox,
                    account,
                    subject,
                    sender,
                    datetime.now().isoformat(),
                    json.dumps(action),
                    confidence,
                ),
            )

    def get_processed_count(self) -> int:
        """Get count of processed emails."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM processed_emails")
            return cursor.fetchone()[0]

    def clear_processed(self, before_days: int | None = None) -> int:
        """Clear processed emails, optionally only those older than N days."""
        with self._connection() as conn:
            if before_days:
                cursor = conn.execute(
                    """
                    DELETE FROM processed_emails
                    WHERE datetime(processed_at) < datetime('now', ?)
                    """,
                    (f"-{before_days} days",),
                )
            else:
                cursor = conn.execute("DELETE FROM processed_emails")
            return cursor.rowcount

    def cleanup_old_records(self, retention_days: int) -> int:
        """
        Remove processed email records older than retention period.

        Args:
            retention_days: Delete records older than this many days.

        Returns:
            Number of records deleted.
        """
        return self.clear_processed(before_days=retention_days)

    # ─── Pending Actions Queue ────────────────────────────────────────────

    def add_pending_action(
        self,
        message_id: str,
        email_summary: str,
        proposed_action: dict[str, Any],
        confidence: float,
        reasoning: str,
    ) -> int:
        """Add an action to the pending queue. Returns the action ID."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pending_actions
                (message_id, email_summary, proposed_action, confidence, reasoning, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    message_id,
                    email_summary,
                    json.dumps(proposed_action),
                    confidence,
                    reasoning,
                    datetime.now().isoformat(),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to insert pending action - no lastrowid returned")
            return cursor.lastrowid

    def get_pending_actions(
        self,
        status: str = "pending",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get pending actions by status."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, message_id, email_summary, proposed_action,
                       confidence, reasoning, created_at, status
                FROM pending_actions
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            )
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row["id"],
                    "message_id": row["message_id"],
                    "email_summary": row["email_summary"],
                    "proposed_action": _safe_json_loads(row["proposed_action"], {}),
                    "confidence": row["confidence"],
                    "reasoning": row["reasoning"],
                    "created_at": row["created_at"],
                    "status": row["status"],
                })
            return results

    def get_pending_action(self, action_id: int) -> dict[str, Any] | None:
        """Get a specific pending action by ID."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, message_id, email_summary, proposed_action,
                       confidence, reasoning, created_at, status
                FROM pending_actions WHERE id = ?
                """,
                (action_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "message_id": row["message_id"],
                "email_summary": row["email_summary"],
                "proposed_action": json.loads(row["proposed_action"]),
                "confidence": row["confidence"],
                "reasoning": row["reasoning"],
                "created_at": row["created_at"],
                "status": row["status"],
            }

    def update_pending_status(self, action_id: int, status: str) -> bool:
        """Update status of a pending action. Returns True if updated."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE pending_actions
                SET status = ?, resolved_at = ?
                WHERE id = ?
                """,
                (status, datetime.now().isoformat(), action_id),
            )
            return cursor.rowcount > 0

    def get_pending_count(self) -> int:
        """Get count of pending actions."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM pending_actions WHERE status = 'pending'"
            )
            return cursor.fetchone()[0]

    # ─── Folder-Pending Actions ───────────────────────────────────────────

    def add_pending_folder_action(
        self,
        message_id: str,
        email_summary: str,
        proposed_action: dict[str, Any],
        confidence: float,
        reasoning: str,
        pending_folder: str,
        pending_account: str,
    ) -> int:
        """Add an action that's waiting for a folder to be created.

        Args:
            message_id: Email message ID.
            email_summary: Brief summary (sender: subject).
            proposed_action: The action to execute once folder exists.
            confidence: AI confidence score.
            reasoning: Why this action was proposed.
            pending_folder: Folder that needs to be created.
            pending_account: Account where folder is needed.

        Returns:
            The pending action ID.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pending_actions
                (message_id, email_summary, proposed_action, confidence, reasoning,
                 created_at, status, pending_folder, pending_account, action_type)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, 'folder_pending')
                """,
                (
                    message_id,
                    email_summary,
                    json.dumps(proposed_action),
                    confidence,
                    reasoning,
                    datetime.now().isoformat(),
                    pending_folder,
                    pending_account,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to insert pending folder action")
            return cursor.lastrowid

    def get_pending_folders(
        self,
        account: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get list of folders that need to be created.

        Args:
            account: Filter by account, or None for all accounts.

        Returns:
            List of dicts with folder, account, message count, and first queued time.
        """
        query = """
            SELECT pending_folder, pending_account,
                   COUNT(*) as message_count,
                   MIN(created_at) as first_queued
            FROM pending_actions
            WHERE status = 'pending'
              AND pending_folder IS NOT NULL
        """
        params: list[Any] = []

        if account:
            query += " AND pending_account = ?"
            params.append(account)

        query += " GROUP BY pending_folder, pending_account ORDER BY first_queued"

        with self._connection() as conn:
            cursor = conn.execute(query, params)
            return [
                {
                    "pending_folder": row["pending_folder"],
                    "pending_account": row["pending_account"],
                    "message_count": row["message_count"],
                    "first_queued": row["first_queued"],
                }
                for row in cursor.fetchall()
            ]

    def get_actions_for_folder(
        self,
        folder: str,
        account: str,
    ) -> list[dict[str, Any]]:
        """Get all pending actions waiting on a specific folder.

        Args:
            folder: Folder name that was pending.
            account: Account the folder is on.

        Returns:
            List of pending action records.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, message_id, email_summary, proposed_action,
                       confidence, reasoning, created_at, status,
                       pending_folder, pending_account
                FROM pending_actions
                WHERE status = 'pending'
                  AND pending_folder = ?
                  AND pending_account = ?
                ORDER BY created_at
                """,
                (folder, account),
            )
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row["id"],
                    "message_id": row["message_id"],
                    "email_summary": row["email_summary"],
                    "proposed_action": _safe_json_loads(row["proposed_action"], {}),
                    "confidence": row["confidence"],
                    "reasoning": row["reasoning"],
                    "created_at": row["created_at"],
                    "status": row["status"],
                    "pending_folder": row["pending_folder"],
                    "pending_account": row["pending_account"],
                })
            return results

    def get_folder_pending_messages(
        self,
        folder: str,
        account: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get sample messages waiting on a folder (for notifications).

        Args:
            folder: Folder name.
            account: Account name.
            limit: Maximum messages to return.

        Returns:
            List with sender, subject, date info for notifications.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT email_summary, created_at
                FROM pending_actions
                WHERE status = 'pending'
                  AND pending_folder = ?
                  AND pending_account = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (folder, account, limit),
            )
            results = []
            for row in cursor.fetchall():
                # Parse "sender: subject" format
                summary = row["email_summary"]
                if ": " in summary:
                    sender, subject = summary.split(": ", 1)
                else:
                    sender, subject = summary, ""
                results.append({
                    "sender": sender,
                    "subject": subject,
                    "date": row["created_at"][:10],  # Just the date part
                })
            return results

    def remove_pending_action(self, action_id: int) -> bool:
        """Remove a pending action by ID (after it's been executed).

        Args:
            action_id: The database ID of the pending action.

        Returns:
            True if action was removed, False if not found.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM pending_actions WHERE id = ?",
                (action_id,),
            )
            return cursor.rowcount > 0

    # ─── Audit Log ────────────────────────────────────────────────────────

    def log_action(
        self,
        message_id: str,
        action: str,
        source: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an action to the audit trail."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (message_id, action, source, timestamp, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    action,
                    source,
                    datetime.now().isoformat(),
                    json.dumps(details) if details else None,
                ),
            )

    def get_audit_log(
        self,
        limit: int = 100,
        action_filter: str | None = None,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get audit log entries."""
        query = "SELECT * FROM audit_log WHERE 1=1"
        params: list[Any] = []

        if action_filter:
            query += " AND action = ?"
            params.append(action_filter)
        if source_filter:
            query += " AND source = ?"
            params.append(source_filter)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._connection() as conn:
            cursor = conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row["id"],
                    "message_id": row["message_id"],
                    "action": row["action"],
                    "source": row["source"],
                    "timestamp": row["timestamp"],
                    "details": _safe_json_loads(row["details"]),
                })
            return results

    # ─── Statistics ───────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        with self._connection() as conn:
            stats = {}

            # Processed count
            cursor = conn.execute("SELECT COUNT(*) FROM processed_emails")
            stats["processed_total"] = cursor.fetchone()[0]

            # Pending count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM pending_actions WHERE status = 'pending'"
            )
            stats["pending_count"] = cursor.fetchone()[0]

            # Actions by type (last 7 days)
            cursor = conn.execute("""
                SELECT action, COUNT(*) as count
                FROM audit_log
                WHERE datetime(timestamp) > datetime('now', '-7 days')
                GROUP BY action
            """)
            stats["actions_7d"] = {row["action"]: row["count"] for row in cursor.fetchall()}

            # Last processed
            cursor = conn.execute(
                "SELECT MAX(processed_at) FROM processed_emails"
            )
            row = cursor.fetchone()
            stats["last_processed"] = row[0] if row else None

            return stats

    # ─── Mailbox Cache ─────────────────────────────────────────────────────

    def get_cached_mailboxes(self, account: str, max_age_minutes: int) -> list[str] | None:
        """
        Get cached mailboxes if fresh, else None.

        Args:
            account: Account name to get mailboxes for.
            max_age_minutes: Maximum age of cache in minutes.

        Returns:
            List of mailbox names if cache is fresh, None otherwise.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT mailboxes, cached_at FROM mailbox_cache
                WHERE account = ?
                """,
                (account,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            # Check if cache is still fresh
            cached_at = datetime.fromisoformat(row["cached_at"])
            age_minutes = (datetime.now() - cached_at).total_seconds() / 60

            if age_minutes > max_age_minutes:
                return None  # Cache expired

            return _safe_json_loads(row["mailboxes"], None)

    def set_cached_mailboxes(self, account: str, mailboxes: list[str]) -> None:
        """
        Store mailboxes in cache with current timestamp.

        Args:
            account: Account name.
            mailboxes: List of mailbox names.
        """
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO mailbox_cache (account, mailboxes, cached_at)
                VALUES (?, ?, ?)
                """,
                (account, json.dumps(mailboxes), datetime.now().isoformat()),
            )

    def clear_mailbox_cache(self, account: str | None = None) -> int:
        """
        Clear cached mailbox lists.

        Args:
            account: Specific account to clear, or None for all accounts.

        Returns:
            Number of cache entries cleared.
        """
        with self._connection() as conn:
            if account:
                cursor = conn.execute(
                    "DELETE FROM mailbox_cache WHERE account = ?",
                    (account,),
                )
            else:
                cursor = conn.execute("DELETE FROM mailbox_cache")
            return cursor.rowcount

    # ─── Email First Seen (Inbox Aging) ───────────────────────────────────

    def track_first_seen(
        self,
        message_id: str,
        mailbox: str,
        account: str,
    ) -> None:
        """Record when an email was first seen by autopilot.

        Uses INSERT OR REPLACE so that if an email returns to INBOX
        (e.g., user moves it back), it gets a fresh timestamp instead
        of immediately aging out.
        """
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO email_first_seen
                (message_id, mailbox, account, first_seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (message_id, mailbox, account, datetime.now().isoformat()),
            )

    def get_first_seen(self, message_id: str) -> dict[str, Any] | None:
        """Get first-seen info for an email."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM email_first_seen WHERE message_id = ?",
                (message_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "message_id": row["message_id"],
                "mailbox": row["mailbox"],
                "account": row["account"],
                "first_seen_at": row["first_seen_at"],
            }

    def get_stale_inbox_emails(self, stale_days: int) -> list[dict[str, Any]]:
        """Get emails first seen more than N days ago."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT message_id, mailbox, account, first_seen_at
                FROM email_first_seen
                WHERE datetime(first_seen_at) < datetime('now', ?)
                ORDER BY first_seen_at ASC
                """,
                (f"-{stale_days} days",),
            )
            return [
                {
                    "message_id": row["message_id"],
                    "mailbox": row["mailbox"],
                    "account": row["account"],
                    "first_seen_at": row["first_seen_at"],
                }
                for row in cursor.fetchall()
            ]

    def remove_first_seen(self, message_id: str) -> None:
        """Remove first-seen tracking for an email (after it's moved/deleted)."""
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM email_first_seen WHERE message_id = ?",
                (message_id,),
            )
