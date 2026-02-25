"""Quick rules mixin for autopilot engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from email_nurse.logging import get_account_logger

from email_nurse.ai.base import EmailAction
from email_nurse.autopilot.config import QuickRule
from email_nurse.autopilot.models import AutopilotDecision, ProcessResult
from email_nurse.mail.actions import (
    LOCAL_ACCOUNT_KEY,
    delete_message,
    mark_as_read,
)
from email_nurse.mail.messages import load_message_content, load_message_headers

if TYPE_CHECKING:
    from email_nurse.mail.messages import EmailMessage

console = Console()


class QuickRulesMixin:
    """Mixin providing pre-AI quick rule matching and execution."""

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
