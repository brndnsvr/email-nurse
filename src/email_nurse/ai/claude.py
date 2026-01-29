"""Anthropic Claude AI provider implementation."""

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

from email_nurse.ai.base import AIProvider, EmailAction, EmailClassification

if TYPE_CHECKING:
    from email_nurse.autopilot.config import QuickRule
    from email_nurse.autopilot.models import AutopilotDecision
    from email_nurse.mail.messages import EmailMessage


CLASSIFICATION_SYSTEM_PROMPT = """You are an email classification assistant. Your task is to analyze emails and recommend actions based on the user's preferences and rules.

Available actions:
- move: Move to a specific folder
- delete: Delete the message (move to trash)
- archive: Archive the message
- mark_read: Mark as read without other action
- mark_unread: Mark as unread
- reply: Send a reply using a template
- forward: Forward to specified addresses
- ignore: Take no action

Respond with a JSON object containing:
- action: One of the available actions
- confidence: 0.0 to 1.0 confidence in the recommendation
- category: A short category label (e.g., "newsletter", "invoice", "personal")
- target_folder: For move actions, the destination folder
- reply_template: For reply actions, the template name to use
- forward_to: For forward actions, list of email addresses
- reasoning: Brief explanation of your decision

Consider the sender, subject, content, and any provided context/rules."""


QUICK_RULE_SYSTEM_PROMPT = """You parse natural language descriptions into email quick rules.

Output ONLY valid JSON matching this exact schema:
{
  "name": "Rule Name",
  "match": {
    "sender_contains": ["pattern"],
    "subject_contains": ["pattern"],
    "sender_domain": ["domain.com"]
  },
  "action": "move",
  "folder": "FolderName"
}

Rules for generating the JSON:
- "name": Generate a concise descriptive name (2-5 words)
- "match": Include ONLY the relevant condition(s):
  - "sender_contains": For specific email addresses or partial matches (e.g., "bob@example.com")
  - "sender_domain": For domain-wide rules (e.g., "github.com" for all @github.com emails)
  - "subject_contains": For subject line patterns
- "action": One of: "move", "delete", "archive", "mark_read", "ignore"
- "folder": Required ONLY if action is "move"
- For multiple actions, use "actions": ["mark_read", "delete"] instead of "action"

Infer action from verbs:
- "trash", "delete", "remove" → "delete"
- "move", "put", "send to", "goes to" → "move"
- "ignore", "skip", "leave alone" → "ignore"
- "archive" → "archive"
- "mark read" → "mark_read"

Output ONLY the JSON object, no explanation or markdown."""


AUTOPILOT_SYSTEM_PROMPT = """You are an intelligent email assistant operating in autopilot mode. Your task is to process emails according to the user's natural language instructions and decide on the appropriate action.

Available actions:
- move: Move to a specific folder (requires target_folder)
- delete: Delete the message (move to trash)
- archive: Archive the message
- mark_read: Mark as read without other action
- reply: Generate and send a reply (requires reply_content)
- forward: Forward to addresses (requires forward_to list)
- create_reminder: Create a Reminders app reminder (requires reminder_name, optional reminder_due)
- ignore: Take no action, leave email as-is

SECONDARY ACTIONS:
You can specify a secondary_action for compound operations. This is useful when an email needs two actions.

Valid secondary actions: archive, move, mark_read, create_reminder
Do NOT use reply, forward, or delete as secondary actions.

Common combinations:
- move + mark_read: Move to a folder and mark as read

CRITICAL GUIDELINES:
1. Follow the user's instructions precisely - they define your behavior
2. Be CONSERVATIVE - when uncertain, use 'ignore' action
3. Express confidence HONESTLY:
   - 0.9-1.0: Very certain, clear match to user's instructions
   - 0.7-0.9: Confident, reasonable interpretation
   - 0.5-0.7: Moderate confidence, some ambiguity
   - <0.5: Low confidence, unclear how to handle
4. For REPLY actions: include the full reply text in reply_content
5. For MOVE actions: specify the exact folder name in target_folder
6. For CREATE_REMINDER actions: include reminder_name and optionally reminder_due (ISO 8601)
7. NEVER delete emails that appear personal, unique, or important
8. Security-sensitive emails (passwords, 2FA, banking) should be left alone

REMINDER EXCLUSIONS:
NEVER create reminders for alerts or reports from monitoring/network tools:
- LibreNMS (any sender or subject referencing LibreNMS)
- LogicMonitor (any sender or subject referencing LogicMonitor)
- NtwkCmdr (any sender or subject referencing NtwkCmdr)
- Rancid (any sender or subject referencing Rancid or RANCID)
These are automated infrastructure alerts — ignore or handle with other actions only.

Respond with ONLY a valid JSON object (no markdown, no explanation):
{
    "action": "action_name",
    "confidence": 0.85,
    "category": "category_label",
    "reasoning": "brief explanation",
    "target_folder": "FolderName",
    "secondary_action": "mark_read",
    "secondary_target_folder": "Archive",
    "reply_content": "full reply text if action is reply",
    "forward_to": ["email@example.com"],
    "reminder_name": "Follow up on email subject",
    "reminder_due": "2025-01-15T09:00:00"
}"""


