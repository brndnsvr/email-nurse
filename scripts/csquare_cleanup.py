#!/usr/bin/env python3
"""
One-time cleanup: DELETE CSquare INBOX messages older than 180 days.
Moves to Trash (works on Exchange accounts).
Processes in small batches to avoid AppleScript timeouts.
"""

import subprocess
import time
from datetime import datetime, timedelta

ACCOUNT = "CSquare"
SOURCE_MAILBOX = "Inbox"
DAYS_OLD = 180
BATCH_SIZE = 20
DELAY_BETWEEN_BATCHES = 2  # seconds

def run_applescript(script: str, timeout: int = 120) -> str:
    """Run AppleScript and return output."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise Exception(f"AppleScript error: {result.stderr}")
    return result.stdout.strip()


def get_counts() -> tuple[int, int]:
    """Get inbox count and old message count."""
    cutoff_date = datetime.now() - timedelta(days=DAYS_OLD)
    cutoff_str = cutoff_date.strftime("%A, %B %d, %Y")

    script = f'''
    tell application "Mail"
        set acct to account "{ACCOUNT}"
        set srcBox to mailbox "{SOURCE_MAILBOX}" of acct
        set cutoffDate to date "{cutoff_str}"

        set totalCount to count of messages of srcBox
        set oldCount to count of (messages of srcBox whose date received < cutoffDate)

        return (totalCount as text) & "," & (oldCount as text)
    end tell
    '''
    try:
        result = run_applescript(script, timeout=180)
        parts = result.split(",")
        return int(parts[0]), int(parts[1])
    except Exception as e:
        print(f"  Warning counting: {e}")
        return -1, -1


def delete_batch() -> tuple[int, int]:
    """Delete a batch of old messages. Returns (found, deleted)."""
    cutoff_date = datetime.now() - timedelta(days=DAYS_OLD)
    cutoff_str = cutoff_date.strftime("%A, %B %d, %Y")

    script = f'''
    tell application "Mail"
        set acct to account "{ACCOUNT}"
        set srcBox to mailbox "{SOURCE_MAILBOX}" of acct
        set cutoffDate to date "{cutoff_str}"

        -- Get old messages
        set oldMsgs to (messages of srcBox whose date received < cutoffDate)
        set totalFound to count of oldMsgs

        if totalFound = 0 then
            return "0,0"
        end if

        -- Limit to batch size
        set batchLimit to {BATCH_SIZE}
        if totalFound > batchLimit then
            set msgsToDelete to items 1 thru batchLimit of oldMsgs
        else
            set msgsToDelete to oldMsgs
        end if

        -- Delete each message (moves to Trash)
        set deletedCount to 0
        repeat with msg in msgsToDelete
            try
                delete msg
                set deletedCount to deletedCount + 1
            end try
        end repeat

        return (totalFound as text) & "," & (deletedCount as text)
    end tell
    '''
    try:
        result = run_applescript(script, timeout=180)
        parts = result.split(",")
        return int(parts[0]), int(parts[1])
    except subprocess.TimeoutExpired:
        print(f"\n  Timeout! Waiting and retrying...")
        return -1, 0
    except Exception as e:
        print(f"\n  Error: {e}")
        return -1, 0


def main():
    print(f"=" * 60)
    print(f"CSquare Inbox Cleanup (DELETE TO TRASH)")
    print(f"  Deleting messages older than {DAYS_OLD} days")
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  Messages go to Trash (recoverable)")
    print(f"=" * 60)
    print()

    print("Getting initial counts...", end=" ", flush=True)
    inbox_count, old_count = get_counts()
    if old_count == 0:
        print("no old messages found! Nothing to do.")
        return
    elif old_count < 0:
        print("couldn't count (will proceed anyway)")
    else:
        print(f"done")
        print(f"  Inbox total: {inbox_count}")
        print(f"  Messages older than {DAYS_OLD} days: {old_count}")

    input("\nPress Enter to start deleting (Ctrl+C to cancel)...")

    total_deleted = 0
    batch_num = 0
    last_found = old_count

    while True:
        batch_num += 1
        print(f"\nBatch {batch_num}: ", end="", flush=True)

        found, deleted = delete_batch()

        if found == 0:
            print("no more old messages found.")
            break
        elif found < 0:
            # Error or timeout, wait and retry
            time.sleep(5)
            continue

        total_deleted += deleted
        remaining = found - deleted
        print(f"found {found}, deleted {deleted}. (Total deleted: {total_deleted}, ~{remaining} remaining)")

        if deleted == 0:
            print("  No messages deleted this batch, stopping.")
            break

        # Check if count is actually decreasing
        if found >= last_found and batch_num > 3:
            print("  Warning: Count not decreasing, checking...")
            _, actual_old = get_counts()
            if actual_old >= last_found:
                print(f"  Delete not working (still {actual_old} old). Stopping.")
                break
            else:
                print(f"  OK, actually {actual_old} remaining.")
                last_found = actual_old
        else:
            last_found = found

        time.sleep(DELAY_BETWEEN_BATCHES)

    print()
    print(f"=" * 60)
    print(f"Done! Deleted {total_deleted} messages (now in Trash)")
    print(f"=" * 60)


if __name__ == "__main__":
    main()
