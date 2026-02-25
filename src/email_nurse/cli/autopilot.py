"""Autopilot mode CLI commands."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from email_nurse.cli import autopilot_app, console, get_settings


@autopilot_app.command("run")
def autopilot_run(
    once: Annotated[bool, typer.Option("--once", help="Run once then exit")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Don't execute actions (test mode)")] = False,
    limit: Annotated[int | None, typer.Option("--limit", "-l", help="Max emails per batch")] = None,
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True, help="Verbosity: -v compact, -vv detailed, -vvv debug")] = 0,
    provider: Annotated[str | None, typer.Option("--provider", "-p", help="AI provider (default from settings)")] = None,
    interactive: Annotated[bool, typer.Option("--interactive", "-i", help="Prompt for folder creation (otherwise queues for later)")] = False,
    auto_create: Annotated[bool, typer.Option("--auto-create", "-c", help="Auto-create missing folders without prompting")] = False,
    account: Annotated[str | None, typer.Option("--account", "-a", help="Process only this account (overrides config)")] = None,
    batch: Annotated[bool, typer.Option("--batch", "-B", help="Process all emails in batches until done")] = False,
    batch_delay: Annotated[int, typer.Option("--batch-delay", help="Seconds to pause between batches")] = 5,
) -> None:
    """Run autopilot email processing."""
    from email_nurse.autopilot import AutopilotEngine, load_autopilot_config
    from email_nurse.logging import setup_logging
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()

    # Initialize per-account logging
    setup_logging(
        log_dir=settings.log_dir,
        log_level=settings.log_level,
        max_bytes=settings.log_rotation_size_mb * 1024 * 1024,
        backup_count=settings.log_backup_count,
    )

    # Use provider from settings if not specified
    provider = provider or settings.ai_provider

    # Load autopilot config
    if not settings.autopilot_config_path.exists():
        console.print("[red]Autopilot config not found.[/red]")
        console.print(f"Run [bold]email-nurse autopilot init[/bold] to create one.")
        raise typer.Exit(1)

    config = load_autopilot_config(settings.autopilot_config_path)

    # Override accounts if --account specified
    if account:
        config.accounts = [account]

    # Get AI provider
    if provider == "claude":
        from email_nurse.ai.claude import ClaudeProvider

        ai = ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.claude_model)
    elif provider == "openai":
        from email_nurse.ai.openai import OpenAIProvider

        ai = OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)
    elif provider == "ollama":
        from email_nurse.ai.ollama import OllamaProvider

        ai = OllamaProvider(host=settings.ollama_host, model=settings.ollama_model)
    else:
        console.print(f"[red]Unknown provider:[/red] {provider}")
        raise typer.Exit(1)

    # Initialize database
    db = AutopilotDatabase(settings.database_path)

    # Create engine
    engine = AutopilotEngine(
        settings=settings,
        ai_provider=ai,
        database=db,
        config=config,
    )

    # Determine model name for display
    if provider == "claude":
        model_name = settings.claude_model
    elif provider == "openai":
        model_name = settings.openai_model
    elif provider == "ollama":
        model_name = settings.ollama_model
    else:
        model_name = "unknown"

    batch_size = limit or 50

    if batch:
        console.print("[bold]Autopilot[/bold] starting in batch mode...")
    else:
        console.print("[bold]Autopilot[/bold] starting...")
    console.print(f"  Provider: {provider}")
    console.print(f"  Model: {model_name}")
    if account:
        console.print(f"  Account: {account}")
    console.print(f"  Dry run: {'Yes' if dry_run else 'No'}")
    if batch:
        console.print(f"  Batch size: {batch_size}")
        console.print(f"  Batch delay: {batch_delay}s")
    if auto_create:
        console.print(f"  Auto-create folders: Yes")
    elif interactive:
        console.print(f"  Interactive: Yes")
    else:
        console.print(f"  Missing folders: Queue for later")

    if batch:
        # Batch mode: process continuously until no more emails
        import signal
        from datetime import datetime

        from email_nurse.autopilot.models import AutopilotRunResult

        stop_requested = False

        def handle_sigint(sig, frame):
            nonlocal stop_requested
            if stop_requested:
                console.print("\n[red]Force quit[/red]")
                raise KeyboardInterrupt
            stop_requested = True
            console.print("\n[yellow]Stopping after current batch (Ctrl+C again to force)[/yellow]")

        # Install signal handler
        original_handler = signal.signal(signal.SIGINT, handle_sigint)

        async def run_batch_mode():
            nonlocal stop_requested
            started_at = datetime.now()

            # Initialize accumulated result
            total_result = AutopilotRunResult(
                started_at=started_at,
                completed_at=started_at,
                dry_run=dry_run,
            )
            batch_num = 0

            try:
                while not stop_requested:
                    batch_num += 1
                    if verbose >= 1:
                        console.print(f"\n[bold]Batch {batch_num}[/bold]: Processing up to {batch_size} emails...")

                    result = await engine.run(
                        dry_run=dry_run,
                        limit=batch_size,
                        verbose=verbose,
                        interactive=interactive,
                        auto_create=auto_create,
                    )

                    # Accumulate results
                    total_result.emails_fetched += result.emails_fetched
                    total_result.emails_processed += result.emails_processed
                    total_result.emails_skipped += result.emails_skipped
                    total_result.actions_executed += result.actions_executed
                    total_result.actions_queued += result.actions_queued
                    total_result.errors += result.errors

                    if verbose >= 1:
                        console.print(
                            f"Batch {batch_num} complete: "
                            f"{result.emails_processed} processed, "
                            f"{result.actions_executed} actions, "
                            f"{result.errors} errors"
                        )

                    # Stop if no emails were fetched (inbox is clear)
                    if result.emails_fetched == 0:
                        console.print("\n[green]No more unprocessed emails. Done![/green]")
                        break

                    # Check if stop was requested
                    if stop_requested:
                        console.print("\n[yellow]Batch mode stopped by user.[/yellow]")
                        break

                    # Delay between batches (unless this was the last batch)
                    if batch_delay > 0 and not stop_requested:
                        if verbose >= 1:
                            console.print(f"[dim]Waiting {batch_delay}s before next batch...[/dim]")
                        await asyncio.sleep(batch_delay)

            except KeyboardInterrupt:
                console.print("\n[red]Interrupted[/red]")

            total_result.completed_at = datetime.now()
            return total_result, batch_num

        try:
            result, total_batches = asyncio.run(run_batch_mode())
        finally:
            # Restore original signal handler
            signal.signal(signal.SIGINT, original_handler)

        # Print batch summary
        console.print(f"\n[bold]Batch Summary[/bold]")
        console.print(f"  Total batches: {total_batches}")
        console.print(f"  Emails fetched: {result.emails_fetched}")
        console.print(f"  Emails processed: {result.emails_processed}")
        console.print(f"  Emails skipped: {result.emails_skipped}")
        console.print(f"  Actions executed: {result.actions_executed}")
        console.print(f"  Actions queued: {result.actions_queued}")
        console.print(f"  Errors: {result.errors}")
        duration = (result.completed_at - result.started_at).total_seconds()
        if duration >= 60:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            console.print(f"  Duration: {minutes}m {seconds}s")
        else:
            console.print(f"  Duration: {duration:.1f}s")
    else:
        # Single run mode (existing behavior)
        async def run_autopilot():
            result = await engine.run(dry_run=dry_run, limit=limit, verbose=verbose, interactive=interactive, auto_create=auto_create)
            return result

        result = asyncio.run(run_autopilot())

        # Print summary
        console.print(f"\n[bold]Summary[/bold]")
        console.print(f"  Emails fetched: {result.emails_fetched}")
        console.print(f"  Emails processed: {result.emails_processed}")
        console.print(f"  Emails skipped: {result.emails_skipped}")
        console.print(f"  Actions executed: {result.actions_executed}")
        console.print(f"  Actions queued: {result.actions_queued}")
        console.print(f"  Errors: {result.errors}")
        duration = (result.completed_at - result.started_at).total_seconds()
        console.print(f"  Duration: {duration:.1f}s")


@autopilot_app.command("watch")
def autopilot_watch(
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True, help="Verbosity: -v normal, -vv detailed, -vvv debug")] = 1,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Don't execute actions (test mode)")] = False,
    poll_interval: Annotated[int | None, typer.Option("--poll", "-p", help="Seconds between inbox count checks (default: 30)")] = None,
    post_scan_interval: Annotated[int | None, typer.Option("--interval", "-i", help="Minutes between scheduled scans (default: 10)")] = None,
    provider: Annotated[str | None, typer.Option("--provider", help="AI provider (default from settings)")] = None,
    account: Annotated[str | None, typer.Option("--account", "-a", help="Process only this account (overrides config)")] = None,
    auto_create: Annotated[bool, typer.Option("--auto-create", "-c", help="Auto-create missing folders without prompting")] = False,
) -> None:
    """
    Run continuous watcher with hybrid triggers.

    Polls inbox every --poll seconds (default 30). Triggers scan when:

    \b
    - New messages detected (count increased)
    - --interval minutes elapsed since last scan (default 10)

    Use Ctrl+C to stop gracefully.
    """
    from email_nurse.autopilot import WatcherEngine, load_autopilot_config
    from email_nurse.logging import setup_logging
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()

    # Initialize logging
    setup_logging(
        log_dir=settings.log_dir,
        log_level=settings.log_level,
        max_bytes=settings.log_rotation_size_mb * 1024 * 1024,
        backup_count=settings.log_backup_count,
    )

    # Use provider from settings if not specified
    provider = provider or settings.ai_provider

    # Load autopilot config
    if not settings.autopilot_config_path.exists():
        console.print("[red]Autopilot config not found.[/red]")
        console.print(f"Run [bold]email-nurse autopilot init[/bold] to create one.")
        raise typer.Exit(1)

    config = load_autopilot_config(settings.autopilot_config_path)

    # Override accounts if --account specified
    if account:
        config.accounts = [account]

    # Get AI provider
    if provider == "claude":
        from email_nurse.ai.claude import ClaudeProvider
        ai = ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.claude_model)
    elif provider == "openai":
        from email_nurse.ai.openai import OpenAIProvider
        ai = OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)
    elif provider == "ollama":
        from email_nurse.ai.ollama import OllamaProvider
        ai = OllamaProvider(host=settings.ollama_host, model=settings.ollama_model)
    else:
        console.print(f"[red]Unknown provider:[/red] {provider}")
        raise typer.Exit(1)

    # Initialize database
    db = AutopilotDatabase(settings.database_path)

    # Create watcher engine
    watcher = WatcherEngine(
        settings=settings,
        ai_provider=ai,
        database=db,
        config=config,
    )

    # Run the watcher
    asyncio.run(watcher.run(
        verbose=verbose,
        dry_run=dry_run,
        auto_create=auto_create,
        poll_interval=poll_interval,
        post_scan_interval=post_scan_interval,
    ))


@autopilot_app.command("queue")
def autopilot_queue(
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max items to show")] = 20,
) -> None:
    """List pending actions awaiting approval."""
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()
    db = AutopilotDatabase(settings.database_path)

    pending = db.get_pending_actions(limit=limit)

    if not pending:
        console.print("[yellow]No pending actions in queue[/yellow]")
        return

    table = Table(title="Pending Actions")
    table.add_column("ID", style="dim", width=6)
    table.add_column("Email", style="cyan", max_width=40)
    table.add_column("Action", style="green")
    table.add_column("Confidence", width=10)
    table.add_column("Reasoning", max_width=40)

    for item in pending:
        action_data = item.get("proposed_action", {})
        conf = item.get("confidence", 0)
        conf_style = "green" if conf >= 0.8 else "yellow" if conf >= 0.6 else "red"
        table.add_row(
            str(item["id"]),
            item.get("email_summary", "")[:40],
            action_data.get("action", "?"),
            f"[{conf_style}]{conf:.0%}[/{conf_style}]",
            item.get("reasoning", "")[:40],
        )

    console.print(table)
    console.print(f"\nUse [bold]email-nurse autopilot approve <id>[/bold] or [bold]reject <id>[/bold]")


@autopilot_app.command("approve")
def autopilot_approve(
    action_id: Annotated[int, typer.Argument(help="Pending action ID to approve")],
) -> None:
    """Approve and execute a pending action."""
    from email_nurse.autopilot import AutopilotEngine, load_autopilot_config
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()
    db = AutopilotDatabase(settings.database_path)

    # Get the pending action
    pending = db.get_pending_action(action_id)
    if not pending:
        console.print(f"[red]Pending action {action_id} not found[/red]")
        raise typer.Exit(1)

    if pending.get("status") != "pending":
        console.print(f"[yellow]Action {action_id} already processed (status: {pending.get('status')})[/yellow]")
        raise typer.Exit(1)

    # Load config and create engine (need AI provider for reply generation if needed)
    config = load_autopilot_config(settings.autopilot_config_path)

    from email_nurse.ai.claude import ClaudeProvider

    ai = ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.claude_model)

    engine = AutopilotEngine(
        settings=settings,
        ai_provider=ai,
        database=db,
        config=config,
    )

    async def execute():
        return await engine.execute_pending_action(action_id)

    result = asyncio.run(execute())

    if result.success:
        console.print(f"[green]✓ Approved and executed:[/green] {result.action}")
    else:
        console.print(f"[red]✗ Failed:[/red] {result.error}")


@autopilot_app.command("reject")
def autopilot_reject(
    action_id: Annotated[int, typer.Argument(help="Pending action ID to reject")],
) -> None:
    """Reject a pending action (remove from queue)."""
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()
    db = AutopilotDatabase(settings.database_path)

    pending = db.get_pending_action(action_id)
    if not pending:
        console.print(f"[red]Pending action {action_id} not found[/red]")
        raise typer.Exit(1)

    if pending.get("status") != "pending":
        console.print(f"[yellow]Action {action_id} already processed (status: {pending.get('status')})[/yellow]")
        raise typer.Exit(1)

    db.update_pending_status(action_id, "rejected")
    console.print(f"[yellow]✓ Rejected action {action_id}[/yellow]")


@autopilot_app.command("history")
def autopilot_history(
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max items to show")] = 20,
    action: Annotated[str | None, typer.Option("--action", "-a", help="Filter by action type")] = None,
) -> None:
    """Show autopilot action history."""
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()
    db = AutopilotDatabase(settings.database_path)

    history = db.get_action_history(limit=limit, action_filter=action)

    if not history:
        console.print("[yellow]No action history found[/yellow]")
        return

    table = Table(title="Action History")
    table.add_column("Time", style="dim", width=16)
    table.add_column("Action", style="green", width=12)
    table.add_column("Source", style="blue", width=10)
    table.add_column("Message ID", style="cyan", width=10)
    table.add_column("Details", max_width=40)

    for item in history:
        timestamp = item.get("timestamp", "")[:16]
        details = item.get("details", {})
        detail_str = details.get("reasoning", "")[:40] if isinstance(details, dict) else str(details)[:40]
        table.add_row(
            timestamp,
            item.get("action", "?"),
            item.get("source", "?"),
            item.get("message_id", "")[:10],
            detail_str,
        )

    console.print(table)


@autopilot_app.command("report")
def autopilot_report(
    to: Annotated[
        str | None,
        typer.Option("--to", "-t", help="Email address to send report to"),
    ] = None,
    date_str: Annotated[
        str | None,
        typer.Option("--date", "-d", help="Date to report on (YYYY-MM-DD)"),
    ] = None,
    preview: Annotated[
        bool,
        typer.Option("--preview", "-p", help="Preview report without sending"),
    ] = False,
    account: Annotated[
        str | None,
        typer.Option("--account", "-a", help="Account to send from"),
    ] = None,
) -> None:
    """
    Generate and send daily activity report.

    By default, sends to the first email address of the first enabled account.
    Use --preview to see the report without sending.
    """
    from datetime import datetime

    from email_nurse.autopilot.reports import DailyReportGenerator
    from email_nurse.mail.accounts import get_accounts
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()
    db = AutopilotDatabase(settings.database_path)

    # Parse date if provided
    report_date = None
    if date_str:
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Invalid date format: {date_str}. Use YYYY-MM-DD.[/red]")
            raise typer.Exit(1)

    # Get recipient if not specified
    if to is None and not preview:
        # Check settings first
        if settings.report_recipient:
            to = settings.report_recipient
        else:
            # Fall back to first email from first enabled account
            accounts = get_accounts()
            enabled = [a for a in accounts if a.enabled and a.email_addresses]
            if enabled:
                to = enabled[0].email_addresses[0]
            else:
                console.print("[red]No email address found. Use --to to specify recipient.[/red]")
                raise typer.Exit(1)

    generator = DailyReportGenerator(db)

    # Use configured account if not specified via CLI
    if account is None and settings.report_account:
        account = settings.report_account

    # Get sender address from settings
    sender_address = settings.report_sender

    if preview:
        report_text = generator.generate_report(report_date)
        console.print(report_text)
    else:
        from_display = sender_address or account or "default"
        console.print(f"[dim]Sending report to {to} (from {from_display})...[/dim]")
        try:
            if generator.send_report(to, report_date, account, sender_address):  # type: ignore[arg-type]
                console.print(f"[green]Report sent to {to}[/green]")
            else:
                console.print("[red]Failed to send report[/red]")
                raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error sending report: {e}[/red]")
            raise typer.Exit(1)


@autopilot_app.command("init")
def autopilot_init() -> None:
    """Initialize autopilot configuration."""
    settings = get_settings()
    settings.ensure_config_dir()

    if settings.autopilot_config_path.exists():
        console.print(f"[yellow]Autopilot config already exists:[/yellow] {settings.autopilot_config_path}")
        overwrite = typer.confirm("Overwrite with example?", default=False)
        if not overwrite:
            return

    example_config = """# Autopilot Configuration
