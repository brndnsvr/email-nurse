"""Ollama local LLM provider implementation."""

import json
from typing import TYPE_CHECKING

from email_nurse.ai.base import AIProvider, EmailAction, EmailClassification

if TYPE_CHECKING:
    from email_nurse.autopilot.models import AutopilotDecision
    from email_nurse.mail.messages import EmailMessage


CLASSIFICATION_PROMPT = """You are an email classification assistant. Analyze the email and respond with ONLY a JSON object (no other text):

Available actions: move, delete, archive, mark_read, mark_unread, flag, unflag, reply, forward, ignore

JSON format:
{
    "action": "action_name",
    "confidence": 0.8,
    "category": "category label",
    "target_folder": "folder for moves or null",
    "reply_template": "template name or null",
    "forward_to": ["emails"] or null,
    "reasoning": "brief explanation"
}

Email to analyze:
"""


AUTOPILOT_PROMPT = """You are an email assistant in autopilot mode. Process emails according to the user's instructions.

Available actions:
- move: Move to folder (set target_folder)
- delete: Delete message
- archive: Archive message
- mark_read: Mark as read
- flag: Flag for attention
- reply: Generate reply (set reply_content)
- forward: Forward (set forward_to)
- ignore: Take no action

Rules:
1. Follow user instructions precisely
2. When uncertain, use 'ignore' action
3. Express confidence honestly (0.0-1.0)
4. Never delete important/personal emails
5. Leave security emails (passwords, 2FA) alone

Respond with ONLY a JSON object:
{
    "action": "action_name",
    "confidence": 0.85,
    "category": "category_label",
    "reasoning": "brief explanation",
    "target_folder": "FolderName",
    "reply_content": "reply text",
    "forward_to": ["email@example.com"]
}

"""


class OllamaProvider(AIProvider):
    """Ollama local LLM provider."""

    def __init__(
        self,
        model: str = "llama3.2",
        host: str = "http://localhost:11434",
    ) -> None:
        """
        Initialize the Ollama provider.

        Args:
            model: Model name to use (e.g., llama3.2, mistral, phi3).
            host: Ollama server URL.
        """
        self.model = model
        self.host = host
        self._client: "ollama.Client | None" = None

    @property
    def client(self) -> "ollama.Client":
        """Lazy-load the Ollama client."""
        if self._client is None:
            import ollama

            self._client = ollama.Client(host=self.host)
        return self._client

    async def classify_email(
        self,
        email: "EmailMessage",
        context: str | None = None,
    ) -> EmailClassification:
        """Classify an email using a local Ollama model."""
        email_content = f"""
Subject: {email.subject}
From: {email.sender}
To: {', '.join(email.recipients)}
Date: {email.date_received}
Content:
{email.content[:2000]}
"""

        prompt = CLASSIFICATION_PROMPT + email_content
        if context:
            prompt = f"Rules to follow:\n{context}\n\n{prompt}"

        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            format="json",
            options={"temperature": 0.3},
        )

        response_text = response.get("response", "{}")

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
{email.content[:2000]}
"""

        prompt = f"""{AUTOPILOT_PROMPT}
USER'S INSTRUCTIONS:
{instructions}

EMAIL TO PROCESS:
{email_content}
"""

        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            format="json",
            options={"temperature": 0.3},
        )

        response_text = response.get("response", "{}")

        try:
            data = json.loads(response_text)
            return AutopilotDecision(
                action=EmailAction(data.get("action", "ignore")),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "No reasoning provided"),
                category=data.get("category"),
                target_folder=data.get("target_folder"),
                target_account=data.get("target_account"),
                reply_content=data.get("reply_content"),
                forward_to=data.get("forward_to"),
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
        """Generate a reply using Ollama."""
        email_content = f"""
Subject: {email.subject}
From: {email.sender}
Content:
{email.content[:2000]}
"""

        prompt = f"""Generate a professional email reply.
Template/Instructions: {template}

Original Email:
{email_content}

Write only the reply content, no headers."""

        if context:
            prompt = f"Context: {context}\n\n{prompt}"

        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            options={"temperature": 0.7},
        )

        return response.get("response", "")

    async def is_available(self) -> bool:
        """Check if Ollama is available and the model is loaded."""
        try:
            models = self.client.list()
            model_names = [m.get("name", "").split(":")[0] for m in models.get("models", [])]
            return self.model.split(":")[0] in model_names
        except Exception:
            return False
