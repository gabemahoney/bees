"""
Tests for the `bees serve` CLI command (src/cli.py handle_serve).

PURPOSE:
Tests flag validation, transport dispatch, the fastmcp/mcp dependency guard, stderr reporting
of fatal startup errors, logging reconfiguration, and --config forwarding for the serve subcommand.

SCOPE - Tests that belong here:
- bees serve flag validation (no flags, --stdio, --http, both flags)
- the dependency guard (b.zhu, b.bop): a missing, half-installed or incompatible fastmcp/mcp stops both
  transports with the clean-reinstall message on stderr, nothing on stdout, and the reason in mcp.log
- fatal startup errors (invalid config, port in use, transport errors) reach stderr; stdout stays
  clean under --stdio (it is the MCP stream)
- --stdio transport: start_server() + mcp.run() called, logging reconfigured
- --http transport: uvicorn.run called, health route registered, scheduler wired
- --http startup fails with the config_load_error JSON when the global config cannot be loaded
- --config forwarded to set_config_path
- UndertakerScheduler not instantiated in stdio path

SCOPE - Tests that DON'T belong here:
- The dependency self-check itself (versions, imports, message text) -> test_serve_deps.py
- MCP server lifecycle internals -> test_mcp_server_lifecycle.py
- Other CLI commands -> test_cli_commands.py
"""

import json
import logging
import signal
import sys
import types
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.cli import build_parser, handle_serve
from src.config import load_global_config
from src.serve_deps import check_serve_dependencies, pip_fix_command


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_serve_args(
    *, stdio=False, http=False, config=None, test_config=None, host="127.0.0.1", port=None, parser=None
):
    """Build a namespace mimicking parsed `bees serve` args."""
    import argparse

    if parser is None:
        parser = build_parser()
        # Retrieve the serve subparser to attach as _parser
        # Walk subparsers to find 'serve'
        for action in parser._subparsers._actions:
            if hasattr(action, '_name_parser_map') and 'serve' in action._name_parser_map:
                parser = action._name_parser_map['serve']
                break

    ns = argparse.Namespace(
        stdio=stdio, http=http, config=config, test_config=test_config,
        host=host, port=port, serve_parser=parser
    )
    return ns


def _serve_subparser():
    """Return the serve subparser from build_parser()."""
    p = build_parser()
    for action in p._subparsers._actions:
        if hasattr(action, '_name_parser_map') and 'serve' in action._name_parser_map:
            return action._name_parser_map['serve']
    raise RuntimeError("serve subparser not found")


