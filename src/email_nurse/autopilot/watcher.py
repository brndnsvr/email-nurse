"""Hybrid trigger watcher for event-driven and interval-based scanning."""

import asyncio
import json
import os
import signal
from datetime import datetime
from types import FrameType
from typing import TYPE_CHECKING

from rich.console import Console

from email_nurse.autopilot.config import AutopilotConfig
from email_nurse.autopilot.engine import AutopilotEngine
from email_nurse.mail.accounts import get_accounts
from email_nurse.mail.messages import get_inbox_count
from email_nurse.storage.database import AutopilotDatabase

if TYPE_CHECKING:
    from email_nurse.ai.base import AIProvider
    from email_nurse.config import Settings

console = Console()


class WatcherEngine:
    """
    Hybrid trigger watcher that combines event-driven and interval-based scanning.

    Polls inbox message counts to detect new messages (event-driven) and also
    runs scheduled scans at configurable intervals after each scan completion.
    """

    # State keys for database persistence
    STATE_LAST_COUNTS = "last_inbox_counts"
    STATE_LAST_SCAN = "last_scan_completed"
    STATE_WATCHER_PID = "watcher_pid"

    def __init__(
        self,
        settings: "Settings",
        ai_provider: "AIProvider",
        database: AutopilotDatabase,
        config: AutopilotConfig,
    ) -> None:
        """
        Initialize the watcher engine.

        Args:
            settings: Application settings (includes poll_interval_seconds, etc).
            ai_provider: AI provider for classification (passed to AutopilotEngine).
            database: Database for tracking state.
            config: Autopilot configuration.
        """
        self.settings = settings
        self.ai_provider = ai_provider
        self.db = database
        self.config = config

        # In-memory state
        self._last_counts: dict[str, int] = {}
        self._last_scan_time: datetime | None = None
        self._scan_in_progress: bool = False
        self._stop_requested: bool = False

        # Runtime options (can be overridden per-run)
        self._verbose: int = 0
        self._dry_run: bool = False
        self._auto_create: bool = False

    def _get_configured_accounts(self) -> list[str]:
        """Get list of accounts to monitor based on configuration."""
        if self.config.accounts:
            return self.config.accounts

        # If no accounts configured, get all enabled accounts from Mail.app
        try:
            all_accounts = get_accounts()
            return [acc.name for acc in all_accounts if acc.enabled]
        except Exception as e:
            if self._verbose >= 2:
                console.print(f"[yellow]Warning: Failed to get accounts: {e}[/yellow]")
            return []

    def _restore_state(self) -> None:
        """Load persisted state from database for crash recovery."""
        # Restore last inbox counts
        counts_json = self.db.get_watcher_state(self.STATE_LAST_COUNTS)
        if counts_json:
            try:
                self._last_counts = json.loads(counts_json)
            except json.JSONDecodeError:
                self._last_counts = {}

        # Restore last scan time
        last_scan = self.db.get_watcher_state(self.STATE_LAST_SCAN)
        if last_scan:
            try:
                self._last_scan_time = datetime.fromisoformat(last_scan)
            except ValueError:
                self._last_scan_time = None

    def _persist_state(self) -> None:
        """Save current state to database for crash recovery."""
        self.db.set_watcher_state(
            self.STATE_LAST_COUNTS,
            json.dumps(self._last_counts),
        )
        if self._last_scan_time:
            self.db.set_watcher_state(
                self.STATE_LAST_SCAN,
                self._last_scan_time.isoformat(),
            )
        self.db.set_watcher_state(
            self.STATE_WATCHER_PID,
            str(os.getpid()),
        )

    def _check_stale_watcher(self) -> None:
        """
        Check if another watcher is already running.

        Raises:
            RuntimeError: If another watcher process is detected.
        """
        stored_pid = self.db.get_watcher_state(self.STATE_WATCHER_PID)
        if stored_pid:
            try:
                pid = int(stored_pid)
                # Check if process exists (signal 0 doesn't actually send a signal)
                os.kill(pid, 0)
                # Process exists - check if it's not us
                if pid != os.getpid():
                    raise RuntimeError(
                        f"Another watcher appears to be running (PID {pid}). "
                        "If this is incorrect, run 'email-nurse autopilot reset-watcher'."
                    )
            except OSError:
                # Process doesn't exist - stale PID, clear it
                pass
            except ValueError:
                # Invalid PID stored - clear it
                pass

    def _update_counts(self) -> None:
        """Refresh inbox counts for all configured accounts."""
        accounts = self._get_configured_accounts()
        for account in accounts:
            for mailbox in self.config.mailboxes:
                try:
                    count = get_inbox_count(account, mailbox)
                    key = f"{account}:{mailbox}"
                    self._last_counts[key] = count
                except Exception as e:
                    if self._verbose >= 2:
                        console.print(
                            f"[yellow]Warning: Failed to get count for "
                            f"{account}/{mailbox}: {e}[/yellow]"
                        )

    def _should_scan_for_new_messages(self) -> tuple[bool, str | None]:
        """
        Check if inbox count increased for any account/mailbox.

        Returns:
            Tuple of (should_scan, reason_details).
        """
        accounts = self._get_configured_accounts()
        for account in accounts:
            for mailbox in self.config.mailboxes:
                key = f"{account}:{mailbox}"
                try:
                    current = get_inbox_count(account, mailbox)
                    previous = self._last_counts.get(key, 0)
                    if current > previous:
                        diff = current - previous
                        return True, f"{diff} new message(s) in {account}/{mailbox}"
                except Exception:
                    continue
        return False, None

    def _should_scan_for_interval(self) -> bool:
        """Check if post-scan interval has elapsed."""
        if self._last_scan_time is None:
            return True  # No scan recorded, trigger one

        elapsed = (datetime.now() - self._last_scan_time).total_seconds()
        interval_seconds = self.settings.post_scan_interval_minutes * 60
        return elapsed >= interval_seconds

    def _decide_trigger(self) -> tuple[str | None, str | None]:
        """
        Decide whether to trigger a scan and why.

        Returns:
            Tuple of (trigger_reason, details) or (None, None) if no trigger needed.
            trigger_reason is one of: "new_messages", "interval", None
        """
        # Priority 1: New messages detected
        should_scan, details = self._should_scan_for_new_messages()
        if should_scan:
            return "new_messages", details

        # Priority 2: Interval elapsed
        if self._should_scan_for_interval():
            return "interval", None

        return None, None

    async def _trigger_scan(self, reason: str, details: str | None = None) -> None:
        """
        Execute a scan using AutopilotEngine.

        Args:
            reason: Why the scan was triggered ("startup", "new_messages", "interval").
            details: Optional details about the trigger (e.g., "3 new messages in iCloud/INBOX").
        """
        if self._scan_in_progress:
            if self._verbose >= 2:
                console.print("[dim]Scan already in progress, skipping[/dim]")
            return

        self._scan_in_progress = True
        try:
            # Log trigger reason
            if self._verbose >= 1:
                timestamp = datetime.now().strftime("%H:%M:%S")
                if details:
                    console.print(
                        f"[cyan][{timestamp}] Triggering scan ({reason}): {details}[/cyan]"
                    )
                else:
                    console.print(f"[cyan][{timestamp}] Triggering scan ({reason})[/cyan]")

            # Capture baseline counts BEFORE scan
            self._update_counts()

            # Create and run AutopilotEngine
            engine = AutopilotEngine(
                settings=self.settings,
                ai_provider=self.ai_provider,
                database=self.db,
                config=self.config,
            )

            result = await engine.run(
                dry_run=self._dry_run,
                verbose=self._verbose,
                auto_create=self._auto_create,
            )

            # Update state AFTER scan
            self._last_scan_time = datetime.now()
            self._update_counts()  # Refresh counts (emails may have been moved)
            self._persist_state()

            # Log results
            if self._verbose >= 1:
                console.print(
                    f"[green]Scan complete:[/green] "
                    f"{result.emails_processed} processed, "
                    f"{result.emails_skipped} skipped, "
                    f"{result.errors} errors"
                )

        except Exception as e:
            if self._verbose >= 1:
                console.print(f"[red]Scan error:[/red] {e}")
        finally:
            self._scan_in_progress = False

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def handle_signal(signum: int, frame: FrameType | None) -> None:
            sig_name = signal.Signals(signum).name
            if self._verbose >= 1:
                console.print(f"\n[yellow]Received {sig_name}, shutting down...[/yellow]")
            self._stop_requested = True

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    async def run(
        self,
        *,
        verbose: int = 1,
        dry_run: bool = False,
        auto_create: bool = False,
        poll_interval: int | None = None,
        post_scan_interval: int | None = None,
    ) -> None:
        """
        Run the watcher loop.

        Args:
            verbose: Verbosity level (0=silent, 1=normal, 2=detailed, 3=debug).
            dry_run: If True, don't execute actions (test mode).
            auto_create: If True, auto-create missing folders without prompting.
            poll_interval: Override poll_interval_seconds from settings.
            post_scan_interval: Override post_scan_interval_minutes from settings.
        """
        self._verbose = verbose
        self._dry_run = dry_run
        self._auto_create = auto_create

        # Apply overrides
        if poll_interval is not None:
            self.settings.poll_interval_seconds = poll_interval
        if post_scan_interval is not None:
            self.settings.post_scan_interval_minutes = post_scan_interval

        # Set up signal handlers
        self._setup_signal_handlers()

        # Check for stale watcher
        self._check_stale_watcher()

        # Restore state from database
        self._restore_state()

        # Register our PID
        self._persist_state()

        if verbose >= 1:
            console.print(
                f"[bold]Watcher started[/bold] "
                f"(poll every {self.settings.poll_interval_seconds}s, "
                f"interval {self.settings.post_scan_interval_minutes}m)"
            )
            accounts = self._get_configured_accounts()
            mailboxes = self.config.mailboxes
            console.print(f"Monitoring: {', '.join(accounts)} / {', '.join(mailboxes)}")
            if dry_run:
                console.print("[yellow]DRY RUN MODE - no actions will be executed[/yellow]")
            console.print("Press Ctrl+C to stop\n")

        # Run startup scan if configured
        if self.settings.watcher_startup_scan:
            await self._trigger_scan(reason="startup")

        # Main watcher loop
        while not self._stop_requested:
            try:
                # Check for trigger conditions
                trigger, details = self._decide_trigger()
                if trigger:
                    await self._trigger_scan(reason=trigger, details=details)

                # Sleep until next check
                await asyncio.sleep(self.settings.poll_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if verbose >= 1:
                    console.print(f"[red]Watcher error:[/red] {e}")
                # Continue running despite errors
                await asyncio.sleep(self.settings.poll_interval_seconds)

        # Cleanup
        if verbose >= 1:
            console.print("[dim]Watcher stopped[/dim]")

    def reset_state(self) -> None:
        """Clear all watcher state (useful for troubleshooting)."""
        self.db.clear_watcher_state()
        self._last_counts = {}
        self._last_scan_time = None
        console.print("[green]Watcher state cleared[/green]")
