# Email Nurse Documentation

Comprehensive technical documentation for the Email Nurse AI-powered email management system.

## Documentation Overview

Email Nurse is an AI-powered email automation tool for macOS Mail.app that intelligently processes, categorizes, and responds to emails using custom rules and AI classification.

### Core Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| [Configuration Guide](./configuration.md) | System setup, environment variables, and file locations | All users |
| [Rules Reference](./rules-reference.md) | Complete `rules.yaml` schema and examples | Rule authors |
| [Templates Reference](./templates-reference.md) | Complete `templates.yaml` schema and examples | Template authors |

## Quick Start

### First Time Setup

1. **Install Email Nurse**
   ```bash
   cd /path/to/email-nurse
   uv pip install -e ".[dev]"
   ```

2. **Initialize Configuration**
   ```bash
   email-nurse init
   ```

3. **Configure API Key**
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-xxxxx
   ```

4. **Test Your Setup**
   ```bash
   email-nurse messages list --limit 5
   email-nurse process --dry-run
   ```

5. **Read the Documentation**
   - Start with [Configuration Guide](./configuration.md)
   - Create rules using [Rules Reference](./rules-reference.md)
   - Add templates using [Templates Reference](./templates-reference.md)

## Document Summaries

### Configuration Guide
**File**: `configuration.md` | **Length**: ~12 KB | **Sections**: 9

Covers the complete configuration system:
- Configuration directory structure
- Environment variables (AI providers, processing settings)
- Initial setup and verification
- AI provider configuration (Claude, OpenAI, Ollama)
- Processing settings and intervals
- Best practices and troubleshooting

**Read this first** to understand where files go and how to configure the system.

### Rules Reference
**File**: `rules-reference.md` | **Length**: ~36 KB | **Sections**: 10

Complete reference for `rules.yaml`:
- Rule structure and anatomy
- 18 condition types with examples:
  - Sender conditions (contains, equals, domain, regex)
  - Subject conditions (contains, equals, regex, starts_with)
  - Body conditions (contains, regex)
  - Recipient conditions (contains, equals)
  - Mailbox/account conditions
  - Read status conditions
  - AI classification
- Condition options (case_sensitive, negate)
- Condition groups (AND/OR logic)
- 10 action types (move, delete, archive, flag, reply, etc.)
- AI-powered rules with context
- Priority and processing order
- 12+ common patterns (newsletters, VIPs, receipts, etc.)

**Read this** to create powerful email processing rules.

### Templates Reference
**File**: `templates-reference.md` | **Length**: ~25 KB | **Sections**: 9

Complete reference for `templates.yaml`:
- Template structure and anatomy
- AI-generated vs static templates
- Variables and placeholders (built-in and custom)
- AI instruction writing best practices
- 20+ template examples:
  - Auto-responders (OOO, weekend)
  - Customer support (acknowledgments, bug reports)
  - Sales and business (quotes, follow-ups)
  - Internal communication (tasks, meetings)
  - Personal productivity
- Subject line handling
- Template validation and troubleshooting
- Performance considerations

**Read this** to create effective reply templates.

## Architecture Overview

### System Components

```
Email Nurse
├── Mail.app Integration (AppleScript)
│   ├── Read messages
│   ├── Execute actions
│   └── Create drafts
│
├── Rule Engine
│   ├── Load rules.yaml
│   ├── Evaluate conditions
│   ├── Match emails
│   └── Trigger actions
│
├── AI Classification
│   ├── Claude (Anthropic)
│   ├── OpenAI (GPT-4)
│   └── Ollama (Local)
│
├── Template Engine
│   ├── Load templates.yaml
│   ├── Variable substitution
│   └── AI generation
│
└── CLI Interface
    ├── email-nurse process
    ├── email-nurse daemon
    └── email-nurse messages
```

### Configuration Flow

```
User creates:
  ~/.config/email-nurse/rules.yaml
  ~/.config/email-nurse/templates.yaml

Environment variables:
  ANTHROPIC_API_KEY=xxx
  EMAIL_NURSE_AI_PROVIDER=claude

Email Nurse loads:
  1. Read config files
  2. Initialize AI provider
  3. Load rules into RuleEngine
  4. Load templates into TemplateManager

Processing:
  1. Fetch emails from Mail.app
  2. For each email:
     a. Evaluate rules in priority order
     b. Check conditions
     c. Execute action (or run AI)
     d. Stop if stop_processing=true
  3. Create drafts or execute actions
