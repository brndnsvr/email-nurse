"""OpenAI GPT provider implementation."""

import json
import os
from typing import TYPE_CHECKING

from email_nurse.ai.base import AIProvider, EmailAction, EmailClassification

if TYPE_CHECKING:
    from email_nurse.autopilot.models import AutopilotDecision
    from email_nurse.mail.messages import EmailMessage


CLASSIFICATION_SYSTEM_PROMPT = """You are an email classification assistant. Analyze emails and recommend actions.

Available actions: move, delete, archive, mark_read, mark_unread, reply, forward, ignore

Respond with JSON:
{
    "action": "action_name",
    "confidence": 0.0-1.0,
    "category": "category label",
    "target_folder": "folder for moves",
    "reply_template": "template name for replies",
    "forward_to": ["emails for forwards"],
    "reasoning": "brief explanation"
}"""


AUTOPILOT_SYSTEM_PROMPT = """You are an intelligent email assistant operating in autopilot mode. Process emails according to the user's instructions and decide on actions.

Available actions:
- move: Move to folder (requires target_folder)
- delete: Delete message
- archive: Archive message
- mark_read: Mark as read
- reply: Generate reply (requires reply_content)
- forward: Forward to addresses (requires forward_to)
- create_reminder: Create a Reminders app reminder (requires reminder_name, optional reminder_due)
- ignore: Take no action

SECONDARY ACTIONS:
You can specify a secondary_action for compound operations.
Valid secondary actions: archive, move, mark_read, create_reminder
Do NOT use reply, forward, or delete as secondary actions.

Common combinations:
- move + mark_read: Move to a folder and mark as read

Guidelines:
1. Follow user instructions precisely
2. Be conservative - when uncertain, use 'ignore'
3. Express confidence honestly (0.0-1.0)
4. Never delete personal/important emails
5. Security emails (passwords, 2FA) should be left alone
6. For CREATE_REMINDER actions: include reminder_name and optionally reminder_due (ISO 8601)

REMINDER EXCLUSIONS:
NEVER create reminders for alerts or reports from monitoring/network tools:
- LibreNMS (any sender or subject referencing LibreNMS)
- LogicMonitor (any sender or subject referencing LogicMonitor)
- NtwkCmdr (any sender or subject referencing NtwkCmdr)
- Rancid (any sender or subject referencing Rancid or RANCID)
These are automated infrastructure alerts — ignore or handle with other actions only.

Respond with JSON only:
{
    "action": "action_name",
    "confidence": 0.85,
    "category": "category_label",
    "reasoning": "brief explanation",
    "target_folder": "FolderName",
    "secondary_action": "mark_read",
    "secondary_target_folder": "Archive",
    "reply_content": "reply text if action is reply",
    "forward_to": ["email@example.com"],
    "reminder_name": "Follow up on email subject",
    "reminder_due": "2025-01-15T09:00:00"
}"""


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
    ) -> None:
        """
        Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
            model: Model to use for classification.
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self._client: "openai.OpenAI | None" = None

    @property
    def client(self) -> "openai.OpenAI":
        """Lazy-load the OpenAI client."""
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self.api_key)
        return self._client

    async def classify_email(
        self,
        email: "EmailMessage",
        context: str | None = None,
    ) -> EmailClassification:
        """Classify an email using GPT."""
        email_content = f"""
Subject: {email.subject}
From: {email.sender}
To: {', '.join(email.recipients)}
Date: {email.date_received}
Content:
{email.content[:3000]}
"""

        user_prompt = f"Analyze this email:\n\n{email_content}"
        if context:
            user_prompt = f"Rules:\n{context}\n\n{user_prompt}"

        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        response_text = response.choices[0].message.content or "{}"

        try:
            data = json.loads(response_text)
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
        """Classify an email using natural language instructions (autopilot mode)."""
        from email_nurse.autopilot.models import AutopilotDecision

        email_content = f"""
Subject: {email.subject}
From: {email.sender}
To: {', '.join(email.recipients)}
Date: {email.date_received}
Mailbox: {email.mailbox}
Account: {email.account}
Read: {"Read" if email.is_read else "Unread"}

Content:
{email.content[:4000]}
"""

        user_prompt = f"""USER'S INSTRUCTIONS:
{instructions}

EMAIL TO PROCESS:
{email_content}

Decide what action to take based on the instructions above."""

        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": AUTOPILOT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        response_text = response.choices[0].message.content or "{}"

        try:
            data = json.loads(response_text)

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

    async def generate_reply(
        self,
        email: "EmailMessage",
        template: str,
        context: str | None = None,
    ) -> str:
        """Generate a reply using GPT."""
        email_content = f"""
Subject: {email.subject}
From: {email.sender}
Content:
{email.content[:2000]}
"""

        prompt = f"Generate a reply using template: {template}\n\nOriginal:\n{email_content}"
        if context:
            prompt = f"Context: {context}\n\n{prompt}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Generate professional email replies. Write only the reply content.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        return response.choices[0].message.content or ""

    async def is_available(self) -> bool:
        """Check if OpenAI API is available."""
        if not self.api_key:
            return False

        try:
            self.client.models.list()
            return True
        except Exception:
            return False
