"""Apple Calendar CLI commands."""

from typing import Annotated

import typer
from rich.table import Table

from email_nurse.cli import calendar_app, console


@calendar_app.command("list")
def calendar_list() -> None:
    """List all calendars from Calendar.app."""
    from email_nurse.calendar import get_calendars
    from email_nurse.calendar.calendars import CalendarAppNotRunningError

    try:
        calendars = get_calendars()
    except CalendarAppNotRunningError:
        console.print("[red]Error: Calendar.app is not running.[/red]")
        console.print("Please open Calendar.app and try again.")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error accessing Calendar.app:[/red] {e}")
        raise typer.Exit(1)

    if not calendars:
        console.print("[yellow]No calendars found[/yellow]")
        return

    table = Table(title="Calendars")
    table.add_column("Name", style="cyan")
    table.add_column("Writable", width=8, justify="center")
    table.add_column("Description", style="dim", max_width=40)

    for cal in calendars:
        writable = "[green]✓[/green]" if cal.writable else "[dim]-[/dim]"
        desc = cal.description[:40] + "..." if len(cal.description) > 40 else cal.description
        table.add_row(cal.name, writable, desc)

    console.print(table)


@calendar_app.command("events")
def calendar_events(
    calendar_name: Annotated[str | None, typer.Option("--calendar", "-c", help="Filter to specific calendar")] = None,
    days: Annotated[int, typer.Option("--days", "-d", help="Number of days ahead")] = 30,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max events to show")] = 50,
) -> None:
    """Show upcoming events.

    Examples:
        email-nurse calendar events                     # Next 30 days, all calendars
        email-nurse calendar events --days 7           # Next 7 days
        email-nurse calendar events -c Work            # Only Work calendar
        email-nurse calendar events -c Personal -n 10  # 10 events from Personal
    """
    from datetime import datetime, timedelta

    from email_nurse.calendar import get_events
    from email_nurse.calendar.calendars import CalendarAppNotRunningError

    start_date = datetime.now()
    end_date = start_date + timedelta(days=days)

    try:
        events = get_events(
            calendar_name=calendar_name,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    except CalendarAppNotRunningError:
        console.print("[red]Error: Calendar.app is not running.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error fetching events:[/red] {e}")
        raise typer.Exit(1)

    if not events:
        cal_filter = f" in '{calendar_name}'" if calendar_name else ""
        console.print(f"[yellow]No events found{cal_filter} in the next {days} days[/yellow]")
        return

    title = f"Upcoming Events ({days} days)"
    if calendar_name:
        title = f"Events: {calendar_name} ({days} days)"

    table = Table(title=title)
    table.add_column("Date/Time", style="blue", width=18)
    table.add_column("Calendar", style="magenta", width=12)
    table.add_column("Summary", style="cyan", max_width=35)
    table.add_column("Location", style="dim", max_width=20)
    table.add_column("Duration", width=8, justify="right")

    for evt in events:
        if evt.all_day:
            time_str = evt.start_date.strftime("%Y-%m-%d") + " all day"
        else:
            time_str = evt.start_date.strftime("%Y-%m-%d %H:%M")

        location = evt.location[:20] + "..." if evt.location and len(evt.location) > 20 else (evt.location or "-")
        summary = evt.summary[:35] + "..." if len(evt.summary) > 35 else evt.summary

        table.add_row(time_str, evt.calendar_name[:12], summary, location, evt.duration_str)

    console.print(table)


@calendar_app.command("today")
def calendar_today(
    calendar_name: Annotated[str | None, typer.Option("--calendar", "-c", help="Filter to specific calendar")] = None,
) -> None:
    """Show today's events.

    Examples:
        email-nurse calendar today           # All calendars
        email-nurse calendar today -c Work   # Only Work calendar
    """
    from email_nurse.calendar import get_events_today
    from email_nurse.calendar.calendars import CalendarAppNotRunningError

    try:
        events = get_events_today(calendar_name=calendar_name)
    except CalendarAppNotRunningError:
        console.print("[red]Error: Calendar.app is not running.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error fetching events:[/red] {e}")
        raise typer.Exit(1)

    if not events:
        cal_filter = f" in '{calendar_name}'" if calendar_name else ""
        console.print(f"[yellow]No events today{cal_filter}[/yellow]")
        return

    from datetime import datetime

    title = f"Today's Events ({datetime.now().strftime('%A, %B %d')})"
    if calendar_name:
        title = f"{calendar_name}: Today"

    table = Table(title=title)
    table.add_column("Time", style="blue", width=12)
    table.add_column("Summary", style="cyan")
    table.add_column("Location", style="dim", max_width=25)

    for evt in events:
        if evt.all_day:
            time_str = "All day"
        else:
            time_str = evt.start_date.strftime("%H:%M") + f" ({evt.duration_str})"

        location = evt.location or "-"
        table.add_row(time_str, evt.summary, location)

    console.print(table)


@calendar_app.command("create")
def calendar_create(
    summary: Annotated[str, typer.Argument(help="Event title")],
    start: Annotated[str, typer.Option("--start", "-s", help="Start date/time (YYYY-MM-DD HH:MM or YYYY-MM-DD)")],
    end: Annotated[str | None, typer.Option("--end", "-e", help="End date/time (default: start + 1 hour)")] = None,
    calendar_name: Annotated[str, typer.Option("--calendar", "-c", help="Target calendar")] = "Calendar",
    location: Annotated[str, typer.Option("--location", "-l", help="Event location")] = "",
    all_day: Annotated[bool, typer.Option("--all-day", "-a", help="All-day event")] = False,
) -> None:
    """Create a calendar event.

    Examples:
        email-nurse calendar create "Team meeting" --start "2026-01-15 14:00"
        email-nurse calendar create "Lunch" -s "2026-01-20 12:00" -e "2026-01-20 13:00" -c Work
        email-nurse calendar create "Conference" -s 2026-02-01 --all-day
        email-nurse calendar create "Doctor" -s "2026-01-21 10:30" -l "123 Main St"
    """
    from datetime import datetime

    from email_nurse.calendar import create_event
    from email_nurse.calendar.calendars import CalendarAppNotRunningError

    # Parse start date
    try:
        if " " in start:
            start_date = datetime.strptime(start, "%Y-%m-%d %H:%M")
        else:
            start_date = datetime.strptime(start, "%Y-%m-%d")
            if not all_day:
                # Default to 9 AM for date-only input
                start_date = start_date.replace(hour=9)
    except ValueError:
        console.print(f"[red]Error: Invalid start date format: {start}[/red]")
        console.print("[dim]Use: YYYY-MM-DD HH:MM or YYYY-MM-DD[/dim]")
        raise typer.Exit(1)

    # Parse end date
    end_date = None
    if end:
        try:
            if " " in end:
                end_date = datetime.strptime(end, "%Y-%m-%d %H:%M")
            else:
                end_date = datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            console.print(f"[red]Error: Invalid end date format: {end}[/red]")
            raise typer.Exit(1)

    try:
        event_id = create_event(
            summary=summary,
            start_date=start_date,
            end_date=end_date,
            calendar_name=calendar_name,
            location=location,
            all_day=all_day,
        )
        console.print(f"[green]✓ Event created in '{calendar_name}'[/green]")
        console.print(f"  ID: [dim]{event_id}[/dim]")
    except CalendarAppNotRunningError:
        console.print("[red]Error: Calendar.app is not running.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error creating event:[/red] {e}")
        raise typer.Exit(1)
