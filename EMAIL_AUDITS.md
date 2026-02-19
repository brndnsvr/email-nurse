# Email Nurse Audit Log

<!-- Run /audit-email to add entries -->

### 2026-02-17 15:30 | 8h | Grade: A

```
total:105 | rules:58 (55%) | ai:47 (45%)
delete:1 | move:91 | ignore:13
folders: Config-Diffs:25 CSQR-Support:12 Marketing:4 Career:4 Orders:2 GitHub:2 Social:1 Script-Logs:1 Real-Estate:1
top-rules: Rancid-Config-Diffs:25 Csquare-Support-Tickets:8 LinkedIn-Jobs:4 Csquare-SHPC-Support:4 Kickstarter-Marketing:2
```

**Issues:** None

Delete review (1) — correct:
- Brick App spam (rule)

AI routing spot-check (20 moves): All correctly categorized. Marketing: Walgreens Photo, Dollar Shave Club, Lucasfilm/Disney, HBO Max, Canva Create, Samsung, Johnny Brusco's, Home Depot, Electrify America, ESET webinar, Fresh Clean Threads. Newsletters: Make: x2, CDW BizTech, Vivobarefoot, NVIDIA GTC, NFHS Network. Finance: Principal Financial Group 401k, Schwab Market Update. Notifications: Chess.com.

Ignores appropriate (13): Work emails from CSquare colleagues (Cindy Cortazzo, Nebyou Gebreyohannes) correctly left in inbox. Healthcare: Walgreens prescription refill, provider survey. Account: Spotify activation. Infrastructure: squid-mon x2, Rancid unattended-upgrades. Rule-based: CSQUARE Leadership, Chase Bank, Apple News Digest, daily.dev Digest, USPS Informed Delivery.

---

### 2026-02-17 10:00 | 8h | Grade: A

```
total:33 | rules:21 (64%) | ai:12 (36%)
delete:0 | move:25 | ignore:8
folders: Config-Diffs:17 Marketing:3 Newsletters:2 Script-Logs:1 Real-Estate:1 Notifications:1
top-rules: Rancid-Config-Diffs:17 daily.dev-Digest:1 USPS-Informed-Delivery:1 Redfin:1 FD-Checker-Logs:1
```

**Issues:** None

Delete review (0) — no deletes this window.

AI routing spot-check (6 moves): All correct. Chick-fil-A, Krispy Kreme, Hilton Grand Vacations → Marketing. TLDR newsletter, Bouqs Co → Newsletters. Airbnb terms/policy update → Notifications.

Ignores appropriate (8): Walgreens prescription refill, Spotify account activation, healthcare provider survey — all correctly left for user action. Infrastructure alerts (squid-mon x2, Rancid unattended-upgrades) correctly ignored per exclusion rules. Rule-based ignores: daily.dev Digest, USPS Informed Delivery.

---

### 2026-02-16 12:00 | 12h | Grade: A

```
total:44 | rules:36 (82%) | ai:8 (18%)
delete:0 | move:40 | ignore:4
folders: Config-Diffs:17 GitHub:12 CSQR-Support:2 Script-Logs:1 Real-Estate:1 Marketing:1
top-rules: Rancid-Config-Diffs:17 GitHub:12 Csquare-SHPC-Support:2 Chase-Bank:2 Redfin:1
```

**Issues:** None

Delete review (0) — no deletes this window.

AI routing spot-check (6 moves): All correct. Krispy Kreme, Hilton Grand Vacations → Marketing. TLDR, Hackr.io → Newsletters. Audible credits, TryHackMe Valentine CTF event → Notifications.

Ignores appropriate (4): Chase Bank x2 (rule). PowerSchool progress report and attendance report for student correctly left in inbox as personal/educational (autopilot).

---

### 2026-02-14 13:30 | 12h | Grade: A

```
total:65 | rules:39 (60%) | ai:26 (40%)
delete:2 | move:59 | ignore:4
folders: Config-Diffs:27 Career:4 Marketing:2 Script-Logs:1 Real-Estate:1
top-rules: Rancid-Config-Diffs:27 LinkedIn-Jobs:4 Kickstarter-Marketing:2 USPS-Informed-Delivery:1 Redfin:1
```

