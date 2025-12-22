"""Autopilot engine for AI-native email processing."""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Console

from email_nurse.ai.base import EmailAction
from email_nurse.autopilot.config import AutopilotConfig
from email_nurse.autopilot.models import (
    AutopilotDecision,
    AutopilotRunResult,
    LowConfidenceAction,
    OutboundPolicy,
    ProcessResult,
)
from email_nurse.mail.actions import (
    VIRTUAL_MAILBOXES,
    delete_message,
    flag_message,
    forward_message,
    mark_as_read,
    move_message,
    reply_to_message,
)
from email_nurse.mail.messages import EmailMessage, get_messages
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

    async def run(
        self,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        verbose: bool = False,
    ) -> AutopilotRunResult:
        """
        Run autopilot processing on emails.

        Args:
            dry_run: If True, don't execute actions, just show what would happen.
            limit: Maximum emails to process (overrides settings).
            verbose: Show detailed output.

        Returns:
            AutopilotRunResult with summary statistics.
        """
        started_at = datetime.now()
        batch_size = limit or self.settings.autopilot_batch_size

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

        if verbose:
            console.print(f"\n[bold]Processing {len(emails)} emails...[/bold]\n")

        # Process each email
        for email in emails:
            try:
                process_result = await self._process_email(email, dry_run=dry_run)

                if process_result.skipped:
                    result.emails_skipped += 1
                elif process_result.queued:
                    result.actions_queued += 1
                    result.emails_processed += 1
                elif process_result.success:
                    result.actions_executed += 1
                    result.emails_processed += 1
                else:
                    result.errors += 1

                if verbose:
                    self._print_result(email, process_result)

                # Rate limiting
                if self.settings.autopilot_rate_limit_delay > 0:
                    await asyncio.sleep(self.settings.autopilot_rate_limit_delay)

            except Exception as e:
                result.errors += 1
                if verbose:
                    console.print(f"[red]Error processing {email.subject[:40]}:[/red] {e}")

        result.completed_at = datetime.now()
        return result

    async def _get_unprocessed_emails(self, limit: int) -> list[EmailMessage]:
        """Get emails that haven't been processed yet."""
        from email_nurse.mail.accounts import get_accounts

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

        for mailbox in self.config.mailboxes:
            for account in accounts:
                try:
                    # Fetch extra to account for filtering, but cap at 100 to avoid timeout
                    # (AppleScript is slow - ~1s per message with content)
                    fetch_limit = min(limit * 3, 100)
                    messages = get_messages(
                        mailbox=mailbox,
                        account=account,
                        limit=fetch_limit,
                        unread_only=False,  # Process ALL emails
                    )
                    # Override mailbox with the one we queried (Gmail reports "All Mail"
                    # for everything, but we need the actual mailbox for lookups)
                    for msg in messages:
                        if msg.mailbox in VIRTUAL_MAILBOXES or msg.mailbox.startswith("[Gmail]"):
                            msg.mailbox = mailbox
                    all_emails.extend(messages)
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Failed to fetch from {mailbox}"
                        f"{f' ({account})' if account else ''}:[/yellow] {e}"
                    )

        # Sort by date (newest first) to prioritize recent emails
        all_emails.sort(key=lambda e: e.date_received or datetime.min, reverse=True)

        # Filter out already processed and apply age filter
        unprocessed = []
        for email in all_emails:
            # Skip if already processed
            if email.id in processed_ids:
                continue

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
    ) -> ProcessResult:
        """Process a single email through autopilot."""
        # Get AI decision
        try:
            decision = await self.ai.autopilot_classify(email, self.config.instructions)
        except Exception as e:
            return ProcessResult(
                message_id=email.id,
                success=False,
                error=str(e),
            )

        # Check confidence threshold
        if decision.confidence < self.settings.confidence_threshold:
            return await self._handle_low_confidence(email, decision, dry_run)

        # Check outbound policy
        if decision.is_outbound:
            return await self._handle_outbound(email, decision, dry_run)

        # Execute the action
        return await self._execute_action(email, decision, dry_run)

    async def _handle_low_confidence(
        self,
        email: EmailMessage,
        decision: AutopilotDecision,
        dry_run: bool,
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
                        proposed_action=decision.model_dump(),
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
                        proposed_action=decision.model_dump(),
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
                    return await self._execute_action(email, decision, dry_run)
                else:
                    if not dry_run:
                        self.db.add_pending_action(
                            message_id=email.id,
                            email_summary=f"{email.sender}: {email.subject[:50]}",
                            proposed_action=decision.model_dump(),
                            confidence=decision.confidence,
                            reasoning=f"[Outbound low confidence] {decision.reasoning}",
                        )
                    return ProcessResult(
                        message_id=email.id,
                        queued=True,
                        reason=f"Outbound confidence ({decision.confidence:.0%}) below threshold",
                    )

            case OutboundPolicy.FULL_AUTOPILOT:
                return await self._execute_action(email, decision, dry_run)

        return ProcessResult(message_id=email.id, skipped=True, reason="Unknown policy")

    async def _execute_action(
        self,
        email: EmailMessage,
        decision: AutopilotDecision,
        dry_run: bool,
    ) -> ProcessResult:
        """Execute the decided action."""
        action_name = decision.action.value

        if dry_run:
            return ProcessResult(
                message_id=email.id,
                success=True,
                action=f"[dry-run] {action_name}",
                reason=decision.reasoning,
            )

        # Determine target account for move operations
        # If main_account is set, all moves go there; otherwise use source account
        target_account = self.config.main_account or email.account

        try:
            match decision.action:
                case EmailAction.MOVE:
                    if decision.target_folder:
                        move_message(
                            email.id,
                            decision.target_folder,
                            target_account,
                            source_mailbox=email.mailbox,
                            source_account=email.account,
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
                    move_message(
                        email.id,
                        "Archive",
                        target_account,
                        source_mailbox=email.mailbox,
                        source_account=email.account,
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

            # Mark as processed and log
            self._mark_processed(email, decision)

            return ProcessResult(
                message_id=email.id,
                success=True,
                action=action_name,
                reason=decision.reasoning,
            )

        except Exception as e:
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
            subject=email.subject[:100],
            sender=email.sender[:100],
            action=decision.model_dump(),
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
            },
        )

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

    def _print_result(self, email: EmailMessage, result: ProcessResult) -> None:
        """Print processing result for verbose mode."""
        subject_short = email.subject[:50] + "..." if len(email.subject) > 50 else email.subject

        if result.skipped:
            console.print(f"  [dim]SKIP[/dim] {subject_short}")
            if result.reason:
                console.print(f"       [dim]{result.reason}[/dim]")
        elif result.queued:
            console.print(f"  [yellow]QUEUE[/yellow] {subject_short}")
            if result.reason:
                console.print(f"        [dim]{result.reason}[/dim]")
        elif result.success:
            console.print(f"  [green]{result.action.upper()}[/green] {subject_short}")
            if result.reason:
                console.print(f"        [dim]{result.reason}[/dim]")
        else:
            console.print(f"  [red]ERROR[/red] {subject_short}")
            if result.error:
                console.print(f"        [red]{result.error}[/red]")

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

        # Execute
        result = await self._execute_action(email, decision, dry_run=False)

        # Update pending status
        if result.success:
            self.db.update_pending_status(action_id, "approved")
        else:
            self.db.update_pending_status(action_id, "rejected")

        return result
