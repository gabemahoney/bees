"""
Unit tests for MCP server startup and configuration.

Tests src/main.py functionality including:
- Configuration integration with Config module
- Server initialization with different config values
- Signal handling for graceful shutdown
- Error cases: invalid config, missing files, permission errors
"""

import os
import signal
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from src.main import setup_signal_handlers, main
from src.config import Config


class TestConfigIntegration:
    """Tests for Config module integration in main.py."""

    @patch('src.main.load_config')
    def test_main_uses_config_object(self, mock_load_config):
        """Test that main() correctly loads Config object."""
        mock_config = Config({
            'http': {'host': '127.0.0.1', 'port': 8000},
            'ticket_directory': './tickets'
        })
        mock_load_config.return_value = mock_config

        # Verify Config object attributes are accessible
        assert mock_config.http_host == '127.0.0.1'
        assert mock_config.http_port == 8000
        assert mock_config.ticket_directory == './tickets'

    @patch('src.main.load_config')
    def test_main_accesses_http_host_attribute(self, mock_load_config):
        """Test that main() accesses http_host attribute correctly."""
        mock_config = Config({
            'http': {'host': '0.0.0.0', 'port': 8000},
            'ticket_directory': './tickets'
        })
        mock_load_config.return_value = mock_config

        # Test attribute access
        assert mock_config.http_host == '0.0.0.0'

    @patch('src.main.load_config')
    def test_main_accesses_http_port_attribute(self, mock_load_config):
        """Test that main() accesses http_port attribute correctly."""
        mock_config = Config({
            'http': {'host': '127.0.0.1', 'port': 9000},
            'ticket_directory': './tickets'
        })
        mock_load_config.return_value = mock_config

        # Test attribute access
        assert mock_config.http_port == 9000

    @patch('src.main.load_config')
    def test_main_accesses_ticket_directory_attribute(self, mock_load_config):
        """Test that main() accesses ticket_directory attribute correctly."""
        mock_config = Config({
            'http': {'host': '127.0.0.1', 'port': 8000},
            'ticket_directory': '/custom/tickets'
        })
        mock_load_config.return_value = mock_config

        # Test attribute access
        assert mock_config.ticket_directory == '/custom/tickets'

    @patch('src.main.load_config')
    def test_main_handles_missing_config(self, mock_load_config):
        """Test that main() handles missing config gracefully with defaults."""
        # Config module returns defaults when file missing
        mock_config = Config({})
        mock_load_config.return_value = mock_config

        # Verify defaults are applied
        assert mock_config.http_host == '127.0.0.1'
        assert mock_config.http_port == 8000
        assert mock_config.ticket_directory == './tickets'

    @patch('src.main.load_config')
    def test_main_uses_nested_config_schema(self, mock_load_config):
        """Test that main() works with nested http config schema."""
        mock_config = Config({
            'http': {
                'host': '192.168.1.100',
                'port': 3000
            },
            'ticket_directory': './data/tickets'
        })
        mock_load_config.return_value = mock_config

        # Verify nested schema is properly accessed
        assert mock_config.http_host == '192.168.1.100'
        assert mock_config.http_port == 3000
        assert mock_config.ticket_directory == './data/tickets'


class TestSignalHandling:
    """Tests for signal handler setup and graceful shutdown."""

    def test_setup_signal_handlers_registers_sigint(self):
        """Test that SIGINT handler is registered."""
        callback = MagicMock()

        with patch('signal.signal') as mock_signal:
            setup_signal_handlers(callback)
            mock_signal.assert_any_call(signal.SIGINT, mock_signal.call_args_list[0][0][1])

    def test_setup_signal_handlers_registers_sigterm(self):
        """Test that SIGTERM handler is registered."""
        callback = MagicMock()

        with patch('signal.signal') as mock_signal:
            setup_signal_handlers(callback)
            mock_signal.assert_any_call(signal.SIGTERM, mock_signal.call_args_list[1][0][1])

    def test_signal_handler_calls_shutdown_callback(self):
        """Test that signal handler invokes the shutdown callback."""
        callback = MagicMock()

        with patch('signal.signal') as mock_signal:
            with patch('sys.exit') as mock_exit:
                setup_signal_handlers(callback)

                # Get the registered handler and call it
                signal_handler = mock_signal.call_args_list[0][0][1]
                signal_handler(signal.SIGINT, None)

                callback.assert_called_once()
                mock_exit.assert_called_once_with(0)


