"""Autopilot engine for AI-native email processing."""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Console

from email_nurse.ai.base import EmailAction
from email_nurse.autopilot.config import AutopilotConfig, QuickRule
from email_nurse.autopilot.models import (
    AutopilotDecision,
    AutopilotRunResult,
    LowConfidenceAction,
    OutboundPolicy,
    ProcessResult,
)
from email_nurse.mail.actions import (
    VIRTUAL_MAILBOXES,
    create_mailbox,
    delete_message,
    find_similar_mailbox,
    flag_message,
    forward_message,
    get_all_mailboxes,
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
        self.mailbox_cache: list[str] = []
        self._cache_loaded = False

    def _load_mailbox_cache(self) -> None:
        """Load mailbox names from disk cache or Mail.app."""
        if self._cache_loaded:
            return
        if not self.config.main_account:
            self._cache_loaded = True
            return

        # Try disk cache first
        cached = self.db.get_cached_mailboxes(
            self.config.main_account,
            self.settings.mailbox_cache_ttl_minutes,
        )
        if cached is not None:
            self.mailbox_cache = cached
            self._cache_loaded = True
            return

        # Cache miss or expired - fetch from Mail.app and store
        try:
            self.mailbox_cache = get_all_mailboxes(self.config.main_account)
            self.db.set_cached_mailboxes(self.config.main_account, self.mailbox_cache)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load mailboxes:[/yellow] {e}")
            self.mailbox_cache = []
        self._cache_loaded = True

    async def run(
        self,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        verbose: bool = False,
        interactive: bool = False,
    ) -> AutopilotRunResult:
        """
        Run autopilot processing on emails.

        Args:
            dry_run: If True, don't execute actions, just show what would happen.
            limit: Maximum emails to process (overrides settings).
            verbose: Show detailed output.
            interactive: If True, prompt for folder creation. If False, queue for later.

        Returns:
            AutopilotRunResult with summary statistics.
        """
        started_at = datetime.now()
        batch_size = limit or self.settings.autopilot_batch_size

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

        if verbose:
            console.print(f"\n[bold]Processing {len(emails)} emails...[/bold]\n")

        # Process each email
        for email in emails:
            try:
                process_result = await self._process_email(
                    email, dry_run=dry_run, interactive=interactive
                )

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
        interactive: bool = False,
    ) -> ProcessResult:
        """Process a single email through autopilot."""
        # Try quick rules first (instant, no API cost)
        quick_result = self._apply_quick_rules(email, dry_run, interactive)
        if quick_result is not None:
            return quick_result

        # No quick rule matched - use AI
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
            return await self._handle_low_confidence(email, decision, dry_run, interactive)

        # Check outbound policy
        if decision.is_outbound:
            return await self._handle_outbound(email, decision, dry_run, interactive)

        # Execute the action
        return await self._execute_action(email, decision, dry_run, interactive)

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
                    return await self._execute_action(email, decision, dry_run, interactive)
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
        target_account: str,
        email: EmailMessage,
        decision: AutopilotDecision,
        interactive: bool,
    ) -> ProcessResult | None:
        """
        Check if folder exists and handle missing folders.

        Returns:
            - None if folder exists or was created (continue with action)
            - ProcessResult if action should be queued or skipped
        """
        # Check if folder exists in cache (case-insensitive)
        folder_exists = any(
            f.lower() == target_folder.lower() for f in self.mailbox_cache
        )

        if folder_exists:
            return None  # Continue with action

        # Folder doesn't exist - find similar
        similar = find_similar_mailbox(target_folder, self.mailbox_cache)

        if interactive:
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
                    create_mailbox(chosen_folder, target_account)
                    self.mailbox_cache.append(chosen_folder)
                    # Update disk cache too
                    self.db.set_cached_mailboxes(target_account, self.mailbox_cache)
                    console.print(f"        [green]✓ Created \"{chosen_folder}\"[/green]")
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
            # Autonomous mode - queue for later review
            self.db.add_pending_action(
                message_id=email.id,
                email_summary=f"{email.sender}: {email.subject[:50]}",
                proposed_action=decision.model_dump(),
                confidence=decision.confidence,
                reasoning=(
                    f"[Folder missing] \"{target_folder}\" doesn't exist"
                    + (f" (similar: \"{similar}\")" if similar else "")
                    + f" - {decision.reasoning}"
                ),
            )
            return ProcessResult(
                message_id=email.id,
                queued=True,
                reason=f"Folder \"{target_folder}\" doesn't exist",
            )

    async def _execute_action(
        self,
        email: EmailMessage,
        decision: AutopilotDecision,
        dry_run: bool,
        interactive: bool = False,
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
        # If main_account is set, all moves go there; otherwise use source account
        target_account = self.config.main_account or email.account

        try:
            match decision.action:
                case EmailAction.MOVE:
                    if decision.target_folder:
                        # Check if folder exists and handle if not
                        result = self._resolve_folder(
                            decision.target_folder,
                            target_account,
                            email,
                            decision,
                            interactive,
                        )
                        if result is not None:
                            return result  # Queued or skipped

                        # Folder resolved - execute move
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
                    # Check if Archive folder exists
                    result = self._resolve_folder(
                        "Archive",
                        target_account,
                        email,
                        decision,
                        interactive,
                    )
                    if result is not None:
                        return result  # Queued or skipped

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
                target_folder=result_folder,
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

    # ─── Quick Rules (Pre-AI) ─────────────────────────────────────────────

    def _apply_quick_rules(
        self,
        email: EmailMessage,
        dry_run: bool,
        interactive: bool,
    ) -> ProcessResult | None:
        """
        Apply quick rules before AI classification.

        Returns:
            ProcessResult if a rule matched, None to continue to AI.
        """
        for rule in self.config.quick_rules:
            if self._matches_rule(email, rule):
                return self._execute_quick_rule(email, rule, dry_run, interactive)
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

        return True

    def _execute_quick_rule(
        self,
        email: EmailMessage,
        rule: QuickRule,
        dry_run: bool,
        interactive: bool,
    ) -> ProcessResult:
        """Execute a matched quick rule."""
        action_name = rule.action
        # Track target folder for move/archive actions
        result_folder: str | None = None
        if rule.action == "move":
            result_folder = rule.folder
        elif rule.action == "archive":
            result_folder = "Archive"

        if dry_run:
            return ProcessResult(
                message_id=email.id,
                success=True,
                action=f"[dry-run] {action_name}",
                target_folder=result_folder,
                reason=f"Rule: {rule.name}",
                rule_matched=rule.name,
            )

        target_account = self.config.main_account or email.account

        try:
            match rule.action:
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
                        )
                        if result is not None:
                            result.rule_matched = rule.name
                            return result

                        move_message(
                            email.id,
                            rule.folder,
                            target_account,
                            source_mailbox=email.mailbox,
                            source_account=email.account,
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
                    )
                    if result is not None:
                        result.rule_matched = rule.name
                        return result

                    move_message(
                        email.id,
                        "Archive",
                        target_account,
                        source_mailbox=email.mailbox,
                        source_account=email.account,
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

            # Mark as processed
            self.db.mark_processed(
                message_id=email.id,
                mailbox=email.mailbox,
                account=email.account,
                subject=email.subject[:100],
                sender=email.sender[:100],
                action={"rule": rule.name, "action": rule.action},
                confidence=1.0,
            )

            self.db.log_action(
                message_id=email.id,
                action=rule.action,
                source=f"rule:{rule.name}",
                details={"rule_name": rule.name, "folder": rule.folder},
            )

            return ProcessResult(
                message_id=email.id,
                success=True,
                action=action_name,
                target_folder=result_folder,
                reason=f"Rule: {rule.name}",
                rule_matched=rule.name,
            )

        except Exception as e:
            return ProcessResult(
                message_id=email.id,
                success=False,
                error=str(e),
                rule_matched=rule.name,
            )

    def _print_result(self, email: EmailMessage, result: ProcessResult) -> None:
        """Print processing result for verbose mode."""
        subject_short = email.subject[:50] + "..." if len(email.subject) > 50 else email.subject

        # Determine source prefix: [RULE] or nothing (AI-classified)
        source_prefix = "[cyan][RULE][/cyan] " if result.rule_matched else ""

        # Format action with optional folder: "MOVE (Marketing)" or just "ARCHIVE"
        def format_action(action: str | None) -> str:
            if not action:
                return "UNKNOWN"
            action_upper = action.upper()
            if result.target_folder:
                return f"{action_upper} ({result.target_folder})"
            return action_upper

        if result.skipped:
            console.print(f"  {source_prefix}[dim]SKIP[/dim] {subject_short}")
            if result.reason:
                console.print(f"        [dim]{result.reason}[/dim]")
        elif result.queued:
            console.print(f"  {source_prefix}[yellow]QUEUE[/yellow] {subject_short}")
            if result.reason:
                console.print(f"        [dim]{result.reason}[/dim]")
        elif result.success:
            console.print(f"  {source_prefix}[green]{format_action(result.action)}[/green] {subject_short}")
            if result.reason:
                console.print(f"        [dim]{result.reason}[/dim]")
        else:
            console.print(f"  {source_prefix}[red]ERROR[/red] {subject_short}")
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

        # Execute with interactive=True since user is actively approving
        result = await self._execute_action(email, decision, dry_run=False, interactive=True)

        # Update pending status
        if result.success:
            self.db.update_pending_status(action_id, "approved")
        else:
            self.db.update_pending_status(action_id, "rejected")

        return result
