"""Apple Reminders CLI commands."""

from typing import Annotated

import typer
from rich.table import Table

from email_nurse.cli import console, reminders_app


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


@reminders_app.command("create")
def reminders_create(
    name: Annotated[str, typer.Argument(help="Reminder title")],
    list_name: Annotated[str, typer.Option("--list", "-l", help="List name")] = "Reminders",
    body: Annotated[str, typer.Option("--body", "-b", help="Notes/body text")] = "",
    due: Annotated[str | None, typer.Option("--due", "-d", help="Due date (YYYY-MM-DD or YYYY-MM-DD HH:MM)")] = None,
    priority: Annotated[int, typer.Option("--priority", "-p", help="Priority: 0=none, 1=high, 5=medium, 9=low")] = 0,
) -> None:
    """Create a new reminder.

    Examples:
        email-nurse reminders create "Call Bob"
        email-nurse reminders create "Review report" --list Work --due 2025-01-15
        email-nurse reminders create "Urgent task" -l Work -p 1
    """
    from datetime import datetime

    from email_nurse.reminders import create_reminder
    from email_nurse.reminders.lists import RemindersAppNotRunningError

    # Parse due date if provided
    due_date = None
    if due:
        try:
            if " " in due:
                due_date = datetime.strptime(due, "%Y-%m-%d %H:%M")
            else:
                due_date = datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            console.print(f"[red]Error: Invalid date format '{due}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM[/red]")
            raise typer.Exit(1)

    try:
        reminder_id = create_reminder(
            name=name,
            list_name=list_name,
            body=body,
            due_date=due_date,
            priority=priority,
        )
        console.print(f"[green]✓ Created reminder in '{list_name}'[/green]")
        console.print(f"  ID: [dim]{reminder_id}[/dim]")
    except RemindersAppNotRunningError:
        console.print("[red]Error: Reminders.app is not running.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creating reminder:[/red] {e}")
        raise typer.Exit(1)


@reminders_app.command("complete")
def reminders_complete(
    reminder_id: Annotated[str, typer.Argument(help="Reminder ID")],
    list_name: Annotated[str, typer.Option("--list", "-l", help="List containing the reminder")] = "Reminders",
) -> None:
    """Mark a reminder as completed.

    The reminder ID can be found using 'reminders show <list> --verbose'.

    Example:
        email-nurse reminders complete "x-apple-reminder://ABC123" --list Work
    """
    from email_nurse.reminders import complete_reminder
    from email_nurse.reminders.lists import RemindersAppNotRunningError

    try:
        complete_reminder(reminder_id, list_name)
        console.print(f"[green]✓ Marked reminder as completed[/green]")
    except RemindersAppNotRunningError:
        console.print("[red]Error: Reminders.app is not running.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error completing reminder:[/red] {e}")
        raise typer.Exit(1)


@reminders_app.command("delete")
def reminders_delete(
    reminder_id: Annotated[str, typer.Argument(help="Reminder ID")],
    list_name: Annotated[str, typer.Option("--list", "-l", help="List containing the reminder")] = "Reminders",
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Delete a reminder permanently.

    The reminder ID can be found using 'reminders show <list> --verbose'.

    Example:
        email-nurse reminders delete "x-apple-reminder://ABC123" --list Work
    """
    from email_nurse.reminders import delete_reminder
    from email_nurse.reminders.lists import RemindersAppNotRunningError

    if not force:
        confirm = typer.confirm("Are you sure you want to delete this reminder?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            raise typer.Exit(0)

    try:
        delete_reminder(reminder_id, list_name)
        console.print(f"[green]✓ Deleted reminder[/green]")
    except RemindersAppNotRunningError:
        console.print("[red]Error: Reminders.app is not running.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error deleting reminder:[/red] {e}")
        raise typer.Exit(1)
