"""Autopilot engine for AI-native email processing."""

import asyncio
import sys
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Console

from email_nurse.logging import get_account_logger, get_error_logger
from email_nurse.applescript.notifications import notify_pending_folders

from email_nurse.ai.base import EmailAction
from email_nurse.autopilot.config import AutopilotConfig, QuickRule
from email_nurse.autopilot.models import (
    AgingResult,
    AutopilotDecision,
    AutopilotRunResult,
    LowConfidenceAction,
    OutboundPolicy,
    ProcessResult,
)
from email_nurse.mail.actions import (
    LOCAL_ACCOUNT_KEY,
    VIRTUAL_MAILBOXES,
    PendingMove,
    create_local_mailbox,
    create_mailbox,
    delete_message,
    find_similar_mailbox,
    flag_message,
    forward_message,
    get_all_mailboxes,
    get_local_mailboxes,
    mark_as_read,
    move_message,
    move_messages_batch,
    reply_to_message,
)
from email_nurse.mail.accounts import get_accounts
from email_nurse.mail.messages import (
    EmailMessage,
    get_messages,
    get_messages_metadata,
    load_message_content,
    load_message_headers,
)
from email_nurse.storage.database import AutopilotDatabase

if TYPE_CHECKING:
    from email_nurse.ai.base import AIProvider
    from email_nurse.config import Settings

console = Console()


