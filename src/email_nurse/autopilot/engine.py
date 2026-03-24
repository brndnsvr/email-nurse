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

from email_nurse.autopilot.output import OutputFormatterMixin
from email_nurse.autopilot.folder_manager import FolderManagerMixin
from email_nurse.autopilot.aging import AgingMixin
from email_nurse.autopilot.action_executor import ActionExecutorMixin
from email_nurse.autopilot.quick_rules import QuickRulesMixin

if TYPE_CHECKING:
    from email_nurse.ai.base import AIProvider
    from email_nurse.config import Settings

console = Console()


class AutopilotEngine(
    QuickRulesMixin,
    ActionExecutorMixin,
    FolderManagerMixin,
    AgingMixin,
    OutputFormatterMixin,
):
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

    def _build_known_folders_context(self) -> str:
        """Build a list of known folder names for AI category/folder consistency.

        Collects folder names from quick rules and the mailbox cache so the AI
        uses exact, canonical folder names instead of inventing variations.

        Returns:
            String listing known folders, or empty if none available.
        """
        folders: set[str] = set()

        # Collect from quick rules
        for rule in self.config.quick_rules:
            if rule.folder:
                folders.add(rule.folder)

        # Collect from mailbox cache
        if self.mailbox_cache:
            folders.update(self.mailbox_cache)

        if not folders:
            return ""

        sorted_folders = sorted(folders)
        return (
            "\n\n## KNOWN FOLDERS (use these exact names for target_folder and category)\n"
            + ", ".join(sorted_folders)
        )

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

        # Reset caches (rebuilt on first fetch)
        for attr in ("_validated_accounts_cache", "_email_queue"):
            if hasattr(self, attr):
                delattr(self, attr)

        # Load mailbox cache for folder checking
        self._load_mailbox_cache()

        result = AutopilotRunResult(
            started_at=started_at,
            completed_at=started_at,  # Updated at end
            emails_fetched=0,
            dry_run=dry_run,
        )

        # Process one email at a time: fetch one, act on it, fetch next.
        # After each action (move/delete), the inbox changes so the next
        # fetch reflects reality. No need to bulk-load metadata upfront.
        chunk_size = self.settings.autopilot_chunk_size
        chunk_sleep = self.settings.autopilot_chunk_sleep
        processed_in_chunk = 0
        printed_header = False

        for _ in range(batch_size):
            email = await self._get_next_unprocessed_email()
            if email is None:
                break

            result.emails_fetched += 1

            if not printed_header and verbose >= 1:
                console.print(f"\n[bold]Processing emails...[/bold]\n")
                printed_header = True

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

            # Flush moves at chunk boundary and clear queue so next
            # fetch reflects the updated inbox state
            if processed_in_chunk >= chunk_size:
                if not dry_run:
                    self._flush_pending_moves(verbose)
                    self._email_queue = []
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

    def _resolve_accounts(self) -> None:
        """Resolve and cache validated account/mailbox names (once per run)."""
        if hasattr(self, "_validated_accounts_cache"):
            return

        if self.config.accounts:
            raw_accounts = self.config.accounts
        else:
            try:
                all_accts = get_accounts()
                raw_accounts = [a.name for a in all_accts if a.enabled]
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to get accounts:[/yellow] {e}")
                raw_accounts = []

        validated = []
        for account in raw_accounts:
            try:
                validated_name = self._validate_account_name(account)
                if validated_name != account:
                    console.print(
                        f"[dim]Note: Using '{validated_name}' "
                        f"(matched from '{account}')[/dim]"
                    )
                validated.append(validated_name)
            except ValueError as e:
                console.print(f"[red]Error: {e}[/red]")
        self._validated_accounts_cache = validated

        self._validated_mailboxes_cache: dict[tuple[str, str], str | None] = {}
        for mailbox in self.config.mailboxes:
            for acct in validated:
                actual = self._validate_mailbox_name(mailbox, acct)
                if actual is None:
                    console.print(
                        f"[yellow]Warning: Mailbox '{mailbox}' not found "
                        f"in account '{acct}', skipping[/yellow]"
                    )
                elif actual != mailbox:
                    console.print(
                        f"[dim]Note: Using '{actual}' "
                        f"(matched from '{mailbox}') for {acct}[/dim]"
                    )
                self._validated_mailboxes_cache[(mailbox, acct)] = actual

    async def _get_next_unprocessed_email(self) -> EmailMessage | None:
        """Return the next unprocessed email, fetching from Mail.app as needed.

        Uses a cached queue: fetches a small metadata batch, filters to
        unprocessed, and pops one at a time. Only re-fetches when the
        queue is empty — so one sysm call serves multiple emails.
        """
        self._resolve_accounts()

        # Pop from cache if available
        if hasattr(self, "_email_queue") and self._email_queue:
            return self._email_queue.pop(0)

        # Cache empty — fetch a fresh batch
        processed_ids = self.db.get_processed_ids(limit=10000)
        cutoff_date = datetime.now() - timedelta(days=self.config.max_age_days)
        accounts = self._validated_accounts_cache
        queue: list[EmailMessage] = []

        for mailbox in self.config.mailboxes:
            for account in accounts:
                actual_mailbox = self._validated_mailboxes_cache.get((mailbox, account))
                if actual_mailbox is None:
                    continue

                try:
                    logger = get_account_logger(account)
                    logger.info(f"Fetching up to 20 emails from {actual_mailbox}")
                    messages = get_messages_metadata(
                        mailbox=actual_mailbox,
                        account=account,
                        limit=20,
                        unread_only=False,
                    )
                    logger.info(f"Fetched {len(messages)} emails from {actual_mailbox}")

                    for msg in messages:
                        if msg.mailbox in VIRTUAL_MAILBOXES or msg.mailbox.startswith("[Gmail]"):
                            msg.mailbox = actual_mailbox

                        if msg.id in processed_ids or msg.id in self._processed_this_run:
                            continue
                        if msg.date_received and msg.date_received < cutoff_date:
                            continue
                        if self._is_excluded(msg):
                            continue

                        queue.append(msg)

                except Exception as e:
                    logger = get_account_logger(account)
                    logger.error(f"Failed to fetch from {actual_mailbox}: {e}")
                    console.print(
                        f"[yellow]Warning: Failed to fetch from {actual_mailbox}"
                        f"{f' ({account})' if account else ''}:[/yellow] {e}"
                    )

        # Sort newest first across all accounts
        queue.sort(key=lambda e: e.date_received or datetime.min, reverse=True)
        self._email_queue = queue

        if queue:
            return self._email_queue.pop(0)
        return None

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
            # Build enriched instructions with PIM context and known folders
            enriched_instructions = self.config.instructions
            pim_context = self._build_pim_context()
            if pim_context:
                enriched_instructions = f"{self.config.instructions}\n{pim_context}"
            folders_context = self._build_known_folders_context()
            if folders_context:
                enriched_instructions = f"{enriched_instructions}\n{folders_context}"

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