```

## Configuration File Reference

### rules.yaml Structure

```yaml
rules:
  - name: string                    # Required: unique identifier
    description: string              # Optional
    enabled: boolean                 # Default: true
    priority: integer                # Default: 100, lower = first
    stop_processing: boolean         # Default: true

    conditions:                      # Optional: list of conditions
      - type: ConditionType          # Required
        value: any                   # Required
        case_sensitive: boolean      # Default: false
        negate: boolean              # Default: false

    condition_groups:                # Optional: grouped conditions
      - operator: "and" | "or"       # Required
        conditions: [...]            # List of conditions

    match_all: boolean               # Default: true (AND vs OR)

    action:                          # Required
      action: EmailAction            # Required
      target_folder: string          # For move actions
      target_account: string         # For cross-account moves
      reply_template: string         # For reply actions
      forward_to: [string]           # For forward actions

    use_ai: boolean                  # Default: false
    ai_context: string               # Optional AI instructions
```

### templates.yaml Structure

```yaml
templates:
  template_name:                     # Required: unique identifier
    description: string              # Optional
    subject_prefix: string           # Optional: "Re: ", "Auto-Reply: ", etc.
    use_ai: boolean                  # Default: true
    content: string                  # Required: text or AI instructions
    variables:                       # Optional: key-value pairs
      KEY: "default value"
```

## Condition Types Quick Reference

| Category | Condition Types |
|----------|-----------------|
| **Sender** | `sender_contains`, `sender_equals`, `sender_domain`, `sender_regex` |
| **Subject** | `subject_contains`, `subject_equals`, `subject_regex`, `subject_starts_with` |
| **Body** | `body_contains`, `body_regex` |
| **Recipient** | `recipient_contains`, `recipient_equals` |
| **Location** | `mailbox_equals`, `account_equals` |
| **Status** | `is_read`, `is_unread` |
| **AI** | `ai_classify` |

## Action Types Quick Reference

| Action | Description | Required Fields |
|--------|-------------|-----------------|
| `move` | Move to folder | `target_folder` |
| `delete` | Delete permanently | None |
| `archive` | Move to Archive | None |
| `mark_read` | Mark as read | None |
| `mark_unread` | Mark as unread | None |
| `flag` | Add flag/star | None |
| `unflag` | Remove flag/star | None |
| `reply` | Auto-reply | `reply_template` |
| `forward` | Forward email | `forward_to` |
| `ignore` | No action | None |

## Common Workflows

### Workflow 1: Simple Newsletter Archiving

**Goal**: Auto-archive newsletters

**Config**:
```yaml
# rules.yaml
rules:
  - name: "Archive Newsletters"
    conditions:
      - type: body_contains
        value: "unsubscribe"
    action:
      action: archive
```

### Workflow 2: VIP Sender Handling

**Goal**: Flag and organize VIP emails

**Config**:
```yaml
# rules.yaml
rules:
  - name: "Flag CEO Emails"
    priority: 10
    stop_processing: false
    conditions:
      - type: sender_equals
        value: "ceo@company.com"
    action:
      action: flag

  - name: "Move to VIP Folder"
    priority: 20
    conditions:
      - type: sender_equals
        value: "ceo@company.com"
    action:
      action: move
      target_folder: "VIP"
```

### Workflow 3: AI-Powered Triage

**Goal**: Let AI categorize complex emails

**Config**:
```yaml
# rules.yaml
rules:
  - name: "AI Triage"
    priority: 999
    conditions: []
    use_ai: true
    ai_context: |
      Categorize:
      - Newsletter → archive
      - Receipt → move to "Finance"
      - Personal → ignore
    action:
      action: ignore
```

### Workflow 4: Auto-Reply with Template

**Goal**: Auto-acknowledge support emails

**Config**:
```yaml
# rules.yaml
rules:
  - name: "Support Auto-Reply"
    conditions:
      - type: recipient_contains
        value: "support@company.com"
    action:
      action: reply
      reply_template: "support_ack"

# templates.yaml
templates:
  support_ack:
    use_ai: true
    content: |
      Thank customer, confirm ticket received,
      set 24-hour response expectation.
