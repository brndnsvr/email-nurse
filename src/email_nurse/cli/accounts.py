"""Account management CLI commands."""

from typing import Annotated

import typer
from rich.table import Table

from email_nurse.cli import accounts_app, console


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