**Issues:**
- Minor: Welcome to the Jungle job alert (msg 35240) routed to Newsletters instead of Career. LinkedIn Jobs rule already sends job alerts to Career — consider a quick-rule for Welcome to the Jungle to match.

Delete review (2) — all correct:
- Brick App spam (rule)
- Sonic restaurant unsolicited survey via Qualtrics (autopilot)

AI routing spot-check (20 moves): All marketing/promo correctly routed to Marketing (Dollar Shave Club, Smoothie King, BackerHome, Fresh Clean Threads, Mensa, Zenni Optical x2, Petlibro, Vivobarefoot, SimpliSafe, TryHackMe, Krispy Kreme, Johnny Brusco's, Walgreens). Newsletters correctly identified (AINews/Substack, Brander Group, Maker Shed). DEV Community challenge correctly sent to Marketing. One MS Outlook notification correctly routed to Notifications.

Ignores appropriate (4): Apple News Digest (rule), USPS Informed Delivery (rule), Apple Inside (rule), Rancid unattended-upgrades alert correctly ignored per exclusion rules (autopilot).

---

### 2026-02-13 17:00 | 48h | Grade: A

```
total:8367 | rules:7791 (93%) | ai:576 (7%)
delete:3 | move:8210 | ignore:150 | create_reminder:4
folders: LogicMonitor:6652 CSQR-Support:976 GitHub:28 Career:20 Marketing:14 Healthcare:13 Real-Estate:7 Newsletters:7 Config-Diffs:4 Script-Logs:3
top-rules: LogicMonitor-Alerts:6652 Csquare-Support-Tickets:505 Csquare-SHPC-Support:471 GitHub:28 LinkedIn-Jobs:18
```

**Issues:**
- Massive LogicMonitor alert volume (6652 moves in 48h vs ~134 in the prior 72h audit). Likely an infrastructure alert storm — worth investigating LM for noisy monitors or alert suppression.
- Duplicate processing still occurring: multiple ignore/move entries for the same message_id visible in ignores and AI moves (e.g., same SPFBL, work threads, Sneds Tour emails processed 2-3x each).
- SPFBL abuse report routing inconsistency: some moved to Notifications, others ignored and left in inbox. AI reasoning varies between "automated notification" and "security matter needing review." Consider a quick-rule to normalize.

Delete review (3) — all correct:
- Obvious spam with misleading health claims, clickbait subject using Unicode chars to evade filters (autopilot)
- Brick App spam (rule)
- Sonic restaurant unsolicited survey email (autopilot)

AI routing spot-check (20 moves): All correctly categorized. SPFBL abuse reports → Notifications. Atlassian Team '26, Mimecast sales outreach, Google Cloud conference, Birdogs, Fresh Clean Threads promos → Marketing. Zed Industries release notes → Newsletters. CSquare IT notification → Notifications. Minor inconsistency: Zed release notes categorized as Newsletters on one run and Notifications on another.

Ignores appropriate (150): Work email threads (DFW Foundation servers SSH troubleshooting, CS2137257 support case, Fabric Discussion), Christie Seaver personal/business emails, Sneds Tour golf registration confirmations, appointment reminders (eye doctor, Performance Medicine), calendar invites (Csquare Fabric Discussion), Have I Been Pwned security alerts, Walgreens pharmacy, SiriusXM subscription notice, Rancid infrastructure alerts, Microsoft Family Safety, LogicMonitor sales engineer correspondence (correctly distinguished from LM alerts), NtwkCmdr waitlist confirmation. Rule-based ignores: CSQUARE Leadership, Apple News/Inside, daily.dev Digest, USPS Informed Delivery, Gate City UMC, Chase Bank, Eastman Credit Union, Hostinger.

---

### 2026-02-09 11:15 | 72h | Grade: A

```
total:422 | rules:215 (51%) | ai:207 (49%)
delete:5 | move:350 | ignore:66 | create_reminder:1
folders: LogicMonitor:98 Career:27 CSQR-Support:18 Marketing:11 Real-Estate:9 GitHub:8 Orders:7 Newsletters:5 Social:3 Script-Logs:2
top-rules: LogicMonitor-Alerts:98 LinkedIn-Jobs:26 Csquare-Support-Tickets:9 Csquare-SHPC-Support:9 Redfin:8
```

**Issues:**
- Duplicate processing: 48 extra audit entries across 376 unique emails (12.8%). Caused by sysm move timeouts — batched moves fail, emails aren't marked processed, and get re-picked-up next cycle. Most duplicates are LogicMonitor alerts retried 3-6x before succeeding.

Delete review (5) — all correct:
- Unsolicited recruiter spam (Manasa Softcom via oorwinmail.com)
- Brick App spam (rule)
- Unsolicited web dev services solicitation
- Phishing email impersonating iCloud (babsmad@me.com with clickme.thryv.com link)
- Rocket Mortgage sweepstakes with missing name field ("Hi ,")

AI routing spot-check (20 moves): All correctly categorized. Marketing emails (Skylight, Dollar Shave Club, Hims, Walgreens, Verizon, ID.me, Airtable x3, Electrify America, Fresh Clean Threads, American Home Design, GitLab webinar) → Marketing. Newsletters (Schwab Market Update, Rep. Tanner Substack) → Newsletters. Notifications (Glassdoor digest, NFHS Network, Alpaca, GitLab commits) → Notifications.

Ignores appropriate (66): School progress reports for Trent S. and Ayden S. (personal/family), SimpliSafe security alert, Electrify America account verification, Zayo meeting coordination threads, CSquare work correspondence, Rancid infrastructure alerts, State Farm claim, RSAC 2026 calendar invite, Venmo payment. All require human attention or are deliberately left in inbox.

---

### 2026-02-04 10:45 | 8h | Grade: A

```
total:133 | rules:103 (77%) | ai:30 (23%)
delete:1 | move:122 | ignore:10
folders: LogicMonitor:85 CSQR-Support:4 Career:3 Orders:2 Script-Logs:1 Real-Estate:1 Newsletters:1 Marketing:1 Config-Diffs:1
top-rules: LogicMonitor-Alerts:85 Csquare-SHPC-Support:4 LinkedIn-Jobs:3 CSQUARE-Leadership:2 daily.dev-Digest:1
```

**Issues:** None

Delete review (1):
- Unsolicited web design follow-up from unknown sender - correct deletion

AI routing spot-check: All 20 sampled moves correctly categorized. Newsletters→Newsletters, marketing→Marketing, financial→Finance, orders→Orders, notifications→Notifications, social→Social.

Ignores appropriate: Sikich webinar invitation, Zayo work correspondence, Walgreens prescription refill, Coffee with Spencer meeting, vehicle registration renewal, unsolicited business pitch. All require user attention or are handled by rules.

---

### 2026-02-03 10:15 | 18h | Grade: A

```
total:303 | rules:202 (67%) | ai:101 (33%)
delete:8 | move:276 | ignore:19
folders: LogicMonitor:134 CSQR-Support:14 Notifications:10 Career:10 GitHub:9 Newsletters:5 Marketing:4
top-rules: LogicMonitor-Alerts:134 NtwkCmdr-Alerts:10 LinkedIn-Jobs:10 GitHub:9 Csquare-SHPC-Support:9
```

**Issues:** None

All 8 deletes were legitimate spam:
- 2 dating site spam (Spicedates)
- 2 WHOIS contact form logo/design solicitations
- 2 unsolicited web dev service pitches
- 1 auction house jewelry marketing
- 1 Brick App spam (rule)

AI routing spot-check: All moves correctly categorized (newsletters→Newsletters, marketing→Marketing, orders→Orders, finance→Finance).

Ignores appropriate: Personal emails from Christie Seaver, business inquiry, healthcare notification from Walgreens, Venmo payment, work correspondence.

---