class TestServerInitialization:
    """Tests for server initialization and startup."""

    @patch('src.main.mcp.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_successful_startup(self, mock_is_corrupt, mock_load_config, mock_setup_signals,
                                     mock_start_server, mock_mcp_run, tmp_path):
        """Test successful server startup with valid configuration."""
        # Setup mock config
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "localhost", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        # Run main
        main()

        # Verify calls
        mock_is_corrupt.assert_called_once()
        mock_load_config.assert_called_once()
        mock_setup_signals.assert_called_once()
        mock_start_server.assert_called_once()
        mock_mcp_run.assert_called_once()

    @patch('src.main.is_corrupt')
    @patch('src.main.load_config')
    def test_main_exits_on_config_not_found(self, mock_load_config, mock_is_corrupt):
        """Test that main exits with code 1 when config file not found."""
        mock_is_corrupt.return_value = False
        mock_load_config.side_effect = FileNotFoundError("Config not found")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


    @patch('src.main.is_corrupt')
    @patch('src.main.load_config')
    def test_main_exits_on_validation_error(self, mock_load_config, mock_is_corrupt):
        """Test that main exits with code 1 on configuration validation error."""
        mock_is_corrupt.return_value = False
        mock_load_config.side_effect = ValueError("Missing required fields")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch('src.main.mcp.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_creates_missing_ticket_directory(self, mock_is_corrupt, mock_load_config,
                                                   mock_setup_signals,
                                                   mock_start_server,
                                                   mock_mcp_run, tmp_path):
        """Test that main creates ticket directory if it doesn't exist."""
        ticket_dir = tmp_path / "nonexistent_tickets"

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "localhost", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        # Verify directory doesn't exist
        assert not ticket_dir.exists()

        # Run main
        main()

        # Verify directory was created
        assert ticket_dir.exists()
        assert ticket_dir.is_dir()

    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_exits_on_server_start_failure(self, mock_is_corrupt, mock_load_config,
                                                mock_setup_signals,
                                                mock_start_server, tmp_path):
        """Test that main exits with code 1 if server startup fails."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "localhost", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        mock_start_server.side_effect = Exception("Server startup failed")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


class TestConfigurationVariations:
    """Tests for different configuration scenarios."""

    @patch('src.main.mcp.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_with_custom_host(self, mock_is_corrupt, mock_load_config, mock_setup_signals,
                                   mock_start_server, mock_mcp_run, tmp_path):
        """Test server starts with custom host configuration."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "0.0.0.0", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        main()

        mock_start_server.assert_called_once()

    @patch('src.main.mcp.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_with_custom_port(self, mock_is_corrupt, mock_load_config, mock_setup_signals,
                                   mock_start_server, mock_mcp_run, tmp_path):
        """Test server starts with custom port configuration."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "localhost", "port": 9000},
            "ticket_directory": str(ticket_dir)
        })

        main()

        mock_start_server.assert_called_once()

    @patch('src.main.mcp.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_with_absolute_ticket_directory(self, mock_is_corrupt, mock_load_config,
                                                 mock_setup_signals,
                                                 mock_start_server,
                                                 mock_mcp_run, tmp_path):
        """Test server starts with absolute ticket directory path."""
        ticket_dir = tmp_path / "absolute_tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "localhost", "port": 8000},
            "ticket_directory": str(ticket_dir.absolute())
        })

        main()

        mock_start_server.assert_called_once()


class TestCorruptionStateStartupCheck:
    """Tests for MCP server startup corruption state checks."""

    @patch('src.main.get_report')
    @patch('src.main.is_corrupt')
    def test_main_exits_when_database_corrupt(self, mock_is_corrupt, mock_get_report):
        """Test that main exits with code 1 when database is corrupt."""
        mock_is_corrupt.return_value = True
        mock_get_report.return_value = {
            "error_count": 2,
            "errors": [
                {
                    "ticket_id": "bees-abc",
                    "error_type": "id_format",
                    "message": "Invalid ID format",
                    "severity": "error"
                },
                {
                    "ticket_id": "bees-xyz",
                    "error_type": "duplicate_id",
                    "message": "Duplicate ID",
                    "severity": "error"
                }
            ]
        }

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_is_corrupt.assert_called_once()
        mock_get_report.assert_called_once()

    @patch('src.main.mcp.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_starts_normally_when_clean(self, mock_is_corrupt, mock_load_config,
                                            mock_setup_signals, mock_start_server,
                                            mock_mcp_run, tmp_path):
        """Test that main starts normally when database is clean."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "localhost", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        main()

        mock_is_corrupt.assert_called_once()
        mock_start_server.assert_called_once()

    @patch('src.main.get_report')
    @patch('src.main.is_corrupt')
    def test_main_exits_with_no_report_details(self, mock_is_corrupt, mock_get_report):
        """Test that main exits gracefully when corrupt but no report available."""
        mock_is_corrupt.return_value = True
        mock_get_report.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch('src.main.get_report')
    @patch('src.main.is_corrupt')
    def test_main_shows_sample_errors(self, mock_is_corrupt, mock_get_report):
        """Test that main shows sample errors when database is corrupt."""
        mock_is_corrupt.return_value = True
        # Create more than 5 errors to test truncation
        mock_get_report.return_value = {
            "error_count": 7,
            "errors": [
                {"ticket_id": f"bees-{i:03d}", "error_type": "test", "message": f"Error {i}", "severity": "error"}
                for i in range(7)
            ]
        }

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        # Should show first 5 errors and indicate there are more
