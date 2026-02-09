#!/usr/bin/env python3
"""
One-time CSquare inbox cleanup with age-based triage.

Brackets (relative to Feb 5, 2026):
  Stale (7+ months):   Before Jul 5, 2025  -> Auto-archive, no review
  Aging (5-7 months):  Jul 5 - Sep 5, 2025 -> AI review (aggressive)
  Recent (3-5 months): Sep 5 - Nov 5, 2025 -> AI review (conservative)
  Current (<3 months): After Nov 5, 2025   -> Don't touch

Usage:
  python scripts/csquare_cleanup.py              # dry-run (default)
  python scripts/csquare_cleanup.py --execute    # actually move messages
"""

import argparse
import json
import logging
import os
import re
import signal
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Add project root to path so we can import email_nurse
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Load config from production .env (override empty values)
_env_file = Path.home() / ".config" / "email-nurse" / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if val and not os.environ.get(key):
                os.environ[key] = val

from email_nurse.applescript.base import escape_applescript_string, run_applescript
from email_nurse.mail.actions import PendingMove, move_messages_batch
from email_nurse.mail.sysm import run_sysm_json, SysmError

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# -- Constants ----------------------------------------------------------------

ACCOUNT = "CSquare"
MAILBOX = "Inbox"
ARCHIVE_MAILBOX = "Archive"
TRASH_MAILBOX = "Deleted Items"

# Age bracket cutoff dates
STALE_CUTOFF = datetime(2025, 7, 5)      # Before this = stale (7+ months)
AGING_CUTOFF = datetime(2025, 9, 5)      # Before this = aging (5-7 months)
RECENT_CUTOFF = datetime(2025, 11, 5)    # Before this = recent (3-5 months)
# After RECENT_CUTOFF = current (don't touch)

BATCH_SIZE = 15
BATCH_DELAY = 2  # seconds between batch moves

# AI classification
AI_MODEL = "claude-haiku-4-5-20251001"
MAX_CONTENT_CHARS = 2000
AI_RETRIES = 3
AI_RETRY_DELAY = 2  # seconds


# -- Data structures ----------------------------------------------------------

@dataclass
class MessageInfo:
    """Lightweight message metadata from enumeration."""
    id: str
    subject: str
    sender: str
    date_received: datetime | None
    bracket: str = ""  # stale, aging, recent, current
    action: str = ""   # archive, trash, keep
    category: str = "" # newsletter, marketing, personal, business, automated
    reasoning: str = ""
    thread_key: str = ""


@dataclass
class ThreadGroup:
    """Group of messages sharing a normalized subject."""
    key: str
    messages: list[MessageInfo] = field(default_factory=list)
    representative: MessageInfo | None = None
    action: str = ""
    category: str = ""
    reasoning: str = ""


# -- Audit log ----------------------------------------------------------------

