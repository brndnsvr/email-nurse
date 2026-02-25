"""Folder management mixin for autopilot engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from email_nurse.logging import get_account_logger, get_error_logger
from email_nurse.applescript.notifications import notify_pending_folders

from email_nurse.mail.actions import (
    LOCAL_ACCOUNT_KEY,
    create_local_mailbox,
    create_mailbox,
    find_similar_mailbox,
    get_all_mailboxes,
    get_local_mailboxes,
)
from email_nurse.mail.accounts import get_accounts

if TYPE_CHECKING:
    from email_nurse.autopilot.models import AutopilotDecision, ProcessResult
    from email_nurse.mail.messages import EmailMessage

console = Console()


class FolderManagerMixin:
    """Mixin providing folder validation, caching, and resolution."""

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
        email: "EmailMessage",
        decision: "AutopilotDecision",
        interactive: bool,
        auto_create: bool = False,
    ) -> "ProcessResult | None":
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
        from email_nurse.autopilot.models import ProcessResult

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