```

## Best Practices Summary

### Rules Best Practices

1. **Start simple**: Begin with basic conditions, add complexity gradually
2. **Use priority**: Organize rules by importance (10 = critical, 999 = fallback)
3. **Test in dry-run**: Always test new rules with `--dry-run` first
4. **Be conservative**: Prefer `move` to trash over `delete`
5. **Use descriptive names**: "Archive GitHub Notifications" not "Rule 1"
6. **Monitor and iterate**: Review logs, adjust conditions based on results

### Template Best Practices

1. **Choose the right type**: AI for context-aware, static for consistency
2. **Write clear instructions**: Be specific, provide structure, set boundaries
3. **Use variables**: Make templates flexible and reusable
4. **Test before deploying**: Review generated replies in dry-run mode
5. **Keep it concise**: Shorter instructions = better AI results
6. **Version control**: Track changes to templates over time

### Configuration Best Practices

1. **Use version control**: Track `rules.yaml` and `templates.yaml` in git
2. **Secure API keys**: Use `.env` files, never commit secrets
3. **Start with dry-run**: Set `EMAIL_NURSE_DRY_RUN=true` initially
4. **Enable logging**: Use `EMAIL_NURSE_LOG_LEVEL=DEBUG` during setup
5. **Backup configs**: Keep backups before major changes
6. **Incremental deployment**: Add rules one at a time, verify each works

## Troubleshooting Guide

### Common Issues

| Issue | Solution | Documentation |
|-------|----------|---------------|
| Configuration not found | Run `email-nurse init` | [Configuration Guide](./configuration.md#initial-setup) |
| API key invalid | Verify `ANTHROPIC_API_KEY` is set | [Configuration Guide](./configuration.md#ai-provider-settings) |
| Rule not matching | Check condition types and values | [Rules Reference](./rules-reference.md#troubleshooting) |
| Template not found | Verify template name matches | [Templates Reference](./templates-reference.md#troubleshooting) |
| AI replies inconsistent | Improve AI instructions | [Templates Reference](./templates-reference.md#writing-effective-ai-instructions) |
| Mail.app connection failed | Grant automation permissions | [Configuration Guide](./configuration.md#troubleshooting) |

### Debug Checklist

1. **Enable debug logging**
   ```bash
   export EMAIL_NURSE_LOG_LEVEL=DEBUG
   ```

2. **Validate configuration**
   ```bash
   email-nurse rules validate
   email-nurse templates validate
   ```

3. **Test specific email**
   ```bash
   email-nurse rules test --message-id <id>
   ```

4. **Run in dry-run mode**
   ```bash
   email-nurse process --dry-run
   ```

5. **Check logs**
   ```bash
   tail -f ~/.config/email-nurse/email-nurse.log
   ```

## Examples and Recipes

Each documentation file includes extensive examples:

- **Configuration Guide**: 7+ environment variable examples, 5+ setup scenarios
- **Rules Reference**: 40+ rule examples, 12+ common patterns
- **Templates Reference**: 20+ template examples, 10+ use cases

### Finding Examples

**In Rules Reference**:
- Search for "Example:" in sections
- See [Common Patterns](./rules-reference.md#common-patterns) section
- Look for YAML code blocks with comments

**In Templates Reference**:
- See [AI Template Examples](./templates-reference.md#ai-template-examples) section
- See [Common Use Cases](./templates-reference.md#common-use-cases) section
- Check example configs in `config/*.yaml.example`

## Additional Resources

### Code Examples

See the example configuration files:
```bash
cat /path/to/email-nurse/config/rules.yaml.example
cat /path/to/email-nurse/config/templates.yaml.example
```

### Source Code

Key modules to understand:
- `/Users/bss/code/email-nurse/src/email_nurse/rules/conditions.py` - Condition types
- `/Users/bss/code/email-nurse/src/email_nurse/rules/engine.py` - Rule processing
- `/Users/bss/code/email-nurse/src/email_nurse/ai/base.py` - AI interface
- `/Users/bss/code/email-nurse/src/email_nurse/templates/manager.py` - Template management
- `/Users/bss/code/email-nurse/src/email_nurse/config.py` - Configuration

### Testing

Run the test suite to see examples in action:
```bash
pytest tests/
pytest tests/test_conditions.py -v
pytest tests/test_rules_engine.py -v
```

## Documentation Maintenance

### Updating Documentation

When making changes to Email Nurse:

1. **Code changes**: Update relevant documentation
2. **New features**: Add examples and update references
3. **Breaking changes**: Highlight in configuration guide
4. **Deprecations**: Mark clearly and provide migration path

### Documentation Standards

- **Format**: Markdown with GitHub-flavored extensions
- **Examples**: Always include working YAML examples
- **Code blocks**: Use syntax highlighting (```yaml, ```bash)
- **Links**: Use relative links between docs
- **Tables**: Use for quick reference information
- **Length**: Aim for comprehensive but scannable

## Contributing

To improve this documentation:

1. Fork the repository
2. Make changes in `/docs`
3. Test examples to ensure they work
4. Submit pull request with clear description

## Version History

- **v1.0** (2024-01): Initial documentation
  - Configuration guide
  - Complete rules reference
  - Complete templates reference
  - Common patterns and examples

## License

Documentation licensed under MIT License (same as Email Nurse).

---

**Ready to get started?** Begin with the [Configuration Guide](./configuration.md) to set up Email Nurse.

**Have questions?** Check the troubleshooting sections in each guide.

**Want examples?** Jump to the common patterns sections in the rules and templates references.
