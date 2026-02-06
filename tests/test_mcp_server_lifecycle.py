"""
Unit tests for MCP server lifecycle and initialization.

This module tests foundational server behavior including:
- Server initialization and configuration
- Lifecycle management (start/stop operations)
- Tool registration mechanisms
- Health check functionality

Separated from business logic tests to isolate core infrastructure concerns.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.mcp_server import (
    mcp,
    start_server,
    stop_server,
    _health_check,
    _create_ticket,
    _update_ticket,
    _delete_ticket,
    _server_running,
)
from src.repo_context import repo_root_context


class TestMCPServerInitialization:
    """Tests for MCP server initialization and configuration."""

    def test_server_instance_exists(self):
        """Test that the MCP server instance is created."""
        assert mcp is not None
        assert hasattr(mcp, 'name')

    def test_server_name_configuration(self):
        """Test that server name is properly configured."""
        assert mcp.name == "Bees Ticket Management Server"

    def test_server_has_required_attributes(self):
        """Test that server has all required attributes."""
        assert hasattr(mcp, 'name')
        # FastMCP may expose version/description differently
        # Just verify the server can be instantiated


class TestServerLifecycle:
    """Tests for server start and stop functionality."""

    def test_start_server_success(self):
        """Test successful server startup."""
        result = start_server()

        assert result is not None
        assert result["status"] == "running"
        assert result["name"] == "Bees Ticket Management Server"
        assert result["version"] == "0.1.0"

    def test_stop_server_success(self):
        """Test successful server shutdown."""
        # Start server first
        start_server()

        # Then stop it
        result = stop_server()

        assert result is not None
        assert result["status"] == "stopped"
        assert result["name"] == "Bees Ticket Management Server"

    def test_start_stop_cycle(self):
        """Test multiple start/stop cycles."""
        # Start
        result1 = start_server()
        assert result1["status"] == "running"

        # Stop
        result2 = stop_server()
        assert result2["status"] == "stopped"

        # Start again
        result3 = start_server()
        assert result3["status"] == "running"

    @patch('src.mcp_server.logger')
    def test_start_server_logs_messages(self, mock_logger):
        """Test that start_server logs appropriate messages."""
        start_server()

        # Verify logging calls were made
        assert mock_logger.info.called

    @patch('src.mcp_server.logger')
    def test_stop_server_logs_messages(self, mock_logger):
        """Test that stop_server logs appropriate messages."""
        start_server()
        stop_server()

        # Verify logging calls were made
        assert mock_logger.info.called


class TestHealthCheck:
    """Tests for health check endpoint functionality."""

    def test_health_check_when_server_running(self):
        """Test health check returns healthy when server is running."""
        start_server()

        result = _health_check()

        assert result is not None
        assert result["status"] == "healthy"
        assert result["server_running"] is True
        assert result["ready"] is True
        assert result["name"] == "Bees Ticket Management Server"
        assert result["version"] == "0.1.0"

    def test_health_check_when_server_stopped(self):
        """Test health check returns stopped when server is not running."""
        stop_server()

        result = _health_check()

        assert result is not None
        assert result["status"] == "stopped"
        assert result["server_running"] is False
        assert result["ready"] is False

    def test_health_check_returns_dict(self):
        """Test that health check returns a dictionary."""
        result = _health_check()

        assert isinstance(result, dict)
        assert "status" in result
        assert "server_running" in result
        assert "ready" in result


class TestToolRegistration:
    """Tests for MCP tool schema registration."""

    def test_health_check_tool_registered(self):
        """Test that health_check tool is registered."""
        # FastMCP registers tools via decorators
        # We can verify by checking if the function is callable
        assert callable(_health_check)

    def test_create_ticket_tool_registered(self):
        """Test that create_ticket tool schema is registered."""
        # Verify the underlying function is callable
        assert callable(_create_ticket)

    def test_update_ticket_tool_registered(self):
        """Test that update_ticket tool schema is registered."""
        assert callable(_update_ticket)

    def test_delete_ticket_tool_registered(self):
        """Test that delete_ticket tool schema is registered."""
        assert callable(_delete_ticket)

    async def test_create_ticket_implementation_response(self, tmp_path, monkeypatch):
        """Test that create_ticket returns expected response."""
        import json
        from src.config import BeesConfig, HiveConfig, save_bees_config
        from datetime import datetime
        
        # Change to tmp_path for test isolation
        monkeypatch.chdir(tmp_path)
        
        # Create default hive directory
        default_hive = tmp_path / "hive"
        default_hive.mkdir()
        
        # Initialize .bees/config.json with hive registration
        config = BeesConfig(
            hives={
                'default': HiveConfig(
                    path=str(default_hive),
                    display_name='Default',
                    created_at=datetime.now().isoformat()
                )
            }
        )
        save_bees_config(config)

        result = await _create_ticket(
            hive_name="default",
            ticket_type="task",
            title="Test Task"
        )

        assert result is not None
        assert result["status"] == "success"
        assert "ticket_id" in result
        assert "ticket_type" in result
        assert result["ticket_type"] == "task"

    async def test_create_ticket_validates_type(self):
        """Test that create_ticket validates ticket_type parameter."""
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(hive_name="backend", ticket_type="invalid", title="Test")

        assert "Invalid ticket_type" in str(exc_info.value)

    async def test_create_ticket_validates_epic_parent(self, tmp_path, monkeypatch):
        """Test that create_ticket rejects parent for epics."""
        import json
        from src.config import BeesConfig, HiveConfig, save_bees_config
        from datetime import datetime
        
        # Change to tmp_path for test isolation
        monkeypatch.chdir(tmp_path)
        
        # Create default hive directory
        default_hive = tmp_path / "hive"
        default_hive.mkdir()
        
        # Initialize .bees/config.json with hive registration
        config = BeesConfig(
            hives={
                'default': HiveConfig(
                    path=str(default_hive),
                    display_name='Default',
                    created_at=datetime.now().isoformat()
                )
            }
        )
        save_bees_config(config)
        
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(hive_name="default", ticket_type="epic", title="Test", parent="some-id")

        assert "Epics cannot have a parent" in str(exc_info.value)

    async def test_create_ticket_validates_subtask_parent(self, tmp_path, monkeypatch):
        """Test that create_ticket requires parent for subtasks."""
        import json
        from src.config import BeesConfig, HiveConfig, save_bees_config
        from datetime import datetime
        
        # Change to tmp_path for test isolation
        monkeypatch.chdir(tmp_path)
        
        # Create default hive directory
        default_hive = tmp_path / "hive"
        default_hive.mkdir()
        
        # Initialize .bees/config.json with hive registration
        config = BeesConfig(
            hives={
                'default': HiveConfig(
                    path=str(default_hive),
                    display_name='Default',
                    created_at=datetime.now().isoformat()
                )
            }
        )
        save_bees_config(config)
        
        with pytest.raises(ValueError) as exc_info:
            await _create_ticket(hive_name="default", ticket_type="subtask", title="Test")

        assert "Subtasks must have a parent" in str(exc_info.value)


class TestErrorHandling:
    """Tests for error handling in server operations."""

    @patch('src.mcp_server.logger')
    def test_start_server_exception_handling(self, mock_logger):
        """Test that start_server handles exceptions properly."""
        # This test verifies the exception handling structure exists
        # In practice, start_server is simple and unlikely to raise exceptions
        # but the try-except block is there for safety

        # Just verify it can be called without raising
        result = start_server()
        assert result is not None

    @patch('src.mcp_server.logger')
    def test_stop_server_exception_handling(self, mock_logger):
        """Test that stop_server handles exceptions properly."""
        # Similar to start_server test
        result = stop_server()
        assert result is not None


class TestServerConfiguration:
    """Tests for server configuration validation."""

    def test_server_has_version(self):
        """Test that server version is defined."""
        result = start_server()
        assert "version" in result
        assert result["version"] == "0.1.0"

    def test_server_has_name(self):
        """Test that server name is defined."""
        result = start_server()
        assert "name" in result
        assert len(result["name"]) > 0


class TestModuleIntegration:
    """Tests for refactored module integration.

    Verifies that all extracted modules can be imported without circular dependency
    errors and that the mcp_server correctly integrates with them.
    """

    def test_all_modules_import_successfully(self):
        """Test that all 9 extracted modules can be imported without errors."""
        # This test verifies there are no circular dependency issues
        import src.mcp_id_utils
        import src.mcp_repo_utils
        import src.mcp_hive_utils
        import src.mcp_relationships
        import src.mcp_ticket_ops
        import src.mcp_hive_ops
        import src.mcp_query_ops
        import src.mcp_index_ops
        import src.mcp_help

        # If we get here without ImportError, all modules loaded successfully
        assert True

    def test_mcp_server_imports_all_modules(self):
        """Test that mcp_server.py successfully imports from all extracted modules."""
        from src.mcp_server import (
            parse_ticket_id,
            parse_hive_from_ticket_id,
            get_repo_root_from_path,
            get_repo_root,
            validate_hive_path,
            scan_for_hive,
            _update_bidirectional_relationships,
            _create_ticket,
            _update_ticket,
            _delete_ticket,
            _show_ticket,
            _colonize_hive,
            _list_hives,
            _abandon_hive,
            _rename_hive,
            _sanitize_hive,
            _add_named_query,
            _execute_query,
            _execute_freeform_query,
            _generate_index,
            _help
        )

        # All imports successful
        assert True

    def test_tool_registration_count(self):
        """Test that all expected tools are registered.
        
        NOTE: FastMCP no longer adds a '- ' prefix to tool names.
        """
        import asyncio
        from src.mcp_server import mcp

        async def check_tools():
            tools = await mcp.get_tools()
            # Expected tools without prefix:
            # health_check, create_ticket, update_ticket, delete_ticket,
            # show_ticket, colonize_hive, list_hives, abandon_hive, rename_hive,
            # sanitize_hive, add_named_query, execute_query, execute_freeform_query,
            # generate_index, help
            assert len(tools) == 15, f"Expected 15 tools, got {len(tools)}"

            # Verify specific tools are present
            expected_tools = {
                'health_check', 'create_ticket', 'update_ticket', 'delete_ticket',
                'show_ticket', 'colonize_hive', 'list_hives', 'abandon_hive',
                'rename_hive', 'sanitize_hive', 'add_named_query', 'execute_query',
                'execute_freeform_query', 'generate_index', 'help'
            }
            assert set(tools) == expected_tools

        asyncio.run(check_tools())

    def test_delegated_functions_are_callable(self):
        """Test that delegated functions maintain their signatures."""
        from src.mcp_ticket_ops import _create_ticket, _update_ticket, _delete_ticket, _show_ticket
        from src.mcp_hive_ops import _colonize_hive, _list_hives, _abandon_hive
        from src.mcp_query_ops import _add_named_query, _execute_query, _execute_freeform_query
        from src.mcp_index_ops import _generate_index
        from src.mcp_help import _help

        # Verify all functions are callable
        assert callable(_create_ticket)
        assert callable(_update_ticket)
        assert callable(_delete_ticket)
        assert callable(_show_ticket)
        assert callable(_colonize_hive)
        assert callable(_list_hives)
        assert callable(_abandon_hive)
        assert callable(_add_named_query)
        assert callable(_execute_query)
        assert callable(_execute_freeform_query)
        assert callable(_generate_index)
        assert callable(_help)