class ClaudeProvider(AIProvider):
    """Anthropic Claude AI provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        """
        Initialize the Claude provider.

        Args:
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
            model: Model to use for classification.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self._client: "anthropic.Anthropic | None" = None

    @property
    def client(self) -> "anthropic.Anthropic":
        """Lazy-load the Anthropic client."""
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _parse_json_response(self, response_text: str) -> dict:
        """Parse JSON from AI response, handling markdown code blocks."""
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text

        return json.loads(json_str.strip())

    async def classify_email(
        self,
        email: "EmailMessage",
        context: str | None = None,
    ) -> EmailClassification:
        """Classify an email using Claude."""
        email_content = f"""
Subject: {email.subject}
From: {email.sender}
To: {', '.join(email.recipients)}
Date: {email.date_received}
Mailbox: {email.mailbox}
Account: {email.account}
Read: {email.is_read}

Content:
{email.content[:3000]}
"""

        user_prompt = f"Analyze this email and recommend an action:\n\n{email_content}"
        if context:
            user_prompt = f"Context/Rules:\n{context}\n\n{user_prompt}"

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=CLASSIFICATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = message.content[0].text

        try:
            data = self._parse_json_response(response_text)

            return EmailClassification(
                action=EmailAction(data.get("action", "ignore")),
                confidence=float(data.get("confidence", 0.5)),
                category=data.get("category"),
                target_folder=data.get("target_folder"),
                target_account=data.get("target_account"),
                reply_template=data.get("reply_template"),
                forward_to=data.get("forward_to"),
                reasoning=data.get("reasoning", "No reasoning provided"),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            return EmailClassification(
                action=EmailAction.IGNORE,
                confidence=0.0,
                reasoning=f"Failed to parse AI response: {e}",
            )

    async def autopilot_classify(
        self,
        email: "EmailMessage",
        instructions: str,
    ) -> "AutopilotDecision":
        """
        Classify an email using natural language instructions (autopilot mode).

        Args:
            email: The email message to classify.
            instructions: User's natural language preferences for email handling.

        Returns:
            AutopilotDecision with action, confidence, and reasoning.
        """
        from email_nurse.autopilot.models import AutopilotDecision

        email_content = f"""
=== EMAIL TO PROCESS ===
Subject: {email.subject}
From: {email.sender}
To: {', '.join(email.recipients)}
Date: {email.date_received}
Mailbox: {email.mailbox}
Account: {email.account}
Read Status: {"Read" if email.is_read else "Unread"}

Content:
{email.content[:4000]}
=== END EMAIL ===
"""

        user_prompt = f"""## USER'S EMAIL HANDLING INSTRUCTIONS:
{instructions}

## EMAIL TO PROCESS:
{email_content}

Based on the user's instructions above, decide what action to take for this email. Respond with only a JSON object."""

        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=AUTOPILOT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = message.content[0].text

        try:
            data = self._parse_json_response(response_text)

            # Parse datetime fields if present
            reminder_due = None
            if data.get("reminder_due"):
                reminder_due = datetime.fromisoformat(data["reminder_due"].replace("Z", "+00:00"))

            event_start = None
            if data.get("event_start"):
                event_start = datetime.fromisoformat(data["event_start"].replace("Z", "+00:00"))

            event_end = None
            if data.get("event_end"):
                event_end = datetime.fromisoformat(data["event_end"].replace("Z", "+00:00"))

            # Parse secondary action if present
            secondary_action = None
            if data.get("secondary_action"):
                try:
                    secondary_action = EmailAction(data["secondary_action"])
                except ValueError:
                    pass  # Invalid secondary action, ignore

            return AutopilotDecision(
                action=EmailAction(data.get("action", "ignore")),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "No reasoning provided"),
                category=data.get("category"),
                target_folder=data.get("target_folder"),
                target_account=data.get("target_account"),
                reply_content=data.get("reply_content"),
                forward_to=data.get("forward_to"),
                # Reminder fields
                reminder_name=data.get("reminder_name"),
                reminder_due=reminder_due,
                reminder_list=data.get("reminder_list"),
                # Event fields
                event_summary=data.get("event_summary"),
                event_start=event_start,
                event_end=event_end,
                event_calendar=data.get("event_calendar"),
                event_all_day=data.get("event_all_day", False),
                # Secondary action fields
                secondary_action=secondary_action,
                secondary_target_folder=data.get("secondary_target_folder"),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            return AutopilotDecision(
                action=EmailAction.IGNORE,
                confidence=0.0,
                reasoning=f"Failed to parse AI response: {e}",
            )

    async def parse_quick_rule(
        self,
        description: str,
        rule_name: str | None = None,
    ) -> "QuickRule":
        """
        Parse a natural language description into a QuickRule.

        Uses claude-haiku for fast, cheap parsing of simple rule descriptions.

        Args:
            description: Natural language description of the rule.
            rule_name: Optional explicit name for the rule.

        Returns:
            QuickRule with parsed match conditions and action.

        Raises:
            ValueError: If the AI response cannot be parsed into a valid rule.
        """
        from email_nurse.autopilot.config import QuickRule

        # Use Haiku for this simple task - fast and cheap
        haiku_model = "claude-haiku-4-5-20251001"

        user_prompt = description
        if rule_name:
            user_prompt = f'Rule name: "{rule_name}"\nDescription: {description}'

        message = self.client.messages.create(
            model=haiku_model,
            max_tokens=500,
            system=QUICK_RULE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = message.content[0].text

        try:
            data = self._parse_json_response(response_text)

            # Override name if explicitly provided
            if rule_name:
                data["name"] = rule_name

            return QuickRule(**data)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            raise ValueError(f"Failed to parse quick rule: {e}\nRaw response: {response_text}")

    async def generate_reply(
        self,
        email: "EmailMessage",
        template: str,
        context: str | None = None,
    ) -> str:
        """Generate a reply using Claude."""
        email_content = f"""
Subject: {email.subject}
From: {email.sender}
Content:
{email.content[:2000]}
"""

        prompt = f"""Generate a reply to this email using the following template/instructions:

Template: {template}

Original Email:
{email_content}
"""
        if context:
            prompt = f"Context: {context}\n\n{prompt}"

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system="You are a helpful assistant that generates professional email replies. Write only the reply content, no subject line or headers.",
            messages=[{"role": "user", "content": prompt}],
        )

        return message.content[0].text

    async def is_available(self) -> bool:
        """Check if Claude API is available."""
        if not self.api_key:
            return False

        try:
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
            )
            return True
        except Exception:
            return False
