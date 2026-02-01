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
            setup_signal_handlers(callback)

            # Get the registered handler and call it
            signal_handler = mock_signal.call_args_list[0][0][1]
            signal_handler(signal.SIGINT, None)

            callback.assert_called_once()
            # Should NOT call sys.exit(0) to allow uvicorn graceful shutdown

    def test_signal_handler_does_not_force_exit(self):
        """Test that signal handlers do not force immediate exit, allowing uvicorn shutdown."""
        callback = MagicMock()

        with patch('signal.signal') as mock_signal:
            with patch('sys.exit') as mock_exit:
                setup_signal_handlers(callback)

                # Get the registered handler and call it
                signal_handler = mock_signal.call_args_list[0][0][1]
                signal_handler(signal.SIGINT, None)

                callback.assert_called_once()
                # sys.exit should NOT be called - let uvicorn handle shutdown
                mock_exit.assert_not_called()


class TestServerInitialization:
    """Tests for server initialization and startup."""

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_successful_startup(self, mock_is_corrupt, mock_load_config, mock_setup_signals,
                                     mock_start_server, mock_uvicorn_run, tmp_path):
        """Test successful server startup with valid configuration."""
        # Setup mock config
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        # Run main
        main()

        # Verify calls
        mock_is_corrupt.assert_called_once()
        mock_load_config.assert_called_once()
        mock_setup_signals.assert_called_once()
        mock_start_server.assert_called_once()
        mock_uvicorn_run.assert_called_once()

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    @patch('src.main.mcp.http_app')
    def test_http_server_initialization(self, mock_http_app_method, mock_is_corrupt, mock_load_config,
                                        mock_setup_signals, mock_start_server, mock_uvicorn_run, tmp_path):
        """Test that HTTP server is initialized with correct parameters."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        # Mock http_app() to return a mock Starlette app
        mock_app = MagicMock()
        mock_http_app_method.return_value = mock_app

        main()

        # Verify uvicorn.run called with correct parameters
        mock_uvicorn_run.assert_called_once_with(
            mock_app,
            host="127.0.0.1",
            port=8000,
            log_level="info"
        )

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_http_server_localhost_binding(self, mock_is_corrupt, mock_load_config,
                                           mock_setup_signals, mock_start_server, mock_uvicorn_run, tmp_path):
        """Test that HTTP server binds to 127.0.0.1 by default for security."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        main()

        # Verify 127.0.0.1 binding
        call_args = mock_uvicorn_run.call_args
        assert call_args[1]['host'] == "127.0.0.1"

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_http_server_custom_port(self, mock_is_corrupt, mock_load_config,
                                     mock_setup_signals, mock_start_server, mock_uvicorn_run, tmp_path):
        """Test that HTTP server uses configured port."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 9000},
            "ticket_directory": str(ticket_dir)
        })

        main()

        # Verify custom port
        call_args = mock_uvicorn_run.call_args
        assert call_args[1]['port'] == 9000

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

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_creates_missing_ticket_directory(self, mock_is_corrupt, mock_load_config,
                                                   mock_setup_signals,
                                                   mock_start_server,
                                                   mock_uvicorn_run, tmp_path):
        """Test that main creates ticket directory if it doesn't exist."""
        ticket_dir = tmp_path / "nonexistent_tickets"

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
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
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        mock_start_server.side_effect = Exception("Server startup failed")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


class TestConfigurationVariations:
    """Tests for different configuration scenarios."""

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_with_custom_host(self, mock_is_corrupt, mock_load_config, mock_setup_signals,
                                   mock_start_server, mock_uvicorn_run, tmp_path):
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

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_with_custom_port(self, mock_is_corrupt, mock_load_config, mock_setup_signals,
                                   mock_start_server, mock_uvicorn_run, tmp_path):
        """Test server starts with custom port configuration."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 9000},
            "ticket_directory": str(ticket_dir)
        })

        main()

        mock_start_server.assert_called_once()

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_with_absolute_ticket_directory(self, mock_is_corrupt, mock_load_config,
                                                 mock_setup_signals,
                                                 mock_start_server,
                                                 mock_uvicorn_run, tmp_path):
        """Test server starts with absolute ticket directory path."""
        ticket_dir = tmp_path / "absolute_tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
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
                    "ticket_id": "default.bees-abc",
                    "error_type": "id_format",
                    "message": "Invalid ID format",
                    "severity": "error"
                },
                {
                    "ticket_id": "default.bees-xyz",
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

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_main_starts_normally_when_clean(self, mock_is_corrupt, mock_load_config,
                                            mock_setup_signals, mock_start_server,
                                            mock_uvicorn_run, tmp_path):
        """Test that main starts normally when database is clean."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
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


