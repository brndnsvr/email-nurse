"""Ops commands: self-healing and database maintenance."""

import logging
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from email_nurse.cli import get_settings, ops_app
from email_nurse.storage.database import AutopilotDatabase

logger = logging.getLogger(__name__)
console = Console()

AUTOPILOT_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.bss.email-nurse.plist"
STATE_DIR = Path.home() / ".config" / "email-nurse"


def _read_timestamp_file(path: Path) -> datetime | None:
    """Read a Unix epoch timestamp from a state file."""
    if not path.exists():
        return None
    try:
        epoch = int(path.read_text().strip())
        return datetime.fromtimestamp(epoch)
    except (ValueError, OSError):
        return None


def _write_timestamp_file(path: Path) -> None:
    """Write current Unix epoch to a state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(time.time())))


def _is_mail_running() -> bool:
    """Check if Mail.app is running."""
    result = subprocess.run(
        ["/usr/bin/pgrep", "-xq", "Mail"],
        capture_output=True,
    )
    return result.returncode == 0


def _get_db(settings=None):
    """Get database instance."""
    if settings is None:
        settings = get_settings()
    return AutopilotDatabase(settings.database_path)


# ─── stuck-check ──────────────────────────────────────────────────────────


@ops_app.command("stuck-check")
def stuck_check(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Report only, don't take action")] = False,
) -> None:
    """Check for stuck messages and restart services if needed."""
    settings = get_settings()
    db = _get_db(settings)

    stuck = db.get_stuck_messages(settings.ops_stuck_threshold_hours)
    count = len(stuck)

    if verbose:
        console.print(f"Stuck messages (>{settings.ops_stuck_threshold_hours}h): {count}")
        for msg in stuck[:10]:
            console.print(f"  {msg['account']}/{msg['mailbox']} - {msg['message_id'][:40]}... (since {msg['first_seen_at']})")
        if count > 10:
            console.print(f"  ... and {count - 10} more")

    if count < settings.ops_stuck_min_count:
        if verbose:
            console.print(f"[green]Healthy[/green] - {count} stuck < threshold {settings.ops_stuck_min_count}")
        db.log_action(
            message_id="ops",
            action="stuck-check:healthy",
            source="ops:stuck-check",
            details={"stuck_count": count, "threshold": settings.ops_stuck_min_count},
        )
        return

    # Check cooldown
    cooldown_file = STATE_DIR / "last-stuck-restart"
    last_action = _read_timestamp_file(cooldown_file)
    if last_action:
        cooldown_until = last_action + timedelta(hours=settings.ops_stuck_cooldown_hours)
        if datetime.now() < cooldown_until:
            remaining = cooldown_until - datetime.now()
            if verbose:
                console.print(
                    f"[yellow]Cooldown active[/yellow] - {count} stuck messages but last restart was "
                    f"{last_action:%H:%M}, cooldown until {cooldown_until:%H:%M} ({remaining.seconds // 60}m remaining)"
                )
            db.log_action(
                message_id="ops",
                action="stuck-check:cooldown",
                source="ops:stuck-check",
                details={"stuck_count": count, "cooldown_until": cooldown_until.isoformat()},
            )
            return

    # Take action
    console.print(f"[red]{count} stuck messages detected[/red] - restarting services")

    if dry_run:
        console.print("[yellow]DRY RUN[/yellow] - would restart Mail.app and autopilot")
        db.log_action(
            message_id="ops",
            action="stuck-check:dry-run",
            source="ops:stuck-check",
            details={"stuck_count": count},
        )
        return

    # Unload autopilot
    if verbose:
        console.print("Unloading autopilot service...")
    subprocess.run(
        ["/bin/launchctl", "unload", str(AUTOPILOT_PLIST)],
        capture_output=True,
    )

    # Kill any running autopilot processes
    subprocess.run(
        ["/usr/bin/pkill", "-f", "email-nurse autopilot"],
        capture_output=True,
    )

    # Quit Mail.app
    if verbose:
        console.print("Quitting Mail.app...")
    subprocess.run(
        ["/usr/bin/osascript", "-e", 'tell application "Mail" to quit'],
        capture_output=True,
    )

    # Wait 5 minutes
    if verbose:
        console.print("Waiting 5 minutes for Mail.app to fully quit...")
    time.sleep(300)

    # Open Mail.app
    if verbose:
        console.print("Opening Mail.app...")
    subprocess.run(["/usr/bin/open", "-a", "Mail"], capture_output=True)

    # Wait 1 minute for sync
    if verbose:
        console.print("Waiting 60s for Mail.app to sync...")
    time.sleep(60)

    # Reload autopilot
    if verbose:
        console.print("Reloading autopilot service...")
    subprocess.run(
        ["/bin/launchctl", "load", str(AUTOPILOT_PLIST)],
        capture_output=True,
    )

    _write_timestamp_file(cooldown_file)

    # Notify
    try:
        from email_nurse.applescript.notifications import notify_simple

        notify_simple(
            f"Restarted Mail.app + autopilot ({count} stuck messages)",
            title="Email Nurse Ops",
            subtitle="stuck-check",
        )
    except Exception:
        pass

    db.log_action(
        message_id="ops",
        action="stuck-check:restart",
        source="ops:stuck-check",
        details={"stuck_count": count},
    )
    console.print("[green]Restart complete[/green]")


# ─── process-health ───────────────────────────────────────────────────────


@ops_app.command("process-health")
def process_health(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Report only, don't take action")] = False,
) -> None:
    """Check autopilot activity and restart if silent too long."""
    settings = get_settings()
    db = _get_db(settings)

    last_ts = db.get_last_activity_timestamp()

    if last_ts is None:
        if verbose:
            console.print("[yellow]No audit_log entries found[/yellow] - nothing to check")
        return

    last_dt = datetime.fromisoformat(last_ts)
    age_minutes = (datetime.now() - last_dt).total_seconds() / 60

    if verbose:
        console.print(f"Last activity: {last_ts} ({age_minutes:.0f} minutes ago)")

    if age_minutes <= settings.ops_silent_minutes:
        if verbose:
            console.print(f"[green]Healthy[/green] - activity {age_minutes:.0f}m ago < threshold {settings.ops_silent_minutes}m")
        db.log_action(
            message_id="ops",
            action="process-health:healthy",
            source="ops:process-health",
            details={"last_activity_minutes": round(age_minutes), "threshold": settings.ops_silent_minutes},
        )
        return

    # Check cooldown
    cooldown_file = STATE_DIR / "last-health-action"
    last_action = _read_timestamp_file(cooldown_file)
    if last_action:
        cooldown_until = last_action + timedelta(minutes=settings.ops_health_cooldown_minutes)
        if datetime.now() < cooldown_until:
            remaining = cooldown_until - datetime.now()
            if verbose:
                console.print(
                    f"[yellow]Cooldown active[/yellow] - silent {age_minutes:.0f}m but last action was "
                    f"{last_action:%H:%M}, cooldown until {cooldown_until:%H:%M} ({remaining.seconds // 60}m remaining)"
                )
            return

    # Check if Mail.app is running — if not, that explains the silence
    mail_running = _is_mail_running()

    if not mail_running:
        msg = f"Autopilot silent {age_minutes:.0f}m — Mail.app is not running (expected)"
        if verbose:
            console.print(f"[yellow]{msg}[/yellow]")
        try:
            from email_nurse.applescript.notifications import notify_simple

            notify_simple(msg, title="Email Nurse Ops", subtitle="process-health")
        except Exception:
            pass
        db.log_action(
            message_id="ops",
            action="process-health:mail-down",
            source="ops:process-health",
            details={"silent_minutes": round(age_minutes), "mail_running": False},
        )
        _write_timestamp_file(cooldown_file)
        return

    console.print(f"[red]Autopilot silent for {age_minutes:.0f} minutes[/red] - restarting service")

    if dry_run:
        console.print("[yellow]DRY RUN[/yellow] - would reload autopilot service")
        db.log_action(
            message_id="ops",
            action="process-health:dry-run",
            source="ops:process-health",
            details={"silent_minutes": round(age_minutes)},
        )
        return

    # Unload + reload autopilot
    if verbose:
        console.print("Reloading autopilot service...")
    subprocess.run(
        ["/bin/launchctl", "unload", str(AUTOPILOT_PLIST)],
        capture_output=True,
    )
    time.sleep(2)
    subprocess.run(
        ["/bin/launchctl", "load", str(AUTOPILOT_PLIST)],
        capture_output=True,
    )

    _write_timestamp_file(cooldown_file)

    try:
        from email_nurse.applescript.notifications import notify_simple

        notify_simple(
            f"Reloaded autopilot (silent {age_minutes:.0f}m)",
            title="Email Nurse Ops",
            subtitle="process-health",
        )
    except Exception:
        pass

    db.log_action(
        message_id="ops",
        action="process-health:restart",
        source="ops:process-health",
        details={"silent_minutes": round(age_minutes)},
    )
    console.print("[green]Autopilot reloaded[/green]")


# ─── db-hygiene ───────────────────────────────────────────────────────────


def _human_bytes(n: int) -> str:
    """Format byte count for display."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


