"""Message viewing and classification CLI commands."""

import asyncio
from typing import Annotated

import typer
from rich.table import Table

from email_nurse.cli import console, get_settings, messages_app


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