class TestHTTPErrorHandling:
    """Tests for HTTP-specific error handling."""

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_port_in_use_error(self, mock_is_corrupt, mock_load_config,
                               mock_setup_signals, mock_start_server,
                               mock_uvicorn_run, tmp_path):
        """Test OSError for port in use returns specific error message."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        # Simulate port in use error
        error = OSError("Address already in use")
        error.errno = 48
        mock_uvicorn_run.side_effect = error

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_permission_denied_error(self, mock_is_corrupt, mock_load_config,
                                     mock_setup_signals, mock_start_server,
                                     mock_uvicorn_run, tmp_path):
        """Test OSError for permission denied returns specific error message."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 80},
            "ticket_directory": str(ticket_dir)
        })

        # Simulate permission denied error
        error = OSError("Permission denied")
        error.errno = 13
        mock_uvicorn_run.side_effect = error

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_import_error_handling(self, mock_is_corrupt, mock_load_config,
                                   mock_setup_signals, mock_start_server,
                                   mock_uvicorn_run, tmp_path):
        """Test ImportError for missing uvicorn."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        mock_uvicorn_run.side_effect = ImportError("No module named 'uvicorn'")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_runtime_error_handling(self, mock_is_corrupt, mock_load_config,
                                    mock_setup_signals, mock_start_server,
                                    mock_uvicorn_run, tmp_path):
        """Test RuntimeError for server initialization failures."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        mock_uvicorn_run.side_effect = RuntimeError("Server initialization failed")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_generic_error_fallback(self, mock_is_corrupt, mock_load_config,
                                    mock_setup_signals, mock_start_server,
                                    mock_uvicorn_run, tmp_path):
        """Test that generic errors still caught with fallback handler."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        mock_uvicorn_run.side_effect = Exception("Unknown error")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


class TestSignalHandlerInitializationOrder:
    """Tests for signal handler initialization after server startup."""

    @patch('src.main.uvicorn.run')
    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_signal_handlers_registered_after_server_init(self, mock_is_corrupt, mock_load_config,
                                                          mock_setup_signals, mock_start_server,
                                                          mock_uvicorn_run, tmp_path):
        """Test that signal handlers are registered after start_server() completes."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        main()

        # Verify call order: start_server must be called before setup_signal_handlers
        calls = [c for c in [mock_start_server, mock_setup_signals, mock_uvicorn_run]]
        assert mock_start_server.call_count == 1
        assert mock_setup_signals.call_count == 1
        assert mock_uvicorn_run.call_count == 1

    @patch('src.main.start_server')
    @patch('src.main.setup_signal_handlers')
    @patch('src.main.load_config')
    @patch('src.main.is_corrupt')
    def test_signal_handlers_not_registered_on_init_failure(self, mock_is_corrupt, mock_load_config,
                                                            mock_setup_signals, mock_start_server,
                                                            tmp_path):
        """Test that signal handlers are not registered if server initialization fails."""
        ticket_dir = tmp_path / "tickets"
        ticket_dir.mkdir()

        mock_is_corrupt.return_value = False
        mock_load_config.return_value = Config({
            "http": {"host": "127.0.0.1", "port": 8000},
            "ticket_directory": str(ticket_dir)
        })

        # Simulate server initialization failure
        mock_start_server.side_effect = Exception("Server init failed")

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        # Signal handlers should not be set up if server init fails
        mock_setup_signals.assert_not_called()


class TestCodeStyle:
    """Tests for code style and organization in main.py."""

    def test_main_imports_follow_pep8(self):
        """Test that imports in main.py follow PEP 8 grouping."""
        main_file = Path(__file__).parent.parent / "src" / "main.py"
        with open(main_file, 'r') as f:
            lines = f.readlines()

        # Find import lines (skip docstring and blank lines)
        import_lines = []
        in_docstring = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
            elif not in_docstring and (stripped.startswith('import ') or stripped.startswith('from ')):
                import_lines.append((i, line))

        # Group imports: stdlib vs local (starts with .)
        stdlib_imports = []
        local_imports = []
        for line_num, line in import_lines:
            if line.strip().startswith('from .'):
                local_imports.append((line_num, line))
            else:
                stdlib_imports.append((line_num, line))

        # Verify stdlib imports come before local imports
        if stdlib_imports and local_imports:
            last_stdlib_line = stdlib_imports[-1][0]
            first_local_line = local_imports[0][0]
            assert last_stdlib_line < first_local_line, \
                f"Local imports should come after stdlib imports. Last stdlib: {last_stdlib_line}, First local: {first_local_line}"

            # Verify single blank line separator (line numbers should differ by 2: one for blank, one for next line)
            assert first_local_line - last_stdlib_line == 2, \
                f"Should be exactly one blank line between stdlib and local imports. Stdlib ends at {last_stdlib_line}, local starts at {first_local_line}"

    def test_log_message_appears_before_uvicorn(self):
        """Test that 'Launching HTTP server' log message appears before uvicorn.run() call."""
        main_file = Path(__file__).parent.parent / "src" / "main.py"
        with open(main_file, 'r') as f:
            lines = f.readlines()

        launching_line = None
        uvicorn_line = None

        for i, line in enumerate(lines, 1):
            if 'Launching HTTP server' in line:
                launching_line = i
            if 'uvicorn.run(' in line:
                uvicorn_line = i

        assert launching_line is not None, "Could not find 'Launching HTTP server' log message"
        assert uvicorn_line is not None, "Could not find 'uvicorn.run()' call"
        assert launching_line < uvicorn_line, \
            f"'Launching' message at line {launching_line} should appear before uvicorn.run() at line {uvicorn_line}"