# Natural language instructions for AI email processing

# Your instructions to the AI - be specific about what you want
instructions: |
  You are managing my personal email inbox. Follow these guidelines:

  1. NEWSLETTERS & MARKETING:
     - Move promotional emails to "Marketing" folder
     - Move newsletters I'm subscribed to to "Newsletters" folder
     - Delete obvious spam

  2. IMPORTANT:
     - Flag emails from my contacts list as important
     - Leave emails about appointments, travel, or finances alone (ignore action)
     - Never delete emails from real people

  3. NOTIFICATIONS:
     - Archive automated notifications from services (GitHub, etc.)
     - Move social media notifications (LinkedIn, Facebook, Instagram, TikTok, etc. but NOT Reddit) to Social folder

  4. REPLIES:
     - Do not auto-reply to anything without my approval

  When in doubt, use 'ignore' action to leave email untouched.

# Mailboxes to process
mailboxes:
  - INBOX

# Specific accounts to process (empty = all accounts)
accounts: []

# Maximum age of emails to process (days)
max_age_days: 7

# Senders to exclude (substring match)
exclude_senders:
  - "noreply@yourbank.com"
  - "security@"

# Subjects to exclude (substring match)
exclude_subjects:
  - "Password Reset"
  - "Two-Factor"
  - "2FA"
  - "Verification Code"
