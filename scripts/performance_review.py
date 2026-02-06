#!/usr/bin/env python3
"""Performance review script for sysm integration.

Usage:
    python scripts/performance_review.py [hours]

Examples:
    python scripts/performance_review.py           # Last 24 hours (default)
    python scripts/performance_review.py 12        # Last 12 hours
    python scripts/performance_review.py 48        # Last 48 hours
"""

import sys
from pathlib import Path

# Add src to path so we can import from email_nurse
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from email_nurse.performance_tracker import get_tracker


def main():
    """Run performance review."""
    hours = 24
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except ValueError:
            print(f"Invalid hours value: {sys.argv[1]}")
            print(__doc__)
            sys.exit(1)

    tracker = get_tracker()
    tracker.print_report(hours=hours)


if __name__ == "__main__":
    main()
