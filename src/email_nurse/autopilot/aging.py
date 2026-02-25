"""Inbox aging mixin for autopilot engine."""

from __future__ import annotations

from datetime import datetime, timedelta

from rich.console import Console

from email_nurse.mail.actions import (
    create_mailbox,
    delete_message,
    move_message,
)
from email_nurse.mail.messages import get_messages

from email_nurse.autopilot.models import AgingResult

console = Console()


class AgingMixin:
    """Mixin providing inbox aging and retention logic."""

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