"""

    settings.autopilot_config_path.write_text(example_config)
    console.print(f"[green]Created[/green] {settings.autopilot_config_path}")
    console.print("\nEdit this file with your instructions, then run:")
    console.print("  [bold]email-nurse autopilot run --dry-run -v[/bold]")


@autopilot_app.command("status")
def autopilot_status() -> None:
    """Show autopilot status and statistics."""
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()

    # Check config
    config_exists = settings.autopilot_config_path.exists()
    console.print(f"[bold]Autopilot Status[/bold]\n")
    console.print(f"Config file: {'[green]✓[/green]' if config_exists else '[red]✗[/red]'} {settings.autopilot_config_path}")

    if not config_exists:
        console.print("\nRun [bold]email-nurse autopilot init[/bold] to create config.")
        return

    # Load config
    from email_nurse.autopilot import load_autopilot_config

    config = load_autopilot_config(settings.autopilot_config_path)
    console.print(f"Mailboxes: {', '.join(config.mailboxes)}")
    console.print(f"Max age: {config.max_age_days} days")

    # Database stats
    if not settings.database_path.exists():
        console.print("\n[yellow]Database not initialized (no runs yet)[/yellow]")
        return

    db = AutopilotDatabase(settings.database_path)

    processed_count = len(db.get_processed_ids(limit=100000))
    pending_count = len(db.get_pending_actions(limit=100000))

    console.print(f"\n[bold]Statistics[/bold]")
    console.print(f"  Processed emails: {processed_count}")
    console.print(f"  Pending actions: {pending_count}")

    # Settings
    console.print(f"\n[bold]Settings[/bold]")
    console.print(f"  Low confidence action: {settings.low_confidence_action}")
    console.print(f"  Confidence threshold: {settings.confidence_threshold:.0%}")
    console.print(f"  Outbound policy: {settings.outbound_policy}")
    console.print(f"  Outbound threshold: {settings.outbound_confidence_threshold:.0%}")


@autopilot_app.command("add-rule")
def autopilot_add_rule(
    description: Annotated[
        str | None,
        typer.Argument(help="Natural language rule description"),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Explicit name for the rule"),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Add a quick rule from natural language description.

    Examples:
        email-nurse autopilot add-rule "move anything from spam@example.com to Junk"
        email-nurse autopilot add-rule "delete all emails from @sketchy.biz"
        email-nurse autopilot add-rule "ignore newsletters with 'unsubscribe' in subject"
        email-nurse autopilot add-rule "mark read and trash marketing from acme.com"

    Run without arguments for interactive mode with full instructions.
    """
    from rich.panel import Panel

    from email_nurse.ai.claude import ClaudeProvider
    from email_nurse.autopilot.config import QuickRule

    settings = get_settings()

    # Interactive mode if no description provided
    if description is None:
        examples = """[cyan]Describe the rule you want to create in plain English.[/cyan]

[dim]Examples:[/dim]
  • "move emails from bob@example.com to Archive"
  • "delete anything from @spam-domain.com"
  • "ignore newsletters with 'unsubscribe' in subject"
  • "mark read and trash marketing from acme.com\""""

        console.print(Panel(examples, title="Quick Rule Generator", border_style="blue"))
        console.print()

        description = typer.prompt("Enter rule description")
        if not description.strip():
            console.print("[yellow]No description provided. Cancelled.[/yellow]")
            raise typer.Exit(0)

    # Initialize Claude provider for parsing
    if not settings.anthropic_api_key:
        console.print("[red]Error: ANTHROPIC_API_KEY not set.[/red]")
        console.print("Set the environment variable or configure it in settings.")
        raise typer.Exit(1)

    ai = ClaudeProvider(api_key=settings.anthropic_api_key)

    console.print("\n[dim]Parsing with AI...[/dim]")

    # Parse the description into a QuickRule
    async def parse_rule() -> QuickRule:
        return await ai.parse_quick_rule(description, rule_name=name)

    try:
        rule = asyncio.run(parse_rule())
    except ValueError as e:
        console.print(f"[red]Failed to parse rule:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        # Catch API errors (authentication, rate limits, etc.)
        error_msg = str(e)
        if "401" in error_msg or "authentication" in error_msg.lower():
            console.print("[red]Authentication failed.[/red]")
            console.print("Please verify your ANTHROPIC_API_KEY is correct.")
            console.print("Check: ~/.config/email-nurse/.env")
        else:
            console.print(f"[red]API error:[/red] {e}")
        raise typer.Exit(1)

    # Display the generated rule
    console.print("\n[bold]Generated Rule:[/bold]")
    rule_display = f"  [cyan]name:[/cyan] \"{rule.name}\"\n"
    rule_display += "  [cyan]match:[/cyan]\n"
    for key, patterns in rule.match.items():
        rule_display += f"    {key}: {patterns}\n"
    if rule.action:
        rule_display += f"  [cyan]action:[/cyan] {rule.action}\n"
    if rule.actions:
        rule_display += f"  [cyan]actions:[/cyan] {rule.actions}\n"
    if rule.folder:
        rule_display += f"  [cyan]folder:[/cyan] {rule.folder}\n"
    console.print(rule_display)

    # Confirm unless --yes
    if not yes:
        if not typer.confirm("Add this rule?", default=True):
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    # Append to config files
    updated_files = []

    # Production config
    if settings.autopilot_config_path.exists():
        try:
            _append_quick_rule_to_config(settings.autopilot_config_path, rule)
            updated_files.append(settings.autopilot_config_path)
        except Exception as e:
            console.print(f"[red]Failed to update production config:[/red] {e}")
            raise typer.Exit(1)

    # Repo config (deploy/config/autopilot.yaml)
    repo_config = Path.cwd() / "deploy" / "config" / "autopilot.yaml"
    if repo_config.exists() and repo_config != settings.autopilot_config_path:
        try:
            _append_quick_rule_to_config(repo_config, rule)
            updated_files.append(repo_config)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to update repo config:[/yellow] {e}")

    # Success message
    for path in updated_files:
        console.print(f"[green]✓ Rule added to[/green] {path}")


def _append_quick_rule_to_config(config_path: Path, rule) -> None:
    """Append a quick rule to autopilot.yaml preserving formatting.

    This function carefully appends a new rule to the quick_rules section
    of the YAML config file while preserving comments and existing formatting.
    """
    content = config_path.read_text()

    # Build the rule YAML manually to control formatting
    rule_lines = [f"\n  # {rule.name}"]
    rule_lines.append(f'  - name: "{rule.name}"')
    rule_lines.append("    match:")

    for key, patterns in rule.match.items():
        if len(patterns) == 1:
            rule_lines.append(f'      {key}: ["{patterns[0]}"]')
        else:
            pattern_str = ", ".join(f'"{p}"' for p in patterns)
            rule_lines.append(f"      {key}: [{pattern_str}]")

    if rule.actions:
        actions_str = ", ".join(rule.actions)
        rule_lines.append(f"    actions: [{actions_str}]")
    elif rule.action:
        rule_lines.append(f"    action: {rule.action}")

    if rule.folder:
        rule_lines.append(f"    folder: {rule.folder}")

    rule_yaml = "\n".join(rule_lines)

    # Find where to insert - after the last rule or at end of quick_rules section
    if "quick_rules:" in content:
        # Append to existing quick_rules section
        # Find the end of the file or next top-level section
        lines = content.split("\n")
        insert_index = len(lines)

        in_quick_rules = False
        for i, line in enumerate(lines):
            if line.strip().startswith("quick_rules:"):
                in_quick_rules = True
                continue
            if in_quick_rules and line and not line.startswith(" ") and not line.startswith("#"):
                # Found next top-level section
                insert_index = i
                break

        # Insert before the next section (or at end)
        lines.insert(insert_index, rule_yaml)
        content = "\n".join(lines)
    else:
        # No quick_rules section exists - add one
        content += "\n\nquick_rules:" + rule_yaml

    config_path.write_text(content)


@autopilot_app.command("reset")
def autopilot_reset(
    older_than: int = typer.Option(
        None,
        "--older-than",
        "-o",
        help="Only clear entries older than N days (default: all)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Reset processed email tracking to re-analyze messages."""
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()

    if not settings.database_path.exists():
        console.print("[yellow]No database found - nothing to reset.[/yellow]")
        return

    db = AutopilotDatabase(settings.database_path)
    current_count = db.get_processed_count()

    if current_count == 0:
        console.print("[yellow]No processed emails to clear.[/yellow]")
        return

    # Describe what will happen
    if older_than:
        desc = f"entries older than {older_than} days"
    else:
        desc = f"all {current_count} entries"

    if not force:
        confirm = typer.confirm(f"Clear {desc} from processed tracking?")
        if not confirm:
            console.print("Cancelled.")
            return

    cleared = db.clear_processed(before_days=older_than)
    console.print(f"[green]✓ Cleared {cleared} processed email records.[/green]")
    console.print("Next autopilot run will re-analyze these messages.")


@autopilot_app.command("reset-watcher")
def autopilot_reset_watcher() -> None:
    """Reset watcher state (clears stale PID lock and counters)."""
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()

    if not settings.database_path.exists():
        console.print("[yellow]No database found - nothing to reset.[/yellow]")
        return

    db = AutopilotDatabase(settings.database_path)
    cleared = db.clear_watcher_state()

    if cleared > 0:
        console.print(f"[green]✓ Cleared watcher state ({cleared} entries).[/green]")
    else:
        console.print("[yellow]No watcher state to clear.[/yellow]")


@autopilot_app.command("clear-cache")
def autopilot_clear_cache(
    account: Annotated[
        str | None,
        typer.Option("--account", "-a", help="Clear cache for specific account only"),
    ] = None,
) -> None:
    """Clear cached mailbox lists (forces fresh fetch from Mail.app)."""
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()

    if not settings.database_path.exists():
        console.print("[yellow]No database found - nothing to clear.[/yellow]")
        return

    db = AutopilotDatabase(settings.database_path)
    cleared = db.clear_mailbox_cache(account=account)

    if cleared > 0:
        target = f"for {account}" if account else "for all accounts"
        console.print(f"[green]✓ Cleared mailbox cache {target}.[/green]")
    else:
        console.print("[yellow]No cached mailboxes to clear.[/yellow]")


@autopilot_app.command("pending-folders")
def autopilot_pending_folders(
    account: Annotated[
        str | None,
        typer.Option("--account", "-a", help="Filter by specific account"),
    ] = None,
) -> None:
    """List folders that need manual creation.

    Shows folders that couldn't be auto-created (e.g., on Exchange accounts)
    along with the messages waiting to be moved to those folders.
    """
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()

    if not settings.database_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        return

    db = AutopilotDatabase(settings.database_path)
    pending = db.get_pending_folders(account=account)

    if not pending:
        console.print("[green]✓ No folders pending creation.[/green]")
        return

    table = Table(title="Folders Pending Manual Creation")
    table.add_column("Folder", style="cyan")
    table.add_column("Account", style="yellow")
    table.add_column("Messages", justify="right")
    table.add_column("Waiting Since")

    total_messages = 0
    for item in pending:
        table.add_row(
            item["pending_folder"],
            item["pending_account"],
            str(item["message_count"]),
            item["first_queued"][:10] if item["first_queued"] else "Unknown",
        )
        total_messages += item["message_count"]

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {len(pending)} folder(s), {total_messages} message(s) waiting")
    console.print("\n[dim]Create folders manually, then run: email-nurse autopilot retry-pending[/dim]")


@autopilot_app.command("retry-pending")
def autopilot_retry_pending(
    account: Annotated[
        str | None,
        typer.Option("--account", "-a", help="Only retry for specific account"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would happen without executing"),
    ] = False,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Increase output verbosity"),
    ] = 1,
) -> None:
    """Retry pending folder actions after creating folders.

    Checks if any folders queued for creation now exist, and executes
    the pending move actions for those folders.

    Example workflow:
        1. Autopilot queues messages for "Leadership" folder on Exchange
        2. You create "Leadership" folder in Outlook Web
        3. Run: email-nurse autopilot retry-pending
        4. Messages are moved to the new folder
    """
    from email_nurse.ai.factory import create_ai_provider
    from email_nurse.autopilot.config import load_autopilot_config
    from email_nurse.autopilot.engine import AutopilotEngine
    from email_nurse.logging import setup_logging
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()
    setup_logging(settings)

    if not settings.database_path.exists():
        console.print("[yellow]No database found.[/yellow]")
        raise typer.Exit(1)

    # Load autopilot config
    config = load_autopilot_config(settings.autopilot_config_path)
    if not config:
        console.print("[red]Error: No autopilot configuration found.[/red]")
        console.print(f"Run 'email-nurse autopilot init' first.")
        raise typer.Exit(1)

    db = AutopilotDatabase(settings.database_path)

    # Create AI provider (needed for engine, even though we won't classify)
    ai_provider = create_ai_provider(settings)

    engine = AutopilotEngine(
        settings=settings,
        ai_provider=ai_provider,
        database=db,
        config=config,
    )

    # Run retry
    results = asyncio.run(
        engine.retry_pending_folders(
            account=account,
            dry_run=dry_run,
            verbose=verbose,
        )
    )

    if results["errors"] > 0:
        raise typer.Exit(1)


@autopilot_app.command("performance")
def autopilot_performance(
    hours: Annotated[int, typer.Option("--hours", "-h", help="Hours to review")] = 24,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Review autopilot performance metrics.

    Displays performance statistics for message retrieval and processing
    over the specified time period. Use this to track sysm performance impact.

    Examples:
        email-nurse autopilot performance              # Last 24 hours
        email-nurse autopilot performance --hours 12   # Last 12 hours
        email-nurse autopilot performance --json       # JSON output
    """
    from email_nurse.performance_tracker import get_tracker

    tracker = get_tracker()

    if json_output:
        import json
        report = tracker.generate_report(hours=hours)
        print(json.dumps(report, indent=2))
    else:
        tracker.print_report(hours=hours)
