"""
Unit tests for help command.

Tests that the help command returns expected structure with commands and concepts.
"""

import pytest
from src.mcp_server import _help


class TestHelp:
    """Tests for help command."""

    def test_help_returns_dict(self):
        """Test that help returns a dictionary."""
        result = _help()
        assert isinstance(result, dict)

    def test_help_has_status_success(self):
        """Test that help returns success status."""
        result = _help()
        assert result.get("status") == "success"

    def test_help_has_commands_list(self):
        """Test that help returns a commands list."""
        result = _help()
        assert "commands" in result
        assert isinstance(result["commands"], list)

    def test_help_commands_not_empty(self):
        """Test that commands list is not empty."""
        result = _help()
        assert len(result["commands"]) > 0

    def test_help_has_concepts_string(self):
        """Test that help returns concepts as string."""
        result = _help()
        assert "concepts" in result
        assert isinstance(result["concepts"], str)

    def test_help_concepts_not_empty(self):
        """Test that concepts string is not empty."""
        result = _help()
        assert len(result["concepts"]) > 0

    def test_help_command_structure(self):
        """Test that each command has expected structure."""
        result = _help()
        for command in result["commands"]:
            assert "name" in command
            assert "description" in command
            assert "parameters" in command
            assert isinstance(command["name"], str)
            assert isinstance(command["description"], str)
            assert isinstance(command["parameters"], list)

    def test_help_parameter_structure(self):
        """Test that parameters have expected structure."""
        result = _help()
        for command in result["commands"]:
            for param in command["parameters"]:
                assert "name" in param
                assert "type" in param
                assert "required" in param
                assert "description" in param
                assert isinstance(param["name"], str)
                assert isinstance(param["type"], str)
                assert isinstance(param["required"], bool)
                assert isinstance(param["description"], str)
