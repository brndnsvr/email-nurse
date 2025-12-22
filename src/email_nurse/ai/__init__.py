"""AI provider integrations for email classification and decisions."""

from email_nurse.ai.base import AIProvider, EmailAction, EmailClassification
from email_nurse.ai.claude import ClaudeProvider
from email_nurse.ai.ollama import OllamaProvider
from email_nurse.ai.openai import OpenAIProvider

__all__ = [
    "AIProvider",
    "EmailAction",
    "EmailClassification",
    "ClaudeProvider",
    "OpenAIProvider",
    "OllamaProvider",
]
