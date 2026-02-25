"""Output formatting mixin for autopilot engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from email_nurse.autopilot.models import ProcessResult
    from email_nurse.mail.messages import EmailMessage

console = Console()


class OutputFormatterMixin:
    """Mixin providing display/output methods for autopilot results."""

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
