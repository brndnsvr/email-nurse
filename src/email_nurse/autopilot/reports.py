"""Daily activity report generation and delivery."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from email_nurse.calendar.events import CalendarEvent
    from email_nurse.reminders.reminders import Reminder
    from email_nurse.storage.database import AutopilotDatabase


class DailyReportGenerator:
    """Generates and sends daily activity reports."""

    def __init__(self, database: AutopilotDatabase) -> None:
        """
        Initialize the report generator.

        Args:
            database: Database instance for querying activity.
        """
        self.db = database

    def _get_tomorrow_events(self) -> list[CalendarEvent]:
        """Get calendar events for tomorrow."""
        from email_nurse.calendar.events import get_events

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today + timedelta(days=1)
        tomorrow_end = tomorrow_start + timedelta(days=1)

        try:
            return get_events(start_date=tomorrow_start, end_date=tomorrow_end)
        except Exception:
            return []  # Calendar app not running or error

    def _get_pending_reminders(self, limit: int = 50) -> list[Reminder]:
        """Get incomplete reminders, prioritizing those with due dates."""
        from email_nurse.reminders.reminders import get_reminders

        try:
            reminders = get_reminders(completed=False, limit=limit)
            # Sort: overdue first, then by due date, then no-date items
            return sorted(
                reminders,
                key=lambda r: (
                    r.due_date is None,  # Items without due dates last
                    r.due_date or datetime.max,
                ),
            )
        except Exception:
            return []  # Reminders app not running or error

    def generate_report(self, report_date: date | None = None) -> str:
        """
        Generate formatted report text for a given day.

        Args:
            report_date: Date to generate report for (defaults to today).

        Returns:
            Formatted plain-text report string.
        """
        activity = self.db.get_daily_activity(report_date)
        tomorrow_events = self._get_tomorrow_events()
        pending_reminders = self._get_pending_reminders()
        return self._format_report(activity, tomorrow_events, pending_reminders)

    def _format_report(
        self,
        activity: dict[str, Any],
        tomorrow_events: list[CalendarEvent] | None = None,
        pending_reminders: list[Reminder] | None = None,
    ) -> str:
        """Format activity data into readable report."""
        lines: list[str] = []
        report_date: date = activity["date"]
        date_str = report_date.strftime("%B %d, %Y")
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%A, %B %d")

        # Header
        lines.append("=" * 60)
        lines.append(f"          Email Nurse Daily Digest - {date_str}")
        lines.append("=" * 60)
        lines.append("")

        # Tomorrow's Schedule section
        if tomorrow_events is not None:
            lines.append(f"TOMORROW'S SCHEDULE ({tomorrow_date})")
            lines.append("-" * 40)
            if not tomorrow_events:
                lines.append("  No events scheduled for tomorrow.")
            else:
                for event in tomorrow_events:
                    if event.all_day:
                        time_str = "  [All-day]    "
                    else:
                        start = event.start_date.strftime("%I:%M %p").lstrip("0")
                        end = event.end_date.strftime("%I:%M %p").lstrip("0")
                        time_str = f"  {start:>8} - {end:<8}"
                    lines.append(f"{time_str} {event.summary}")
                    if event.location:
                        lines.append(f"               @ {event.location}")
            lines.append("")

        # Pending Reminders section
        if pending_reminders is not None:
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            lines.append(f"PENDING REMINDERS ({len(pending_reminders)} items)")
            lines.append("-" * 40)
            if not pending_reminders:
                lines.append("  All caught up! No pending reminders.")
            else:
                max_shown = 10
                for idx, reminder in enumerate(pending_reminders):
                    if idx >= max_shown:
                        remaining = len(pending_reminders) - idx
                        lines.append(f"  ... and {remaining} more")
                        break

                    if reminder.due_date:
                        if reminder.due_date < today_start:
                            # Overdue
                            due_str = reminder.due_date.strftime("%b %d")
                            prefix = f"  OVERDUE ({due_str}):"
                        elif reminder.due_date < today_end:
                            prefix = "  Due Today:"
                        else:
                            due_str = reminder.due_date.strftime("%b %d")
                            prefix = f"  Due {due_str}:"
                    else:
                        prefix = "  [No date]:"

                    # Truncate long reminder names
                    name = reminder.name
                    if len(name) > 40:
                        name = name[:37] + "..."
                    lines.append(f"{prefix} {name}")
            lines.append("")

        # Email Activity Summary section
        lines.append("EMAIL ACTIVITY")
        lines.append("-" * 14)

        total = activity["total"]
        action_counts = activity["action_counts"]
        error_count = activity["error_count"]

        if total == 0:
            lines.append("No email activity recorded today.")
            lines.append("")
        else:
            lines.append(f"Total Processed:  {total} email{'s' if total != 1 else ''}")

            # Action breakdown
            for action, count in sorted(action_counts.items()):
                action_display = action.replace("_", " ").title()
                lines.append(f"  * {action_display}: {count}")

            if error_count > 0:
                lines.append(f"Errors:           {error_count}")
            lines.append("")

        # By Folder section
        folder_counts = activity["folder_counts"]
        if folder_counts:
            lines.append("BY FOLDER")
            lines.append("-" * 9)
            for folder, count in sorted(
                folder_counts.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"  {folder}: {count}")
            lines.append("")

        # By Account section
        account_counts = activity["account_counts"]
        if account_counts:
            lines.append("BY ACCOUNT")
            lines.append("-" * 10)
            for account, count in sorted(
                account_counts.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"  {account}: {count}")
            lines.append("")

        # Detailed log section
        entries = activity["entries"]
        if entries:
            lines.append("-" * 60)
            lines.append("                      DETAILED LOG")
            lines.append("-" * 60)
            lines.append("")

            for entry in entries:
                lines.extend(self._format_entry(entry))
                lines.append("")

        # Footer
        lines.append("-" * 60)
        lines.append("Generated by email-nurse")

        return "\n".join(lines)

    def _format_entry(self, entry: dict[str, Any]) -> list[str]:
        """Format a single log entry."""
        lines: list[str] = []

        # Parse timestamp
        timestamp_str = entry.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            time_str = timestamp.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            time_str = "??:??:??"

        action = entry.get("action", "UNKNOWN").upper()
        sender = entry.get("sender", "Unknown sender")
        subject = entry.get("subject", "(no subject)")
        confidence = entry.get("confidence")

        # Get target folder from details JSON
        details_str = entry.get("details")
        target_folder = None
        if details_str:
            try:
                details = json.loads(details_str) if isinstance(details_str, str) else details_str
                target_folder = details.get("folder") or details.get("target_folder")
            except (json.JSONDecodeError, TypeError):
                pass

        # Format action line
        if target_folder:
            lines.append(f"[{time_str}] {action} -> {target_folder}")
        else:
            lines.append(f"[{time_str}] {action}")

        # Sender and subject
        lines.append(f"  From: {sender}")

        # Truncate subject if too long
        if len(subject) > 50:
            subject = subject[:47] + "..."
        lines.append(f"  Subject: {subject}")

        # Confidence if available
        if confidence is not None:
            lines.append(f"  Confidence: {int(confidence * 100)}%")

        return lines

    def _format_report_html(
        self,
        activity: dict[str, Any],
        tomorrow_events: list[CalendarEvent] | None = None,
        pending_reminders: list[Reminder] | None = None,
    ) -> str:
        """Format activity data into HTML email."""
        report_date: date = activity["date"]
        date_str = report_date.strftime("%B %d, %Y")
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%A, %B %d")

        total = activity["total"]
        action_counts = activity["action_counts"]
        error_count = activity["error_count"]
        folder_counts = activity["folder_counts"]
        account_counts = activity["account_counts"]
        entries = activity["entries"]

        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Build HTML
        html_parts = [
            '<!DOCTYPE html>',
            '<html>',
            '<head>',
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '<style>',
            '  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f5f5f7; }',
            '  .container { background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }',
            '  .header { text-align: center; border-bottom: 3px solid #007aff; padding-bottom: 20px; margin-bottom: 30px; }',
            '  .header h1 { margin: 0; color: #007aff; font-size: 28px; }',
            '  .header .date { color: #666; font-size: 16px; margin-top: 8px; }',
            '  .summary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; border-radius: 8px; margin-bottom: 30px; }',
            '  .summary h2 { margin: 0 0 16px 0; font-size: 20px; }',
            '  .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }',
            '  .stat-item { background: rgba(255,255,255,0.2); padding: 12px; border-radius: 6px; }',
            '  .stat-label { font-size: 13px; opacity: 0.9; margin-bottom: 4px; }',
            '  .stat-value { font-size: 24px; font-weight: bold; }',
            '  .section { margin-bottom: 30px; }',
            '  .section h3 { color: #007aff; font-size: 18px; margin-bottom: 16px; border-bottom: 2px solid #e5e5e7; padding-bottom: 8px; }',
            '  .section h3.calendar { color: #1a73e8; border-bottom-color: #1a73e8; }',
            '  .section h3.reminders { color: #f57c00; border-bottom-color: #f57c00; }',
            '  table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }',
            '  th { background: #f5f5f7; color: #333; font-weight: 600; text-align: left; padding: 12px; border-bottom: 2px solid #007aff; }',
            '  td { padding: 10px 12px; border-bottom: 1px solid #e5e5e7; }',
            '  tr:hover { background: #f9f9f9; }',
            '  .event-time { color: #666; font-size: 13px; white-space: nowrap; }',
            '  .event-title { font-weight: 500; }',
            '  .event-location { color: #666; font-size: 13px; }',
            '  .reminder-item { padding: 8px 0; border-bottom: 1px solid #e5e5e7; }',
            '  .reminder-item:last-child { border-bottom: none; }',
            '  .reminder-overdue { color: #d32f2f; }',
            '  .reminder-today { color: #1976d2; }',
            '  .reminder-due { color: #666; font-size: 13px; }',
            '  .log-entry { background: #f9f9f9; border-left: 4px solid #007aff; padding: 16px; margin-bottom: 12px; border-radius: 4px; }',
            '  .log-entry.error { border-left-color: #ff3b30; }',
            '  .log-time { color: #666; font-size: 13px; font-weight: 600; }',
            '  .log-action { color: #007aff; font-weight: 600; margin: 4px 0; }',
            '  .log-detail { color: #666; font-size: 14px; margin: 2px 0; }',
            '  .footer { text-align: center; color: #999; font-size: 13px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e5e7; }',
            '  .no-activity { text-align: center; color: #999; padding: 40px; }',
            '  .empty-section { color: #999; font-style: italic; padding: 16px 0; }',
            '</style>',
            '</head>',
            '<body>',
            '<div class="container">',
            '  <div class="header">',
            '    <h1>Email Nurse Daily Digest</h1>',
            f'    <div class="date">{date_str}</div>',
            '  </div>',
        ]

        # Tomorrow's Schedule section
        if tomorrow_events is not None:
            html_parts.append('  <div class="section">')
            html_parts.append(f'    <h3 class="calendar">📅 Tomorrow\'s Schedule ({tomorrow_date})</h3>')
            if not tomorrow_events:
                html_parts.append('    <div class="empty-section">No events scheduled for tomorrow.</div>')
            else:
                html_parts.append('    <table>')
                html_parts.append('      <tr><th style="width: 140px;">Time</th><th>Event</th><th>Location</th></tr>')
                for event in tomorrow_events:
                    if event.all_day:
                        time_str = "All day"
                    else:
                        start = event.start_date.strftime("%I:%M %p").lstrip("0")
                        end = event.end_date.strftime("%I:%M %p").lstrip("0")
                        time_str = f"{start} - {end}"
                    location = event.location or ""
                    html_parts.append(f'      <tr><td class="event-time">{time_str}</td><td class="event-title">{event.summary}</td><td class="event-location">{location}</td></tr>')
                html_parts.append('    </table>')
            html_parts.append('  </div>')

        # Pending Reminders section
        if pending_reminders is not None:
            html_parts.append('  <div class="section">')
            html_parts.append(f'    <h3 class="reminders">✅ Pending Reminders ({len(pending_reminders)} items)</h3>')
            if not pending_reminders:
                html_parts.append('    <div class="empty-section">All caught up! No pending reminders.</div>')
            else:
                html_parts.append('    <div>')
                max_shown = 10
                for idx, reminder in enumerate(pending_reminders):
                    if idx >= max_shown:
                        remaining = len(pending_reminders) - idx
                        html_parts.append(f'    <div class="reminder-item" style="color: #666; font-style: italic;">... and {remaining} more</div>')
                        break

                    if reminder.due_date:
                        if reminder.due_date < today_start:
                            due_str = reminder.due_date.strftime("%b %d")
                            prefix = f'<span class="reminder-overdue"><strong>⚠ OVERDUE</strong> ({due_str}):</span>'
                        elif reminder.due_date < today_end:
                            prefix = '<span class="reminder-today"><strong>📌 Due Today:</strong></span>'
                        else:
                            due_str = reminder.due_date.strftime("%b %d")
                            prefix = f'<span class="reminder-due">Due {due_str}:</span>'
                    else:
                        prefix = '<span class="reminder-due">[No date]:</span>'

                    name = reminder.name
                    if len(name) > 50:
                        name = name[:47] + "..."
                    html_parts.append(f'    <div class="reminder-item">{prefix} {name}</div>')
                html_parts.append('    </div>')
            html_parts.append('  </div>')

        # Summary section
        if total == 0:
            html_parts.append('  <div class="no-activity">No email activity recorded today.</div>')
        else:
            html_parts.append('  <div class="summary">')
            html_parts.append('    <h2>Summary</h2>')
            html_parts.append('    <div class="stat-grid">')
            html_parts.append('      <div class="stat-item">')
            html_parts.append('        <div class="stat-label">Total Processed</div>')
            html_parts.append(f'        <div class="stat-value">{total}</div>')
            html_parts.append('      </div>')

            for action, count in sorted(action_counts.items()):
                action_display = action.replace("_", " ").title()
                html_parts.append('      <div class="stat-item">')
                html_parts.append(f'        <div class="stat-label">{action_display}</div>')
                html_parts.append(f'        <div class="stat-value">{count}</div>')
                html_parts.append('      </div>')

            if error_count > 0:
                html_parts.append('      <div class="stat-item">')
                html_parts.append('        <div class="stat-label">Errors</div>')
                html_parts.append(f'        <div class="stat-value" style="color: #ff3b30;">{error_count}</div>')
                html_parts.append('      </div>')

            html_parts.append('    </div>')
            html_parts.append('  </div>')

        # By Folder section
        if folder_counts:
            html_parts.append('  <div class="section">')
            html_parts.append('    <h3>By Folder</h3>')
            html_parts.append('    <table>')
            html_parts.append('      <tr><th>Folder</th><th>Count</th></tr>')
            for folder, count in sorted(folder_counts.items(), key=lambda x: x[1], reverse=True):
                html_parts.append(f'      <tr><td>{folder}</td><td><strong>{count}</strong></td></tr>')
            html_parts.append('    </table>')
            html_parts.append('  </div>')

        # By Account section
        if account_counts:
            html_parts.append('  <div class="section">')
            html_parts.append('    <h3>By Account</h3>')
            html_parts.append('    <table>')
            html_parts.append('      <tr><th>Account</th><th>Count</th></tr>')
            for account, count in sorted(account_counts.items(), key=lambda x: x[1], reverse=True):
                html_parts.append(f'      <tr><td>{account}</td><td><strong>{count}</strong></td></tr>')
            html_parts.append('    </table>')
            html_parts.append('  </div>')

        # Detailed log section
        if entries:
            html_parts.append('  <div class="section">')
            html_parts.append('    <h3>Detailed Activity Log</h3>')

            for entry in entries:
                html_parts.extend(self._format_entry_html(entry))

            html_parts.append('  </div>')

        # Footer
        html_parts.append('  <div class="footer">')
        html_parts.append('    Generated by Email Nurse')
        html_parts.append('  </div>')
        html_parts.append('</div>')
        html_parts.append('</body>')
        html_parts.append('</html>')

        return '\n'.join(html_parts)

    def _format_entry_html(self, entry: dict[str, Any]) -> list[str]:
        """Format a single log entry as HTML."""
        lines: list[str] = []

        # Parse timestamp
        timestamp_str = entry.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            time_str = timestamp.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            time_str = "??:??:??"

        action = entry.get("action", "UNKNOWN").upper()
        sender = entry.get("sender", "Unknown sender")
        subject = entry.get("subject", "(no subject)")
        confidence = entry.get("confidence")

        # Get target folder from details JSON
        details_str = entry.get("details")
        target_folder = None
        if details_str:
            try:
                import json
                details = json.loads(details_str) if isinstance(details_str, str) else details_str
                target_folder = details.get("folder") or details.get("target_folder")
            except (json.JSONDecodeError, TypeError):
                pass

        # Determine if error
        is_error = action in ["ERROR", "SKIP"]
        entry_class = "log-entry error" if is_error else "log-entry"

        lines.append(f'    <div class="{entry_class}">')
        lines.append(f'      <div class="log-time">{time_str}</div>')

        if target_folder:
            lines.append(f'      <div class="log-action">{action} → {target_folder}</div>')
        else:
            lines.append(f'      <div class="log-action">{action}</div>')

        lines.append(f'      <div class="log-detail"><strong>From:</strong> {sender}</div>')

        # Truncate subject if too long
        if len(subject) > 60:
            subject = subject[:57] + "..."
        lines.append(f'      <div class="log-detail"><strong>Subject:</strong> {subject}</div>')

        if confidence is not None:
            lines.append(f'      <div class="log-detail"><strong>Confidence:</strong> {int(confidence * 100)}%</div>')

        lines.append('    </div>')

        return lines

    def send_report(
        self,
        to_address: str,
        report_date: date | None = None,
        from_account: str | None = None,
        sender_address: str | None = None,
    ) -> bool:
        """
        Generate and email the daily report.

        Args:
            to_address: Recipient email address.
            report_date: Date to report on (defaults to today).
            from_account: Account to send from (uses default if not specified).
            sender_address: Specific sender email address (must belong to from_account).

        Returns:
            True if email was sent successfully, False otherwise.
        """
        from email_nurse.config import Settings
        from email_nurse.mail.actions import compose_email, send_email_smtp

        settings = Settings()

        # Get activity data and PIM context for both plain text and HTML formatting
        activity = self.db.get_daily_activity(report_date)
        tomorrow_events = self._get_tomorrow_events()
        pending_reminders = self._get_pending_reminders()

        report_text = self._format_report(activity, tomorrow_events, pending_reminders)
        report_html = self._format_report_html(activity, tomorrow_events, pending_reminders)

        actual_date = report_date or date.today()
        subject = f"Email Nurse Daily Digest - {actual_date.strftime('%b %d, %Y')}"

        # Use direct SMTP if configured, otherwise fall back to Mail.app
        if settings.smtp_enabled and settings.smtp_host and settings.smtp_username and settings.smtp_password:
            return send_email_smtp(
                to_address=to_address,
                subject=subject,
                content=report_text,
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_username=settings.smtp_username,
                smtp_password=settings.smtp_password,
                from_address=settings.smtp_from_address or sender_address,
                use_tls=settings.smtp_use_tls,
                html_content=report_html,
            )
        else:
            # Fall back to Mail.app
            return compose_email(
                to_address=to_address,
                subject=subject,
                content=report_text,
                from_account=from_account,
                sender_address=sender_address,
                send_immediately=True,
            )
