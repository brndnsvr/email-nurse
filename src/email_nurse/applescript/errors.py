"""AppleScript error classes for macOS app integrations."""


class AppleScriptError(Exception):
    """Raised when an AppleScript command fails."""

    def __init__(self, message: str, script: str | None = None) -> None:
        super().__init__(message)
        self.script = script


class AppNotRunningError(AppleScriptError):
    """Raised when a target macOS app is not running."""

    def __init__(self, app_name: str = "Application") -> None:
        super().__init__(
            f"{app_name} is not running. Please open {app_name} and try again.",
            script=None,
        )
        self.app_name = app_name