@pytest.fixture(autouse=True)
def serve_log_path(monkeypatch, tmp_path):
    """Send `bees serve` file logging (~/.bees/mcp.log) to tmp_path; restore the root logger after."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    root_logger = logging.getLogger()
    original_handlers, original_level = root_logger.handlers[:], root_logger.level
    yield tmp_path / ".bees" / "mcp.log"
    for handler in root_logger.handlers[:]:
        if handler not in original_handlers:
            handler.close()
    root_logger.handlers[:] = original_handlers
    root_logger.setLevel(original_level)


@pytest.fixture(autouse=True)
def healthy_serve_dependencies(monkeypatch):
    """Report fastmcp and mcp as usable, whatever this test environment holds (the self-check has its own tests)."""
    monkeypatch.setattr("src.cli.check_serve_dependencies", lambda: None)


@pytest.fixture
def real_dependency_check(monkeypatch):
    """Undo healthy_serve_dependencies: run the real src.serve_deps self-check."""
    monkeypatch.setattr("src.cli.check_serve_dependencies", check_serve_dependencies)


def _fake_namespace_fastmcp():
    """A `fastmcp` left as an empty folder: importable, no __file__, no names (b.zhu)."""
    module = types.ModuleType("fastmcp")
    module.__file__ = None
    module.__path__ = []
    return module


CLEAN_REINSTALL_PIPX = "pipx uninstall bees-md && pipx install 'bees-md[serve]'"


@pytest.fixture
def server_mocks(monkeypatch, tmp_path):
    """Stub everything `handle_serve` starts, so a run that gets past a guard does nothing real.

    Returns the mocks: mcp, http_app, start, uvicorn_run, load_global_config and repo_root.
    """
    monkeypatch.setattr("src.cli.get_repo_root_from_path", lambda p: tmp_path)
    mocks = SimpleNamespace(
        mcp=MagicMock(),
        http_app=MagicMock(),
        start=MagicMock(),
        uvicorn_run=MagicMock(),
        load_global_config=MagicMock(return_value={}),
        repo_root=tmp_path,
    )
    mocks.mcp.http_app.return_value = mocks.http_app
    with ExitStack() as stack:
        stack.enter_context(patch("src.mcp_server.start_server", mocks.start))
        stack.enter_context(patch("src.mcp_server.stop_server", MagicMock()))
        stack.enter_context(patch("src.mcp_server.mcp", mocks.mcp))
        stack.enter_context(patch("src.mcp_server._health_check", MagicMock()))
        stack.enter_context(patch("src.config.load_bees_config", return_value=None))
        stack.enter_context(patch("src.config.load_global_config", mocks.load_global_config))
        stack.enter_context(patch("src.mcp_undertaker.UndertakerScheduler"))
        stack.enter_context(patch("uvicorn.run", mocks.uvicorn_run))
        yield mocks


# ---------------------------------------------------------------------------
# TestServeFlagValidation
# ---------------------------------------------------------------------------


class TestServeFlagValidation:
    def test_serve_stdio_alone_proceeds(self, monkeypatch, tmp_path):
        """--stdio with mocked internals proceeds without raising SystemExit."""
        monkeypatch.setattr("src.cli.get_repo_root_from_path", lambda p: tmp_path)

        mock_mcp = MagicMock()
        mock_start = MagicMock()

        with patch("src.mcp_server.start_server", mock_start):
            with patch("src.mcp_server.mcp", mock_mcp):
                args = _make_serve_args(stdio=True)
                # Should not raise SystemExit
                handle_serve(args)

        mock_mcp.run.assert_called_once_with(transport="stdio")

    def test_serve_http_proceeds(self, monkeypatch, tmp_path):
        """--http with mocked internals proceeds without raising SystemExit."""
        monkeypatch.setattr("src.cli.get_repo_root_from_path", lambda p: tmp_path)

        mock_mcp = MagicMock()
        mock_mcp.http_app.return_value = MagicMock()

        with patch("src.mcp_server.start_server"):
            with patch("src.mcp_server.mcp", mock_mcp):
                with patch("src.config.load_bees_config", return_value=None):
                    with patch("src.config.load_global_config", return_value={}):
                        with patch("uvicorn.run"):
                            args = _make_serve_args(http=True)
                            # Should not raise SystemExit
                            handle_serve(args)

    def test_serve_both_flags_exits_2(self):
        """--stdio --http together is rejected by argparse (mutually exclusive), exits 2."""
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["serve", "--stdio", "--http"])
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# TestServeExtraGating
# ---------------------------------------------------------------------------


TRANSPORTS = [pytest.param("stdio", id="stdio"), pytest.param("http", id="http")]


class TestServeExtraGating:
    """b.zhu / b.bop: an unusable fastmcp or mcp stops `bees serve` with a clean message on stderr only."""

    @pytest.fixture(autouse=True)
    def _server(self, server_mocks):
        self.server = server_mocks

    def _serve_expecting_exit(self, transport, capsys, code=1):
        """Run handle_serve for a transport, assert SystemExit(code), return (stdout, stderr)."""
        args = _make_serve_args(stdio=transport == "stdio", http=transport == "http")
        with pytest.raises(SystemExit) as exc_info:
            handle_serve(args)
        assert exc_info.value.code == code
        captured = capsys.readouterr()
        return captured.out, captured.err

    def _assert_server_not_started(self):
        self.server.start.assert_not_called()
        self.server.mcp.run.assert_not_called()
        self.server.uvicorn_run.assert_not_called()

    @pytest.mark.parametrize("transport", TRANSPORTS)
    @pytest.mark.parametrize(
        "broken_fastmcp,cause",
        [
            pytest.param(None, "fastmcp cannot be imported", id="missing"),
            pytest.param(_fake_namespace_fastmcp(), "fastmcp is installed incompletely", id="namespace_package"),
        ],
    )
    def test_broken_fastmcp_exits_1_with_clean_reinstall(
        self, real_dependency_check, monkeypatch, capsys, serve_log_path, transport, broken_fastmcp, cause
    ):
        """A missing or half-installed (importable, no files) fastmcp fails both transports (b.zhu): exit 1, nothing on stdout, stderr names the cause, both clean-reinstall commands for the published 'bees-md[serve]' (not bees-cli) and the log, and mcp.log holds the cause."""
        monkeypatch.setitem(sys.modules, "fastmcp", broken_fastmcp)  # None makes the import raise ImportError

        out, err = self._serve_expecting_exit(transport, capsys)

        assert out == ""
        assert cause in err
        assert CLEAN_REINSTALL_PIPX in err
        assert pip_fix_command() in err
        assert "bees-cli" not in err
        assert str(serve_log_path) in err
        assert cause in serve_log_path.read_text()
        self._assert_server_not_started()

    @pytest.mark.parametrize("transport", TRANSPORTS)
    def test_unwritable_bees_dir_still_reports_on_stderr(self, real_dependency_check, monkeypatch, capsys, serve_log_path, transport):
        """If ~/.bees cannot be created (a file is in the way), the dependency message still reaches stderr, exit 1, stdout empty."""
        serve_log_path.parent.write_text("not a directory")
        monkeypatch.setitem(sys.modules, "fastmcp", None)

        out, err = self._serve_expecting_exit(transport, capsys)

        assert out == ""
        assert "fastmcp cannot be imported" in err
        assert CLEAN_REINSTALL_PIPX in err
        assert str(serve_log_path) in err
        assert serve_log_path.parent.read_text() == "not a directory"
        self._assert_server_not_started()

    @pytest.mark.parametrize("transport", TRANSPORTS)
    def test_incompatible_mcp_import_failure_exits_1_on_stderr(
        self, monkeypatch, capsys, serve_log_path, transport
    ):
        """If the server module still fails to import after the self-check, both transports exit 1 with the reason and the clean-reinstall command on stderr (HTTP used to log it to mcp.log only) and nothing on stdout."""
        monkeypatch.setitem(sys.modules, "src.mcp_server", None)  # `from .mcp_server import ...` raises ImportError

        out, err = self._serve_expecting_exit(transport, capsys)

        assert out == ""
        assert "cannot be imported" in err
        assert CLEAN_REINSTALL_PIPX in err
        assert str(serve_log_path) in err
        assert "cannot be imported" in serve_log_path.read_text()
        self.server.uvicorn_run.assert_not_called()

    def test_serve_no_flags_exits_2_even_when_dependencies_are_broken(self, real_dependency_check, monkeypatch, capsys):
        """Usage errors are reported before the dependency check: no transport flag is still exit 2."""
        monkeypatch.setitem(sys.modules, "fastmcp", _fake_namespace_fastmcp())

        _, err = self._serve_expecting_exit("none", capsys, code=2)

        assert CLEAN_REINSTALL_PIPX not in err


# ---------------------------------------------------------------------------
# TestStdioTransport
# ---------------------------------------------------------------------------


class TestStdioTransport:
    """Tests for the --stdio execution path."""

    @pytest.fixture(autouse=True)
    def _patch_imports(self, monkeypatch, tmp_path):
        """Patch mcp_server symbols and repo root for every test in this class."""
        monkeypatch.setattr("src.cli.get_repo_root_from_path", lambda p: tmp_path)

        self.mock_mcp = MagicMock()
        self.mock_start = MagicMock()
        self.tmp_path = tmp_path

    def _run_stdio(self):
        args = _make_serve_args(stdio=True)
        with patch("src.mcp_server.start_server", self.mock_start):
            with patch("src.mcp_server.mcp", self.mock_mcp):
                handle_serve(args)

    def test_stdio_calls_mcp_run(self):
        """mcp.run(transport='stdio') is called on the --stdio path."""
        self._run_stdio()
        self.mock_mcp.run.assert_called_once_with(transport="stdio")

    def test_stdio_starts_with_malformed_global_config(self, mock_global_bees_dir):
        """--stdio loads the global config lazily (b.cyd): a malformed file does not stop the server from starting."""
        config_path = mock_global_bees_dir / "config.json"
        config_path.write_text("{invalid json")

        self._run_stdio()

        self.mock_mcp.run.assert_called_once_with(transport="stdio")
        assert config_path.read_text() == "{invalid json"

    def test_stdio_calls_start_server(self):
        """start_server() is called before mcp.run()."""
        call_order = []
        self.mock_start.side_effect = lambda: call_order.append("start_server")
        self.mock_mcp.run.side_effect = lambda **kw: call_order.append("mcp.run")

        self._run_stdio()

        assert call_order == ["start_server", "mcp.run"]

    def test_stdio_no_undertaker(self):
        """handle_serve stdio path never instantiates UndertakerScheduler."""
        with patch("src.mcp_server.start_server", self.mock_start):
            with patch("src.mcp_server.mcp", self.mock_mcp):
                with patch("src.mcp_undertaker.UndertakerScheduler") as mock_sched:
                    args = _make_serve_args(stdio=True)
                    handle_serve(args)
                    mock_sched.assert_not_called()

    def test_stdio_logging_to_file(self, serve_log_path):
        """Root logger handlers are replaced with a single FileHandler to ~/.bees/mcp.log after --stdio."""
        logging.getLogger().addHandler(logging.StreamHandler())

        self._run_stdio()

        handlers = logging.getLogger().handlers
        assert not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                       for h in handlers), (
            "StreamHandler should have been removed from root logger"
        )
        assert [h.baseFilename for h in handlers if isinstance(h, logging.FileHandler)] == [str(serve_log_path)]
        assert serve_log_path.exists()

    def test_stdio_transport_error_goes_to_stderr_and_log_not_stdout(self, capsys, serve_log_path):
        """A transport error exits 1 with a one-line message and the log path on stderr; stdout (the MCP stream) stays empty (b.bop)."""
        self.mock_mcp.run.side_effect = RuntimeError("pipe broke")

        with pytest.raises(SystemExit) as exc_info:
            self._run_stdio()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "stdio transport error: pipe broke" in captured.err
        assert str(serve_log_path) in captured.err
        assert "pipe broke" in serve_log_path.read_text()


# ---------------------------------------------------------------------------
# TestConfigFlag
# ---------------------------------------------------------------------------


class TestConfigFlag:
    def test_config_forwarded_to_set_config_path(self, monkeypatch, tmp_path):
        """--config /some/path calls set_config_path with that exact path."""
        monkeypatch.setattr("src.cli.get_repo_root_from_path", lambda p: tmp_path)

        captured_paths = []

        def mock_set_config(path):
            captured_paths.append(path)

        mock_mcp = MagicMock()
        mock_start = MagicMock()

        with patch("src.cli.set_config_path", mock_set_config):
            with patch("src.mcp_server.start_server", mock_start):
                with patch("src.mcp_server.mcp", mock_mcp):
                    args = _make_serve_args(stdio=True, config="/some/path")
                    handle_serve(args)

        assert captured_paths == ["/some/path"]


# ---------------------------------------------------------------------------
# TestHttpTransport
# ---------------------------------------------------------------------------


class TestHttpTransport:
    """Tests for the --http execution path."""

    @pytest.fixture(autouse=True)
    def _server(self, server_mocks):
        self.server = server_mocks

    def _run_http(self, **kwargs):
        """Invoke handle_serve with --http and optional overrides."""
        args = _make_serve_args(http=True, **kwargs)
        handle_serve(args)

    # ------------------------------------------------------------------
    # Test 1 — uvicorn.run receives default host/port
    # ------------------------------------------------------------------

    def test_http_calls_uvicorn_run(self):
        """uvicorn.run() is called with default host=127.0.0.1 and port=8000."""
        self._run_http()

        self.server.uvicorn_run.assert_called_once()
        _, kwargs = self.server.uvicorn_run.call_args
        assert kwargs.get("host") == "127.0.0.1"
        assert kwargs.get("port") == 8000

    # ------------------------------------------------------------------
    # Test 2 — custom host/port forwarded to uvicorn.run
    # ------------------------------------------------------------------

    def test_http_host_port_forwarded(self):
        """--host 0.0.0.0 --port 9000 is forwarded verbatim to uvicorn.run()."""
        self._run_http(host="0.0.0.0", port=9000)

        self.server.uvicorn_run.assert_called_once()
        _, kwargs = self.server.uvicorn_run.call_args
        assert kwargs.get("host") == "0.0.0.0"
        assert kwargs.get("port") == 9000

    # ------------------------------------------------------------------
    # Test 3 — start_server() called before uvicorn.run()
    # ------------------------------------------------------------------

    def test_http_calls_start_server(self):
        """start_server() is called before uvicorn.run() on the --http path."""
        call_order = []
        self.server.start.side_effect = lambda: call_order.append("start_server")
        self.server.uvicorn_run.side_effect = lambda *a, **kw: call_order.append("uvicorn.run")

        self._run_http()

        assert "start_server" in call_order
        assert "uvicorn.run" in call_order
        assert call_order.index("start_server") < call_order.index("uvicorn.run")

    # ------------------------------------------------------------------
    # Test 4 — /health route registered on the Starlette app
    # ------------------------------------------------------------------

    def test_http_health_route_registered(self):
        """app.add_route('/health', ...) is called on the http_app object."""
        self._run_http()

        self.server.http_app.add_route.assert_called_once()
        route_path = self.server.http_app.add_route.call_args[0][0]
        assert route_path == "/health"

    # ------------------------------------------------------------------
    # Test 5 — UndertakerScheduler instantiated when config present
    # ------------------------------------------------------------------

    def test_http_scheduler_created_when_config_present(self):
        """UndertakerScheduler is instantiated when load_bees_config returns a config."""
        mock_hive_cfg = MagicMock()
        mock_hive_cfg.undertaker_schedule_seconds = 60
        mock_hive_cfg.undertaker_schedule_query_yaml = "- ['status=open']"
        mock_hive_cfg.undertaker_schedule_query_name = None
        mock_hive_cfg.undertaker_schedule_log_path = None

        mock_config = MagicMock()
        mock_config.child_tiers = {}
        mock_config.hives = {"main": mock_hive_cfg}

        with patch("src.config.load_bees_config", return_value=mock_config):
            with patch("src.mcp_undertaker.UndertakerScheduler") as mock_scheduler_cls:
                mock_scheduler_instance = MagicMock()
                mock_scheduler_instance.active = False
                mock_scheduler_cls.return_value = mock_scheduler_instance

                self._run_http()

                mock_scheduler_cls.assert_called_once_with(mock_config, self.server.repo_root)

    # ------------------------------------------------------------------
    # Test 6 — signal handlers registered for SIGINT and SIGTERM
    # ------------------------------------------------------------------

    def test_http_signal_handlers_registered(self):
        """signal.signal() is called for SIGINT and SIGTERM during --http startup."""
        with patch("signal.signal") as mock_signal:
            self._run_http()

            registered_signals = {c.args[0] for c in mock_signal.call_args_list}
            assert signal.SIGINT in registered_signals
            assert signal.SIGTERM in registered_signals

    # ------------------------------------------------------------------
    # Test 7 — --config flag forwarded to set_config_path on --http path
    # ------------------------------------------------------------------

    def test_http_config_flag_works(self):
        """--config /some/path with --http calls set_config_path with that exact path."""
        captured_paths = []

        def mock_set_config(path):
            captured_paths.append(path)

        with patch("src.cli.set_config_path", mock_set_config):
            self._run_http(config="/some/path")

        assert captured_paths == ["/some/path"]

    # ------------------------------------------------------------------
    # b.cyd — a global config that cannot be loaded stops the server at startup
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("port", [pytest.param(None, id="no_port"), pytest.param(9000, id="explicit_port")])
    def test_http_refuses_to_start_on_unloadable_config(self, capsys, mock_global_bees_dir, serve_log_path, port):
        """A malformed global config fails startup with the error JSON on stdout, a short message with the log path on stderr, and exit 1, with or without --port."""
        config_path = mock_global_bees_dir / "config.json"
        config_path.write_text("{invalid json")
        self.server.load_global_config.side_effect = load_global_config  # the real loader, on the real file

        with pytest.raises(SystemExit) as exc_info:
            self._run_http(port=port)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["error_type"] == "config_load_error"
        assert result["path"] == str(config_path)
        assert "Failed to start server" in captured.err
        assert str(serve_log_path) in captured.err
        self.server.uvicorn_run.assert_not_called()
        self.server.start.assert_not_called()
        assert config_path.read_text() == "{invalid json"

    # ------------------------------------------------------------------
    # b.bop — every other fatal startup error reaches stderr, with the log path
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "error,fragment",
        [
            pytest.param(OSError(98, "Address already in use"), "Port 8000 is already in use", id="port_in_use"),
            pytest.param(OSError(13, "Permission denied"), "Permission denied for 127.0.0.1:8000", id="permission_denied"),
            pytest.param(OSError(99, "Cannot assign requested address"), "Network error", id="other_os_error"),
            pytest.param(RuntimeError("loop closed"), "Failed to start server: loop closed", id="runtime_error"),
            pytest.param(FileNotFoundError("no config here"), "Configuration error", id="file_not_found"),
            pytest.param(KeyError("surprise"), "Unexpected error", id="unexpected_error"),
        ],
    )
    def test_http_startup_failure_goes_to_stderr_and_log(self, capsys, serve_log_path, error, fragment):
        """A failing HTTP start exits 1 with the reason and the log path on stderr, the reason in mcp.log, and nothing on stdout."""
        self.server.uvicorn_run.side_effect = error

        with pytest.raises(SystemExit) as exc_info:
            self._run_http()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert fragment in captured.err
        assert str(serve_log_path) in captured.err
        assert fragment in serve_log_path.read_text()

    def test_http_invalid_bees_config_goes_to_stderr_with_exit_2(self, capsys, serve_log_path):
        """An invalid bees config exits 2 with the reason and the log path on stderr and nothing on stdout."""
        with patch("src.config.load_bees_config", side_effect=ValueError("tier names must be unique")):
            with pytest.raises(SystemExit) as exc_info:
                self._run_http()

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "tier names must be unique" in captured.err
        assert str(serve_log_path) in captured.err
        self.server.start.assert_not_called()

    # ------------------------------------------------------------------
    # Test 8 — port resolution priority: CLI > config > default
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "args_port,global_config,expected_port",
        [
            (None, {"http": {"port": 8001}}, 8001),
            (9000, {"http": {"port": 8001}}, 9000),
        ],
        ids=["port_from_config", "cli_overrides_config"],
    )
    def test_http_port_resolution(self, args_port, global_config, expected_port):
        """effective_port respects priority: --port CLI flag > http.port config > 8000 default."""
        self.server.load_global_config.return_value = global_config
        self._run_http(port=args_port)

        _, kwargs = self.server.uvicorn_run.call_args
        assert kwargs.get("port") == expected_port


# ---------------------------------------------------------------------------
# TestTestConfigFlag
# ---------------------------------------------------------------------------


class TestTestConfigFlag:
    """Tests for the --test-config flag in bees serve."""

    @pytest.fixture(autouse=True)
    def _server(self, server_mocks):
        self.server = server_mocks

    # --- Happy path tests ---

    def test_file_path_calls_override(self, tmp_path):
        """--test-config /path/to/file.json reads file and calls set_test_config_override."""
        config = {"schema_version": "3.0", "scopes": {"/repo": {"hives": {}}}}
        config_file = tmp_path / "test_cfg.json"
        config_file.write_text(json.dumps(config))

        with patch("src.cli.set_test_config_override") as mock_override:
            args = _make_serve_args(http=True, test_config=str(config_file))
            handle_serve(args)

        mock_override.assert_called_once_with(config)

    def test_inline_json_calls_override(self):
        """--test-config '{...}' parses JSON and calls set_test_config_override."""
        inline = '{"schema_version":"2.0","scopes":{}}'

        with patch("src.cli.set_test_config_override") as mock_override:
            args = _make_serve_args(http=True, test_config=inline)
            handle_serve(args)

        mock_override.assert_called_once_with({"schema_version": "2.0", "scopes": {}})

    def test_bare_flag_calls_override_with_empty_config(self):
        """--test-config (bare, no value) calls set_test_config_override with empty config."""
        with patch("src.cli.set_test_config_override") as mock_override:
            args = _make_serve_args(http=True, test_config="")
            handle_serve(args)

        mock_override.assert_called_once_with({"schema_version": "4.0", "scopes": {}})

    def test_info_log_emitted(self, caplog):
        """An INFO log mentioning test mode is emitted when --test-config is active."""
        with patch("src.cli.set_test_config_override"):
            with caplog.at_level(logging.INFO, logger="src.cli"):
                args = _make_serve_args(http=True, test_config="")
                handle_serve(args)

        assert any(
            "test mode" in r.message.lower() or "in-memory" in r.message.lower()
            for r in caplog.records
        )

    # --- Error path tests ---

    def test_mutual_exclusion_with_config_flag(self, capsys):
        """--config and --test-config together → exit 1, stderr mentions both flags."""
        args = _make_serve_args(http=True, config="/some/path", test_config="")

        with pytest.raises(SystemExit) as exc_info:
            handle_serve(args)

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "--config" in err and "--test-config" in err

    @pytest.mark.parametrize(
        "test_config,err_fragment",
        [
            ("/nonexistent/path.json", None),      # file not found: path or "not found" in stderr
            ("{bad json", "json"),                  # invalid inline JSON
            ('{"wrong":"shape"}', "scopes"),        # schema validation failure
        ],
        ids=["file_not_found", "bad_inline_json", "schema_validation"],
    )
    def test_error_inputs_exit_1(self, capsys, test_config, err_fragment):
        """Bad --test-config values all exit 1 with a descriptive stderr message."""
        args = _make_serve_args(http=True, test_config=test_config)

        with pytest.raises(SystemExit) as exc_info:
            handle_serve(args)

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        if err_fragment is None:
            # file-not-found case: path or "not found" in stderr
            assert test_config in err or "not found" in err.lower()
        else:
            assert err_fragment in err.lower()


# ---------------------------------------------------------------------------
# TestTestConfigIsolation
# ---------------------------------------------------------------------------


class TestTestConfigIsolation:
    """Integration: in-memory override never mutates config file on disk."""

    def test_disk_unchanged_under_override(self, mock_global_bees_dir, isolated_bees_env):
        """Config file bytes are identical before and after 3 save_global_config calls under override."""
        from src.config import load_global_config, save_global_config, set_test_config_override

        isolated_bees_env.write_config()
        config_file = mock_global_bees_dir / "config.json"
        initial_bytes = config_file.read_bytes()

        try:
            set_test_config_override({"schema_version": "3.0", "scopes": {}})

            save_global_config({"scopes": {"/op1": {"hives": {}}}, "schema_version": "3.0"})
            save_global_config({"scopes": {"/op2": {"hives": {}}}, "schema_version": "3.0"})
            save_global_config({"scopes": {"/op3": {"hives": {}}}, "schema_version": "3.0"})

            # In-memory state reflects the last write
            in_memory = load_global_config()
            assert "/op3" in in_memory["scopes"]

            # Disk is byte-identical to before the override
            assert config_file.read_bytes() == initial_bytes
        finally:
            set_test_config_override(None)

    def test_load_modify_save_round_trip(self, mock_global_bees_dir, isolated_bees_env):
        """load_global_config → mutate in-place → save_global_config preserves data.

        Reproduces the aliasing bug where save_global_config would .clear()
        the override dict and then .update() from the same (now-empty) object.
        """
        from src.config import load_global_config, save_global_config, set_test_config_override

        try:
            set_test_config_override({"schema_version": "3.0", "scopes": {}})

            # Load returns a reference to the override; mutate in-place then save
            cfg = load_global_config()
            cfg["scopes"]["/new/**"] = {"hives": {"demo": {"path": "/tmp/demo"}}}
            save_global_config(cfg)

            # The in-memory override must still contain the mutation
            reloaded = load_global_config()
            assert "/new/**" in reloaded["scopes"], "In-place mutation lost after save"
            assert "demo" in reloaded["scopes"]["/new/**"]["hives"]
        finally:
            set_test_config_override(None)
