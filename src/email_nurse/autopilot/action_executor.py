"""Action execution mixin for autopilot engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from email_nurse.logging import get_account_logger

from email_nurse.ai.base import EmailAction
from email_nurse.autopilot.models import ProcessResult
from email_nurse.mail.actions import (
    LOCAL_ACCOUNT_KEY,
    PendingMove,
    delete_message,
    flag_message,
    forward_message,
    mark_as_read,
    move_message,
    move_messages_batch,
    reply_to_message,
)

if TYPE_CHECKING:
    from email_nurse.autopilot.models import AutopilotDecision
    from email_nurse.mail.messages import EmailMessage

console = Console()


class ActionExecutorMixin:
    """Mixin providing action execution, batch moves, and mark-processed logic."""

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
                "folder": decision.target_folder,
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