class AuditLog:
    """Append-only JSONL audit log."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = open(path, "a")

    def log(self, **kwargs):
        kwargs["timestamp"] = datetime.now().isoformat()
        self._fh.write(json.dumps(kwargs) + "\n")
        self._fh.flush()

    def close(self):
        self._fh.close()


# -- Phase 1: Enumerate -------------------------------------------------------

def enumerate_messages() -> list[MessageInfo]:
    """Fetch all CSquare Inbox message metadata via AppleScript."""
    print("Phase 1: Enumerating CSquare Inbox messages...")

    account_escaped = escape_applescript_string(ACCOUNT)
    mailbox_escaped = escape_applescript_string(MAILBOX)

    script = f'''
    tell application "Mail"
        set output to ""
        set RS to (ASCII character 30)
        set US to (ASCII character 31)

        repeat with msg in (messages of mailbox "{mailbox_escaped}" of account "{account_escaped}")
            set msgId to id of msg as string
            set msgSubject to subject of msg
            set msgSender to sender of msg
            set msgDateReceived to date received of msg as string

            if output is not "" then set output to output & RS
            set output to output & msgId & US & msgSubject & US & msgSender & US & msgDateReceived
        end repeat

        return output
    end tell
    '''

    result = run_applescript(script, timeout=600)
    if not result:
        return []

    messages = []
    for record in result.split("\x1e"):
        parts = record.split("\x1f")
        if len(parts) >= 4:
            messages.append(MessageInfo(
                id=parts[0],
                subject=parts[1],
                sender=parts[2],
                date_received=_parse_date(parts[3]),
            ))

    print(f"  Found {len(messages)} messages")
    return messages


def _parse_date(date_str: str) -> datetime | None:
    """Parse AppleScript date string."""
    if not date_str or date_str == "missing value":
        return None
    formats = [
        "%A, %B %d, %Y at %I:%M:%S %p",
        "%A, %B %d, %Y at %H:%M:%S",
        "%a, %b %d, %Y at %I:%M:%S %p",
        "%B %d, %Y at %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


# -- Phase 2: Categorize by age -----------------------------------------------

def categorize_by_age(messages: list[MessageInfo]) -> dict[str, list[MessageInfo]]:
    """Sort messages into age brackets."""
    print("\nPhase 2: Categorizing by age...")

    buckets: dict[str, list[MessageInfo]] = {
        "stale": [],
        "aging": [],
        "recent": [],
        "current": [],
        "unknown": [],  # no date
    }

    for msg in messages:
        if msg.date_received is None:
            msg.bracket = "unknown"
            buckets["unknown"].append(msg)
        elif msg.date_received < STALE_CUTOFF:
            msg.bracket = "stale"
            msg.action = "archive"
            buckets["stale"].append(msg)
        elif msg.date_received < AGING_CUTOFF:
            msg.bracket = "aging"
            buckets["aging"].append(msg)
        elif msg.date_received < RECENT_CUTOFF:
            msg.bracket = "recent"
            buckets["recent"].append(msg)
        else:
            msg.bracket = "current"
            buckets["current"].append(msg)

    print()
    print(f"  {'Bracket':<20} {'Count':>6}  Action")
    print(f"  {'-'*20} {'-'*6}  {'-'*30}")
    print(f"  {'Stale (7+ mo)':<20} {len(buckets['stale']):>6}  Auto-archive (no review)")
    print(f"  {'Aging (5-7 mo)':<20} {len(buckets['aging']):>6}  AI review (aggressive)")
    print(f"  {'Recent (3-5 mo)':<20} {len(buckets['recent']):>6}  AI review (conservative)")
    print(f"  {'Current (<3 mo)':<20} {len(buckets['current']):>6}  Don't touch")
    if buckets["unknown"]:
        print(f"  {'Unknown date':<20} {len(buckets['unknown']):>6}  Keep (no date)")

    return buckets


# -- Phase 3: AI Classification -----------------------------------------------

def normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd:/FW: prefixes and normalize whitespace for thread grouping."""
    cleaned = re.sub(r"^(re|fwd?|fw)\s*:\s*", "", subject, flags=re.IGNORECASE)
    # Repeat to handle nested Re: Re: Fwd:
    cleaned = re.sub(r"^(re|fwd?|fw)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(re|fwd?|fw)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().lower()


def group_into_threads(messages: list[MessageInfo]) -> list[ThreadGroup]:
    """Group messages by normalized subject into threads."""
    thread_map: dict[str, ThreadGroup] = {}
    for msg in messages:
        key = normalize_subject(msg.subject)
        msg.thread_key = key
        if key not in thread_map:
            thread_map[key] = ThreadGroup(key=key)
        thread_map[key].messages.append(msg)

    # Pick representative: most recent message in each thread
    for group in thread_map.values():
        group.messages.sort(
            key=lambda m: m.date_received or datetime.min, reverse=True
        )
        group.representative = group.messages[0]

    return list(thread_map.values())


def load_message_content(msg_id: str) -> str:
    """Load message content via sysm, falling back to AppleScript."""
    # Try sysm first
    try:
        data = run_sysm_json(["mail", "read", msg_id, "--json"], timeout=15)
        if isinstance(data, dict):
            return data.get("content", "")
        elif isinstance(data, list) and data:
            return data[0].get("content", "")
    except SysmError:
        pass

    # Fallback: AppleScript
    try:
        mailbox_escaped = escape_applescript_string(MAILBOX)
        account_escaped = escape_applescript_string(ACCOUNT)
        script = f'''
        tell application "Mail"
            set msg to first message of mailbox "{mailbox_escaped}" of account "{account_escaped}" whose id is {msg_id}
            set msgContent to ""
            try
                set msgContent to content of msg
                if length of msgContent > {MAX_CONTENT_CHARS} then
                    set msgContent to text 1 thru {MAX_CONTENT_CHARS} of msgContent
                end if
            end try
            return msgContent
        end tell
        '''
        return run_applescript(script, timeout=30) or ""
    except Exception:
        return ""


def classify_thread(thread: ThreadGroup, bracket: str) -> dict:
    """Classify a thread using Claude Haiku. Returns {"action", "category", "reasoning"}."""
    import anthropic

    msg = thread.representative
    content = load_message_content(msg.id)
    snippet = content[:MAX_CONTENT_CHARS] if content else "(no content available)"

    if bracket == "aging":
        guidelines = (
            "Be AGGRESSIVE with cleanup. Most messages this old (5-7 months) should be archived or trashed. "
            "Newsletters, marketing, automated notifications, and old business correspondence -> archive or trash. "
            "Only keep messages that are clearly unresolved personal conversations or action items."
        )
    else:
        guidelines = (
            "Be CONSERVATIVE with cleanup. These messages are 3-5 months old. "
            "Keep anything that might still be relevant or need follow-up. "
            "Only archive/trash clear newsletters, marketing, and spam-like messages."
        )

    prompt = f"""Classify this email for inbox cleanup. Respond ONLY with valid JSON, no other text.

Guidelines: {guidelines}

Email:
- From: {msg.sender}
- Subject: {msg.subject}
- Date: {msg.date_received}
- Content (snippet): {snippet}

Respond with exactly this JSON format:
{{"action": "archive|trash|keep", "category": "newsletter|marketing|personal|business|automated", "reasoning": "brief reason"}}"""

    client = anthropic.Anthropic()

    for attempt in range(AI_RETRIES):
        try:
            response = client.messages.create(
                model=AI_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Extract JSON from response (handle markdown code blocks)
            if "```" in text:
                text = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                text = text.group(1) if text else ""
            return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            if attempt < AI_RETRIES - 1:
                time.sleep(AI_RETRY_DELAY * (attempt + 1))
            else:
                logger.warning(f"AI classification failed for '{msg.subject}': {e}")
                return {"action": "keep", "category": "unknown", "reasoning": f"AI error: {e}"}

    return {"action": "keep", "category": "unknown", "reasoning": "exhausted retries"}


def classify_bracket(messages: list[MessageInfo], bracket: str) -> list[MessageInfo]:
    """Classify all messages in a bracket using AI, grouped by thread."""
    if not messages:
        return messages

    label = "Aging (5-7 mo)" if bracket == "aging" else "Recent (3-5 mo)"
    print(f"\n  Classifying {label} bracket ({len(messages)} messages)...")

    threads = group_into_threads(messages)
    print(f"    {len(threads)} unique threads to classify")

    classified = 0
    for i, thread in enumerate(threads, 1):
        result = classify_thread(thread, bracket)
        thread.action = result["action"]
        thread.category = result.get("category", "unknown")
        thread.reasoning = result.get("reasoning", "")

        # Apply to all thread members
        for msg in thread.messages:
            msg.action = thread.action
            msg.category = thread.category
            msg.reasoning = thread.reasoning

        classified += 1
        if classified % 10 == 0 or classified == len(threads):
            print(f"    Classified {classified}/{len(threads)} threads", end="\r")

    print(f"    Classified {len(threads)}/{len(threads)} threads")
    return messages


def run_ai_classification(buckets: dict[str, list[MessageInfo]]):
    """Phase 3: AI classification of aging and recent brackets."""
    print("\nPhase 3: AI Classification...")

    if not buckets["aging"] and not buckets["recent"]:
        print("  No messages in AI review brackets. Skipping.")
        return

    classify_bracket(buckets["aging"], "aging")
    classify_bracket(buckets["recent"], "recent")


# -- Phase 4: Summary ---------------------------------------------------------

def present_summary(buckets: dict[str, list[MessageInfo]]) -> dict[str, list[MessageInfo]]:
    """Show per-bracket breakdown and return actionable messages."""
    print("\n" + "=" * 60)
    print("Phase 4: Cleanup Summary")
    print("=" * 60)

    actions: dict[str, list[MessageInfo]] = {
        "archive": [],
        "trash": [],
        "keep": [],
    }

    # Stale -> all archive
    for msg in buckets["stale"]:
        actions["archive"].append(msg)

    # AI-classified brackets
    for bracket in ("aging", "recent"):
        for msg in buckets[bracket]:
            bucket = actions.get(msg.action, actions["keep"])
            bucket.append(msg)

    # Current + unknown -> keep (not tracked in actions)

    print(f"\n  Action breakdown:")
    print(f"    Archive: {len(actions['archive'])} messages")
    print(f"      - Stale (auto): {len(buckets['stale'])}")
    ai_archive = [m for m in actions["archive"] if m.bracket != "stale"]
    print(f"      - AI-classified: {len(ai_archive)}")
    print(f"    Trash:   {len(actions['trash'])} messages")
    print(f"    Keep:    {len(actions['keep'])} messages")
    print(f"    Current: {len(buckets['current'])} messages (untouched)")

    # Top senders being archived/trashed
    moved = actions["archive"] + actions["trash"]
    if moved:
        sender_counts: dict[str, int] = defaultdict(int)
        for msg in moved:
            sender_counts[msg.sender] += 1
        top_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        print(f"\n  Top senders being cleaned up:")
        for sender, count in top_senders:
            print(f"    {count:>4}  {sender[:60]}")

    # Sample subjects per action
    for action_name in ("archive", "trash", "keep"):
        msgs = actions[action_name]
        if msgs:
            print(f"\n  Sample {action_name} subjects:")
            for msg in msgs[:5]:
                bracket_tag = f"[{msg.bracket}]"
                cat_tag = f"[{msg.category}]" if msg.category else ""
                print(f"    {bracket_tag:<10} {cat_tag:<14} {msg.subject[:50]}")
            if len(msgs) > 5:
                print(f"    ... and {len(msgs) - 5} more")

    return actions


# -- Phase 5: Execute ---------------------------------------------------------

def execute_moves(actions: dict[str, list[MessageInfo]], audit: AuditLog):
    """Execute the actual message moves."""
    print("\n" + "=" * 60)
    print("Phase 5: Executing moves")
    print("=" * 60)

    archive_msgs = actions["archive"]
    trash_msgs = actions["trash"]

    total = len(archive_msgs) + len(trash_msgs)
    if total == 0:
        print("  Nothing to move.")
        return

    done = 0
    failed = 0

    def process_batch(messages: list[MessageInfo], target_mailbox: str, label: str):
        nonlocal done, failed
        for i in range(0, len(messages), BATCH_SIZE):
            batch = messages[i:i + BATCH_SIZE]
            moves = [
                PendingMove(
                    message_id=msg.id,
                    target_mailbox=target_mailbox,
                    target_account=ACCOUNT,
                    source_mailbox=MAILBOX,
                    source_account=ACCOUNT,
                )
                for msg in batch
            ]

            try:
                moved = move_messages_batch(moves)
                done += moved
                batch_failed = len(batch) - moved
                failed += batch_failed

                for msg in batch:
                    audit.log(
                        action=label,
                        message_id=msg.id,
                        subject=msg.subject,
                        sender=msg.sender,
                        bracket=msg.bracket,
                        category=msg.category,
                        target=target_mailbox,
                        success=True,
                    )

                pct = int((done + failed) / total * 100)
                print(f"  [{pct:>3}%] {label}: moved {moved}/{len(batch)} (total: {done}/{total})", end="\r")

            except Exception as e:
                failed += len(batch)
                for msg in batch:
                    audit.log(
                        action=label,
                        message_id=msg.id,
                        subject=msg.subject,
                        sender=msg.sender,
                        bracket=msg.bracket,
                        target=target_mailbox,
                        success=False,
                        error=str(e),
                    )
                print(f"\n  Error in batch: {e}")

            if i + BATCH_SIZE < len(messages):
                time.sleep(BATCH_DELAY)

    if archive_msgs:
        print(f"\n  Archiving {len(archive_msgs)} messages -> {ARCHIVE_MAILBOX}")
        process_batch(archive_msgs, ARCHIVE_MAILBOX, "archive")

    if trash_msgs:
        print(f"\n  Trashing {len(trash_msgs)} messages -> {TRASH_MAILBOX}")
        process_batch(trash_msgs, TRASH_MAILBOX, "trash")

    print(f"\n\n  Done: {done} moved, {failed} failed")


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CSquare inbox cleanup")
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually move messages (default: dry-run)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("CSquare Inbox Cleanup (Age-Based Triage)")
    print(f"  Account: {ACCOUNT}")
    print(f"  Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Set up audit log
    log_path = Path(__file__).parent / f"csquare_cleanup_log_{datetime.now().strftime('%Y%m%d')}.jsonl"
    audit = AuditLog(log_path)

    # Graceful shutdown
    def handle_signal(signum, frame):
        print("\n\nInterrupted! Flushing audit log...")
        audit.log(event="interrupted", signal=signum)
        audit.close()
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        # Phase 1: Enumerate
        messages = enumerate_messages()
        if not messages:
            print("No messages found. Exiting.")
            return

        audit.log(event="enumerated", count=len(messages))

        # Phase 2: Categorize
        buckets = categorize_by_age(messages)

        # Phase 3: AI Classification
        run_ai_classification(buckets)

        # Phase 4: Summary
        actions = present_summary(buckets)

        audit.log(
            event="classification_complete",
            archive=len(actions["archive"]),
            trash=len(actions["trash"]),
            keep=len(actions["keep"]),
        )

        # Phase 5: Execute (or not)
        if not args.execute:
            print(f"\n  DRY-RUN mode. Re-run with --execute to apply changes.")
            print(f"  Audit log: {log_path}")
            return

        movable = len(actions["archive"]) + len(actions["trash"])
        if movable == 0:
            print("\n  Nothing to move.")
            return

        confirm = input(f"\n  About to move {movable} messages. Continue? [y/N] ")
        if confirm.lower() != "y":
            print("  Aborted.")
            return

        execute_moves(actions, audit)
        audit.log(event="completed")

    finally:
        audit.close()

    print(f"\n  Audit log: {log_path}")
    print("Done!")


if __name__ == "__main__":
    main()