class AutopilotEngine:
    """Engine for autopilot email processing."""

    def __init__(
        self,
        settings: "Settings",
        ai_provider: "AIProvider",
        database: AutopilotDatabase,
        config: AutopilotConfig,
    ) -> None:
        """
        Initialize the autopilot engine.

        Args:
            settings: Application settings.
            ai_provider: AI provider for classification.
            database: Database for tracking state.
            config: Autopilot configuration.
        """
        self.settings = settings
        self.ai = ai_provider
        self.db = database
        self.config = config
        self.mailbox_cache: list[str] = []
        self._local_mailbox_cache: list[str] = []
        self._cache_loaded_for: str | None = None  # Track which account cache is loaded for
        # Track folders queued for creation during this run (for notifications)
        self._new_pending_folders: dict[tuple[str, str], list[dict]] = {}  # (folder, account) -> messages
        # Batch move optimization: defer moves and execute in single AppleScript call
        self._pending_moves: list[PendingMove] = []
        # Track emails to mark as processed after batch move succeeds
        self._deferred_processed: list[dict] = []
        # In-run dedup: track message IDs processed during this run to prevent
        # re-processing before batch flush marks them in the database
        self._processed_this_run: set[int] = set()

    def _build_pim_context(self) -> str:
        """Build context about today's calendar and reminders for AI.

        Returns:
            String containing today's events and pending reminders, or empty if unavailable.
        """
        context_parts = []

        # Get today's calendar events
        try:
            from email_nurse.calendar import get_events_today

            events = get_events_today()
            if events:
                event_lines = []
                for e in events[:10]:  # Limit to 10 events
                    time_str = e.start_date.strftime("%H:%M") if not e.all_day else "All day"
                    event_lines.append(f"  - {time_str}: {e.summary}")
                context_parts.append("TODAY'S CALENDAR:\n" + "\n".join(event_lines))
        except Exception:
            pass  # Calendar unavailable, continue without

        # Get pending reminders
        try:
            from email_nurse.reminders import get_reminders

            reminders = get_reminders(completed=False)
            if reminders:
                reminder_lines = []
                for r in reminders[:10]:  # Limit to 10 reminders
                    due_str = r.due_date.strftime("%Y-%m-%d") if r.due_date else "No due date"
                    reminder_lines.append(f"  - [{due_str}] {r.name}")
                context_parts.append("PENDING REMINDERS:\n" + "\n".join(reminder_lines))
        except Exception:
            pass  # Reminders unavailable, continue without

        if context_parts:
            return "\n\n## CURRENT CONTEXT (for your awareness)\n" + "\n\n".join(context_parts)
        return ""

    def _load_mailbox_cache(self, account: str | None = None) -> None:
        """Load mailbox names from disk cache or Mail.app.

        Args:
            account: Account to load mailboxes for. If not provided,
                     uses main_account from config, or first account in config.accounts.
        """
        # Determine which account to load mailboxes for
        target_account = account or self.config.main_account
        if not target_account and self.config.accounts:
            target_account = self.config.accounts[0]

        if not target_account:
            # No account specified anywhere - can't load mailboxes
            return

        # Check if we already have mailboxes for this specific account
        if self._cache_loaded_for == target_account and self.mailbox_cache:
            return

        # Try disk cache first
        cached = self.db.get_cached_mailboxes(
            target_account,
            self.settings.mailbox_cache_ttl_minutes,
        )
        if cached is not None:
            self.mailbox_cache = cached
            self._cache_loaded_for = target_account
            return

        # Cache miss or expired - fetch from Mail.app and store
        try:
            self.mailbox_cache = get_all_mailboxes(target_account)
            self.db.set_cached_mailboxes(target_account, self.mailbox_cache)
            self._cache_loaded_for = target_account  # Only mark loaded on success
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load mailboxes:[/yellow] {e}")
            self.mailbox_cache = []
            self._cache_loaded_for = None  # Don't mark loaded on failure - allow retry

    def _is_local_folder(self, folder_name: str) -> bool:
        """Check if a folder should route to local 'On My Mac' mailboxes."""
        return any(
            f.lower() == folder_name.lower()
            for f in self.config.local_folders
        )

    def _load_local_mailbox_cache(self) -> list[str]:
        """Load local 'On My Mac' mailbox names from cache or Mail.app."""
        # Check if we already have a local mailbox cache in memory
        if hasattr(self, '_local_mailbox_cache') and self._local_mailbox_cache:
            return self._local_mailbox_cache

        # Try disk cache first
        cached = self.db.get_cached_mailboxes(
            LOCAL_ACCOUNT_KEY,
            self.settings.mailbox_cache_ttl_minutes,
        )
        if cached is not None:
            self._local_mailbox_cache = cached
            return cached

        # Cache miss - fetch from Mail.app
        try:
            self._local_mailbox_cache = get_local_mailboxes()
            self.db.set_cached_mailboxes(LOCAL_ACCOUNT_KEY, self._local_mailbox_cache)
            return self._local_mailbox_cache
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load local mailboxes:[/yellow] {e}")
            self._local_mailbox_cache = []
            return []

    def _queue_move(
        self,
        message_id: str,
        target_mailbox: str,
        target_account: str | None,
        source_mailbox: str | None,
        source_account: str | None,
    ) -> None:
        """Queue a move operation for batch execution at end of run."""
        self._pending_moves.append(
            PendingMove(
                message_id=message_id,
                target_mailbox=target_mailbox,
                target_account=target_account,
                source_mailbox=source_mailbox,
                source_account=source_account,
            )
        )

    def _flush_pending_moves(self, verbose: int = 0) -> int:
        """Execute pending batch moves and mark deferred emails as processed.

        Called at chunk boundaries and at end of run. Resets pending state
        after execution so the next chunk starts fresh.

        Returns:
            Number of messages successfully moved.
        """
        if not self._pending_moves:
            return 0

        if verbose >= 2:
            console.print(f"[dim]Executing {len(self._pending_moves)} moves in batch...[/dim]")
        moved_count, moved_ids = move_messages_batch(self._pending_moves)
        if verbose >= 2:
            console.print(f"[dim]Batch moved {moved_count} messages[/dim]")

        # Only mark deferred emails as processed if their move actually succeeded
        if moved_ids and self._deferred_processed:
            marked = 0
            for item in self._deferred_processed:
                if item["message_id"] in moved_ids:
                    self.db.mark_processed(**item)
                    marked += 1
            if verbose >= 2:
                console.print(f"[dim]Marked {marked}/{len(self._deferred_processed)} emails as processed[/dim]")

        # Reset for next chunk
        self._pending_moves = []
        self._deferred_processed = []

        return moved_count

    def _validate_account_name(self, account_name: str) -> str:
        """Validate account name and return the correctly-cased version.

        AppleScript account lookups are case-sensitive, so we need to
        match the exact name Mail.app uses.

        Args:
            account_name: Account name from CLI/config

        Returns:
            The correctly-cased account name from Mail.app

        Raises:
            ValueError: If account doesn't exist in Mail.app
        """
        try:
            all_accounts = get_accounts()
        except Exception:
            # Can't validate - let it fail later with the original name
            return account_name

        account_names = [a.name for a in all_accounts]

        # Exact match - use as-is
        if account_name in account_names:
            return account_name

        # Case-insensitive match - return correctly-cased version
        lower_name = account_name.lower()
        for name in account_names:
            if name.lower() == lower_name:
                return name

        # No match - raise helpful error with available accounts
        available = ", ".join(f'"{n}"' for n in account_names) or "none found"
        raise ValueError(
            f'Account "{account_name}" not found in Mail.app. '
            f"Available accounts: {available}"
        )

    def _validate_mailbox_name(self, mailbox_name: str, account: str) -> str | None:
        """Validate mailbox name and return the correctly-cased version.

        AppleScript mailbox lookups are case-sensitive, so we need to
        match the exact name Mail.app uses. Exchange/Outlook use "Inbox"
        while IMAP typically uses "INBOX".

        Args:
            mailbox_name: Mailbox name from config (e.g., "INBOX")
            account: Account name to check mailboxes for

        Returns:
            The correctly-cased mailbox name, or None if not found
        """
        try:
            mailboxes = get_all_mailboxes(account)
        except Exception:
            # Can't validate - let it fail later with the original name
            return mailbox_name

        # Exact match - use as-is
        if mailbox_name in mailboxes:
            return mailbox_name

        # Case-insensitive match - return correctly-cased version
        lower_name = mailbox_name.lower()
        for name in mailboxes:
            if name.lower() == lower_name:
                return name

        # No match found
        return None

    async def run(
        self,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        verbose: int = 0,
        interactive: bool = False,
        auto_create: bool = False,
    ) -> AutopilotRunResult:
        """
        Run autopilot processing on emails.

        Args:
            dry_run: If True, don't execute actions, just show what would happen.
            limit: Maximum emails to process (overrides settings).
            verbose: Verbosity level (0=silent, 1=compact, 2=detailed, 3=debug).
            interactive: If True, prompt for folder creation. If False, queue for later.
            auto_create: If True, auto-create missing folders without prompting.

        Returns:
            AutopilotRunResult with summary statistics.
        """
        started_at = datetime.now()
        batch_size = limit or self.settings.autopilot_batch_size

        # Reset pending folder tracking for this run
        self._new_pending_folders = {}

        # Reset pending moves for batch execution
        self._pending_moves = []

        # Reset deferred processed tracking (for quick rules with batched moves)
        self._deferred_processed = []

        # Load mailbox cache for folder checking
        self._load_mailbox_cache()

        # Get emails to process
        emails = await self._get_unprocessed_emails(batch_size)

        result = AutopilotRunResult(
            started_at=started_at,
            completed_at=started_at,  # Updated at end
            emails_fetched=len(emails),
            dry_run=dry_run,
        )

        if not emails:
            result.completed_at = datetime.now()
            return result

        if verbose >= 1:
            console.print(f"\n[bold]Processing {len(emails)} emails...[/bold]\n")

        # Process emails in chunks — flush moves between chunks for reliability
        chunk_size = self.settings.autopilot_chunk_size
        chunk_sleep = self.settings.autopilot_chunk_sleep
        processed_in_chunk = 0

        for email in emails:
            try:
                process_result = await self._process_email(
                    email, dry_run=dry_run, interactive=interactive, auto_create=auto_create
                )

                if process_result.skipped:
                    result.emails_skipped += 1
                elif process_result.queued:
                    result.actions_queued += 1
                    result.emails_processed += 1
                    self._processed_this_run.add(email.id)
                elif process_result.success:
                    result.actions_executed += 1
                    result.emails_processed += 1
                    self._processed_this_run.add(email.id)
                else:
                    result.errors += 1

                if verbose >= 1:
                    self._print_result(email, process_result, verbose)

                # Rate limiting
                if self.settings.autopilot_rate_limit_delay > 0:
                    await asyncio.sleep(self.settings.autopilot_rate_limit_delay)

                processed_in_chunk += 1

            except Exception as e:
                result.errors += 1
                logger = get_account_logger(email.account)
                logger.error(f"Error processing \"{email.subject[:40]}\": {e}")
                if verbose >= 1:
                    console.print(f"[red]Error processing {email.subject[:40]}:[/red] {e}")
                processed_in_chunk += 1

            # Flush moves at chunk boundary
            if processed_in_chunk >= chunk_size:
                if not dry_run:
                    self._flush_pending_moves(verbose)
                    if chunk_sleep > 0:
                        await asyncio.sleep(chunk_sleep)
                processed_in_chunk = 0

        # Run inbox aging checks if enabled
        if self.config.inbox_aging_enabled:
            await self._run_aging_checks(dry_run, verbose)

        # Cleanup old processed email records (retention policy)
        if not dry_run:
            deleted = self.db.cleanup_old_records(self.config.processed_retention_days)
            if deleted > 0 and verbose >= 1:
                console.print(
                    f"[dim]Cleaned up {deleted} processed records "
                    f"older than {self.config.processed_retention_days} days[/dim]"
                )

            # Also cleanup old reminder tracking records
            deleted_reminders = self.db.cleanup_old_reminder_records(
                self.config.processed_retention_days
            )
            if deleted_reminders > 0 and verbose >= 2:
                console.print(
                    f"[dim]Cleaned up {deleted_reminders} reminder records "
                    f"older than {self.config.processed_retention_days} days[/dim]"
                )

            # Also cleanup old calendar event tracking records
            deleted_events = self.db.cleanup_old_event_records(
                self.config.processed_retention_days
            )
            if deleted_events > 0 and verbose >= 2:
                console.print(
                    f"[dim]Cleaned up {deleted_events} event records "
                    f"older than {self.config.processed_retention_days} days[/dim]"
                )

            # Cleanup stale rule failure records (shorter retention - 7 days)
            deleted_failures = self.db.cleanup_old_rule_failures(days=7)
            if deleted_failures > 0 and verbose >= 2:
                console.print(
                    f"[dim]Cleaned up {deleted_failures} stale rule failure records[/dim]"
                )

        # Flush any remaining pending moves from the last chunk
        if not dry_run:
            self._flush_pending_moves(verbose)

        # Show notification for any new pending folders
        if not dry_run and self._new_pending_folders:
            self._notify_pending_folders(verbose)

        result.completed_at = datetime.now()
        return result

    async def _get_unprocessed_emails(self, limit: int) -> list[EmailMessage]:
        """Get emails that haven't been processed yet."""
        # Get already processed IDs for filtering
        processed_ids = self.db.get_processed_ids(limit=10000)

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=self.config.max_age_days)

        all_emails: list[EmailMessage] = []

        # Fetch from each configured mailbox/account
        # If no accounts specified, fetch from all enabled accounts
        if self.config.accounts:
            accounts = self.config.accounts
        else:
            try:
                all_accts = get_accounts()
                accounts = [a.name for a in all_accts if a.enabled]
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to get accounts:[/yellow] {e}")
                accounts = []

        # Validate account names (case-sensitive matching for AppleScript)
        validated_accounts = []
        for account in accounts:
            try:
                validated_name = self._validate_account_name(account)
                if validated_name != account:
                    console.print(
                        f"[dim]Note: Using '{validated_name}' "
                        f"(matched from '{account}')[/dim]"
                    )
                validated_accounts.append(validated_name)
            except ValueError as e:
                console.print(f"[red]Error: {e}[/red]")
                # Skip invalid accounts but continue with others
        accounts = validated_accounts

        for mailbox in self.config.mailboxes:
            for account in accounts:
                # Validate mailbox name (case-insensitive for Exchange vs IMAP)
                actual_mailbox = self._validate_mailbox_name(mailbox, account)
                if actual_mailbox is None:
                    console.print(
                        f"[yellow]Warning: Mailbox '{mailbox}' not found "
                        f"in account '{account}', skipping[/yellow]"
                    )
                    continue
                if actual_mailbox != mailbox:
                    console.print(
                        f"[dim]Note: Using '{actual_mailbox}' "
                        f"(matched from '{mailbox}') for {account}[/dim]"
                    )

                try:
                    # Fetch extra to account for filtering out already-processed emails.
                    # With lazy AppleScript iteration, we can safely fetch more messages
                    # without timeout risk (only iterates up to limit, doesn't enumerate all).
                    # Cap at 500 to handle large inboxes with many processed emails.
                    fetch_limit = min(limit * 3, 500)
                    logger = get_account_logger(account)
                    logger.info(f"Fetching up to {fetch_limit} emails from {actual_mailbox}")
                    # Use metadata-only fetch for ~20x speedup (content loaded on-demand)
                    messages = get_messages_metadata(
                        mailbox=actual_mailbox,
                        account=account,
                        limit=fetch_limit,
                        unread_only=False,  # Process ALL emails
                    )
                    # Override mailbox with the one we queried (Gmail reports "All Mail"
                    # for everything, but we need the actual mailbox for lookups)
                    for msg in messages:
                        if msg.mailbox in VIRTUAL_MAILBOXES or msg.mailbox.startswith("[Gmail]"):
                            msg.mailbox = actual_mailbox
                    all_emails.extend(messages)
                    logger.info(f"Fetched {len(messages)} emails from {actual_mailbox}")
                except Exception as e:
                    logger = get_account_logger(account)
                    logger.error(f"Failed to fetch from {actual_mailbox}: {e}")
                    console.print(
                        f"[yellow]Warning: Failed to fetch from {actual_mailbox}"
                        f"{f' ({account})' if account else ''}:[/yellow] {e}"
                    )

        # Sort by date (newest first) to prioritize recent emails
        all_emails.sort(key=lambda e: e.date_received or datetime.min, reverse=True)

        # Filter out already processed and apply age filter
        unprocessed = []
        seen_this_fetch: set[int] = set()
        for email in all_emails:
            # Skip if already processed (DB) or handled earlier this run
            if email.id in processed_ids or email.id in self._processed_this_run:
                continue

            # Skip duplicates within this fetch (Mail.app can return the same message twice)
            if email.id in seen_this_fetch:
                continue
            seen_this_fetch.add(email.id)

            # Skip if too old
            if email.date_received and email.date_received < cutoff_date:
                continue

            # Skip if matches exclusion patterns
            if self._is_excluded(email):
                continue

            unprocessed.append(email)

            if len(unprocessed) >= limit:
                break

        return unprocessed

    async def _process_email(
        self,
        email: EmailMessage,
        *,
        dry_run: bool = False,
        interactive: bool = False,
        auto_create: bool = False,
    ) -> ProcessResult:
        """Process a single email through autopilot."""
        logger = get_account_logger(email.account)
        subject_short = email.subject[:60] if email.subject else "(no subject)"
        logger.info(f"Processing: \"{subject_short}\" from {email.sender}")

        # Track first-seen for inbox aging (only if aging is enabled)
        if self.config.inbox_aging_enabled and not dry_run:
            self.db.track_first_seen(email.id, email.mailbox, email.account)

        # Try quick rules first (instant, no API cost)
        quick_result = self._apply_quick_rules(email, dry_run, interactive, auto_create)
        if quick_result is not None:
            if quick_result.rule_matched:
                action_str = quick_result.action or "unknown"
                folder_str = f" -> {quick_result.target_folder}" if quick_result.target_folder else ""
                logger.info(f"Quick rule \"{quick_result.rule_matched}\": {action_str.upper()}{folder_str}")
            return quick_result

        # No quick rule matched - use AI
        # Ensure content is loaded for AI classification (lazy loading optimization)
        if not email.content_loaded:
            try:
                load_message_content(email)
            except Exception as e:
                logger = get_account_logger(email.account)
                failure_count = self.db.increment_rule_failure(
                    email.id, "content_loading", str(e)
                )
                max_retries = 3

                if failure_count >= max_retries:
                    logger.warning(
                        f"Content loading failed {failure_count}x, giving up: "
                        f"{type(e).__name__}: {e}"
                    )
                    self.db.mark_processed(
                        message_id=email.id,
                        mailbox=email.mailbox,
                        account=email.account,
                        subject=(email.subject or "")[:100],
                        sender=(email.sender or "")[:100],
                        action={
                            "action": "content_load_failed",
                            "note": "max_retries_exceeded",
                            "error": str(e)[:200],
                        },
                        confidence=0.0,
                    )
                    self.db.clear_rule_failures(email.id)
                    return ProcessResult(
                        message_id=email.id,
                        success=False,
                        error=f"Content loading failed after {failure_count} attempts: {e}",
                    )
                else:
                    logger.error(
                        f"Content loading failed (attempt {failure_count}/{max_retries}): "
                        f"{type(e).__name__}: {e}"
                    )
                    return ProcessResult(
                        message_id=email.id,
                        success=False,
                        error=str(e),
                    )

        try:
            # Build enriched instructions with PIM context
            enriched_instructions = self.config.instructions
            pim_context = self._build_pim_context()
            if pim_context:
                enriched_instructions = f"{self.config.instructions}\n{pim_context}"

            decision = await self.ai.autopilot_classify(email, enriched_instructions)

            # Hard block: NEVER allow archive action from AI - convert to ignore
            if decision.action == EmailAction.ARCHIVE:
                logger.info("AI suggested ARCHIVE, converting to IGNORE (archive disabled)")
                decision.action = EmailAction.IGNORE
            if decision.secondary_action == EmailAction.ARCHIVE:
                decision.secondary_action = None

            folder_str = f" -> {decision.target_folder}" if decision.target_folder else ""
            logger.info(
                f"AI decision: {decision.action.value.upper()}{folder_str} "
                f"(confidence: {decision.confidence:.0%})"
            )
        except Exception as e:
            # Track failure count for retry logic
            failure_count = self.db.increment_rule_failure(
                email.id, "ai_classification", str(e)
            )
            max_retries = 3

            if failure_count >= max_retries:
                # Max retries exceeded - give up and mark as processed
                logger.warning(
                    f"AI classification failed {failure_count}x, giving up: "
                    f"{type(e).__name__}: {e}"
                )
                self.db.mark_processed(
                    message_id=email.id,
                    mailbox=email.mailbox,
                    account=email.account,
                    subject=(email.subject or "")[:100],
                    sender=(email.sender or "")[:100],
                    action={
                        "action": "classification_failed",
                        "note": "max_retries_exceeded",
                        "error": str(e)[:200],
                    },
                    confidence=0.0,
                )
                self.db.clear_rule_failures(email.id)
                return ProcessResult(
                    message_id=email.id,
                    success=False,
                    error=f"Classification failed after {failure_count} attempts: {e}",
                )
            else:
                # Will retry on next scan
                logger.error(
                    f"AI classification failed (attempt {failure_count}/{max_retries}): "
                    f"{type(e).__name__}: {e}"
                )
                return ProcessResult(
                    message_id=email.id,
                    success=False,
                    error=str(e),
                )

        # Check confidence threshold
        if decision.confidence < self.settings.confidence_threshold:
            return await self._handle_low_confidence(email, decision, dry_run, interactive)

        # Check outbound policy
        if decision.is_outbound:
            return await self._handle_outbound(email, decision, dry_run, interactive)

        # Execute the action
        return await self._execute_action(email, decision, dry_run, interactive, auto_create)

    async def _handle_low_confidence(
        self,
        email: EmailMessage,
        decision: AutopilotDecision,
        dry_run: bool,
        interactive: bool,
    ) -> ProcessResult:
        """Handle low-confidence decisions based on settings."""
        action_setting = LowConfidenceAction(self.settings.low_confidence_action)

        match action_setting:
            case LowConfidenceAction.FLAG_FOR_REVIEW:
                if not dry_run:
                    flag_message(
                        email.id,
                        flagged=True,
                        source_mailbox=email.mailbox,
                        source_account=email.account,
                    )
                    self._mark_processed(email, decision)
                return ProcessResult(
                    message_id=email.id,
                    success=True,
                    action="flag",
                    reason=f"Low confidence ({decision.confidence:.0%})",
                )

            case LowConfidenceAction.SKIP:
                return ProcessResult(
                    message_id=email.id,
                    skipped=True,
                    reason=f"Low confidence ({decision.confidence:.0%})",
                )

            case LowConfidenceAction.QUEUE_FOR_APPROVAL:
                if not dry_run:
                    self.db.add_pending_action(
                        message_id=email.id,
                        email_summary=f"{email.sender}: {email.subject[:50]}",
                        proposed_action=decision.model_dump(mode="json"),
                        confidence=decision.confidence,
                        reasoning=decision.reasoning,
                    )
                return ProcessResult(
                    message_id=email.id,
                    queued=True,
                    reason=f"Low confidence ({decision.confidence:.0%})",
                )

        return ProcessResult(message_id=email.id, skipped=True, reason="Unknown policy")

    async def _handle_outbound(
        self,
        email: EmailMessage,
        decision: AutopilotDecision,
        dry_run: bool,
        interactive: bool,
    ) -> ProcessResult:
        """Handle outbound (reply/forward) actions based on policy."""
        policy = OutboundPolicy(self.settings.outbound_policy)

        match policy:
            case OutboundPolicy.REQUIRE_APPROVAL:
                # Always queue outbound actions
                if not dry_run:
                    self.db.add_pending_action(
                        message_id=email.id,
                        email_summary=f"{email.sender}: {email.subject[:50]}",
                        proposed_action=decision.model_dump(mode="json"),
                        confidence=decision.confidence,
                        reasoning=f"[Outbound] {decision.reasoning}",
                    )
                return ProcessResult(
                    message_id=email.id,
                    queued=True,
                    reason="Outbound requires approval",
                )

            case OutboundPolicy.ALLOW_HIGH_CONFIDENCE:
                if decision.confidence >= self.settings.outbound_confidence_threshold:
                    return await self._execute_action(email, decision, dry_run, interactive)
                else:
                    if not dry_run:
                        self.db.add_pending_action(
                            message_id=email.id,
                            email_summary=f"{email.sender}: {email.subject[:50]}",
                            proposed_action=decision.model_dump(mode="json"),
                            confidence=decision.confidence,
                            reasoning=f"[Outbound low confidence] {decision.reasoning}",
                        )
                    return ProcessResult(
                        message_id=email.id,
                        queued=True,
                        reason=f"Outbound confidence ({decision.confidence:.0%}) below threshold",
                    )

            case OutboundPolicy.FULL_AUTOPILOT:
                return await self._execute_action(email, decision, dry_run, interactive)

        return ProcessResult(message_id=email.id, skipped=True, reason="Unknown policy")

    def _prompt_folder_decision(
        self,
        target_folder: str,
        similar_folder: str | None,
    ) -> tuple[str | None, bool]:
        """
        Prompt user for folder decision in interactive mode.

        Returns:
            Tuple of (folder_to_use, should_create).
            folder_to_use is None if user chose to skip.
        """
        console.print(f"        [yellow]⚠️  Folder \"{target_folder}\" doesn't exist.[/yellow]")

        if similar_folder:
            console.print(f"        Similar folder found: [cyan]\"{similar_folder}\"[/cyan]")
            response = console.input(
                f"        [1] Use \"{similar_folder}\"  [2] Create \"{target_folder}\"  [s] Skip: "
            ).strip().lower()

            if response == "1":
                return similar_folder, False
            elif response == "2":
                return target_folder, True
            else:  # 's' or anything else
                return None, False
        else:
            console.print("        No similar folders found.")
            response = console.input(
                f"        Create \"{target_folder}\"? [y/N/skip]: "
            ).strip().lower()

            if response == "y":
                return target_folder, True
            else:
                return None, False

    def _resolve_folder(
        self,
        target_folder: str,
        target_account: str | None,
        email: EmailMessage,
        decision: AutopilotDecision,
        interactive: bool,
        auto_create: bool = False,
    ) -> ProcessResult | None:
        """
        Check if folder exists and handle missing folders.

        Uses per-account folder policies from config, with CLI flags as overrides:
        - auto_create CLI flag: Always create folder (overrides policy)
        - interactive CLI flag: Always prompt user (overrides policy)
        - Otherwise: Use account's folder_policy (auto_create, interactive, queue)

        Args:
            target_account: Account to check, or LOCAL_ACCOUNT_KEY for local "On My Mac" mailboxes.
            interactive: CLI flag to force interactive mode.
            auto_create: CLI flag to force auto-creation.

        Returns:
            - None if folder exists or was created (continue with action)
            - ProcessResult if action should be queued or skipped
        """
        is_local = target_account == LOCAL_ACCOUNT_KEY
        account_for_policy = target_account if not is_local else "On My Mac"

        # Load appropriate mailbox cache
        if is_local:
            mailbox_list = self._load_local_mailbox_cache()
        else:
            self._load_mailbox_cache(target_account)
            mailbox_list = self.mailbox_cache

        # Check if folder exists in cache (case-insensitive)
        folder_exists = any(
            f.lower() == target_folder.lower() for f in mailbox_list
        )

        if folder_exists:
            return None  # Continue with action

        # Folder doesn't exist - find similar
        similar = find_similar_mailbox(target_folder, mailbox_list)

        # Determine effective policy: CLI flags override config
        if auto_create:
            effective_policy = "auto_create"
        elif interactive:
            effective_policy = "interactive"
        else:
            effective_policy = self.config.get_folder_policy(account_for_policy)

        if effective_policy == "auto_create":
            # Auto-create mode - just create the folder
            try:
                if is_local:
                    create_local_mailbox(target_folder)
                    self._local_mailbox_cache.append(target_folder)
                    # Update disk cache atomically to keep in sync
                    self.db.set_cached_mailboxes(LOCAL_ACCOUNT_KEY, self._local_mailbox_cache)
                else:
                    create_mailbox(target_folder, target_account)
                    self.mailbox_cache.append(target_folder)
                    # Update disk cache atomically to keep in sync
                    self.db.set_cached_mailboxes(target_account, self.mailbox_cache)
                location = "On My Mac" if is_local else target_account
                console.print(f"        [green]✓ Created \"{target_folder}\" ({location})[/green]")
                return None  # Continue with action
            except Exception as e:
                return ProcessResult(
                    message_id=email.id,
                    success=False,
                    error=f"Failed to create folder \"{target_folder}\": {e}",
                )

        if effective_policy == "interactive":
            # Prompt user for decision
            chosen_folder, should_create = self._prompt_folder_decision(
                target_folder, similar
            )

            if chosen_folder is None:
                # User chose to skip
                return ProcessResult(
                    message_id=email.id,
                    skipped=True,
                    reason=f"Skipped: folder \"{target_folder}\" doesn't exist",
                )

            if should_create:
                # Create the folder
                try:
                    if is_local:
                        create_local_mailbox(chosen_folder)
                        self._local_mailbox_cache.append(chosen_folder)
                        # Update disk cache atomically to keep in sync
                        self.db.set_cached_mailboxes(LOCAL_ACCOUNT_KEY, self._local_mailbox_cache)
                    else:
                        create_mailbox(chosen_folder, target_account)
                        self.mailbox_cache.append(chosen_folder)
                        # Update disk cache atomically to keep in sync
                        self.db.set_cached_mailboxes(target_account, self.mailbox_cache)
                    location = "On My Mac" if is_local else target_account
                    console.print(f"        [green]✓ Created \"{chosen_folder}\" ({location})[/green]")
                except Exception as e:
                    return ProcessResult(
                        message_id=email.id,
                        success=False,
                        error=f"Failed to create folder \"{chosen_folder}\": {e}",
                    )
            else:
                # User chose to use existing similar folder - update decision
                decision.target_folder = chosen_folder

            return None  # Continue with action
        else:
            # Queue policy - queue for manual folder creation with folder info
            pending_account = account_for_policy if account_for_policy else email.account
            self.db.add_pending_folder_action(
                message_id=email.id,
                email_summary=f"{email.sender}: {email.subject[:50]}",
                proposed_action=decision.model_dump(mode="json"),
                confidence=decision.confidence,
                reasoning=(
                    f"[Folder missing] \"{target_folder}\" doesn't exist"
                    + (f" (similar: \"{similar}\")" if similar else "")
                    + f" - {decision.reasoning}"
                ),
                pending_folder=target_folder,
                pending_account=pending_account,
            )

            # Track for end-of-run notification
            key = (target_folder, pending_account)
            if key not in self._new_pending_folders:
                self._new_pending_folders[key] = []
            self._new_pending_folders[key].append({
                "sender": email.sender,
                "subject": email.subject,
                "date": email.date.strftime("%Y-%m-%d %H:%M") if email.date else "",
            })

            return ProcessResult(
                message_id=email.id,
                queued=True,
                reason=f"Folder \"{target_folder}\" doesn't exist (queued for {pending_account})",
            )

    def _notify_pending_folders(self, verbose: int) -> None:
        """Show notification for folders that need manual creation.

        Checks per-account notification settings and shows an AppleScript dialog
        with folder names, message counts, and sample messages.

        Args:
            verbose: Verbosity level for console output.
        """
        if not self._new_pending_folders:
            return

        # Build pending items for notification, respecting per-account settings
        pending_items: list[dict] = []
        for (folder, account), messages in self._new_pending_folders.items():
            # Check if this account wants notifications
            if not self.config.should_notify(account):
                continue

            pending_items.append({
                "pending_folder": folder,
                "pending_account": account,
                "message_count": len(messages),
                "sample_messages": messages[:3],  # Show up to 3 samples
            })

        if not pending_items:
            return

        # Log and show console message
        total_folders = len(pending_items)
        total_messages = sum(item["message_count"] for item in pending_items)
        if verbose >= 1:
            console.print(
                f"\n[yellow]⚠ {total_folders} folder(s) need creation, "
                f"{total_messages} message(s) waiting[/yellow]"
            )

        # Show AppleScript notification dialog
        try:
            notify_pending_folders(pending_items)
        except Exception as e:
            logger = get_error_logger()
            logger.warning(f"Failed to show pending folders notification: {e}")

    async def retry_pending_folders(
        self,
        account: str | None = None,
        dry_run: bool = False,
        verbose: int = 1,
    ) -> dict[str, int]:
        """Retry pending folder actions for folders that now exist.

        Checks if any folders queued for creation now exist, and executes
        the pending move actions for those folders.

        Args:
            account: Optionally filter to a specific account.
            dry_run: If True, show what would happen without executing.
            verbose: Verbosity level for output.

        Returns:
            Dict with counts: {resolved_folders, executed_actions, errors}
        """
        results = {"resolved_folders": 0, "executed_actions": 0, "errors": 0}

        # Get all pending folders
        pending = self.db.get_pending_folders(account=account)
        if not pending:
            if verbose >= 1:
                console.print("[dim]No pending folders to retry.[/dim]")
            return results

        if verbose >= 1:
            console.print(f"\n[bold]Checking {len(pending)} pending folder(s)...[/bold]\n")

        for item in pending:
            folder = item["pending_folder"]
            pending_account = item["pending_account"]

            # Load mailbox cache for this account
            is_local = pending_account == "On My Mac"
            if is_local:
                mailbox_list = self._load_local_mailbox_cache()
            else:
                self._load_mailbox_cache(pending_account)
                mailbox_list = self.mailbox_cache

            # Check if folder now exists
            folder_exists = any(
                f.lower() == folder.lower() for f in mailbox_list
            )

            if not folder_exists:
                if verbose >= 2:
                    console.print(
                        f"[dim]  ✗ \"{folder}\" ({pending_account}) "
                        f"- still doesn't exist ({item['message_count']} waiting)[/dim]"
                    )
                continue

            # Folder exists! Process pending actions
            results["resolved_folders"] += 1
            if verbose >= 1:
                console.print(
                    f"[green]  ✓ \"{folder}\" ({pending_account}) "
                    f"- found! Processing {item['message_count']} pending action(s)...[/green]"
                )

            # Get all pending actions for this folder
            actions = self.db.get_actions_for_folder(folder, pending_account)

            for action_record in actions:
                try:
                    if dry_run:
                        if verbose >= 1:
                            console.print(
                                f"      [dry-run] Would execute: {action_record['email_summary']}"
                            )
                        results["executed_actions"] += 1
                        continue

                    # Execute the pending action
                    proposed = action_record["proposed_action"]
                    message_id = action_record["message_id"]

                    # Execute the move
                    if is_local:
                        move_message(message_id, folder, LOCAL_ACCOUNT_KEY)
                    else:
                        move_message(message_id, folder, pending_account)

                    # Mark as processed
                    self.db.mark_as_processed(message_id, proposed)

                    # Remove from pending
                    self.db.remove_pending_action(action_record["id"])

                    results["executed_actions"] += 1
                    if verbose >= 1:
                        console.print(
                            f"      [green]✓[/green] Moved: {action_record['email_summary']}"
                        )

                except Exception as e:
                    results["errors"] += 1
                    logger = get_account_logger(pending_account)
                    logger.error(
                        f"Failed to process pending action for "
                        f"\"{action_record['email_summary']}\": {e}"
                    )
                    if verbose >= 1:
                        console.print(
                            f"      [red]✗[/red] Error: {action_record['email_summary']} - {e}"
                        )

        if verbose >= 1:
            console.print(
                f"\n[bold]Retry complete:[/bold] "
                f"{results['resolved_folders']} folder(s) resolved, "
                f"{results['executed_actions']} action(s) executed, "
                f"{results['errors']} error(s)"
            )

        return results

    async def _execute_action(
        self,
        email: EmailMessage,
        decision: AutopilotDecision,
        dry_run: bool,
        interactive: bool = False,
        auto_create: bool = False,
    ) -> ProcessResult:
        """Execute the decided action."""
        action_name = decision.action.value
        # Track target folder for move/archive actions
        result_folder: str | None = None
        if decision.action == EmailAction.MOVE:
            result_folder = decision.target_folder
        elif decision.action == EmailAction.ARCHIVE:
            result_folder = "Archive"

        if dry_run:
            return ProcessResult(
                message_id=email.id,
                success=True,
                action=f"[dry-run] {action_name}",
                target_folder=result_folder,
                reason=decision.reasoning,
            )

        # Determine target account for move operations
        # Check if folder should go to local "On My Mac" mailboxes
        if decision.target_folder and self._is_local_folder(decision.target_folder):
            target_account = LOCAL_ACCOUNT_KEY  # Route to local "On My Mac"
        elif decision.action == EmailAction.ARCHIVE:
            # Archive always goes to source account's Archive folder (not main_account)
            if self._is_local_folder("Archive"):
                target_account = LOCAL_ACCOUNT_KEY  # Archive locally if Archive is in local_folders
            else:
                target_account = email.account  # Source account's Archive
        else:
            # Standard routing: main_account or source account
            target_account = self.config.main_account or email.account

        try:
            match decision.action:
                case EmailAction.MOVE:
                    if not decision.target_folder:
                        # Empty/None target folder is invalid for MOVE
                        return ProcessResult(
                            message_id=email.id,
                            success=False,
                            error="MOVE action requires target_folder but none provided",
                        )
                    # Check if folder exists and handle if not
                    result = self._resolve_folder(
                        decision.target_folder,
                        target_account,
                        email,
                        decision,
                        interactive,
                        auto_create,
                    )
                    if result is not None:
                        return result  # Queued or skipped

                    # Folder resolved - queue move for batch execution
                    self._queue_move(
                        email.id,
                        decision.target_folder,
                        target_account,
                        email.mailbox,
                        email.account,
                    )

                case EmailAction.DELETE:
                    # Delete always goes to the source account's trash
                    delete_message(
                        email.id,
                        permanent=False,
                        source_mailbox=email.mailbox,
                        source_account=email.account,
                    )

                case EmailAction.ARCHIVE:
                    # Check if Archive folder exists
                    result = self._resolve_folder(
                        "Archive",
                        target_account,
                        email,
                        decision,
                        interactive,
                        auto_create,
                    )
                    if result is not None:
                        return result  # Queued or skipped

                    # Queue archive move for batch execution
                    self._queue_move(
                        email.id,
                        "Archive",
                        target_account,
                        email.mailbox,
                        email.account,
                    )

                case EmailAction.MARK_READ:
                    mark_as_read(
                        email.id,
                        read=True,
                        source_mailbox=email.mailbox,
                        source_account=email.account,
                    )

                case EmailAction.FLAG:
                    flag_message(
                        email.id,
                        flagged=True,
                        source_mailbox=email.mailbox,
                        source_account=email.account,
                    )

                case EmailAction.REPLY:
                    if decision.reply_content:
                        reply_to_message(
                            email.id,
                            decision.reply_content,
                            send_immediately=True,
                            source_mailbox=email.mailbox,
                            source_account=email.account,
                        )

                case EmailAction.FORWARD:
                    if decision.forward_to:
                        forward_message(
                            email.id,
                            decision.forward_to,
                            send_immediately=True,
                            source_mailbox=email.mailbox,
                            source_account=email.account,
                        )

                case EmailAction.IGNORE:
                    pass  # No action needed

                case EmailAction.CREATE_REMINDER:
                    if decision.reminder_name:
                        # Check if reminder already exists for this email
                        if self.db.has_reminder_for_email(email.id):
                            existing = self.db.get_reminder_for_email(email.id)
                            reminder_logger = get_account_logger(email.account)
                            reminder_logger.info(
                                f"Skipping duplicate reminder for {email.id[:12]}... "
                                f"(existing: {existing['reminder_name'] if existing else 'unknown'})"
                            )
                            return ProcessResult(
                                message_id=email.id,
                                success=True,
                                action="create_reminder",
                                reason=f"Reminder already exists: {existing['reminder_name'] if existing else 'unknown'}",
                            )

                        from email_nurse.reminders import create_reminder_from_email

                        reminder_list = decision.reminder_list or "Reminders"
                        reminder_id = create_reminder_from_email(
                            message_id=email.id,
                            name=decision.reminder_name,
                            list_name=reminder_list,
                            due_date=decision.reminder_due,
                            subject=email.subject,
                            sender=email.sender,
                        )

                        # Record the reminder creation to prevent duplicates
                        self.db.record_reminder_created(
                            message_id=email.id,
                            reminder_id=reminder_id,
                            reminder_name=decision.reminder_name,
                            reminder_list=reminder_list,
                        )
                    else:
                        return ProcessResult(
                            message_id=email.id,
                            success=False,
                            error="CREATE_REMINDER requires reminder_name",
                        )

                case EmailAction.CREATE_EVENT:
                    if decision.event_summary and decision.event_start:
                        # Check if calendar event already exists for this email
                        if self.db.has_event_for_email(email.id):
                            existing = self.db.get_event_for_email(email.id)
                            event_logger = get_account_logger(email.account)
                            event_logger.info(
                                f"Skipping duplicate event for {email.id[:12]}... "
                                f"(existing: {existing['event_summary'] if existing else 'unknown'})"
                            )
                            return ProcessResult(
                                message_id=email.id,
                                success=True,
                                action="create_event",
                                reason=f"Event already exists: {existing['event_summary'] if existing else 'unknown'}",
                            )

                        from email_nurse.calendar import create_event_from_email

                        event_calendar = decision.event_calendar or "Calendar"
                        event_id = create_event_from_email(
                            summary=decision.event_summary,
                            start_date=decision.event_start,
                            message_id=email.id,
                            calendar_name=event_calendar,
                            end_date=decision.event_end,
                            subject=email.subject,
                            sender=email.sender,
                        )

                        # Record the event creation to prevent duplicates
                        self.db.record_event_created(
                            message_id=email.id,
                            event_id=event_id,
                            event_summary=decision.event_summary,
                            event_calendar=event_calendar,
                            event_start=decision.event_start.isoformat(),
                        )
                    else:
                        return ProcessResult(
                            message_id=email.id,
                            success=False,
                            error="CREATE_EVENT requires event_summary and event_start",
                        )

            # Execute secondary action if present
            secondary_error: str | None = None
            if decision.secondary_action:
                _, secondary_error = await self._execute_secondary_action(
                    email, decision, interactive, auto_create
                )
                if secondary_error:
                    logger = get_account_logger(email.account)
                    logger.warning(f"Secondary action warning: {secondary_error}")

            # Mark as processed and log
            self._mark_processed(email, decision)

            # Clear any previous AI action failures on success
            self.db.clear_rule_failures(email.id)

            # Remove from first-seen tracking if email was moved out of inbox
            if decision.action != EmailAction.IGNORE:
                self.db.remove_first_seen(email.id)

            # Build action name with secondary if present
            full_action_name = action_name
            if decision.secondary_action:
                full_action_name = f"{action_name}+{decision.secondary_action.value}"

            return ProcessResult(
                message_id=email.id,
                success=True,
                action=full_action_name,
                target_folder=result_folder,
                reason=decision.reasoning,
            )

        except Exception as e:
            logger = get_account_logger(email.account)
            error_str = str(e).lower()

            # Classify error type (same patterns as quick rules)
            is_message_gone = "invalid index" in error_str or "-1719" in error_str

            # Track failure count for retry logic (use "ai_action" as pseudo-rule name)
            failure_count = self.db.increment_rule_failure(email.id, "ai_action", str(e))
            max_retries = 3

            if is_message_gone:
                # Message was already moved/deleted - mark as processed
                logger.info(
                    f"AI action ({action_name}): Email no longer in mailbox, "
                    "marking as processed"
                )
                self.db.mark_processed(
                    message_id=email.id,
                    mailbox=email.mailbox,
                    account=email.account,
                    subject=(email.subject or "")[:100],
                    sender=(email.sender or "")[:100],
                    action={
                        "action": action_name,
                        "confidence": decision.confidence,
                        "note": "already_moved",
                    },
                    confidence=decision.confidence,
                )
                self.db.clear_rule_failures(email.id)
                return ProcessResult(
                    message_id=email.id,
                    success=True,
                    action=action_name,
                    target_folder=result_folder,
                    reason=f"{decision.reasoning} (already moved)",
                )

            elif failure_count >= max_retries:
                # Max retries exceeded - give up and mark as processed to stop retry loop
                logger.warning(
                    f"AI action ({action_name}) failed {failure_count}x, giving up: {e}"
                )
                self.db.mark_processed(
                    message_id=email.id,
                    mailbox=email.mailbox,
                    account=email.account,
                    subject=(email.subject or "")[:100],
                    sender=(email.sender or "")[:100],
                    action={
                        "action": action_name,
                        "confidence": decision.confidence,
                        "note": "max_retries_exceeded",
                        "error": str(e)[:200],
                    },
                    confidence=0.0,
                )
                self.db.clear_rule_failures(email.id)
                return ProcessResult(
                    message_id=email.id,
                    success=False,
                    error=f"Failed after {failure_count} attempts: {e}",
                )

            else:
                # Transient or unknown error - will retry on next scan
                logger.error(
                    f"AI action ({action_name}) failed "
                    f"(attempt {failure_count}/{max_retries}): {e}"
                )
                return ProcessResult(
                    message_id=email.id,
                    success=False,
                    error=str(e),
                )

    def _mark_processed(self, email: EmailMessage, decision: AutopilotDecision) -> None:
        """Mark an email as processed in the database."""
        self.db.mark_processed(
            message_id=email.id,
            mailbox=email.mailbox,
            account=email.account,
            subject=(email.subject or "")[:100],
            sender=(email.sender or "")[:100],
            action=decision.model_dump(mode="json"),
            confidence=decision.confidence,
        )

        self.db.log_action(
            message_id=email.id,
            action=decision.action.value,
            source="autopilot",
            details={
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
                "category": decision.category,
                "secondary_action": decision.secondary_action.value if decision.secondary_action else None,
            },
        )

    async def _execute_secondary_action(
        self,
        email: EmailMessage,
        decision: AutopilotDecision,
        interactive: bool = False,
        auto_create: bool = False,
    ) -> tuple[bool, str | None]:
        """
        Execute the secondary action if present.

        Returns:
            Tuple of (success, error_message). Success is True even if no secondary action.
        """
        if not decision.secondary_action:
            return True, None

        # Validate: outbound/destructive actions not allowed as secondary
        if decision.has_invalid_secondary:
            logger = get_account_logger(email.account)
            logger.warning(
                f"Invalid secondary action {decision.secondary_action.value} - "
                "REPLY/FORWARD not allowed as secondary actions, skipping"
            )
            return True, None  # Ignore invalid secondary, don't fail

        if decision.secondary_action == EmailAction.DELETE:
            logger = get_account_logger(email.account)
            logger.warning("DELETE not allowed as secondary action, skipping")
            return True, None

        logger = get_account_logger(email.account)
        action_name = decision.secondary_action.value

        # Determine target account for secondary move operations
        secondary_folder = decision.secondary_target_folder
        if secondary_folder and self._is_local_folder(secondary_folder):
            target_account = LOCAL_ACCOUNT_KEY
        elif decision.secondary_action == EmailAction.ARCHIVE:
            if self._is_local_folder("Archive"):
                target_account = LOCAL_ACCOUNT_KEY
            else:
                target_account = email.account
        else:
            target_account = self.config.main_account or email.account

        try:
            match decision.secondary_action:
                case EmailAction.MOVE:
                    if not secondary_folder:
                        logger.warning("Secondary MOVE action missing target folder, skipping")
                        return True, None

                    result = self._resolve_folder(
                        secondary_folder, target_account, email, decision,
                        interactive, auto_create
                    )
                    if result is not None:
                        logger.info(f"Secondary MOVE skipped: folder '{secondary_folder}' issue")
                        return True, f"Secondary MOVE skipped: folder issue"

                    # Queue secondary move for batch execution
                    self._queue_move(
                        email.id, secondary_folder, target_account,
                        email.mailbox, email.account
                    )

                case EmailAction.ARCHIVE:
                    archive_folder = secondary_folder or "Archive"
                    result = self._resolve_folder(
                        archive_folder, target_account, email, decision,
                        interactive, auto_create
                    )
                    if result is not None:
                        logger.info("Secondary ARCHIVE skipped: Archive folder issue")
                        return True, "Secondary ARCHIVE skipped"

                    # Queue secondary archive for batch execution
                    self._queue_move(
                        email.id, archive_folder, target_account,
                        email.mailbox, email.account
                    )

                case EmailAction.MARK_READ:
                    mark_as_read(
                        email.id, read=True,
                        source_mailbox=email.mailbox, source_account=email.account
                    )

                case EmailAction.FLAG:
                    flag_message(
                        email.id, flagged=True,
                        source_mailbox=email.mailbox, source_account=email.account
                    )

                case EmailAction.CREATE_REMINDER:
                    if not decision.reminder_name:
                        logger.warning("Secondary CREATE_REMINDER missing reminder_name, skipping")
                        return True, None

                    # Deduplication check
                    if self.db.has_reminder_for_email(email.id):
                        existing = self.db.get_reminder_for_email(email.id)
                        logger.info(
                            f"Secondary reminder skipped - already exists: "
                            f"{existing['reminder_name'] if existing else 'unknown'}"
                        )
                        return True, None

                    from email_nurse.reminders import create_reminder_from_email

                    reminder_list = decision.reminder_list or "Reminders"
                    reminder_id = create_reminder_from_email(
                        message_id=email.id,
                        name=decision.reminder_name,
                        list_name=reminder_list,
                        due_date=decision.reminder_due,
                        subject=email.subject,
                        sender=email.sender,
                    )

                    self.db.record_reminder_created(
                        message_id=email.id,
                        reminder_id=reminder_id,
                        reminder_name=decision.reminder_name,
                        reminder_list=reminder_list,
                    )

                case EmailAction.CREATE_EVENT:
                    if not decision.event_summary or not decision.event_start:
                        logger.warning("Secondary CREATE_EVENT missing required fields, skipping")
                        return True, None

                    # Deduplication check
                    if self.db.has_event_for_email(email.id):
                        existing = self.db.get_event_for_email(email.id)
                        logger.info(
                            f"Secondary event skipped - already exists: "
                            f"{existing['event_summary'] if existing else 'unknown'}"
                        )
                        return True, None

                    from email_nurse.calendar import create_event_from_email

                    event_calendar = decision.event_calendar or "Calendar"
                    event_id = create_event_from_email(
                        summary=decision.event_summary,
                        start_date=decision.event_start,
                        message_id=email.id,
                        calendar_name=event_calendar,
                        end_date=decision.event_end,
                        subject=email.subject,
                        sender=email.sender,
                    )

                    self.db.record_event_created(
                        message_id=email.id,
                        event_id=event_id,
                        event_summary=decision.event_summary,
                        event_calendar=event_calendar,
                        event_start=decision.event_start.isoformat(),
                    )

                case EmailAction.IGNORE:
                    pass

                case _:
                    logger.warning(f"Unsupported secondary action: {action_name}")

            logger.info(f"Secondary action executed: {action_name}")
            return True, None

        except Exception as e:
            logger.error(f"Secondary action {action_name} failed: {e}")
            return False, str(e)

    def _is_excluded(self, email: EmailMessage) -> bool:
        """Check if email should be excluded from processing."""
        sender_lower = email.sender.lower()
        subject_lower = email.subject.lower()

        # Check sender exclusions
        for pattern in self.config.exclude_senders:
            if pattern.lower() in sender_lower:
                return True

        # Check subject exclusions
        for pattern in self.config.exclude_subjects:
            if pattern.lower() in subject_lower:
                return True

        return False

    # ─── Quick Rules (Pre-AI) ─────────────────────────────────────────────

    def _apply_quick_rules(
        self,
        email: EmailMessage,
        dry_run: bool,
        interactive: bool,
        auto_create: bool = False,
    ) -> ProcessResult | None:
        """
        Apply quick rules before AI classification.

        Returns:
            ProcessResult if a rule matched, None to continue to AI.
        """
        for rule in self.config.quick_rules:
            if self._matches_rule(email, rule):
                return self._execute_quick_rule(email, rule, dry_run, interactive, auto_create)
        return None  # No match, continue to AI

    def _matches_rule(self, email: EmailMessage, rule: QuickRule) -> bool:
        """Check if an email matches a quick rule's conditions."""
        sender_lower = email.sender.lower()
        subject_lower = email.subject.lower()

        # All conditions must match (AND logic)
        # Within each condition, any pattern matches (OR logic)

        if "sender_contains" in rule.match:
            patterns = rule.match["sender_contains"]
            if not any(p.lower() in sender_lower for p in patterns):
                return False

        if "subject_contains" in rule.match:
            patterns = rule.match["subject_contains"]
            if not any(p.lower() in subject_lower for p in patterns):
                return False

        if "sender_domain" in rule.match:
            # Extract domain from sender email
            # Format: "Name <email@domain.com>" or "email@domain.com"
            import re
            domain_match = re.search(r"@([\w.-]+)", email.sender)
            if domain_match:
                sender_domain = domain_match.group(1).lower()
                patterns = rule.match["sender_domain"]
                if not any(p.lower() == sender_domain or sender_domain.endswith("." + p.lower()) for p in patterns):
                    return False
            else:
                return False  # No domain found, can't match

        # Body content matching (OR logic within list)
        if "body_contains" in rule.match:
            # Load content on-demand (lazy loading optimization)
            if not email.content_loaded:
                load_message_content(email)
            body_lower = email.content.lower()
            patterns = rule.match["body_contains"]
            if not any(p.lower() in body_lower for p in patterns):
                return False

        # Header content matching (OR logic within list)
        if "header_contains" in rule.match:
            if not email.headers_loaded:
                load_message_headers(email)
            headers_lower = email.headers.lower()
            patterns = rule.match["header_contains"]
            if not any(p.lower() in headers_lower for p in patterns):
                return False

        # Subject matching with AND logic (ALL patterns must match)
        if "subject_contains_all" in rule.match:
            patterns = rule.match["subject_contains_all"]
            if not all(p.lower() in subject_lower for p in patterns):
                return False

        return True

    def _execute_quick_rule(
        self,
        email: EmailMessage,
        rule: QuickRule,
        dry_run: bool,
        interactive: bool,
        auto_create: bool = False,
    ) -> ProcessResult:
        """Execute a matched quick rule (supports multiple actions)."""
        actions = rule.get_actions()
        action_names = "+".join(actions)

        # Track target folder for move/archive actions (first one wins for display)
        result_folder: str | None = None
        for act in actions:
            if act == "move" and rule.folder:
                result_folder = rule.folder
                break
            elif act == "archive":
                result_folder = "Archive"
                break

        if dry_run:
            return ProcessResult(
                message_id=email.id,
                success=True,
                action=f"[dry-run] {action_names}",
                target_folder=result_folder,
                reason=f"Rule: {rule.name}",
                rule_matched=rule.name,
            )

        # Determine target account - check if folder is local first
        if rule.folder and self._is_local_folder(rule.folder):
            target_account = LOCAL_ACCOUNT_KEY  # Route to local "On My Mac"
        elif "archive" in actions and self._is_local_folder("Archive"):
            target_account = LOCAL_ACCOUNT_KEY  # Archive locally
        else:
            target_account = self.config.main_account or email.account

        try:
            # Execute each action in order
            for act in actions:
                match act:
                    case "delete":
                        delete_message(
                            email.id,
                            permanent=False,
                            source_mailbox=email.mailbox,
                            source_account=email.account,
                        )

                    case "move":
                        if rule.folder:
                            # Check folder exists (reuse existing logic)
                            result = self._resolve_folder(
                                rule.folder,
                                target_account,
                                email,
                                AutopilotDecision(
                                    action=EmailAction.MOVE,
                                    confidence=1.0,
                                    reasoning=f"Quick rule: {rule.name}",
                                    target_folder=rule.folder,
                                ),
                                interactive,
                                auto_create,
                            )
                            if result is not None:
                                result.rule_matched = rule.name
                                return result

                            # Queue move for batch execution
                            self._queue_move(
                                email.id,
                                rule.folder,
                                target_account,
                                email.mailbox,
                                email.account,
                            )

                    case "archive":
                        result = self._resolve_folder(
                            "Archive",
                            target_account,
                            email,
                            AutopilotDecision(
                                action=EmailAction.ARCHIVE,
                                confidence=1.0,
                                reasoning=f"Quick rule: {rule.name}",
                            ),
                            interactive,
                            auto_create,
                        )
                        if result is not None:
                            result.rule_matched = rule.name
                            return result

                        # Queue archive for batch execution
                        self._queue_move(
                            email.id,
                            "Archive",
                            target_account,
                            email.mailbox,
                            email.account,
                        )

                    case "mark_read":
                        mark_as_read(
                            email.id,
                            read=True,
                            source_mailbox=email.mailbox,
                            source_account=email.account,
                        )

                    case "ignore":
                        pass  # Do nothing, but don't pass to AI

            # Defer marking as processed for move/archive actions (batched moves)
            # so we only mark after the batch move actually succeeds
            has_deferred_move = "move" in actions or "archive" in actions
            processed_data = {
                "message_id": email.id,
                "mailbox": email.mailbox,
                "account": email.account,
                "subject": (email.subject or "")[:100],
                "sender": (email.sender or "")[:100],
                "action": {"rule": rule.name, "actions": actions},
                "confidence": 1.0,
            }

            if has_deferred_move:
                # Defer until batch move completes
                self._deferred_processed.append(processed_data)
            else:
                # No batched action, mark immediately
                self.db.mark_processed(**processed_data)

            self.db.log_action(
                message_id=email.id,
                action=action_names,
                source=f"rule:{rule.name}",
                details={"rule_name": rule.name, "actions": actions, "folder": rule.folder},
            )

            # Remove from first-seen tracking if email was moved out of inbox
            if "ignore" not in actions:
                self.db.remove_first_seen(email.id)

            # Clear any previous failure records on success
            self.db.clear_rule_failures(email.id)

            return ProcessResult(
                message_id=email.id,
                success=True,
                action=action_names,
                target_folder=result_folder,
                reason=f"Rule: {rule.name}",
                rule_matched=rule.name,
            )

        except Exception as e:
            logger = get_account_logger(email.account)
            error_str = str(e).lower()

            # Classify error type
            is_message_gone = "invalid index" in error_str or "-1719" in error_str
            is_transient = any(
                x in error_str
                for x in ["timeout", "timed out", "connection", "busy", "temporarily"]
            )

            # Track failure count for retry logic
            failure_count = self.db.increment_rule_failure(email.id, rule.name, str(e))
            max_retries = 3

            if is_message_gone:
                # Message was already moved/deleted - mark as processed
                logger.info(
                    f"Quick rule \"{rule.name}\": Email no longer in mailbox, "
                    "marking as processed"
                )
                self.db.mark_processed(
                    message_id=email.id,
                    mailbox=email.mailbox,
                    account=email.account,
                    subject=(email.subject or "")[:100],
                    sender=(email.sender or "")[:100],
                    action={"rule": rule.name, "actions": actions, "note": "already_moved"},
                    confidence=1.0,
                )
                self.db.clear_rule_failures(email.id)
                return ProcessResult(
                    message_id=email.id,
                    success=True,
                    action=action_names,
                    target_folder=rule.folder,
                    reason=f"Rule: {rule.name} (already moved)",
                    rule_matched=rule.name,
                )

            elif failure_count >= max_retries:
                # Max retries exceeded - give up and mark as processed to stop retry loop
                logger.warning(
                    f"Quick rule \"{rule.name}\" failed {failure_count}x, giving up: {e}"
                )
                self.db.mark_processed(
                    message_id=email.id,
                    mailbox=email.mailbox,
                    account=email.account,
                    subject=(email.subject or "")[:100],
                    sender=(email.sender or "")[:100],
                    action={
                        "rule": rule.name,
                        "actions": actions,
                        "note": "max_retries_exceeded",
                        "error": str(e)[:200],
                    },
                    confidence=0.0,
                )
                self.db.clear_rule_failures(email.id)
                return ProcessResult(
                    message_id=email.id,
                    success=False,
                    error=f"Failed after {failure_count} attempts: {e}",
                    rule_matched=rule.name,
                )

            else:
                # Transient or unknown error - will retry on next scan
                logger.error(
                    f"Quick rule \"{rule.name}\" failed "
                    f"(attempt {failure_count}/{max_retries}): {e}"
                )
                return ProcessResult(
                    message_id=email.id,
                    success=False,
                    error=str(e),
                    rule_matched=rule.name,
                )

    def _print_result(self, email: EmailMessage, result: ProcessResult, verbose: int) -> None:
        """Print processing result based on verbosity level."""
        if verbose == 1:
            self._print_result_compact(email, result)
        elif verbose == 2:
            self._print_result_detailed(email, result)
        elif verbose >= 3:
            self._print_result_debug(email, result)

    def _format_action(self, result: ProcessResult) -> str:
        """Format action with optional folder: 'MOVE (Marketing)' or just 'ARCHIVE'."""
        if not result.action:
            return "UNKNOWN"
        action_upper = result.action.upper()
        if result.target_folder:
            return f"{action_upper} ({result.target_folder})"
        return action_upper

    def _get_error_reason(self, error: str | None) -> str:
        """Extract a brief human-readable reason from an error message."""
        if not error:
            return "Failed"

        error_lower = error.lower()

        # Message not found (deleted during processing)
        if "-1719" in error or "invalid index" in error_lower:
            return "Msg not found"

        # Authentication errors
        if (
            "authenticationerror" in error_lower
            or "401" in error
            or "invalid x-api-key" in error_lower
        ):
            return "Auth failed"

        # AI classification errors
        if "ai classification failed" in error_lower:
            return "AI error"

        # Timeouts
        if "timeout" in error_lower:
            return "Timeout"

        # Rate limiting
        if "ratelimiterror" in error_lower or "429" in error:
            return "Rate limited"

        # Mailbox not found
        if "mailbox" in error_lower and "doesn't exist" in error_lower:
            return "Folder missing"

        return "Failed"

    def _print_result_compact(self, email: EmailMessage, result: ProcessResult) -> None:
        """Print compact one-liner for -v mode."""
        # Build prefix: [RULE] if matched, empty otherwise
        prefix = "[cyan][RULE][/cyan] " if result.rule_matched else ""

        # Truncate subject for second line
        subject_short = email.subject[:50] + "..." if len(email.subject) > 50 else email.subject

        if result.skipped:
            console.print(f"  {prefix}[dim]SKIP[/dim] {email.sender}")
            console.print(f"    {subject_short}")
        elif result.queued:
            console.print(f"  {prefix}[yellow]QUEUE[/yellow] {email.sender}")
            console.print(f"    {subject_short}")
        elif result.success:
            console.print(f"  {prefix}[green]{self._format_action(result)}[/green] {email.sender}")
            console.print(f"    {subject_short}")
        else:
            reason = self._get_error_reason(result.error)
            console.print(f"  {prefix}[red]ERROR[/red] [dim]({reason})[/dim] {email.sender}")
            console.print(f"    {subject_short}")

    def _print_result_detailed(self, email: EmailMessage, result: ProcessResult) -> None:
        """Print detailed output for -vv mode (includes reason/error)."""
        prefix = "[cyan][RULE][/cyan] " if result.rule_matched else ""
        subject_short = email.subject[:50] + "..." if len(email.subject) > 50 else email.subject

        if result.skipped:
            console.print(f"  {prefix}[dim]SKIP[/dim] {email.sender}")
            console.print(f"    {subject_short}")
            if result.reason:
                console.print(f"        [dim]{result.reason}[/dim]")
        elif result.queued:
            console.print(f"  {prefix}[yellow]QUEUE[/yellow] {email.sender}")
            console.print(f"    {subject_short}")
            if result.reason:
                console.print(f"        [dim]{result.reason}[/dim]")
        elif result.success:
            console.print(f"  {prefix}[green]{self._format_action(result)}[/green] {email.sender}")
            console.print(f"    {subject_short}")
            if result.reason:
                console.print(f"        [dim]{result.reason}[/dim]")
        else:
            console.print(f"  {prefix}[red]ERROR[/red] {email.sender}")
            console.print(f"    {subject_short}")
            if result.error:
                console.print(f"        [red]{result.error}[/red]")

    def _print_result_debug(self, email: EmailMessage, result: ProcessResult) -> None:
        """Print debug output for -vvv mode (includes all metadata)."""
        prefix = "[cyan][RULE][/cyan] " if result.rule_matched else ""
        subject_short = email.subject[:50] + "..." if len(email.subject) > 50 else email.subject

        if result.skipped:
            console.print(f"  {prefix}[dim]SKIP[/dim] {email.sender}")
        elif result.queued:
            console.print(f"  {prefix}[yellow]QUEUE[/yellow] {email.sender}")
        elif result.success:
            console.print(f"  {prefix}[green]{self._format_action(result)}[/green] {email.sender}")
        else:
            console.print(f"  {prefix}[red]ERROR[/red] {email.sender}")

        console.print(f"    {subject_short}")

        # Show reason or error
        if result.reason:
            console.print(f"        [dim]{result.reason}[/dim]")
        if result.error:
            console.print(f"        [red]{result.error}[/red]")

        # Debug metadata
        console.print(f"        [dim]ID: {email.id[:12]}...[/dim]")
        console.print(f"        [dim]Account: {email.account} / {email.mailbox}[/dim]")
        if email.date_received:
            console.print(f"        [dim]Date: {email.date_received.strftime('%Y-%m-%d %H:%M')}[/dim]")
        if result.rule_matched:
            console.print(f"        [dim]Matched rule: {result.rule_matched}[/dim]")

    # ─── Inbox Aging ─────────────────────────────────────────────────────

    async def _run_aging_checks(
        self,
        dry_run: bool,
        verbose: int,
    ) -> AgingResult:
        """Run inbox aging checks: move stale emails, delete expired reviews."""
        from email_nurse.mail.messages import get_message_by_id

        result = AgingResult()
        target_account = self.config.main_account or ""

        if verbose >= 1:
            console.print("\n[bold]Checking inbox aging...[/bold]")

        # Phase 1: Move stale INBOX emails to Needs Review
        stale_emails = self.db.get_stale_inbox_emails(self.config.inbox_stale_days)

        for email_info in stale_emails:
            try:
                # Fetch the email to verify it still exists in INBOX
                email = get_message_by_id(email_info["message_id"])
                if not email:
                    # Email no longer exists, clean up tracking
                    self.db.remove_first_seen(email_info["message_id"])
                    continue

                # Check if still in INBOX (might have been moved by user)
                if email.mailbox.upper() != "INBOX":
                    self.db.remove_first_seen(email_info["message_id"])
                    continue

                if dry_run:
                    if verbose >= 1:
                        subject_short = email.subject[:40] + "..." if len(email.subject) > 40 else email.subject
                        console.print(f"  [dim][AGING][/dim] [yellow]→ {self.config.needs_review_folder}[/yellow] {subject_short}")
                    result.moved_to_review += 1
                    continue

                # Ensure Needs Review folder exists
                if self.config.needs_review_folder.lower() not in [m.lower() for m in self.mailbox_cache]:
                    try:
                        create_mailbox(self.config.needs_review_folder, target_account)
                        self.mailbox_cache.append(self.config.needs_review_folder)
                        # Clear disk cache so it refetches all mailboxes next run
                        self.db.clear_mailbox_cache(target_account)
                    except Exception as e:
                        if verbose >= 1:
                            console.print(f"  [red]Failed to create {self.config.needs_review_folder}:[/red] {e}")
                        result.errors += 1
                        continue

                # Move to Needs Review
                move_message(
                    email.id,
                    self.config.needs_review_folder,
                    target_account,
                    source_mailbox=email.mailbox,
                    source_account=email.account,
                )

                # Update tracking - email is now in Needs Review, remove from first-seen
                self.db.remove_first_seen(email.id)

                # Log the action
                self.db.log_action(
                    message_id=email.id,
                    action="aging_move",
                    source="aging",
                    details={"target_folder": self.config.needs_review_folder},
                )

                result.moved_to_review += 1

                if verbose >= 1:
                    subject_short = email.subject[:40] + "..." if len(email.subject) > 40 else email.subject
                    console.print(f"  [dim][AGING][/dim] [yellow]MOVE ({self.config.needs_review_folder})[/yellow] {subject_short}")

            except Exception as e:
                if verbose >= 1:
                    console.print(f"  [red]Aging error:[/red] {e}")
                result.errors += 1

        # Phase 2: Delete emails that have been in Needs Review too long
        # We need to check emails in the Needs Review folder directly
        try:
            needs_review_emails = get_messages(
                mailbox=self.config.needs_review_folder,
                account=target_account,
                limit=100,
                unread_only=False,
            )

            cutoff = datetime.now() - timedelta(days=self.config.needs_review_retention_days)

            for email in needs_review_emails:
                if email.date_received and email.date_received < cutoff:
                    try:
                        if dry_run:
                            if verbose >= 1:
                                subject_short = email.subject[:40] + "..." if len(email.subject) > 40 else email.subject
                                console.print(f"  [dim][AGING][/dim] [red]DELETE[/red] {subject_short}")
                            result.deleted_from_review += 1
                            continue

                        delete_message(
                            email.id,
                            permanent=False,  # Soft delete to Trash
                            source_mailbox=self.config.needs_review_folder,
                            source_account=target_account,
                        )

                        self.db.log_action(
                            message_id=email.id,
                            action="aging_delete",
                            source="aging",
                            details={"from_folder": self.config.needs_review_folder},
                        )

                        result.deleted_from_review += 1

                        if verbose >= 1:
                            subject_short = email.subject[:40] + "..." if len(email.subject) > 40 else email.subject
                            console.print(f"  [dim][AGING][/dim] [red]DELETE[/red] {subject_short}")

                    except Exception as e:
                        if verbose >= 1:
                            console.print(f"  [red]Aging delete error:[/red] {e}")
                        result.errors += 1

        except Exception:
            # Needs Review folder might not exist yet, that's fine
            pass

        # Phase 3: Apply folder retention rules
        for rule in self.config.folder_retention_rules:
            rule_account = rule.account or target_account
            try:
                folder_emails = get_messages(
                    mailbox=rule.folder,
                    account=rule_account,
                    limit=100,
                    unread_only=False,
                )

                retention_cutoff = datetime.now() - timedelta(days=rule.retention_days)

                for email in folder_emails:
                    if email.date_received and email.date_received < retention_cutoff:
                        try:
                            if dry_run:
                                if verbose >= 1:
                                    subject_short = email.subject[:40] + "..." if len(email.subject) > 40 else email.subject
                                    console.print(f"  [dim][RETENTION][/dim] [red]DELETE[/red] ({rule.folder}, {rule.retention_days}d) {subject_short}")
                                result.retention_deleted += 1
                                continue

                            delete_message(
                                email.id,
                                permanent=False,  # Soft delete to Trash
                                source_mailbox=rule.folder,
                                source_account=rule_account,
                            )

                            self.db.log_action(
                                message_id=email.id,
                                action="retention_delete",
                                source="retention",
                                details={"from_folder": rule.folder, "retention_days": rule.retention_days},
                            )

                            result.retention_deleted += 1

                            if verbose >= 1:
                                subject_short = email.subject[:40] + "..." if len(email.subject) > 40 else email.subject
                                console.print(f"  [dim][RETENTION][/dim] [red]DELETE[/red] ({rule.folder}, {rule.retention_days}d) {subject_short}")

                        except Exception as e:
                            if verbose >= 1:
                                console.print(f"  [red]Retention delete error:[/red] {e}")
                            result.errors += 1

            except Exception:
                # Folder might not exist yet, that's fine
                pass

        if verbose >= 1 and (result.moved_to_review > 0 or result.deleted_from_review > 0 or result.retention_deleted > 0):
            console.print(f"  Aging: {result.moved_to_review} moved, {result.deleted_from_review} deleted, {result.retention_deleted} retention purged")

        return result

    async def execute_pending_action(self, action_id: int) -> ProcessResult:
        """Execute a pending action that was queued for approval."""
        pending = self.db.get_pending_action(action_id)
        if not pending:
            return ProcessResult(
                message_id="unknown",
                success=False,
                error="Pending action not found",
            )

        # Get the email
        from email_nurse.mail.messages import get_message_by_id

        email = get_message_by_id(pending["message_id"])
        if not email:
            self.db.update_pending_status(action_id, "rejected")
            return ProcessResult(
                message_id=pending["message_id"],
                success=False,
                error="Email no longer exists",
            )

        # Reconstruct the decision
        decision = AutopilotDecision(**pending["proposed_action"])

        # Execute with interactive=True since user is actively approving
        result = await self._execute_action(email, decision, dry_run=False, interactive=True)

        # Update pending status
        if result.success:
            self.db.update_pending_status(action_id, "approved")
        else:
            self.db.update_pending_status(action_id, "rejected")

        return result
