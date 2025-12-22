# Rules Reference

Complete reference for `rules.yaml` - the email processing rules configuration file.

## Table of Contents

- [Overview](#overview)
- [Rule Structure](#rule-structure)
- [Condition Types](#condition-types)
- [Condition Options](#condition-options)
- [Condition Groups](#condition-groups)
- [Action Types](#action-types)
- [AI-Powered Rules](#ai-powered-rules)
- [Priority and Processing Order](#priority-and-processing-order)
- [Common Patterns](#common-patterns)

## Overview

The `rules.yaml` file defines automated email processing rules. Each rule consists of:

1. **Metadata**: Name, description, enabled status
2. **Priority**: Execution order (lower = first)
3. **Conditions**: When the rule matches
4. **Action**: What to do when matched
5. **Processing Control**: Whether to stop after this rule

**Location**: `~/.config/email-nurse/rules.yaml`

## Rule Structure

### Complete Rule Anatomy

```yaml
rules:
  - name: "Rule Name"                    # Required: unique identifier
    description: "What this rule does"   # Optional: human-readable description
    enabled: true                        # Optional: default true
    priority: 100                        # Optional: default 100 (lower = earlier)
    stop_processing: true                # Optional: default true

    # Simple conditions (all must match by default)
    conditions:
      - type: sender_domain
        value: example.com
        case_sensitive: false            # Optional: default false
        negate: false                    # Optional: default false

    # OR logic for simple conditions
    match_all: true                      # true = AND, false = OR

    # Advanced: grouped conditions with custom logic
    condition_groups:
      - operator: and                    # "and" or "or"
        conditions:
          - type: subject_contains
            value: urgent
          - type: is_unread
            value: true

    # Action to perform
    action:
      action: move                       # Required: action type
      target_folder: "Archive"           # Action-specific parameters
      target_account: null               # Optional: for cross-account moves
      reply_template: null               # Optional: for reply actions
      forward_to: null                   # Optional: for forward actions

    # Optional: AI-powered classification
    use_ai: false                        # Enable AI for this rule
    ai_context: null                     # Additional context for AI
```

### Minimal Rule Example

```yaml
rules:
  - name: "Archive Newsletters"
    conditions:
      - type: sender_domain
        value: newsletter.com
    action:
      action: archive
```

### Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Unique rule name |
| `description` | string | No | `null` | Human-readable description |
| `enabled` | boolean | No | `true` | Whether rule is active |
| `priority` | integer | No | `100` | Execution order (lower = first) |
| `stop_processing` | boolean | No | `true` | Stop evaluating rules after match |
| `conditions` | list | No | `[]` | List of conditions |
| `condition_groups` | list | No | `[]` | List of condition groups |
| `match_all` | boolean | No | `true` | `true` = AND all conditions, `false` = OR |
| `action` | object | Yes | - | Action to perform |
| `use_ai` | boolean | No | `false` | Use AI for classification |
| `ai_context` | string | No | `null` | Additional AI context |

## Condition Types

Email Nurse supports 18 condition types across 7 categories.

### Sender Conditions

Match based on who sent the email.

#### sender_contains

Match if sender address contains a substring.

```yaml
conditions:
  - type: sender_contains
    value: "@company.com"
```

**Use cases**:
- Match multiple addresses from same domain
- Partial email matching
- Catch sender name variations

**Examples**:
```yaml
# Match any @github.com sender
- type: sender_contains
  value: "@github.com"

# Match sender name
- type: sender_contains
  value: "John Smith"
```

#### sender_equals

Match exact sender address.

```yaml
conditions:
  - type: sender_equals
    value: "boss@company.com"
    case_sensitive: false
```

**Use cases**:
- VIP sender rules
- Specific contact handling
- Exact address matching

**Examples**:
```yaml
# Flag emails from CEO
- type: sender_equals
  value: "ceo@company.com"

# Case-sensitive exact match
- type: sender_equals
  value: "Support@Example.com"
  case_sensitive: true
```

#### sender_domain

Match sender's email domain (case-insensitive).

```yaml
conditions:
  - type: sender_domain
    value: "github.com"
```

**Use cases**:
- Organize by service/company
- Domain-based filtering
- Corporate email handling

**Examples**:
```yaml
# All GitHub notifications
- type: sender_domain
  value: "github.com"

# All internal emails
- type: sender_domain
  value: "mycompany.com"

# Exclude a domain (using negate)
- type: sender_domain
  value: "spam.com"
  negate: true
```

#### sender_regex

Match sender using regular expression.

```yaml
conditions:
  - type: sender_regex
    value: "noreply|no-reply|donotreply"
    case_sensitive: false
```

**Use cases**:
- Complex pattern matching
- Multiple variations
- Advanced filtering

**Examples**:
```yaml
# Match multiple no-reply variations
- type: sender_regex
  value: "^(noreply|no-reply|donotreply)@"

# Match numbered support addresses (support1@, support2@, etc.)
- type: sender_regex
  value: "^support\\d+@company\\.com$"

# Match any subdomain
- type: sender_regex
  value: "@.*\\.github\\.com$"

# Case-sensitive regex
- type: sender_regex
  value: "^[A-Z][a-z]+@important\\.com$"
  case_sensitive: true
```

### Subject Conditions

Match based on email subject line.

#### subject_contains

Match if subject contains a substring.

```yaml
conditions:
  - type: subject_contains
    value: "invoice"
```

**Use cases**:
- Keyword filtering
- Topic categorization
- Simple subject matching

**Examples**:
```yaml
# Find invoices
- type: subject_contains
  value: "invoice"

# Newsletter detection
- type: subject_contains
  value: "newsletter"

# Case-sensitive match
- type: subject_contains
  value: "URGENT"
  case_sensitive: true

# Exclude subjects containing word
- type: subject_contains
  value: "spam"
  negate: true
```

#### subject_equals

Match exact subject line.

```yaml
conditions:
  - type: subject_equals
    value: "Daily Report"
    case_sensitive: false
```

**Use cases**:
- Automated reports
- Exact subject matching
- Specific email types

**Examples**:
```yaml
# Daily automated report
- type: subject_equals
  value: "Daily Sales Report"

# Exact match for notification
- type: subject_equals
  value: "Password Reset Request"
```

#### subject_regex

Match subject using regular expression.

```yaml
conditions:
  - type: subject_regex
    value: "(?i)re:.*invoice #\\d+"
```

**Use cases**:
- Complex pattern matching
- Multiple variations
- Advanced filtering

**Examples**:
```yaml
# Match invoice with number
- type: subject_regex
  value: "invoice #\\d+"

# Match tickets (TICKET-1234, TKT-5678, etc.)
- type: subject_regex
  value: "(?i)(ticket|tkt)-\\d+"

# Match "Re:" or "Fwd:" prefixes
- type: subject_regex
  value: "^(re|fwd):"
  case_sensitive: false

# Detect urgent/spam keywords
- type: subject_regex
  value: "(?i)(urgent|winner|lottery|congratulations)"
```

#### subject_starts_with

Match if subject starts with a string.

```yaml
conditions:
  - type: subject_starts_with
    value: "[GitHub]"
```

**Use cases**:
- Prefixed emails
- Categorized subjects
- Tagged messages

**Examples**:
```yaml
# GitHub notifications
- type: subject_starts_with
  value: "[GitHub]"

# Jira tickets
- type: subject_starts_with
  value: "[JIRA]"

# Re: replies
- type: subject_starts_with
  value: "Re:"

# Case-sensitive tag
- type: subject_starts_with
  value: "[URGENT]"
  case_sensitive: true
```

### Body Conditions

Match based on email content/body.

#### body_contains

Match if email body contains a substring.

```yaml
conditions:
  - type: body_contains
    value: "unsubscribe"
```

**Use cases**:
- Newsletter detection
- Content-based filtering
- Keyword matching

**Examples**:
```yaml
# Detect newsletters (unsubscribe link required by law)
- type: body_contains
  value: "unsubscribe"

# Marketing emails
- type: body_contains
  value: "click here to view in browser"

# Specific content
- type: body_contains
  value: "quarterly results"
```

**Note**: Body matching searches plain text content, not HTML.

#### body_regex

Match body using regular expression.

```yaml
conditions:
  - type: body_regex
    value: "https?://.*\\.pdf"
```

**Use cases**:
- Pattern detection
- Link extraction
- Complex content matching

**Examples**:
```yaml
# Find PDF links
- type: body_regex
  value: "https?://.*\\.pdf"

# Detect tracking links
- type: body_regex
  value: "utm_source="

# Find phone numbers
- type: body_regex
  value: "\\(?\\d{3}\\)?[-. ]?\\d{3}[-. ]?\\d{4}"

# Match invoice amounts
- type: body_regex
  value: "\\$\\d+\\.\\d{2}"
```

### Recipient Conditions

Match based on email recipients (To/Cc).

#### recipient_contains

Match if any recipient contains a substring.

```yaml
conditions:
  - type: recipient_contains
    value: "@team.company.com"
```

**Use cases**:
- Mailing list detection
- Team email handling
- Group recipient matching

**Examples**:
```yaml
# Team mailing list
- type: recipient_contains
  value: "team@company.com"

# Any recipient in a domain
- type: recipient_contains
  value: "@engineering.company.com"
```

#### recipient_equals

Match if any recipient exactly equals an address.

```yaml
conditions:
  - type: recipient_equals
    value: "all-hands@company.com"
```

**Use cases**:
- Specific mailing list
- Group email handling
- Exact recipient matching

**Examples**:
```yaml
# Company-wide announcements
- type: recipient_equals
  value: "everyone@company.com"

# Specific distribution list
- type: recipient_equals
  value: "engineering-team@company.com"
```

### Mailbox/Account Conditions

Match based on which mailbox/account received the email.

#### mailbox_equals

Match emails in a specific mailbox/folder.

```yaml
conditions:
  - type: mailbox_equals
    value: "INBOX"
```

**Use cases**:
- Folder-specific rules
- Process only certain mailboxes
- Skip archived emails

**Examples**:
```yaml
# Only process inbox
- type: mailbox_equals
  value: "INBOX"

# Process sent items
- type: mailbox_equals
  value: "Sent"

# Case-sensitive folder name
- type: mailbox_equals
  value: "Important Clients"
  case_sensitive: true
```

#### account_equals

Match emails in a specific email account.

```yaml
conditions:
  - type: account_equals
    value: "work@company.com"
```

**Use cases**:
- Account-specific rules
- Separate work/personal handling
- Multi-account workflows

**Examples**:
```yaml
# Only work account
- type: account_equals
  value: "work@company.com"

# Personal email only
- type: account_equals
  value: "personal@gmail.com"
```

### Read Status Conditions

Match based on read/unread status.

#### is_read

Match only read emails.

```yaml
conditions:
  - type: is_read
    value: true
```

**Use cases**:
- Archive read emails
- Clean up processed messages
- Skip already-seen emails

**Examples**:
```yaml
# Archive old read emails
- type: is_read
  value: true
```

**Note**: The `value` field is required but ignored; only the type matters.

#### is_unread

Match only unread emails.

```yaml
conditions:
  - type: is_unread
    value: true
```

**Use cases**:
- Process only new emails
- Skip already-reviewed messages
- Focus on unread inbox

**Examples**:
```yaml
# Process only unread messages
- type: is_unread
  value: true
```

### AI Conditions

Special condition type for AI-powered classification.

#### ai_classify

Always matches; triggers AI classification.

```yaml
conditions:
  - type: ai_classify
    value: true
```

**Use cases**:
- Fallback AI classification
- Complex decision-making
- Context-aware processing

See [AI-Powered Rules](#ai-powered-rules) for details.

## Condition Options

All conditions support two optional flags:

### case_sensitive

Controls case-sensitive matching.

**Default**: `false` (case-insensitive)

```yaml
conditions:
  # Case-insensitive (default): matches "GitHub", "github", "GITHUB"
  - type: sender_domain
    value: "github.com"
    case_sensitive: false

  # Case-sensitive: only matches exact case
  - type: subject_contains
    value: "URGENT"
    case_sensitive: true
```

**Applies to**:
- All sender conditions (except `sender_domain`, which is always case-insensitive)
- All subject conditions
- All body conditions
- All recipient conditions
- Mailbox/account conditions

**Does not apply to**:
- `sender_domain` (always case-insensitive)
- `is_read` / `is_unread` (no text matching)
- `ai_classify` (no text matching)

### negate

Inverts the condition result (logical NOT).

**Default**: `false`

```yaml
conditions:
  # Normal: match emails FROM github.com
  - type: sender_domain
    value: "github.com"
    negate: false

  # Negated: match emails NOT FROM github.com
  - type: sender_domain
    value: "github.com"
    negate: true
```

**Examples**:

```yaml
# Match emails that DON'T contain "unsubscribe"
- type: body_contains
  value: "unsubscribe"
  negate: true

# Match emails NOT from spam domains
- type: sender_regex
  value: "@(spam|bulk|marketing)\\."
  negate: true

# Match read emails (same as is_read)
- type: is_unread
  value: true
  negate: true
```

## Condition Groups

Condition groups allow complex logical expressions with nested AND/OR logic.

### Basic Condition Group

```yaml
condition_groups:
  - operator: and  # or "or"
    conditions:
      - type: sender_domain
        value: github.com
      - type: is_unread
        value: true
```

### Multiple Groups

Multiple groups are combined using the rule's `match_all` setting:

```yaml
# Groups are combined with AND
match_all: true
condition_groups:
  # Group 1: (sender is GitHub AND unread)
  - operator: and
    conditions:
      - type: sender_domain
        value: github.com
      - type: is_unread
        value: true

  # Group 2: (subject contains "PR" OR subject contains "Issue")
  - operator: or
    conditions:
      - type: subject_contains
        value: "PR"
      - type: subject_contains
        value: "Issue"

# Final logic: Group1 AND Group2
# = (GitHub AND unread) AND (PR OR Issue)
```

### Mixing Simple Conditions and Groups

Simple conditions and groups can be combined:

```yaml
match_all: true
conditions:
  # Simple condition
  - type: sender_domain
    value: company.com

condition_groups:
  # Group with OR logic
  - operator: or
    conditions:
      - type: subject_contains
        value: urgent
      - type: subject_contains
        value: important

# Final logic: (sender is company.com) AND (urgent OR important)
```

### Complex Example

```yaml
# Match: (GitHub OR GitLab) AND (Unread) AND (PR OR Issue OR Merge)
match_all: true

condition_groups:
  # Group 1: Source
  - operator: or
    conditions:
      - type: sender_domain
        value: github.com
      - type: sender_domain
        value: gitlab.com

  # Group 2: Status
  - operator: and
    conditions:
      - type: is_unread
        value: true

  # Group 3: Type
  - operator: or
    conditions:
      - type: subject_contains
        value: "Pull Request"
      - type: subject_contains
        value: "Issue"
      - type: subject_contains
        value: "Merge Request"
```

## Action Types

Actions define what happens when a rule matches.

### move

Move email to a folder.

```yaml
action:
  action: move
  target_folder: "Archive"
  target_account: null  # Optional: move to different account
```

**Required fields**:
- `target_folder`: Destination folder name

**Optional fields**:
- `target_account`: Destination account (for cross-account moves)

**Examples**:

```yaml
# Move to Archive folder
action:
  action: move
  target_folder: "Archive"

# Move to folder with spaces
action:
  action: move
  target_folder: "Important Clients"

# Move to subfolder (use forward slash)
action:
  action: move
  target_folder: "Projects/Email Nurse"

# Cross-account move
action:
  action: move
  target_folder: "INBOX"
  target_account: "personal@gmail.com"
```

### delete

Permanently delete email.

```yaml
action:
  action: delete
```

**No additional fields required.**

**Warning**: This permanently deletes emails. Use with caution!

**Recommendation**: Use `move` to a "Trash" folder instead for safety:

```yaml
action:
  action: move
  target_folder: "Trash"
```

### archive

Move email to Archive folder.

```yaml
action:
  action: archive
```

**No additional fields required.**

Equivalent to:
```yaml
action:
  action: move
  target_folder: "Archive"
```

### mark_read / mark_unread

Change read status.

```yaml
# Mark as read
action:
  action: mark_read

# Mark as unread
action:
  action: mark_unread
```

**No additional fields required.**

**Use cases**:
- Mark newsletters as read automatically
- Flag important emails as unread for follow-up
- Clean up notification emails

### flag / unflag

Add or remove flag/star.

```yaml
# Add flag
action:
  action: flag

# Remove flag
action:
  action: unflag
```

**No additional fields required.**

**Use cases**:
- Flag VIP sender emails
- Mark important categories
- Highlight emails for review

### reply

Auto-reply using a template.

```yaml
action:
  action: reply
  reply_template: "out_of_office"
```

**Required fields**:
- `reply_template`: Template name (from `templates.yaml`)

**Examples**:

```yaml
# Out of office auto-reply
action:
  action: reply
  reply_template: "out_of_office"

# AI-generated acknowledgment
action:
  action: reply
  reply_template: "acknowledge"
```

See [Templates Reference](./templates-reference.md) for template creation.

**Note**: Replies are created as drafts by default, not sent immediately.

### forward

Forward email to other addresses.

```yaml
action:
  action: forward
  forward_to:
    - "assistant@company.com"
    - "backup@company.com"
```

**Required fields**:
- `forward_to`: List of recipient email addresses

**Examples**:

```yaml
# Forward to single address
action:
  action: forward
  forward_to:
    - "assistant@company.com"

# Forward to multiple addresses
action:
  action: forward
  forward_to:
    - "boss@company.com"
    - "team@company.com"
```

**Note**: Forwards are created as drafts by default, not sent immediately.

### ignore

Take no action (useful for AI rules with fallback).

```yaml
action:
  action: ignore
```

**No additional fields required.**

**Use cases**:
- Default action for AI rules
- Skip processing certain emails
- Placeholder action

## AI-Powered Rules

Rules can use AI for intelligent classification instead of (or in addition to) fixed conditions.

### Basic AI Rule

```yaml
- name: "AI Classification"
  use_ai: true
  conditions: []  # Matches everything
  action:
    action: ignore  # Fallback if AI fails
```

### AI with Context

Provide instructions to guide the AI:

```yaml
- name: "Smart Newsletter Filter"
  use_ai: true
  ai_context: |
    Determine if this is a newsletter or promotional email.

    Criteria:
    - Contains "unsubscribe" link
    - Marketing content
    - Bulk sender patterns

    If newsletter: move to "Newsletters" folder
    If promotional: move to "Marketing" folder
    Otherwise: ignore (leave in inbox)
  action:
    action: ignore  # Fallback
```

### AI with Pre-Filtering

Combine conditions with AI for efficiency:

```yaml
- name: "AI Triage Unread"
  conditions:
    # Only run AI on unread emails from certain domains
    - type: is_unread
      value: true
    - type: sender_domain
      value: company.com
  use_ai: true
  ai_context: |
    Classify this internal email:
    - Urgent: flag and leave in inbox
    - FYI: mark as read
    - Meeting: move to "Meetings" folder
  action:
    action: ignore
```

### AI Classification Response

When `use_ai: true`, the AI determines:
- **Action**: Which action to take (move, delete, flag, etc.)
- **Confidence**: How confident it is (0.0 to 1.0)
- **Target**: Folder name, template, or other action-specific data
- **Reasoning**: Explanation of the decision

If confidence is below threshold (default 0.7), the action is not executed.

### AI Context Best Practices

1. **Be specific**: Give clear categories and criteria
2. **Provide examples**: Show expected behavior
3. **Set boundaries**: Define what to do when uncertain
4. **Use structured format**: Lists and clear sections
5. **Be conservative**: Default to "ignore" when in doubt

**Good AI Context**:

```yaml
ai_context: |
  Classify into one of these categories:

  1. Newsletter (move to "Newsletters"):
     - Has unsubscribe link
     - Marketing/promotional content
     - Regular publication (daily, weekly)

  2. Receipt (move to "Receipts"):
     - Contains order number or invoice
     - From known shopping/service sites
     - Payment confirmation

  3. Personal (ignore):
     - Direct personal communication
     - Not automated/bulk email

  If uncertain, use "ignore" to leave in inbox.
  Be conservative with deletion.
```

**Bad AI Context**:

```yaml
ai_context: "Organize my email"  # Too vague
```

## Priority and Processing Order

### Priority Values

Rules are evaluated in priority order:
- **Lower number = higher priority** (evaluated first)
- Default priority: `100`
- Range: Any integer (typically 1-999)

```yaml
rules:
  # Evaluated FIRST (highest priority)
  - name: "VIP Sender"
    priority: 10
    # ...

  # Evaluated SECOND
  - name: "Important Keywords"
    priority: 50
    # ...

  # Evaluated THIRD
  - name: "General Categorization"
    priority: 100
    # ...

  # Evaluated LAST (lowest priority)
  - name: "AI Fallback"
    priority: 999
    # ...
```

### Stop Processing

Control whether rule evaluation continues after a match:

```yaml
# Stop after this rule matches
- name: "High Priority Action"
  priority: 10
  stop_processing: true
  # ...

# Continue evaluating more rules
- name: "Add Flag"
  priority: 20
  stop_processing: false
  # ...
```

**Default**: `true` (stop after match)

### Processing Flow

1. **Sort rules** by priority (ascending)
2. **For each rule**:
   - Check if `enabled: true`
   - Evaluate conditions
   - If matched:
     - Execute action (unless dry-run)
     - If `stop_processing: true`, stop
     - Otherwise, continue to next rule
3. **Return result** (action taken or none)

### Example Processing

```yaml
rules:
  # Priority 10: Check for VIPs first
  - name: "VIP Sender"
    priority: 10
    stop_processing: true
    conditions:
      - type: sender_equals
        value: "ceo@company.com"
    action:
      action: flag

  # Priority 50: Category-specific rules
  - name: "GitHub Notifications"
    priority: 50
    stop_processing: true
    conditions:
      - type: sender_domain
        value: github.com
    action:
      action: move
      target_folder: "GitHub"

  # Priority 100: General filters
  - name: "Newsletter Archive"
    priority: 100
    stop_processing: true
    conditions:
      - type: body_contains
        value: unsubscribe
    action:
      action: archive

  # Priority 999: Fallback AI
  - name: "AI Classification"
    priority: 999
    stop_processing: true
    use_ai: true
    conditions: []
    action:
      action: ignore
```

**Email from CEO**: Matches "VIP Sender" (priority 10), flagged, stops.

**Email from GitHub**: Skips "VIP Sender", matches "GitHub Notifications" (priority 50), moved, stops.

**Newsletter**: Skips first two, matches "Newsletter Archive" (priority 100), archived, stops.

**Unknown email**: Skips all, reaches "AI Classification" (priority 999), AI decides.

### Stacking Actions

To apply multiple actions, use `stop_processing: false`:

```yaml
rules:
  # First: Flag important sender
  - name: "Flag Important"
    priority: 10
    stop_processing: false  # Continue processing
    conditions:
      - type: sender_domain
        value: important.com
    action:
      action: flag

  # Second: Move to folder
  - name: "Move to Project Folder"
    priority: 20
    stop_processing: true  # Stop here
    conditions:
      - type: sender_domain
        value: important.com
    action:
      action: move
      target_folder: "Important Project"

# Result: Email is both flagged AND moved
```

## Common Patterns

Practical recipes for typical email automation scenarios.

### Newsletter Management

Auto-archive newsletters:

```yaml
- name: "Archive Newsletters"
  description: "Auto-archive emails with unsubscribe links"
  priority: 100
  conditions:
    - type: body_contains
      value: "unsubscribe"
  action:
    action: archive
  stop_processing: true
```

Archive from known newsletter senders:

```yaml
- name: "Substack Newsletters"
  priority: 90
  conditions:
    - type: sender_domain
      value: "substack.com"
  action:
    action: move
    target_folder: "Newsletters"
  stop_processing: true
```

### Service Notifications

Organize by service:

```yaml
- name: "GitHub Notifications"
  priority: 50
  conditions:
    - type: sender_domain
      value: "github.com"
  action:
    action: move
    target_folder: "GitHub"
  stop_processing: true

- name: "Jira Notifications"
  priority: 50
  conditions:
    - type: sender_domain
      value: "atlassian.net"
  action:
    action: move
    target_folder: "Jira"
  stop_processing: true
```

Mark certain notifications as read:

```yaml
- name: "Auto-Read Social Media"
  priority: 80
  conditions:
    - type: sender_domain
      value: "linkedin.com"
  action:
    action: mark_read
  stop_processing: false  # Allow other rules to process
```

### Spam/Unwanted Email

Delete obvious spam (use cautiously):

```yaml
- name: "Delete Spam Keywords"
  description: "Delete emails with spam keywords"
  enabled: false  # Disabled by default for safety
  priority: 10
  conditions:
    - type: subject_regex
      value: "(?i)(winner|lottery|prize|congratulations|urgent|act now)"
    - type: sender_regex
      value: "@(spam|bulk)\\."
  match_all: false  # Match if ANY condition true
  action:
    action: delete
  stop_processing: true
```

Safer: Move to Junk:

```yaml
- name: "Move Spam to Junk"
  priority: 10
  conditions:
    - type: subject_regex
      value: "(?i)(winner|lottery|crypto|bitcoin)"
  action:
    action: move
    target_folder: "Junk"
  stop_processing: true
```

### VIP Senders

Flag important senders:

```yaml
- name: "Flag VIP Senders"
  priority: 5  # High priority
  stop_processing: false  # Allow further processing
  conditions:
    - type: sender_equals
      value: "ceo@company.com"
  action:
    action: flag
```

Multiple VIPs:

```yaml
- name: "Flag VIP Senders"
  priority: 5
  stop_processing: false
  match_all: false  # OR logic
  conditions:
    - type: sender_equals
      value: "ceo@company.com"
    - type: sender_equals
      value: "cto@company.com"
    - type: sender_equals
      value: "important-client@client.com"
  action:
    action: flag
```

### Auto-Reply

Out of office:

```yaml
- name: "Out of Office Reply"
  priority: 1  # Highest priority
  enabled: false  # Enable when on vacation
  conditions:
    - type: is_unread
      value: true
  action:
    action: reply
    reply_template: "out_of_office"
  stop_processing: false
```

Auto-acknowledge specific senders:

```yaml
- name: "Auto-Acknowledge Support"
  priority: 10
  conditions:
    - type: recipient_contains
      value: "support@mycompany.com"
    - type: is_unread
      value: true
  action:
    action: reply
    reply_template: "support_ack"
  stop_processing: false
```

### Receipts and Finance

Organize financial emails:

```yaml
- name: "Organize Receipts"
  priority: 50
  match_all: false  # OR logic
  conditions:
    - type: subject_contains
      value: "receipt"
    - type: subject_contains
      value: "invoice"
    - type: subject_contains
      value: "payment"
    - type: body_regex
      value: "order #\\d+"
  action:
    action: move
    target_folder: "Finance/Receipts"
  stop_processing: true
```

Flag high-value invoices:

```yaml
- name: "Flag Large Invoices"
  priority: 20
  stop_processing: false
  conditions:
    - type: subject_contains
      value: "invoice"
    - type: body_regex
      value: "\\$[1-9]\\d{3,}"  # $1000+
  action:
    action: flag
```

### Mailing Lists

Archive mailing lists:

```yaml
- name: "Archive Mailing Lists"
  priority: 100
  match_all: false
  conditions:
    - type: recipient_contains
      value: "all-company@company.com"
    - type: recipient_contains
      value: "engineering-team@company.com"
  action:
    action: move
    target_folder: "Mailing Lists"
  stop_processing: true
```

### Meeting Invites

Organize calendar invites:

```yaml
- name: "Meeting Invites"
  priority: 60
  match_all: false
  conditions:
    - type: subject_starts_with
      value: "Invitation:"
    - type: subject_contains
      value: "meeting"
    - type: body_contains
      value: "has invited you"
  action:
    action: move
    target_folder: "Calendar"
  stop_processing: true
```

### Catch-All AI Rules

AI for unmatched emails:

```yaml
- name: "AI Triage Remaining"
  priority: 999  # Lowest priority
  conditions: []  # Match everything that reaches here
  use_ai: true
  ai_context: |
    Classify this email:

    Categories:
    1. Newsletter → archive
    2. Receipt/Invoice → move to "Finance"
    3. Marketing → move to "Marketing"
    4. Personal → ignore (keep in inbox)
    5. Notification → mark as read

    When uncertain, use "ignore" to leave in inbox.
    Be conservative with moves and deletions.
  action:
    action: ignore
  stop_processing: true
```

AI for specific domain:

```yaml
- name: "AI Triage Work Email"
  priority: 200
  conditions:
    - type: account_equals
      value: "work@company.com"
    - type: is_unread
      value: true
  use_ai: true
  ai_context: |
    Triage this work email:
    - Urgent/Important: flag
    - Meeting-related: move to "Meetings"
    - Project updates: move to "Projects"
    - FYI/Low priority: mark as read
  action:
    action: ignore
  stop_processing: true
```

### Multi-Account Management

Separate work and personal:

```yaml
# Work account rules
- name: "Work Archive Old Read"
  priority: 100
  conditions:
    - type: account_equals
      value: "work@company.com"
    - type: is_read
      value: true
    - type: mailbox_equals
      value: "INBOX"
  action:
    action: archive
  stop_processing: true

# Personal account rules
- name: "Personal Newsletter Archive"
  priority: 100
  conditions:
    - type: account_equals
      value: "personal@gmail.com"
    - type: body_contains
      value: "unsubscribe"
  action:
    action: archive
  stop_processing: true
```

Cross-account forwarding:

```yaml
- name: "Forward Work to Personal"
  priority: 50
  conditions:
    - type: account_equals
      value: "work@company.com"
    - type: sender_equals
      value: "boss@company.com"
  action:
    action: forward
    forward_to:
      - "personal@gmail.com"
  stop_processing: false
```

### Complex Condition Logic

GitHub PRs requiring review:

```yaml
- name: "GitHub Review Requests"
  priority: 30
  match_all: true
  condition_groups:
    # Must be from GitHub
    - operator: and
      conditions:
        - type: sender_domain
          value: "github.com"

    # Must be unread
    - operator: and
      conditions:
        - type: is_unread
          value: true

    # Must be PR or review request
    - operator: or
      conditions:
        - type: subject_contains
          value: "requested your review"
        - type: subject_contains
          value: "Pull Request"
        - type: body_contains
          value: "review requested"
  action:
    action: flag
  stop_processing: false
```

Urgent emails from team:

```yaml
- name: "Urgent Team Emails"
  priority: 5
  match_all: true
  condition_groups:
    # From internal domain
    - operator: and
      conditions:
        - type: sender_domain
          value: "company.com"

    # Contains urgent keywords
    - operator: or
      conditions:
        - type: subject_contains
          value: "urgent"
        - type: subject_contains
          value: "asap"
        - type: subject_starts_with
          value: "[URGENT]"
  action:
    action: flag
  stop_processing: false
```

## Best Practices

### 1. Start Simple

Begin with basic rules and add complexity as needed:

```yaml
# Good: Start here
- name: "Archive Newsletters"
  conditions:
    - type: body_contains
      value: "unsubscribe"
  action:
    action: archive

# Add later: More sophisticated rules
```

### 2. Use Descriptive Names

```yaml
# Bad
- name: "Rule 1"

# Good
- name: "Archive Marketing Emails from Salesforce"
```

### 3. Test with Dry Run

Always test new rules in dry-run mode:

```bash
email-nurse process --dry-run
```

### 4. Use Priority Effectively

```yaml
# High priority (10-50): VIPs, critical emails
- priority: 10

# Medium priority (50-150): Categorization
- priority: 100

# Low priority (150-900): General cleanup
- priority: 200

# Very low priority (900+): AI fallback
- priority: 999
```

### 5. Be Conservative with Deletion

Prefer `move` to trash over `delete`:

```yaml
# Safer
action:
  action: move
  target_folder: "Trash"

# Risky
action:
  action: delete
```

### 6. Use Comments

```yaml
rules:
  # VIP Sender Rules
  # These run first to ensure important emails are flagged
  - name: "Flag CEO"
    # ...

  # Service Notifications
  # Organize automated notifications by service
  - name: "GitHub"
    # ...
```

### 7. Validate Regularly

```bash
# Validate rules syntax
email-nurse rules validate

# List enabled rules
email-nurse rules list

# Test against specific email
email-nurse rules test --message-id <id>
```

### 8. Version Control

Track your rules configuration:

```bash
cd ~/.config/email-nurse
git init
git add rules.yaml templates.yaml
git commit -m "Initial email rules"
```

### 9. Monitor and Iterate

- Check logs regularly
- Review flagged/moved emails
- Adjust conditions based on false positives
- Refine AI context for better results

### 10. Security Considerations

- Never auto-reply to unknown senders (spam amplification)
- Be careful with forward rules (data leakage)
- Review delete rules carefully (data loss)
- Use case-sensitive matching for sensitive patterns

## Troubleshooting

### Rule Not Matching

**Problem**: Email should match but doesn't.

**Solutions**:
1. Check condition types match field (sender vs subject vs body)
2. Verify case sensitivity settings
3. Test regex patterns externally
4. Check `negate` flag isn't inverting logic
5. Review `match_all` setting (AND vs OR)

### Too Many Matches

**Problem**: Rule matches too broadly.

**Solutions**:
1. Add more specific conditions
2. Use exact matching instead of contains
3. Add negative conditions to exclude
4. Adjust priority to run later
5. Set `stop_processing: false` to allow override

### Actions Not Executing

**Problem**: Rule matches but action doesn't happen.

**Solutions**:
1. Check if running in dry-run mode
2. Verify folder names exist
3. Check account names are correct
4. Review template names match templates.yaml
5. Ensure AI provider is configured (for AI rules)

### AI Rules Inconsistent

**Problem**: AI makes unexpected decisions.

**Solutions**:
1. Provide more specific AI context
2. Give examples in the context
3. Increase confidence threshold
4. Add pre-filter conditions
5. Review AI reasoning in logs

## Next Steps

- [Templates Reference](./templates-reference.md) - Create reply templates
- [Configuration Guide](./configuration.md) - Environment variables and settings
- [CLI Reference](./cli-reference.md) - Command-line usage (coming soon)
