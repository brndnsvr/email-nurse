"""Command-line interface for email-nurse."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from email_nurse.config import Settings

app = typer.Typer(
    name="email-nurse",
    help="AI-powered email management for macOS Mail.app",
    no_args_is_help=True,
)
console = Console()

# Sub-command groups
accounts_app = typer.Typer(help="Manage email accounts")
messages_app = typer.Typer(help="View and process messages")
rules_app = typer.Typer(help="Manage processing rules")
autopilot_app = typer.Typer(help="Autopilot mode operations")
reminders_app = typer.Typer(help="Apple Reminders integration")

app.add_typer(accounts_app, name="accounts")
app.add_typer(messages_app, name="messages")
app.add_typer(rules_app, name="rules")
app.add_typer(autopilot_app, name="autopilot")
app.add_typer(reminders_app, name="reminders")


def get_settings() -> Settings:
    """Load application settings."""
    return Settings()


@app.command()
def version() -> None:
    """Show version information."""
    from email_nurse import __version__

    console.print(f"email-nurse v{__version__}")


@app.command()
def init(
    config_dir: Annotated[
        Path | None,
        typer.Option("--config-dir", "-c", help="Configuration directory"),
    ] = None,
) -> None:
    """Initialize configuration directory with example files."""
    settings = get_settings()
    if config_dir:
        settings.config_dir = config_dir

    settings.ensure_config_dir()

    # Create example rules file if it doesn't exist
    if not settings.rules_path.exists():
        example_rules = """# Email Nurse Rules Configuration
# Each rule defines conditions to match and actions to take

rules:
  - name: "Archive Newsletters"
    description: "Move newsletters to Archive folder"
    enabled: true
    priority: 100
    conditions:
      - type: subject_contains
        value: "newsletter"
      - type: subject_contains
        value: "unsubscribe"
    match_all: false
    action:
      action: move
      target_folder: "Archive"
    stop_processing: true

  - name: "Flag Important"
    description: "Flag emails from important senders"
    enabled: true
    priority: 50
    conditions:
      - type: sender_domain
        value: "example.com"
    action:
      action: flag
    stop_processing: false

  - name: "AI Triage"
    description: "Use AI to classify unmatched emails"
    enabled: false
    priority: 999
    conditions: []
    use_ai: true
    ai_context: "Classify this email. Move marketing to Marketing folder, invoices to Finance folder, social media (not Reddit) to Social folder."
    action:
      action: ignore
"""
        settings.rules_path.write_text(example_rules)
        console.print(f"[green]Created[/green] {settings.rules_path}")

    # Create example templates file if it doesn't exist
    if not settings.templates_path.exists():
        example_templates = """# Email Nurse Reply Templates
# Templates can be static text or AI instructions

templates:
  acknowledge:
    description: "Simple acknowledgment reply"
    use_ai: true
    content: |
      Generate a brief, professional acknowledgment of this email.
      Thank the sender and indicate the message has been received.
      Keep it under 3 sentences.

  out_of_office:
    description: "Out of office auto-reply"
    use_ai: false
    content: |
      Thank you for your email. I am currently out of the office
      and will respond to your message when I return.

      Best regards

  follow_up:
    description: "Request more information"
    use_ai: true
    content: |
      Generate a polite reply asking for clarification or more details
      about the main topic of this email. Be specific about what
      additional information would be helpful.
