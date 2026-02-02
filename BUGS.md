# Known Bugs

## Priority 1: Active Failures

### BUG-001: datetime serialization error on AI actions
**Status:** Active - failing daily
**Impact:** High - AI actions with datetime fields (reminder, flag, calendar) fail
**Error:** `Object of type datetime is not JSON serializable`
**Root Cause:** `AutopilotDecision.model_dump()` returns datetime objects, but `json.dumps()` in database storage can't serialize them
**Fix:** Use `model_dump(mode='json')` instead of `model_dump()` to convert datetimes to ISO strings
**Files:** `src/email_nurse/autopilot/engine.py` (lines 696, 725, 743, 919, 1459)

---

## Priority 2: Intermittent/Self-Recovering

### BUG-002: Mail.app AppleScript "Invalid index" race condition
**Status:** Intermittent - self-recovers on retry
**Impact:** Low - occasional fetch failures, recovers next run
**Error:** `Mail got an error: Can't get item X of every message... Invalid index. (-1719)`
**Root Cause:** Email moved/deleted between fetch and access (race condition with Mail.app sync)
**Workaround:** System retries automatically, but could add defensive index checking
**Files:** `src/email_nurse/mail/messages.py`

### BUG-003: AppleScript timeout on large mailboxes
**Status:** Rare
**Impact:** Low - single run skipped, recovers next cycle
**Error:** `AppleScript timed out after 120s`
**Root Cause:** CSquare Inbox sometimes has 100+ messages causing slow AppleScript
**Workaround:** Consider batch fetching or increasing timeout for specific accounts

---

## Priority 3: Resolved/Historical

### BUG-004: Authentication method error (RESOLVED)
**Status:** Resolved - was transient API key issue
**Error:** `Could not resolve authentication method. Expected either api_key or auth_token`
**Root Cause:** Temporary .env loading issue or API key rotation
**Resolution:** Self-resolved after .env was refreshed

---

## Priority 4: Enhancement Opportunities

### ENH-001: Inconsistent Csquare support routing (FIXED)
**Status:** Fixed 2026-02-02
**Description:** Same type of Csquare emails routed to different folders
**Fix:** Added catch-all quick rule for support@csquare.com

### ENH-002: Rancid SP-RANCID2 missing rule (FIXED)
**Status:** Fixed 2026-02-02
**Description:** Rancid emails from alternate server not caught by rule
**Fix:** Added SP-RANCID2.evoquedcs.com to sender_contains

### ENH-003: LogicMonitor reports vs alerts inconsistency (FIXED)
**Status:** Fixed 2026-02-02
**Description:** Reports went to Notifications, alerts to LogicMonitor
**Fix:** Added quick rule for reports@evoquedcs.logicmonitor.com
