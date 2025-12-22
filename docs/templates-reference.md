# Templates Reference

Complete reference for `templates.yaml` - the reply template configuration file.

## Table of Contents

- [Overview](#overview)
- [Template Structure](#template-structure)
- [Template Types](#template-types)
- [Variables and Placeholders](#variables-and-placeholders)
- [AI-Generated Templates](#ai-generated-templates)
- [Static Templates](#static-templates)
- [Common Use Cases](#common-use-cases)
- [Best Practices](#best-practices)

## Overview

The `templates.yaml` file defines reply templates for automated email responses. Templates can be:

1. **AI-Generated**: Provide instructions, AI generates contextual reply
2. **Static**: Pre-written text sent as-is
3. **Hybrid**: Static text with AI-enhanced personalization

**Location**: `~/.config/email-nurse/templates.yaml`

## Template Structure

### Complete Template Anatomy

```yaml
templates:
  template_name:                        # Unique identifier
    description: "What this template does"  # Optional: human-readable
    subject_prefix: "Re: "               # Optional: add to subject line
    use_ai: true                         # true = AI generates, false = static
    content: |                           # Template content or AI instructions
      For AI templates: instructions for generation
      For static templates: actual text to send

    variables:                           # Optional: placeholder variables
      DATE: "2024-01-15"
      CONTACT: "support@company.com"
```

### Minimal Template Example

```yaml
templates:
  simple_reply:
    content: "Thank you for your email. I'll get back to you soon."
```

### Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| Template name | string | Yes | - | Unique identifier (used in rules) |
| `description` | string | No | `null` | Human-readable description |
| `subject_prefix` | string | No | `null` | Prefix to add to reply subject |
| `use_ai` | boolean | No | `true` | Use AI to generate reply |
| `content` | string | Yes | - | Template content or AI instructions |
| `variables` | object | No | `{}` | Variable placeholders and defaults |

## Template Types

### AI-Generated Template

The AI reads the original email and generates a contextual reply based on your instructions.

```yaml
templates:
  acknowledge:
    description: "AI-generated acknowledgment"
    use_ai: true
    content: |
      Generate a brief, professional acknowledgment.
      - Thank the sender for their message
      - Indicate it has been received
      - Keep it under 3 sentences
      - Match the formality of the original email
```

**Advantages**:
- Contextual and personalized
- Adapts to email content
- Natural language generation
- Matches sender's tone

**Use cases**:
- Acknowledgments
- Follow-up requests
- Meeting scheduling
- Support responses

### Static Template

Pre-written text sent exactly as defined.

```yaml
templates:
  out_of_office:
    description: "Static out-of-office reply"
    use_ai: false
    subject_prefix: "Auto-Reply: "
    content: |
      Thank you for your email. I am currently out of the office
      with limited access to email.

      I will respond when I return on January 15, 2024.

      For urgent matters, please contact support@company.com.

      Best regards
```

**Advantages**:
- Consistent messaging
- No AI costs
- Faster generation
- Fully controlled content

**Use cases**:
- Out of office replies
- Standard responses
- Legal disclaimers
- Automated confirmations

### Hybrid Template (AI with Variables)

Combine static variables with AI generation:

```yaml
templates:
  hybrid_response:
    use_ai: true
    variables:
      COMPANY_NAME: "Acme Corp"
      SUPPORT_EMAIL: "support@acme.com"
    content: |
      Generate a professional response that includes:
      - Thank them for contacting {COMPANY_NAME}
      - Acknowledge their specific question/request
      - For technical issues, direct them to {SUPPORT_EMAIL}
      - Keep it friendly and helpful
```

**Note**: Variable substitution happens before AI processing.

## Variables and Placeholders

### Defining Variables

Variables provide default values for placeholders:

```yaml
templates:
  template_with_vars:
    use_ai: false
    variables:
      DATE: "2024-01-15"
      CONTACT_NAME: "John Smith"
      CONTACT_EMAIL: "john@company.com"
      PHONE: "+1-555-0100"
    content: |
      I will be back on {DATE}.
      Contact {CONTACT_NAME} at {CONTACT_EMAIL} or {PHONE}.
```

### Variable Syntax

Use curly braces for placeholders:

```yaml
content: |
  Hello {NAME},

  Thank you for your email about {TOPIC}.
  We will respond within {TIMEFRAME}.

  {SIGNATURE}
```

### Built-in Variables

Email Nurse automatically provides these variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `{SENDER_NAME}` | Original sender's name | "John Smith" |
| `{SENDER_EMAIL}` | Original sender's email | "john@example.com" |
| `{SUBJECT}` | Original email subject | "Project Update" |
| `{DATE}` | Current date | "2024-01-15" |
| `{TIME}` | Current time | "14:30" |

**Example**:

```yaml
templates:
  auto_acknowledge:
    use_ai: false
    content: |
      Hi {SENDER_NAME},

      Thank you for your email regarding "{SUBJECT}".
      I received it on {DATE} at {TIME}.

      I'll respond within 24 hours.

      Best regards
```

### Custom Variables

Define your own variables for reusability:

```yaml
templates:
  support_response:
    variables:
      SUPPORT_HOURS: "Monday-Friday 9AM-5PM EST"
      SLA_TIME: "24 hours"
      TICKET_SYSTEM: "https://support.company.com"
    content: |
      Thank you for contacting support.

      Support hours: {SUPPORT_HOURS}
      Response time: {SLA_TIME}
      Track your request: {TICKET_SYSTEM}
```

## AI-Generated Templates

### How AI Templates Work

1. **User defines instructions** in `content` field
2. **Email Nurse reads** the original email
3. **AI analyzes** the email and instructions
4. **AI generates** a contextual reply
5. **Reply is created** as a draft in Mail.app

### Writing Effective AI Instructions

#### Be Specific

```yaml
# Bad: Too vague
content: "Write a nice reply"

# Good: Specific instructions
content: |
  Generate a professional acknowledgment:
  - Thank them for their email
  - Confirm you received their request
  - Set expectation for 24-48 hour response
  - Keep it under 4 sentences
```

#### Provide Structure

```yaml
content: |
  Generate a reply with this structure:

  1. Opening: Thank them for reaching out
  2. Acknowledgment: Summarize their request briefly
  3. Next Steps: Explain what will happen next
  4. Timeline: When they can expect a response
  5. Closing: Professional sign-off

  Tone: Professional but friendly
  Length: 4-6 sentences
```

#### Define Tone and Style

```yaml
content: |
  Generate a casual, friendly reply:
  - Use conversational language
  - Be warm and approachable
  - Avoid overly formal language
  - Match the sender's tone
  - Add a touch of personality
```

#### Give Examples

```yaml
content: |
  Generate a meeting scheduling reply.

  Example format:
  "Thanks for reaching out! I'd be happy to meet.
  I'm available:
  - Tuesday 2-4 PM
  - Wednesday 10 AM-12 PM
  - Thursday 3-5 PM

  Do any of these work for you?"

  Generate similar response with reasonable times.
```

#### Set Boundaries

```yaml
content: |
  Generate a polite decline:
  - Thank them for the opportunity
  - Briefly explain you can't accommodate this
  - Do NOT make excuses or apologize excessively
  - Wish them well
  - Keep it professional and concise
```

### AI Template Examples

#### Acknowledgment

```yaml
templates:
  acknowledge:
    description: "Brief acknowledgment of receipt"
    use_ai: true
    content: |
      Generate a brief, professional acknowledgment:
      - Thank the sender for their message
      - Confirm the message has been received
      - Indicate it will be reviewed
      - Keep it under 3 sentences
      - Match the formality level of the original email
```

#### Information Request

```yaml
templates:
  request_info:
    description: "Ask for more information"
    use_ai: true
    content: |
      Generate a polite request for clarification:
      - Identify what's unclear in the original email
      - Ask 1-2 specific questions
      - Be professional and helpful
      - Keep it concise (3-4 sentences)
```

#### Meeting Scheduling

```yaml
templates:
  schedule_meeting:
    description: "Propose meeting times"
    use_ai: true
    content: |
      Generate a meeting scheduling reply:
      - Acknowledge the topic they want to discuss
      - Propose 2-3 specific time slots (use reasonable business hours)
      - Ask about their preferred format (call, video, in-person)
      - Keep it professional and accommodating
```

#### Decline Request

```yaml
templates:
  decline_politely:
    description: "Politely decline a request"
    use_ai: true
    content: |
      Generate a polite but firm decline:
      - Thank them for thinking of you
      - Briefly state you cannot accommodate the request
      - Do NOT apologize excessively or make long excuses
      - Wish them well finding an alternative
      - Keep it professional and concise (3-4 sentences)
```

#### Support Response

```yaml
templates:
  support_ack:
    description: "Technical support acknowledgment"
    use_ai: true
    content: |
      Generate a support ticket acknowledgment:
      - Confirm you received their support request
      - Briefly summarize your understanding of the issue
      - Set expectation for response time (24-48 hours)
      - Ask for any additional details that would help
      - Provide ticket/reference number if applicable
      - Professional and reassuring tone
```

#### Follow-up

```yaml
templates:
  follow_up:
    description: "Follow up on previous conversation"
    use_ai: true
    content: |
      Generate a friendly follow-up:
      - Reference the previous conversation/email
      - Ask if they need anything else
      - Offer to help with next steps
      - Keep it brief and helpful
      - Warm, professional tone
```

## Static Templates

### Simple Static Reply

```yaml
templates:
  simple_thanks:
    description: "Simple thank you"
    use_ai: false
    content: |
      Thank you for your email.

      I'll review it and get back to you soon.

      Best regards
```

### Out of Office

```yaml
templates:
  out_of_office:
    description: "Out of office auto-reply"
    use_ai: false
    subject_prefix: "Auto-Reply: "
    variables:
      RETURN_DATE: "January 15, 2024"
      BACKUP_CONTACT: "assistant@company.com"
    content: |
      Thank you for your email. I am currently out of the office
      with limited access to email.

      I will respond to your message when I return on {RETURN_DATE}.

      For urgent matters, please contact {BACKUP_CONTACT}.

      Best regards
```

### Standard Confirmation

```yaml
templates:
  order_confirmation:
    description: "Order received confirmation"
    use_ai: false
    variables:
      PROCESSING_TIME: "2-3 business days"
      SUPPORT_EMAIL: "support@company.com"
    content: |
      Thank you for your order!

      We have received your request and will begin processing
      within {PROCESSING_TIME}.

      You will receive a confirmation email with tracking information
      once your order ships.

      If you have any questions, please contact {SUPPORT_EMAIL}.

      Thank you for your business!
```

### Unsubscribe Confirmation

```yaml
templates:
  unsubscribe:
    description: "Unsubscribe confirmation"
    use_ai: false
    subject_prefix: "Confirmed: "
    content: |
      You have been successfully unsubscribed from our mailing list.

      You will no longer receive marketing emails from us.

      If this was a mistake, you can resubscribe at:
      https://company.com/subscribe

      Thank you.
```

### Meeting Confirmation

```yaml
templates:
  meeting_confirmed:
    description: "Meeting time confirmation"
    use_ai: false
    variables:
      MEETING_TIME: "Tuesday, January 15 at 2:00 PM"
      MEETING_LINK: "https://zoom.us/j/123456789"
    content: |
      Meeting confirmed for {MEETING_TIME}.

      Join via: {MEETING_LINK}

      I'll send an agenda 24 hours before the meeting.

      Looking forward to speaking with you!
```

## Common Use Cases

### Auto-Responders

#### Vacation/OOO

```yaml
templates:
  vacation:
    description: "Vacation auto-reply"
    use_ai: false
    subject_prefix: "Auto-Reply: "
    variables:
      START_DATE: "January 10"
      END_DATE: "January 20"
      BACKUP_PERSON: "Jane Smith"
      BACKUP_EMAIL: "jane@company.com"
    content: |
      Thank you for your email.

      I am on vacation from {START_DATE} to {END_DATE} with
      limited email access.

      For urgent matters, please contact {BACKUP_PERSON}
      at {BACKUP_EMAIL}.

      I will respond to your message when I return.

      Best regards
```

#### Weekend Auto-Reply

```yaml
templates:
  weekend_reply:
    description: "Weekend auto-reply"
    use_ai: false
    content: |
      Thank you for your email.

      I don't check email on weekends. I'll respond to your
      message on Monday.

      For urgent matters, please call the office at +1-555-0100.

      Have a great weekend!
```

### Customer Support

#### Initial Support Response

```yaml
templates:
  support_received:
    description: "Support ticket received"
    use_ai: true
    variables:
      SUPPORT_SLA: "within 24 hours"
      SUPPORT_PORTAL: "https://support.company.com"
    content: |
      Generate a support acknowledgment:
      - Thank them for contacting support
      - Confirm ticket has been created
      - Summarize the issue they reported
      - Set expectation: will respond {SUPPORT_SLA}
      - Provide portal link: {SUPPORT_PORTAL}
      - Ask if they have additional details
      - Professional, helpful tone
```

#### Bug Report Acknowledgment

```yaml
templates:
  bug_report_ack:
    description: "Bug report acknowledgment"
    use_ai: true
    content: |
      Generate a bug report acknowledgment:
      - Thank them for reporting the issue
      - Confirm the bug has been logged
      - Briefly describe your understanding of the problem
      - Explain it will be investigated by engineering
      - Offer to keep them updated on progress
      - Helpful, technical but accessible tone
```

### Sales and Business

#### Lead Follow-up

```yaml
templates:
  sales_followup:
    description: "Sales lead follow-up"
    use_ai: true
    content: |
      Generate a sales follow-up:
      - Thank them for their interest
      - Reference what product/service they asked about
      - Ask 1-2 qualifying questions
      - Offer to schedule a demo or call
      - Provide contact information
      - Professional, enthusiastic tone
      - 4-5 sentences
```

#### Quote Request Response

```yaml
templates:
  quote_response:
    description: "Quote request response"
    use_ai: true
    variables:
      TURNAROUND_TIME: "2-3 business days"
      SALES_EMAIL: "sales@company.com"
    content: |
      Generate a quote request response:
      - Thank them for requesting a quote
      - Confirm you received their requirements
      - Ask any clarifying questions needed
      - Set expectation: quote ready in {TURNAROUND_TIME}
      - Provide contact: {SALES_EMAIL}
      - Professional, helpful tone
```

### Internal Communication

#### Task Acknowledgment

```yaml
templates:
  task_received:
    description: "Task assignment acknowledgment"
    use_ai: true
    content: |
      Generate an internal task acknowledgment:
      - Confirm you received the task
      - Summarize your understanding of requirements
      - Provide estimated completion time
      - Ask about priorities if multiple tasks
      - Professional, collaborative tone
      - Keep it brief (3-4 sentences)
```

#### Meeting Request Response

```yaml
templates:
  meeting_accept:
    description: "Accept meeting invitation"
    use_ai: true
    content: |
      Generate a meeting acceptance:
      - Confirm you can attend
      - Ask if there's anything to prepare
      - Offer to help with agenda if needed
      - Friendly, professional tone
      - 2-3 sentences
```

### Personal Productivity

#### Email Batch Processing

```yaml
templates:
  batch_reply:
    description: "Batch processing response"
    use_ai: true
    content: |
      Generate a brief acknowledgment:
      - Thank them for their email
      - Explain you process email in batches
      - Set expectation for response time (24-48 hours)
      - Professional, efficient tone
      - 2-3 sentences
```

#### Referral

```yaml
templates:
  referral:
    description: "Refer to another person"
    use_ai: true
    variables:
      REFERRAL_NAME: "John Smith"
      REFERRAL_EMAIL: "john@company.com"
    content: |
      Generate a referral response:
      - Thank them for reaching out
      - Explain {REFERRAL_NAME} is the best person for this
      - Provide their contact: {REFERRAL_EMAIL}
      - Offer to make an introduction if helpful
      - Professional, helpful tone
```

## Best Practices

### 1. Choose the Right Template Type

**Use AI templates when**:
- Response needs context from the email
- Personalization is important
- Tone needs to match sender
- Request requires understanding

**Use static templates when**:
- Same response every time
- No context needed
- Speed is critical
- Consistency is required
- Privacy concerns (no AI processing)

### 2. Write Clear AI Instructions

```yaml
# Bad: Too vague
content: "Reply nicely"

# Good: Specific and structured
content: |
  Generate a professional reply with:
  1. Thank them for their message
  2. Acknowledge their specific request
  3. Set expectations for next steps
  4. Professional, friendly tone
  5. 3-4 sentences
```

### 3. Use Variables for Flexibility

```yaml
templates:
  flexible_ooo:
    use_ai: false
    variables:
      RETURN_DATE: "January 15"
      BACKUP_EMAIL: "assistant@company.com"
    content: |
      I'm out of office until {RETURN_DATE}.
      Contact {BACKUP_EMAIL} for urgent matters.
```

Update variables without changing template:

```yaml
# Just update the variables section
variables:
  RETURN_DATE: "February 20"
  BACKUP_EMAIL: "manager@company.com"
```

### 4. Test Templates Before Deploying

```bash
# Test in dry-run mode
email-nurse process --dry-run

# Review generated replies before sending
# (Replies are created as drafts by default)
```

### 5. Organize Templates by Category

```yaml
templates:
  # Out of Office
  ooo_vacation:
    # ...
  ooo_weekend:
    # ...

  # Support
  support_ack:
    # ...
  bug_report:
    # ...

  # Sales
  sales_inquiry:
    # ...
  quote_request:
    # ...
```

### 6. Keep Content Concise

```yaml
# Good: Concise AI instructions
content: |
  Brief professional acknowledgment.
  Thank sender, confirm receipt, 2-3 sentences.

# Bad: Overly complex instructions
content: |
  Generate a comprehensive, detailed, thoughtful response
  that carefully considers all aspects of their message
  while maintaining a professional yet approachable tone...
  [10 more lines]
```

### 7. Version Control Templates

Track changes to your templates:

```bash
cd ~/.config/email-nurse
git add templates.yaml
git commit -m "Add new support templates"
```

### 8. Use Descriptive Names

```yaml
# Bad
templates:
  template1:
    # ...

# Good
templates:
  support_bug_report_acknowledgment:
    # ...
```

### 9. Document Your Templates

```yaml
templates:
  complex_template:
    description: |
      Used for: Sales inquiries about Enterprise plan
      Triggers: Rule "Sales Inquiry" in rules.yaml
      Generated: AI-based with qualification questions
    content: |
      # ...
```

### 10. Handle Edge Cases

```yaml
templates:
  smart_response:
    use_ai: true
    content: |
      Generate an appropriate response.

      If the email is:
      - A question: Answer helpfully
      - A request: Acknowledge and explain next steps
      - A complaint: Be empathetic and solution-focused
      - Unclear: Ask for clarification politely

      Always be professional and helpful.
```

## Subject Line Handling

### Default Behavior

By default, replies use "Re: [original subject]":

Original: "Project Update"
Reply: "Re: Project Update"

### Custom Subject Prefix

Override the default prefix:

```yaml
templates:
  custom_subject:
    subject_prefix: "Auto-Reply: "
    # ...
```

Original: "Project Update"
Reply: "Auto-Reply: Project Update"

### Remove Prefix

Use empty string to keep original subject:

```yaml
templates:
  no_prefix:
    subject_prefix: ""
    # ...
```

Original: "Project Update"
Reply: "Project Update"

### AI-Generated Subject

For AI templates, you can ask AI to modify the subject:

```yaml
templates:
  ai_subject:
    use_ai: true
    content: |
      Generate a reply.

      Subject line: Add "[Processed]" prefix to original subject.
      Body: [your instructions]
```

## Template Validation

### Validate Templates

```bash
# Check templates.yaml syntax
email-nurse templates validate

# List all templates
email-nurse templates list

# Show specific template
email-nurse templates show out_of_office
```

### Common Validation Errors

**Missing required fields**:
```yaml
# Error: content is required
templates:
  broken:
    description: "Missing content"
    # No content field!
```

**Invalid YAML syntax**:
```yaml
# Error: Inconsistent indentation
templates:
  broken:
  description: "Wrong indent"
    content: "Also wrong"
```

**Invalid variable syntax**:
```yaml
# Error: Variables should use curly braces
content: "Return on $DATE"  # Wrong
content: "Return on {DATE}"  # Correct
```

## Troubleshooting

### Template Not Found

**Error**: "Template 'xyz' not found"

**Solution**:
1. Check template name in rules.yaml matches templates.yaml
2. Verify templates.yaml is in correct location
3. Check for typos in template name

### AI Reply Not Generated

**Error**: Reply is empty or generic

**Solution**:
1. Ensure AI provider is configured
2. Check API key is valid
3. Review AI instructions for clarity
4. Enable debug logging to see AI errors

### Variables Not Substituted

**Error**: Reply contains "{VARIABLE_NAME}" literally

**Solution**:
1. Check variable is defined in `variables` section
2. Verify variable name matches exactly (case-sensitive)
3. Ensure curly braces syntax: `{VAR}` not `$VAR` or `%VAR%`

### Reply Tone Doesn't Match

**Error**: AI reply too formal/informal

**Solution**:
1. Add explicit tone instructions
2. Give examples of desired style
3. Ask AI to "match sender's tone"
4. Be more specific about formality level

## Advanced Techniques

### Conditional Instructions

```yaml
templates:
  smart_reply:
    use_ai: true
    content: |
      Analyze the email and respond appropriately:

      IF sender is asking a question:
        - Answer the question directly
        - Provide helpful details
        - Ask if they need more info

      IF sender is making a request:
        - Acknowledge the request
        - Confirm if you can help
        - Explain next steps or timeline

      IF sender is providing information:
        - Thank them for the update
        - Confirm you received it
        - Ask clarifying questions if needed

      Always be professional and helpful.
```

### Multi-Language Support

```yaml
templates:
  multilingual_reply:
    use_ai: true
    content: |
      Detect the language of the incoming email.
      Reply in the SAME language.

      Content:
      - Thank them for their message
      - Confirm receipt
      - Professional tone

      Languages to support: English, Spanish, French, German
```

### Context-Aware Responses

```yaml
templates:
  context_aware:
    use_ai: true
    content: |
      Consider the email's context:
      - Time sent (business hours vs after hours)
      - Day of week (weekday vs weekend)
      - Email history (first contact vs ongoing conversation)
      - Urgency indicators in subject/body

      Adjust response accordingly:
      - Urgent → prioritize, respond quickly
      - After hours → acknowledge, set timeline
      - First contact → warmer, more detailed
      - Follow-up → brief, focused
```

## Performance Considerations

### AI Template Costs

Each AI template generates an API call:
- Claude: ~$0.002-0.01 per email
- OpenAI: ~$0.001-0.005 per email
- Ollama: Free (local)

**Cost optimization**:
1. Use static templates when possible
2. Pre-filter with rules before AI
3. Use simpler/shorter AI instructions
4. Consider local Ollama for high volume

### Generation Speed

**AI templates**: 1-5 seconds per email
**Static templates**: Instant

For high-volume processing, prefer static templates or local AI.

## Next Steps

- [Rules Reference](./rules-reference.md) - Use templates in reply actions
- [Configuration Guide](./configuration.md) - Set up AI providers
- [CLI Reference](./cli-reference.md) - Test templates (coming soon)

## Examples Repository

Full working examples available in the example configs:

```bash
# View example templates
cat ~/.config/email-nurse/templates.yaml.example

# Copy examples as starting point
cp config/templates.yaml.example ~/.config/email-nurse/templates.yaml
```
