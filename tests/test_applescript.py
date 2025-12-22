"""Tests for AppleScript utilities."""

import pytest

from email_nurse.mail.applescript import escape_applescript_string


class TestEscapeAppleScriptString:
    """Tests for AppleScript string escaping."""

    def test_escape_quotes(self) -> None:
        """Test that double quotes are escaped."""
        result = escape_applescript_string('Hello "World"')
        assert result == 'Hello \\"World\\"'

    def test_escape_backslashes(self) -> None:
        """Test that backslashes are escaped."""
        result = escape_applescript_string("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_escape_combined(self) -> None:
        """Test escaping both quotes and backslashes."""
        result = escape_applescript_string('Say "Hello\\World"')
        assert result == 'Say \\"Hello\\\\World\\"'

    def test_no_escape_needed(self) -> None:
        """Test string that needs no escaping."""
        result = escape_applescript_string("Simple text")
        assert result == "Simple text"

    def test_empty_string(self) -> None:
        """Test empty string."""
        result = escape_applescript_string("")
        assert result == ""
