"""Template management for reply actions."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Template(BaseModel):
    """A reply template."""

    name: str = Field(description="Template identifier")
    description: str | None = Field(default=None, description="Template description")
    subject_prefix: str | None = Field(
        default=None, description="Prefix to add to subject (e.g., 'Re: ')"
    )
    content: str = Field(description="Template content or instructions for AI")
    use_ai: bool = Field(
        default=True, description="If True, content is instructions for AI generation"
    )
    variables: dict[str, str] = Field(
        default_factory=dict, description="Variable placeholders and defaults"
    )


class TemplateManager:
    """Manages reply templates."""

    def __init__(self, templates: list[Template] | None = None) -> None:
        """
        Initialize the template manager.

        Args:
            templates: List of templates to manage.
        """
        self._templates: dict[str, Template] = {}
        for t in templates or []:
            self._templates[t.name] = t

    def get(self, name: str) -> Template | None:
        """Get a template by name."""
        return self._templates.get(name)

    def add(self, template: Template) -> None:
        """Add or update a template."""
        self._templates[template.name] = template

    def remove(self, name: str) -> bool:
        """Remove a template by name."""
        if name in self._templates:
            del self._templates[name]
            return True
        return False

    def list_all(self) -> list[Template]:
        """Get all templates."""
        return list(self._templates.values())

    @classmethod
    def from_yaml(cls, path: Path) -> "TemplateManager":
        """
        Load templates from a YAML file.

        Args:
            path: Path to the YAML file.

        Returns:
            TemplateManager with loaded templates.
        """
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        templates = []
        for name, config in data.get("templates", {}).items():
            templates.append(
                Template(
                    name=name,
                    description=config.get("description"),
                    subject_prefix=config.get("subject_prefix"),
                    content=config.get("content", ""),
                    use_ai=config.get("use_ai", True),
                    variables=config.get("variables", {}),
                )
            )

        return cls(templates)

    def to_yaml(self, path: Path) -> None:
        """Save templates to a YAML file."""
        data = {"templates": {}}

        for template in self._templates.values():
            data["templates"][template.name] = {
                "description": template.description,
                "subject_prefix": template.subject_prefix,
                "content": template.content,
                "use_ai": template.use_ai,
                "variables": template.variables,
            }

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