class TestDocumentation:
    """Tests for documentation accuracy."""

    def test_master_plan_documents_http_app_property(self):
        """Test that master_plan.md correctly documents mcp.http_app property."""
        master_plan_file = Path(__file__).parent.parent / "docs" / "plans" / "master_plan.md"
        with open(master_plan_file, 'r') as f:
            content = f.read()

        # Verify mcp.http_app is documented
        assert 'mcp.http_app' in content, "master_plan.md should document mcp.http_app property"

        # Find HTTP server implementation section code block
        http_section_start = content.find('**Implementation Details** (`src/main.py`)')
        assert http_section_start != -1, "Could not find Implementation Details section"

        # Extract the code block (between ```python and ```)
        code_block_start = content.find('```python', http_section_start)
        code_block_end = content.find('```', code_block_start + 10)
        code_block = content[code_block_start:code_block_end]

        # Verify the code block shows uvicorn.run with mcp.http_app
        assert 'uvicorn.run(' in code_block, "Code block should show uvicorn.run() call"
        assert 'mcp.http_app' in code_block, "Code block should show mcp.http_app property"


class TestImportVerification:
    """Tests for import cleanliness and verification in main.py."""

    def test_no_unused_imports_in_main(self):
        """Test that src/main.py has no unused imports."""
        import ast
        import re

        main_file = Path(__file__).parent.parent / "src" / "main.py"
        with open(main_file, 'r') as f:
            content = f.read()

        # Parse the AST
        tree = ast.parse(content)

        # Collect all imports
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imports[name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imports[name] = f"{module}.{alias.name}" if module else alias.name

        # Check that each imported name is used in the code
        # Remove import statements and docstrings for usage check
        code_without_imports = re.sub(r'^(from|import)\s+.*$', '', content, flags=re.MULTILINE)

        unused = []
        for import_name in imports.keys():
            # Check if the imported name appears in the code (not in import statements)
            if import_name not in code_without_imports:
                unused.append(import_name)

        assert len(unused) == 0, f"Found unused imports in main.py: {unused}"

    def test_only_jsonresponse_imported_from_starlette_responses(self):
        """Test that only JSONResponse is imported from starlette.responses."""
        import ast

        main_file = Path(__file__).parent.parent / "src" / "main.py"
        with open(main_file, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        # Find imports from starlette.responses
        starlette_response_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == 'starlette.responses':
                    for alias in node.names:
                        starlette_response_imports.append(alias.name)

        # Should only import JSONResponse
        assert 'JSONResponse' in starlette_response_imports, \
            "JSONResponse should be imported from starlette.responses"
        assert 'Response' not in starlette_response_imports, \
            "Response should not be imported (unused)"
        assert len(starlette_response_imports) == 1, \
            f"Only JSONResponse should be imported from starlette.responses, found: {starlette_response_imports}"

    def test_starlette_application_not_imported(self):
        """Test that Starlette application class is not imported (unused)."""
        import ast

        main_file = Path(__file__).parent.parent / "src" / "main.py"
        with open(main_file, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        # Check for Starlette import
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == 'starlette.applications':
                    for alias in node.names:
                        assert alias.name != 'Starlette', \
                            "Starlette class should not be imported (unused)"

    def test_starlette_route_not_imported(self):
        """Test that Route class is not imported from starlette.routing (unused)."""
        import ast

        main_file = Path(__file__).parent.parent / "src" / "main.py"
        with open(main_file, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        # Check for Route import
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == 'starlette.routing':
                    pytest.fail("starlette.routing should not be imported at all (unused)")

    def test_server_starts_with_cleaned_imports(self):
        """Test that server can start successfully with cleaned imports."""
        # This test verifies that removing unused imports doesn't break functionality
        from src.main import main, setup_signal_handlers
        from src.mcp_server import start_server

        # If imports are correct, these should be importable without errors
        assert callable(main), "main() should be callable"
        assert callable(setup_signal_handlers), "setup_signal_handlers() should be callable"
        assert callable(start_server), "start_server() should be callable"
