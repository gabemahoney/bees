"""
Unit tests for mcp_help.py module.

Tests the help documentation function to verify it returns expected structure
and includes all critical MCP tool documentation.
"""

import pytest
from typing import Dict, Any
from src.mcp_help import _help


class TestHelpFunction:
    """Test suite for the _help() function."""

    def test_help_returns_dict(self):
        """Test that _help() returns a dictionary."""
        result = _help()
        assert isinstance(result, dict)

    def test_help_has_required_keys(self):
        """Test that _help() returns dict with 'status', 'commands' and 'concepts' keys."""
        result = _help()
        assert 'status' in result
        assert 'commands' in result
        assert 'concepts' in result

    def test_help_status_is_success(self):
        """Test that status field is 'success'."""
        result = _help()
        assert result['status'] == 'success'

    def test_help_commands_is_list(self):
        """Test that commands field is a list."""
        result = _help()
        assert isinstance(result['commands'], list)

    def test_help_commands_not_empty(self):
        """Test that commands list is not empty."""
        result = _help()
        assert len(result['commands']) > 0

    def test_help_concepts_is_string(self):
        """Test that concepts field is a string."""
        result = _help()
        assert isinstance(result['concepts'], str)

    def test_help_includes_all_mcp_tools(self):
        """Test that all MCP tools are documented in commands."""
        result = _help()
        command_names = [cmd['name'] for cmd in result['commands']]

        # All MCP tools that should be documented
        expected_tools = [
            'health_check',
            'create_ticket',
            'update_ticket',
            'delete_ticket',
            'show_ticket',
            'add_named_query',
            'execute_query',
            'execute_freeform_query',
            'generate_index',
            'colonize_hive',
            'list_hives',
            'abandon_hive',
            'rename_hive',
            'sanitize_hive'
        ]

        for tool in expected_tools:
            assert tool in command_names, f"Tool '{tool}' missing from help commands"

    def test_help_commands_have_structure(self):
        """Test that each command has expected structure (name, description, parameters)."""
        result = _help()

        for cmd in result['commands']:
            assert 'name' in cmd, "Command missing 'name' field"
            assert 'description' in cmd, "Command missing 'description' field"
            assert 'parameters' in cmd, "Command missing 'parameters' field"
            assert isinstance(cmd['name'], str), "Command name must be string"
            assert isinstance(cmd['description'], str), "Command description must be string"
            assert isinstance(cmd['parameters'], list), "Command parameters must be list"

    def test_help_concepts_includes_hives(self):
        """Test that concepts section includes HIVES documentation."""
        result = _help()
        concepts = result['concepts']
        assert 'HIVES' in concepts
        assert '.bees/config.json' in concepts
        assert '.hive/identity.json' in concepts

    def test_help_concepts_includes_ticket_types(self):
        """Test that concepts section includes TICKET TYPES documentation."""
        result = _help()
        concepts = result['concepts']
        assert 'TICKET TYPES' in concepts
        assert 'Epic' in concepts
        assert 'Task' in concepts
        assert 'Subtask' in concepts

    def test_help_concepts_includes_relationships(self):
        """Test that concepts section includes PARENT/CHILD RELATIONSHIPS documentation."""
        result = _help()
        concepts = result['concepts']
        assert 'PARENT/CHILD RELATIONSHIPS' in concepts
        assert 'Bidirectional sync' in concepts

    def test_help_concepts_includes_dependencies(self):
        """Test that concepts section includes DEPENDENCIES documentation."""
        result = _help()
        concepts = result['concepts']
        assert 'DEPENDENCIES' in concepts
        assert 'up_dependencies' in concepts
        assert 'down_dependencies' in concepts

    def test_help_concepts_includes_queries(self):
        """Test that concepts section includes QUERIES documentation."""
        result = _help()
        concepts = result['concepts']
        assert 'QUERIES' in concepts
        assert 'Multi-stage pipeline' in concepts

    def test_help_concepts_includes_critical_warning(self):
        """Test that concepts section includes critical warning about direct file modifications."""
        result = _help()
        concepts = result['concepts']
        assert 'CRITICAL' in concepts
        assert 'NEVER modify tickets' in concepts or 'NEVER modify tickets or directory structure directly' in concepts

    def test_help_is_pure_function(self):
        """Test that _help() can be called without MCP context (pure function)."""
        # Should not raise any exceptions
        result1 = _help()
        result2 = _help()

        # Results should be identical (deterministic)
        assert result1 == result2

    def test_help_create_ticket_has_required_parameters(self):
        """Test that create_ticket command documents required parameters."""
        result = _help()
        create_ticket_cmd = next(cmd for cmd in result['commands'] if cmd['name'] == 'create_ticket')

        param_names = [p['name'] for p in create_ticket_cmd['parameters']]

        # Required parameters for create_ticket
        assert 'ticket_type' in param_names
        assert 'title' in param_names
        assert 'hive_name' in param_names

    def test_help_update_ticket_has_ticket_id_parameter(self):
        """Test that update_ticket command documents ticket_id parameter."""
        result = _help()
        update_ticket_cmd = next(cmd for cmd in result['commands'] if cmd['name'] == 'update_ticket')

        param_names = [p['name'] for p in update_ticket_cmd['parameters']]
        assert 'ticket_id' in param_names

    def test_help_return_type_matches_signature(self):
        """Test that return type matches Dict[str, Any]."""
        result = _help()
        assert isinstance(result, dict)

        # All values should be of type Any (specifically: str or list)
        for key, value in result.items():
            assert isinstance(key, str)
            assert value is not None