@ops_app.command("db-hygiene")
def db_hygiene(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Report only, don't delete")] = False,
) -> None:
    """Clean up old database records and vacuum."""
    settings = get_settings()
    db = _get_db(settings)

    retention = settings.ops_db_retention_days
    first_seen = settings.ops_db_first_seen_days

    # Before counts
    before = db.get_table_counts()
    if verbose:
        console.print(f"Retention: {retention}d (general), {first_seen}d (first_seen)")
        console.print("\n[bold]Before:[/bold]")
        for table, count in before.items():
            console.print(f"  {table}: {count:,}")

    if dry_run:
        console.print("\n[yellow]DRY RUN[/yellow] - showing what would be cleaned:")
        # For dry-run, just show counts but don't delete
        console.print(f"  audit_log: records older than {retention}d")
        console.print(f"  processed_emails: records older than {retention}d")
        console.print(f"  email_first_seen: records older than {first_seen}d")
        console.print(f"  created_reminders: records older than {retention}d")
        console.print(f"  created_events: records older than {retention}d")
        console.print(f"  rule_failures: records older than 7d")
        console.print(f"  pending_actions: resolved entries older than {first_seen}d")
        return

    # Run cleanups
    deleted = {}
    deleted["audit_log"] = db.cleanup_old_audit_log(retention)
    deleted["processed_emails"] = db.cleanup_old_records(retention)
    deleted["email_first_seen"] = db.cleanup_old_first_seen(first_seen)
    deleted["created_reminders"] = db.cleanup_old_reminder_records(retention)
    deleted["created_events"] = db.cleanup_old_event_records(retention)
    deleted["rule_failures"] = db.cleanup_old_rule_failures(7)
    deleted["pending_actions"] = db.cleanup_resolved_pending(first_seen)

    total_deleted = sum(deleted.values())

    # Vacuum
    bytes_freed = db.vacuum()

    # After counts
    after = db.get_table_counts()

    # Print report
    table = Table(title="DB Hygiene Report")
    table.add_column("Table", style="cyan")
    table.add_column("Before", justify="right")
    table.add_column("Deleted", justify="right", style="red")
    table.add_column("After", justify="right", style="green")

    for tbl in before:
        d = deleted.get(tbl, 0)
        style = "red" if d > 0 else "dim"
        table.add_row(tbl, f"{before[tbl]:,}", f"{d:,}" if d else "-", f"{after.get(tbl, 0):,}", style=style)

    console.print()
    console.print(table)
    console.print(f"\nTotal deleted: {total_deleted:,} rows")
    console.print(f"Space freed: {_human_bytes(bytes_freed)}")

    # Log summary
    db.log_action(
        message_id="ops",
        action="db-hygiene:complete",
        source="ops:db-hygiene",
        details={
            "deleted": deleted,
            "total_deleted": total_deleted,
            "bytes_freed": bytes_freed,
        },
    )
