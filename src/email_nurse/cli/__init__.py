"""Command-line interface for email-nurse."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

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
autopilot_app = typer.Typer(help="Autopilot mode operations")
reminders_app = typer.Typer(help="Apple Reminders integration")
calendar_app = typer.Typer(help="Apple Calendar integration")
ops_app = typer.Typer(help="Ops: self-healing and maintenance")

app.add_typer(accounts_app, name="accounts")
app.add_typer(messages_app, name="messages")
app.add_typer(autopilot_app, name="autopilot")
app.add_typer(reminders_app, name="reminders")
app.add_typer(calendar_app, name="calendar")
app.add_typer(ops_app, name="ops")


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


@app.command()
def run(
    once: Annotated[bool, typer.Option("--once", help="Run once then exit")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Don't execute actions")] = True,
) -> None:
    """Run the email processing daemon."""
    console.print("[bold]Email Nurse[/bold] starting...")
    console.print(f"  Dry run: {'Yes' if dry_run else 'No'}")

    if once:
        console.print("\n[yellow]Single run mode - not implemented[/yellow]")
        console.print("[dim]Use 'email-nurse autopilot run' instead[/dim]")
    else:
        console.print("\n[yellow]Daemon mode not yet implemented[/yellow]")
        console.print("Use --once for single run")


# Import sub-modules to trigger command registration
from email_nurse.cli import accounts  # noqa: E402, F401
from email_nurse.cli import messages  # noqa: E402, F401
from email_nurse.cli import autopilot  # noqa: E402, F401
from email_nurse.cli import reminders  # noqa: E402, F401
from email_nurse.cli import calendar  # noqa: E402, F401
from email_nurse.cli import ops  # noqa: E402, F401

if __name__ == "__main__":
    app()
