"""Performance tracking for autopilot operations.

Tracks metrics across sessions to measure sysm performance impact.
"""

import json
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class OperationMetric(BaseModel):
    """A single operation metric."""

    timestamp: str = Field(description="ISO timestamp of operation")
    operation: str = Field(description="Operation name (e.g., 'fetch_messages')")
    provider: str | None = Field(default=None, description="Provider used (applescript/sysm)")
    duration_seconds: float = Field(description="Operation duration in seconds")
    message_count: int = Field(default=0, description="Number of messages processed")
    account: str | None = Field(default=None, description="Account name")
    mailbox: str | None = Field(default=None, description="Mailbox name")
    success: bool = Field(default=True, description="Whether operation succeeded")
    error: str | None = Field(default=None, description="Error message if failed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class PerformanceTracker:
    """Tracks performance metrics across sessions."""

    def __init__(self, metrics_file: Path | None = None):
        """Initialize tracker.

        Args:
            metrics_file: Path to metrics JSON file. Defaults to ~/.config/email-nurse/metrics.jsonl
        """
        if metrics_file is None:
            config_dir = Path.home() / ".config" / "email-nurse"
            config_dir.mkdir(parents=True, exist_ok=True)
            metrics_file = config_dir / "metrics.jsonl"

        self.metrics_file = metrics_file

    def log_metric(self, metric: OperationMetric) -> None:
        """Log a metric to the metrics file.

        Uses JSONL format (one JSON object per line) for easy append and parsing.

        Args:
            metric: Metric to log
        """
        with open(self.metrics_file, "a") as f:
            f.write(metric.model_dump_json() + "\n")

    @contextmanager
    def track_operation(
        self,
        operation: str,
        provider: str | None = None,
        account: str | None = None,
        mailbox: str | None = None,
        message_count: int = 0,
        **metadata,
    ):
        """Context manager to track operation duration.

        Usage:
            with tracker.track_operation("fetch_messages", provider="sysm", message_count=50):
                # ... do work ...
                pass

        Args:
            operation: Operation name
            provider: Provider used (applescript/sysm)
            account: Account name
            mailbox: Mailbox name
            message_count: Number of messages
            **metadata: Additional metadata
        """
        start_time = time.time()
        success = True
        error = None

        try:
            yield
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            duration = time.time() - start_time
            metric = OperationMetric(
                timestamp=datetime.now().isoformat(),
                operation=operation,
                provider=provider,
                duration_seconds=round(duration, 3),
                message_count=message_count,
                account=account,
                mailbox=mailbox,
                success=success,
                error=error,
                metadata=metadata,
            )
            self.log_metric(metric)

    def get_metrics(
        self,
        since: datetime | None = None,
        operation: str | None = None,
        provider: str | None = None,
    ) -> list[OperationMetric]:
        """Read metrics from file with optional filtering.

        Args:
            since: Only return metrics after this timestamp
            operation: Filter by operation name
            provider: Filter by provider

        Returns:
            List of metrics matching filters
        """
        if not self.metrics_file.exists():
            return []

        metrics = []
        with open(self.metrics_file) as f:
            for line in f:
                metric = OperationMetric.model_validate_json(line)

                # Apply filters
                if since and datetime.fromisoformat(metric.timestamp) < since:
                    continue
                if operation and metric.operation != operation:
                    continue
                if provider and metric.provider != provider:
                    continue

                metrics.append(metric)

        return metrics

    def generate_report(self, hours: int = 24) -> dict[str, Any]:
        """Generate performance report for the last N hours.

        Args:
            hours: Number of hours to include in report

        Returns:
            Report dictionary with statistics
        """
        since = datetime.now() - timedelta(hours=hours)
        metrics = self.get_metrics(since=since)

        if not metrics:
            return {
                "period_hours": hours,
                "start_time": since.isoformat(),
                "end_time": datetime.now().isoformat(),
                "total_operations": 0,
                "message": "No metrics found for this period",
            }

        # Overall stats
        total_ops = len(metrics)
        successful_ops = sum(1 for m in metrics if m.success)
        failed_ops = total_ops - successful_ops
        total_messages = sum(m.message_count for m in metrics)
        total_duration = sum(m.duration_seconds for m in metrics)

        # Provider breakdown
        provider_stats = {}
        for provider in ["applescript", "sysm", None]:
            provider_metrics = [m for m in metrics if m.provider == provider]
            if provider_metrics:
                provider_name = provider or "unknown"
                provider_stats[provider_name] = {
                    "operations": len(provider_metrics),
                    "messages": sum(m.message_count for m in provider_metrics),
                    "total_duration": round(sum(m.duration_seconds for m in provider_metrics), 2),
                    "avg_duration": round(
                        sum(m.duration_seconds for m in provider_metrics) / len(provider_metrics), 3
                    ),
                    "avg_messages_per_op": round(
                        sum(m.message_count for m in provider_metrics) / len(provider_metrics), 1
                    ),
                }

        # Operation type breakdown
        operation_stats = {}
        for op in set(m.operation for m in metrics):
            op_metrics = [m for m in metrics if m.operation == op]
            operation_stats[op] = {
                "count": len(op_metrics),
                "avg_duration": round(sum(m.duration_seconds for m in op_metrics) / len(op_metrics), 3),
                "total_duration": round(sum(m.duration_seconds for m in op_metrics), 2),
                "success_rate": round(sum(1 for m in op_metrics if m.success) / len(op_metrics), 2),
            }

        # Message retrieval performance (fetch_messages operations only)
        fetch_metrics = [m for m in metrics if m.operation == "fetch_messages" and m.message_count > 0]
        fetch_stats = None
        if fetch_metrics:
            by_provider = {}
            for provider in ["applescript", "sysm"]:
                provider_fetches = [m for m in fetch_metrics if m.provider == provider]
                if provider_fetches:
                    durations = [m.duration_seconds for m in provider_fetches]
                    msg_counts = [m.message_count for m in provider_fetches]
                    by_provider[provider] = {
                        "operations": len(provider_fetches),
                        "total_messages": sum(msg_counts),
                        "avg_duration": round(sum(durations) / len(durations), 3),
                        "min_duration": round(min(durations), 3),
                        "max_duration": round(max(durations), 3),
                        "avg_messages_per_op": round(sum(msg_counts) / len(msg_counts), 1),
                    }

            fetch_stats = {
                "total_fetches": len(fetch_metrics),
                "total_messages_fetched": sum(m.message_count for m in fetch_metrics),
                "by_provider": by_provider,
            }

            # Calculate speedup if both providers have data
            if "sysm" in by_provider and "applescript" in by_provider:
                sysm_avg = by_provider["sysm"]["avg_duration"]
                applescript_avg = by_provider["applescript"]["avg_duration"]
                if applescript_avg > 0:
                    speedup = ((applescript_avg - sysm_avg) / applescript_avg) * 100
                    fetch_stats["sysm_speedup_percent"] = round(speedup, 1)

        return {
            "period_hours": hours,
            "start_time": since.isoformat(),
            "end_time": datetime.now().isoformat(),
            "total_operations": total_ops,
            "successful_operations": successful_ops,
            "failed_operations": failed_ops,
            "total_messages_processed": total_messages,
            "total_duration_seconds": round(total_duration, 2),
            "avg_duration_per_operation": round(total_duration / total_ops, 3) if total_ops > 0 else 0,
            "provider_stats": provider_stats,
            "operation_stats": operation_stats,
            "message_retrieval": fetch_stats,
        }

    def print_report(self, hours: int = 24) -> None:
        """Print a formatted report to console.

        Args:
            hours: Number of hours to include in report
        """
        report = self.generate_report(hours)

        print(f"\n{'='*70}")
        print(f"PERFORMANCE REPORT - Last {hours} hours")
        print(f"{'='*70}")
        print(f"Period: {report['start_time']} to {report['end_time']}")
        print(f"\nOVERALL STATS:")
        print(f"  Total Operations: {report['total_operations']}")
        print(f"  Successful: {report['successful_operations']}")
        print(f"  Failed: {report['failed_operations']}")
        print(f"  Total Messages: {report['total_messages_processed']}")
        print(f"  Total Duration: {report['total_duration_seconds']}s")
        print(f"  Avg per Operation: {report['avg_duration_per_operation']}s")

        if report.get("provider_stats"):
            print(f"\nPROVIDER BREAKDOWN:")
            for provider, stats in report["provider_stats"].items():
                print(f"  {provider.upper()}:")
                print(f"    Operations: {stats['operations']}")
                print(f"    Messages: {stats['messages']}")
                print(f"    Total Duration: {stats['total_duration']}s")
                print(f"    Avg Duration: {stats['avg_duration']}s")
                print(f"    Avg Messages/Op: {stats['avg_messages_per_op']}")

        if report.get("message_retrieval"):
            fetch = report["message_retrieval"]
            print(f"\nMESSAGE RETRIEVAL PERFORMANCE:")
            print(f"  Total Fetches: {fetch['total_fetches']}")
            print(f"  Total Messages: {fetch['total_messages_fetched']}")

            if "by_provider" in fetch:
                for provider, stats in fetch["by_provider"].items():
                    print(f"\n  {provider.upper()}:")
                    print(f"    Operations: {stats['operations']}")
                    print(f"    Messages: {stats['total_messages']}")
                    print(f"    Avg Duration: {stats['avg_duration']}s")
                    print(f"    Min/Max: {stats['min_duration']}s / {stats['max_duration']}s")
                    print(f"    Avg Messages/Op: {stats['avg_messages_per_op']}")

            if "sysm_speedup_percent" in fetch:
                speedup = fetch["sysm_speedup_percent"]
                print(f"\n  ⚡ SYSM SPEEDUP: {speedup:+.1f}%")
                if speedup > 0:
                    print(f"     sysm is {speedup:.1f}% faster than AppleScript")
                else:
                    print(f"     sysm is {abs(speedup):.1f}% slower than AppleScript")

        if report.get("operation_stats"):
            print(f"\nOPERATION BREAKDOWN:")
            for op, stats in report["operation_stats"].items():
                print(f"  {op}:")
                print(f"    Count: {stats['count']}")
                print(f"    Avg Duration: {stats['avg_duration']}s")
                print(f"    Success Rate: {stats['success_rate']*100:.0f}%")

        print(f"{'='*70}\n")


# Global tracker instance
_tracker: PerformanceTracker | None = None


def get_tracker() -> PerformanceTracker:
    """Get or create global tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = PerformanceTracker()
    return _tracker
