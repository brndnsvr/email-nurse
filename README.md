# email-nurse

AI-powered email management and automation for macOS Mail.app.

## Features

- **Mail.app Integration**: Direct access via AppleScript to read messages, manage mailboxes, and perform actions
- **Autopilot Mode**: Intelligent email processing with natural language instructions
- **Quick Rules**: Instant pattern matching before AI (no API cost) for known senders/domains
- **AI Classification**: Use Claude, OpenAI, or local Ollama models to intelligently categorize emails
- **Multi-Level Verbosity**: `-v` compact, `-vv` detailed, `-vvv` debug output
- **Inbox Aging**: Automatically move stale emails to review folder and clean up
- **Multi-Account Support**: Process emails from multiple accounts to a central location
- **Reminders Integration**: View and manage macOS Reminders.app lists
- **Flexible Actions**: Move, delete, archive, flag, reply, forward emails automatically

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/email-nurse.git
cd email-nurse

# Create virtual environment and install
uv venv
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

### direnv (optional)

If you use [direnv](https://direnv.net/), you can auto-activate the virtual environment when entering the directory:

```bash
# Create .envrc file
echo 'source .venv/bin/activate' > .envrc

# Allow direnv for this directory
direnv allow
```

## Quick Start

```bash
# Initialize configuration
email-nurse init

# List email accounts
email-nurse accounts list

# List recent messages
email-nurse messages list --limit 5

# Run autopilot (dry-run to preview)
email-nurse autopilot run --dry-run -v

# Run autopilot for real
email-nurse autopilot run -v

# View reminders
email-nurse reminders lists
```

## Utilities

| Script | Description |
|--------|-------------|
| `log-viewer.sh` | Interactive log viewer for tailing autopilot logs |
| `launch-autopilot.sh` | LaunchAgent wrapper for scheduled runs |

## Documentation

Comprehensive technical documentation is available in the [`docs/`](./docs) directory:

- **[Configuration Guide](./docs/configuration.md)** - System setup, environment variables, and file locations
- **[Rules Reference](./docs/rules-reference.md)** - Complete `rules.yaml` schema with 40+ examples
- **[Templates Reference](./docs/templates-reference.md)** - Complete `templates.yaml` schema with 20+ examples

## Configuration

Configuration files are stored in `~/.config/email-nurse/`:

- `autopilot.yaml` - Autopilot settings, quick rules, inbox aging ([reference](./docs/configuration.md#autopilotyaml))
- `rules.yaml` - Processing rules ([reference](./docs/rules-reference.md))
- `templates.yaml` - Reply templates ([reference](./docs/templates-reference.md))

Copy the example files from `config/` to get started, or see the [Configuration Guide](./docs/configuration.md) for detailed setup instructions.

### Environment Variables

```bash
# AI Provider (claude, openai, ollama)
EMAIL_NURSE_AI_PROVIDER=claude

# API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Local models
EMAIL_NURSE_OLLAMA_HOST=http://localhost:11434
EMAIL_NURSE_OLLAMA_MODEL=llama3.2
```

## Development

```bash
# Run tests
pytest

# Run linter
ruff check src tests

# Type checking
mypy src
```

## License

MIT
