# AI Providers Guide

Email Nurse supports multiple AI providers for email classification. This guide covers configuration, model selection, and implementation details.

## Table of Contents

- [Provider Overview](#provider-overview)
- [Claude (Anthropic)](#claude-anthropic)
- [OpenAI](#openai)
- [Ollama (Local)](#ollama-local)
- [Model Selection Guide](#model-selection-guide)
- [Provider Interface](#provider-interface)
- [Error Handling](#error-handling)
- [Prompt Engineering](#prompt-engineering)

## Provider Overview

| Provider | Best For | Latency | Cost | Privacy |
|----------|----------|---------|------|---------|
| **Claude** | Natural language understanding, nuanced classification | ~500ms-1s | $$$ | Cloud |
| **OpenAI** | GPT-4 users, existing workflows | ~500ms-1s | $$$ | Cloud |
| **Ollama** | Privacy, offline use, no API costs | ~1-5s | Free | Local |

## Claude (Anthropic)

### Configuration

```bash
# Required
export ANTHROPIC_API_KEY=sk-ant-xxxxx

# Optional: Override default model
export EMAIL_NURSE_CLAUDE_MODEL=claude-haiku-4-5-20251001
```

Or in `~/.config/email-nurse/.env`:
```bash
EMAIL_NURSE_ANTHROPIC_API_KEY=sk-ant-xxxxx
EMAIL_NURSE_CLAUDE_MODEL=claude-haiku-4-5-20251001
```

### Available Models (as of December 2025)

| Model ID | Display Name | Best For |
|----------|--------------|----------|
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 | **Default** - Fast, cost-effective |
| `claude-sonnet-4-5-20250929` | Claude Sonnet 4.5 | Balance of quality and speed |
| `claude-opus-4-5-20251101` | Claude Opus 4.5 | Highest quality, complex tasks |

### Listing Available Models

```bash
# Query available models with your API key
curl https://api.anthropic.com/v1/models \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01"
```

### Usage in Code

```python
from email_nurse.ai.claude import ClaudeProvider

# Uses settings from environment
provider = ClaudeProvider()

# Or explicit configuration
provider = ClaudeProvider(
    api_key="sk-ant-xxxxx",
    model="claude-haiku-4-5-20251001"
)

# Classify email
result = await provider.autopilot_classify(email, instructions)
print(f"Action: {result.action}, Confidence: {result.confidence}")
```

### Implementation Details

The Claude provider (`ai/claude.py`) uses the Anthropic Python SDK:

```python
class ClaudeProvider(AIProvider):
    def __init__(self, api_key=None, model="claude-haiku-4-5-20251001"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None  # Lazy-loaded

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client
```

**Key features:**
- Lazy client initialization (import on first use)
- Falls back to `ANTHROPIC_API_KEY` environment variable
- Parses JSON from markdown code blocks
- Handles structured output for classification

## OpenAI

### Configuration

```bash
export EMAIL_NURSE_AI_PROVIDER=openai
export OPENAI_API_KEY=sk-xxxxx
export EMAIL_NURSE_OPENAI_MODEL=gpt-4o
```

### Available Models

| Model | Best For |
|-------|----------|
| `gpt-4o` | Default - Latest GPT-4 with vision |
| `gpt-4-turbo` | High quality, faster than base GPT-4 |
| `gpt-3.5-turbo` | Fastest, most cost-effective |

### Usage

```python
from email_nurse.ai.openai import OpenAIProvider

provider = OpenAIProvider(
    api_key="sk-xxxxx",
    model="gpt-4o"
)
```

## Ollama (Local)

### Configuration

```bash
# Install Ollama
brew install ollama

# Pull a model
ollama pull llama3.2

# Start server
ollama serve

# Configure Email Nurse
export EMAIL_NURSE_AI_PROVIDER=ollama
export EMAIL_NURSE_OLLAMA_HOST=http://localhost:11434
export EMAIL_NURSE_OLLAMA_MODEL=llama3.2
```

### Available Models

| Model | Size | Best For |
|-------|------|----------|
| `llama3.2` | 3B | Default - Good balance |
| `llama3.1` | 8B+ | Higher quality |
| `mistral` | 7B | Fast, efficient |
| `phi3` | 3.8B | Compact, efficient |

### Benefits

- **Privacy**: Emails never leave your machine
- **Cost**: No API fees
- **Offline**: Works without internet
- **Speed**: Can be faster for local hardware

### Limitations

- Requires local compute resources (RAM, CPU/GPU)
- Model quality may vary compared to cloud providers
- Initial model download can be large (2-8GB+)

## Model Selection Guide

### Use Haiku 4.5 (Default) When:

- Processing high volumes of email
- Cost is a primary concern
- Classifications are straightforward
- Speed is important (e.g., real-time processing)

### Use Sonnet 4.5 When:

- Need more nuanced understanding
- Emails have complex context
- Higher accuracy is worth the cost
- Writing replies that need quality

### Use Opus 4.5 When:

- Complex multi-step reasoning needed
- Critical emails (legal, financial)
- Highest quality replies required
- Cost is not a concern

### Use Ollama When:

- Privacy is paramount
- Processing confidential emails
- No internet access
- Want to avoid API costs entirely

## Provider Interface

All providers implement the `AIProvider` abstract base class:

```python
from abc import ABC, abstractmethod

class AIProvider(ABC):
    @abstractmethod
    async def classify_email(
        self,
        email: EmailMessage,
        context: str | None = None,
    ) -> EmailClassification:
        """Classify a single email with optional context."""
        pass

    @abstractmethod
    async def autopilot_classify(
        self,
        email: EmailMessage,
        instructions: str,
    ) -> AutopilotDecision:
        """Classify email using natural language instructions."""
        pass

    async def parse_quick_rule(
        self,
        description: str,
        rule_name: str | None = None,
    ) -> QuickRule:
        """Parse natural language into a quick rule."""
        pass

    async def generate_reply(
        self,
        email: EmailMessage,
        template: str,
        context: str | None = None,
    ) -> str:
        """Generate a reply using a template."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available."""
        pass
```

### EmailClassification

```python
@dataclass
class EmailClassification:
    action: EmailAction          # move, delete, archive, etc.
    confidence: float            # 0.0 to 1.0
    category: str | None         # "newsletter", "invoice", etc.
    target_folder: str | None    # For move actions
    target_account: str | None   # For cross-account moves
    reply_template: str | None   # For reply actions
    forward_to: list[str] | None # For forward actions
    reasoning: str               # Why this action was chosen
```

### AutopilotDecision

```python
@dataclass
class AutopilotDecision:
    action: EmailAction
    confidence: float
    reasoning: str
    category: str | None = None
    target_folder: str | None = None
    target_account: str | None = None
    reply_content: str | None = None  # Full reply text
    forward_to: list[str] | None = None
```

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `authentication_error: invalid x-api-key` | API key is invalid or expired | Get new key from console |
| `rate_limit_error` | Too many requests | Add delay between calls |
| `model_not_found` | Model ID is wrong | Check available models |
| `connection_error` | Network issues | Check internet/Ollama server |

### Graceful Degradation

The autopilot engine handles AI failures gracefully:

```python
try:
    decision = await self.ai.autopilot_classify(email, instructions)
except Exception as e:
    print(f"AI classification failed: {e}", file=sys.stderr)
    return ProcessResult(
        message_id=email.id,
        success=False,
        error=str(e),
    )
```

### Testing Provider Availability

```python
provider = ClaudeProvider()
if await provider.is_available():
    # Provider is ready
    result = await provider.classify_email(email)
else:
    # Handle unavailable provider
    print("AI provider not available")
```

## Prompt Engineering

### System Prompts

Email Nurse uses specialized system prompts for different tasks:

**Classification System Prompt** (`CLASSIFICATION_SYSTEM_PROMPT`):
- Lists available actions
- Specifies JSON output format
- Provides confidence guidelines

**Autopilot System Prompt** (`AUTOPILOT_SYSTEM_PROMPT`):
- Critical guidelines for email handling
- Confidence score interpretation
- Safety rules (never delete personal emails)

**Quick Rule System Prompt** (`QUICK_RULE_SYSTEM_PROMPT`):
- Parses natural language to JSON
- Strict output format
- Examples of pattern matching

### User Instructions

The `instructions` field in `autopilot.yaml` is passed directly to the AI:

```yaml
instructions: |
  You are managing my personal email inbox. Follow these guidelines:

  1. NEWSLETTERS: Move to "Newsletters" folder
  2. IMPORTANT: Flag emails from VIPs
  3. FINANCIAL: Move to "Finance" folder
  4. NEVER delete emails from real people

  When in doubt, use 'ignore' action.
```

### Best Practices

1. **Be specific**: "Move promotional emails to Marketing" not "Handle marketing"
2. **Provide examples**: List specific senders or domains
3. **Set boundaries**: Explicitly state what NOT to do
4. **Use ignore as default**: When uncertain, leave email alone
5. **Test with dry-run**: Always verify with `--dry-run` first

## Adding a New Provider

To add a new AI provider:

1. Create `ai/newprovider.py`:

```python
from email_nurse.ai.base import AIProvider, EmailClassification

class NewProvider(AIProvider):
    def __init__(self, api_key=None, model="default"):
        self.api_key = api_key
        self.model = model

    async def classify_email(self, email, context=None):
        # Call your API
        response = await self._call_api(email, context)
        return EmailClassification(
            action=response["action"],
            confidence=response["confidence"],
            reasoning=response["reasoning"],
        )

    async def autopilot_classify(self, email, instructions):
        # Implementation...
        pass

    async def is_available(self):
        # Check connectivity
        try:
            await self._ping_api()
            return True
        except Exception:
            return False
```

2. Add settings to `config.py`:

```python
newprovider_api_key: str | None = Field(default=None)
newprovider_model: str = Field(default="default-model")
```

3. Add to CLI provider selection in `cli.py`:

```python
elif provider == "newprovider":
    from email_nurse.ai.newprovider import NewProvider
    ai = NewProvider(
        api_key=settings.newprovider_api_key,
        model=settings.newprovider_model
    )
```

## Related Documentation

- [Architecture Guide](./architecture.md) - Overall system design
- [Configuration Guide](./configuration.md) - Settings and environment
- [Troubleshooting Guide](./troubleshooting.md) - Common issues