"""
        settings.templates_path.write_text(example_templates)
        console.print(f"[green]Created[/green] {settings.templates_path}")

    console.print(f"\n[bold]Configuration initialized at:[/bold] {settings.config_dir}")


# === Accounts Commands ===


@accounts_app.command("list")
def accounts_list() -> None:
    """List all configured email accounts."""
    from email_nurse.mail.accounts import get_accounts

    try:
        accounts = get_accounts()
    except Exception as e:
        console.print(f"[red]Error accessing Mail.app:[/red] {e}")
        raise typer.Exit(1)

    if not accounts:
        console.print("[yellow]No email accounts found in Mail.app[/yellow]")
        return

    table = Table(title="Email Accounts")
    table.add_column("Name", style="cyan")
    table.add_column("Email Addresses", style="green")
    table.add_column("Type", style="blue")
    table.add_column("Enabled", style="yellow")

    for acct in accounts:
        table.add_row(
            acct.name,
            ", ".join(acct.email_addresses),
            acct.account_type,
            "✓" if acct.enabled else "✗",
        )

    console.print(table)


@accounts_app.command("sync")
def accounts_sync(
    account: Annotated[
        str | None,
        typer.Argument(help="Account name to sync (all if not specified)"),
    ] = None,
) -> None:
    """Trigger sync/check for new mail."""
    from email_nurse.mail.accounts import sync_account, sync_all_accounts

    try:
        if account:
            console.print(f"Syncing account: {account}")
            sync_account(account)
        else:
            console.print("Syncing all accounts...")
            sync_all_accounts()
        console.print("[green]Sync triggered successfully[/green]")
    except Exception as e:
        console.print(f"[red]Sync failed:[/red] {e}")
        raise typer.Exit(1)


# === Messages Commands ===


@messages_app.command("list")
def messages_list(
    mailbox: Annotated[str, typer.Option("--mailbox", "-m", help="Mailbox name")] = "INBOX",
    account: Annotated[str | None, typer.Option("--account", "-a", help="Account name")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of messages")] = 10,
    unread: Annotated[bool, typer.Option("--unread", "-u", help="Only unread messages")] = False,
) -> None:
    """List messages in a mailbox."""
    from email_nurse.mail.messages import get_messages

    try:
        messages = get_messages(
            mailbox=mailbox,
            account=account,
            limit=limit,
            unread_only=unread,
        )
    except Exception as e:
        console.print(f"[red]Error fetching messages:[/red] {e}")
        raise typer.Exit(1)

    if not messages:
        console.print("[yellow]No messages found[/yellow]")
        return

    table = Table(title=f"Messages in {mailbox}")
    table.add_column("ID", style="dim", width=8)
    table.add_column("From", style="cyan", max_width=30)
    table.add_column("Subject", style="green", max_width=50)
    table.add_column("Date", style="blue", width=12)
    table.add_column("Read", width=4)

    for msg in messages:
        date_str = msg.date_received.strftime("%m/%d %H:%M") if msg.date_received else "-"
        table.add_row(
            msg.id[:8],
            msg.sender[:30],
            msg.subject[:50],
            date_str,
            "✓" if msg.is_read else "",
        )

    console.print(table)


@messages_app.command("show")
def messages_show(
    message_id: Annotated[str, typer.Argument(help="Message ID to display")],
) -> None:
    """Show details of a specific message."""
    from email_nurse.mail.messages import get_message_by_id

    msg = get_message_by_id(message_id)
    if not msg:
        console.print(f"[red]Message not found:[/red] {message_id}")
        raise typer.Exit(1)

    console.print(f"\n[bold]Subject:[/bold] {msg.subject}")
    console.print(f"[bold]From:[/bold] {msg.sender}")
    console.print(f"[bold]To:[/bold] {', '.join(msg.recipients)}")
    console.print(f"[bold]Date:[/bold] {msg.date_received}")
    console.print(f"[bold]Account:[/bold] {msg.account}")
    console.print(f"[bold]Mailbox:[/bold] {msg.mailbox}")
    console.print(f"[bold]Read:[/bold] {'Yes' if msg.is_read else 'No'}")
    console.print("\n[bold]Content:[/bold]")
    console.print(msg.content[:2000])


@messages_app.command("classify")
def messages_classify(
    mailbox: Annotated[str, typer.Option("--mailbox", "-m")] = "INBOX",
    account: Annotated[str | None, typer.Option("--account", "-a")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 5,
    provider: Annotated[str, typer.Option("--provider", "-p")] = "claude",
) -> None:
    """Classify messages using AI (dry run)."""
    from email_nurse.mail.messages import get_messages

    settings = get_settings()

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

    messages = get_messages(mailbox=mailbox, account=account, limit=limit, unread_only=True)

    if not messages:
        console.print("[yellow]No unread messages to classify[/yellow]")
        return

    console.print(f"\n[bold]Classifying {len(messages)} messages with {provider}...[/bold]\n")

    async def classify_all():
        for msg in messages:
            console.print(f"[cyan]{msg.subject[:60]}[/cyan]")
            try:
                result = await ai.classify_email(msg)
                console.print(
                    f"  → [green]{result.action.value}[/green] "
                    f"({result.confidence:.0%}) - {result.reasoning}"
                )
            except Exception as e:
                console.print(f"  → [red]Error:[/red] {e}")
            console.print()

    asyncio.run(classify_all())


# === Rules Commands ===


@rules_app.command("list")
def rules_list() -> None:
    """List all configured rules."""
    settings = get_settings()

    from email_nurse.config import load_rules

    rules = load_rules(settings.rules_path)

    if not rules:
        console.print("[yellow]No rules configured[/yellow]")
        console.print(f"Run [bold]email-nurse init[/bold] to create example rules")
        return

    table = Table(title="Processing Rules")
    table.add_column("Priority", style="dim", width=8)
    table.add_column("Name", style="cyan")
    table.add_column("Action", style="green")
    table.add_column("Enabled", width=7)
    table.add_column("AI", width=4)

    for rule in sorted(rules, key=lambda r: r.get("priority", 100)):
        action = rule.get("action", {})
        table.add_row(
            str(rule.get("priority", 100)),
            rule.get("name", "unnamed"),
            action.get("action", "?"),
            "✓" if rule.get("enabled", True) else "✗",
            "✓" if rule.get("use_ai", False) else "",
        )

    console.print(table)


@app.command()
def run(
    once: Annotated[bool, typer.Option("--once", help="Run once then exit")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Don't execute actions")] = True,
) -> None:
    """Run the email processing daemon."""
    console.print("[bold]Email Nurse[/bold] starting...")
    console.print(f"  Dry run: {'Yes' if dry_run else 'No'}")

    if once:
        console.print("\n[yellow]Single run mode - processing once then exiting[/yellow]")
        # TODO: Implement single processing run
        console.print("[dim]Processing not yet implemented[/dim]")
    else:
        console.print("\n[yellow]Daemon mode not yet implemented[/yellow]")
        console.print("Use --once for single run")


# === Autopilot Commands ===


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
    from email_nurse.storage.database import AutopilotDatabase

    settings = get_settings()

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


# === Reminders Commands ===


@reminders_app.command("lists")
def reminders_lists(
    counts: Annotated[bool, typer.Option("--counts", "-c", help="Include reminder counts (slow)")] = False,
) -> None:
    """List all reminder lists from Reminders.app.

    Note: The --counts option can be very slow if you have lists with
    thousands of items due to Reminders.app performance limitations.
    """
    from email_nurse.reminders import get_lists
    from email_nurse.reminders.lists import RemindersAppNotRunningError

    try:
        lists = get_lists(include_counts=counts)
    except RemindersAppNotRunningError:
        console.print("[red]Error: Reminders.app is not running.[/red]")
        console.print("Please open Reminders.app and try again.")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error accessing Reminders.app:[/red] {e}")
        raise typer.Exit(1)

    if not lists:
        console.print("[yellow]No reminder lists found[/yellow]")
        return

    table = Table(title="Reminder Lists")
    table.add_column("Name", style="cyan")
    if counts:
        table.add_column("Incomplete", style="green", justify="right")

    for lst in lists:
        if counts:
            count_str = str(lst.count) if lst.count > 0 else "-"
            table.add_row(lst.name, count_str)
        else:
            table.add_row(lst.name)

    console.print(table)
    if not counts:
        console.print("[dim]Use --counts to show reminder counts (may be slow)[/dim]")


@reminders_app.command("show")
def reminders_show(
    list_name: Annotated[str, typer.Argument(help="Name of the reminder list")],
    completed: Annotated[bool, typer.Option("--completed", "-c", help="Show completed items")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max items to show")] = 50,
) -> None:
    """Show reminders in a specific list.

    Note: Lists with many items (1000+) may be slow due to Reminders.app performance.
    """
    from email_nurse.reminders import get_reminders
    from email_nurse.reminders.lists import RemindersAppNotRunningError

    try:
        # completed=False by default to show incomplete, True to show all (or completed)
        reminders = get_reminders(
            list_name=list_name,
            completed=True if completed else False,
            limit=limit,
        )
    except RemindersAppNotRunningError:
        console.print("[red]Error: Reminders.app is not running.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error fetching reminders:[/red] {e}")
        raise typer.Exit(1)

    if not reminders:
        status = "completed" if completed else "incomplete"
        console.print(f"[yellow]No {status} reminders in '{list_name}'[/yellow]")
        return

    table = Table(title=f"Reminders: {list_name}")
    table.add_column("", width=3)  # Status checkbox
    table.add_column("Name", style="cyan", max_width=50)
    table.add_column("Due", style="blue", width=12)
    table.add_column("Priority", width=8)
    table.add_column("Link", width=4)

    for r in reminders:
        status = "[green]✓[/green]" if r.completed else "[ ]"
        due_str = r.due_date.strftime("%Y-%m-%d") if r.due_date else "-"

        priority_styles = {"high": "[red]high[/red]", "medium": "[yellow]med[/yellow]", "low": "[dim]low[/dim]"}
        priority_str = priority_styles.get(r.priority_label, "-") if r.priority > 0 else "-"

        has_link = "📧" if r.email_link else ""

        table.add_row(status, r.name[:50], due_str, priority_str, has_link)

    console.print(table)


@reminders_app.command("incomplete")
def reminders_incomplete(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max items to show")] = 30,
) -> None:
    """Show all incomplete reminders across all lists.

    Warning: This may be slow if you have lists with many items.
    Consider using 'reminders show <list>' for specific lists.
    """
    from email_nurse.reminders import get_lists, get_reminders
    from email_nurse.reminders.lists import RemindersAppNotRunningError

    try:
        lists = get_lists()
    except RemindersAppNotRunningError:
        console.print("[red]Error: Reminders.app is not running.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error accessing Reminders.app:[/red] {e}")
        raise typer.Exit(1)

    # Filter to lists with incomplete items
    lists_with_items = [lst for lst in lists if lst.count > 0]

    if not lists_with_items:
        console.print("[yellow]No incomplete reminders found[/yellow]")
        return

    # Warn about large lists
    large_lists = [lst for lst in lists_with_items if lst.count > 100]
    if large_lists:
        console.print(f"[yellow]Warning: Some lists have many items. This may take a while...[/yellow]")

    all_reminders = []
    remaining = limit

    for lst in lists_with_items:
        if remaining <= 0:
            break

        try:
            reminders = get_reminders(
                list_name=lst.name,
                completed=False,
                limit=min(remaining, lst.count),
            )
            all_reminders.extend(reminders)
            remaining -= len(reminders)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not fetch from '{lst.name}': {e}[/yellow]")
            continue

    if not all_reminders:
        console.print("[yellow]No incomplete reminders found[/yellow]")
        return

    # Sort by due date (None values at end)
    all_reminders.sort(key=lambda r: (r.due_date is None, r.due_date or ""))

    table = Table(title="Incomplete Reminders")
    table.add_column("List", style="dim", width=15)
    table.add_column("Name", style="cyan", max_width=45)
    table.add_column("Due", style="blue", width=12)
    table.add_column("Priority", width=8)

    for r in all_reminders:
        due_str = r.due_date.strftime("%Y-%m-%d") if r.due_date else "-"
        priority_styles = {"high": "[red]high[/red]", "medium": "[yellow]med[/yellow]", "low": "[dim]low[/dim]"}
        priority_str = priority_styles.get(r.priority_label, "-") if r.priority > 0 else "-"

        table.add_row(r.list_name[:15], r.name[:45], due_str, priority_str)

    console.print(table)


if __name__ == "__main__":
    app()
