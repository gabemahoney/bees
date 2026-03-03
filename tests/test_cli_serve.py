"""
Tests for the `bees serve` CLI command (src/cli.py handle_serve).

PURPOSE:
Tests flag validation, transport dispatch, fastmcp import guard, logging
reconfiguration, and --config forwarding for the serve subcommand.

SCOPE - Tests that belong here:
- bees serve flag validation (no flags, --stdio, --http, both flags)
- fastmcp ImportError guard
- --stdio transport: start_server() + mcp.run() called, logging reconfigured
- --http transport: uvicorn.run called, health route registered, scheduler wired
- --config forwarded to set_config_path
- UndertakerScheduler not instantiated in stdio path

SCOPE - Tests that DON'T belong here:
- MCP server lifecycle internals -> test_mcp_server_lifecycle.py
- Other CLI commands -> test_cli_commands.py
"""

import json
import logging
import signal
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from src.cli import build_parser, handle_serve


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


# ---------------------------------------------------------------------------
# TestServeFlagValidation
# ---------------------------------------------------------------------------


class TestServeFlagValidation:
    def test_serve_no_flags_exits_2(self, capsys):
        """bees serve with no transport flag exits 2 after printing usage."""
        args = _make_serve_args()

        with pytest.raises(SystemExit) as exc_info:
            handle_serve(args)

        assert exc_info.value.code == 2

    def test_serve_stdio_alone_proceeds(self, monkeypatch, tmp_path):
        """--stdio with mocked internals proceeds without raising SystemExit."""
        monkeypatch.setattr("src.cli.get_repo_root_from_path", lambda p: tmp_path)

        mock_mcp = MagicMock()
        mock_start = MagicMock()

        with patch.dict("sys.modules", {"fastmcp": MagicMock()}):
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

        with patch.dict("sys.modules", {"fastmcp": MagicMock()}):
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


class TestServeExtraGating:
    def test_serve_missing_fastmcp_exits_1(self, capsys):
        """When fastmcp is not importable, handle_serve exits 1 with install instructions."""
        args = _make_serve_args(stdio=True)

        with patch.dict("sys.modules", {"fastmcp": None}):
            with pytest.raises(SystemExit) as exc_info:
                handle_serve(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out.strip())
        assert result["status"] == "error"
        assert "fastmcp" in result["message"]


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
        with patch.dict("sys.modules", {"fastmcp": MagicMock()}):
            with patch("src.mcp_server.start_server", self.mock_start):
                with patch("src.mcp_server.mcp", self.mock_mcp):
                    handle_serve(args)

    def test_stdio_calls_mcp_run(self):
        """mcp.run(transport='stdio') is called on the --stdio path."""
        self._run_stdio()
        self.mock_mcp.run.assert_called_once_with(transport="stdio")

    def test_stdio_calls_start_server(self):
        """start_server() is called before mcp.run()."""
        call_order = []
        self.mock_start.side_effect = lambda: call_order.append("start_server")
        self.mock_mcp.run.side_effect = lambda **kw: call_order.append("mcp.run")

        self._run_stdio()

        assert call_order == ["start_server", "mcp.run"]

    def test_stdio_no_undertaker(self):
        """handle_serve stdio path never instantiates UndertakerScheduler."""
        with patch.dict("sys.modules", {"fastmcp": MagicMock()}):
            with patch("src.mcp_server.start_server", self.mock_start):
                with patch("src.mcp_server.mcp", self.mock_mcp):
                    with patch("src.mcp_undertaker.UndertakerScheduler") as mock_sched:
                        args = _make_serve_args(stdio=True)
                        handle_serve(args)
                        mock_sched.assert_not_called()

    def test_stdio_logging_to_file(self):
        """Root logger handlers are replaced with a single FileHandler after --stdio."""
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        original_level = root_logger.level
        stream_handler = logging.StreamHandler()
        root_logger.addHandler(stream_handler)

        try:
            self._run_stdio()

            handlers = logging.getLogger().handlers
            assert len(handlers) >= 1
            assert not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
                           for h in handlers), (
                "StreamHandler should have been removed from root logger"
            )
            assert any(isinstance(h, logging.FileHandler) for h in handlers)
        finally:
            # Close any FileHandlers added by the stdio path to avoid ResourceWarning
            for h in root_logger.handlers[:]:
                if isinstance(h, logging.FileHandler) and h not in original_handlers:
                    h.close()
            root_logger.handlers.clear()
            for h in original_handlers:
                root_logger.addHandler(h)
            root_logger.setLevel(original_level)


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
            with patch.dict("sys.modules", {"fastmcp": MagicMock()}):
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
    def _patch_http_deps(self, monkeypatch, tmp_path):
        """Patch common dependencies for every HTTP transport test."""
        monkeypatch.setattr("src.cli.get_repo_root_from_path", lambda p: tmp_path)
        self.tmp_path = tmp_path

        self.mock_mcp = MagicMock()
        self.mock_http_app = MagicMock()
        self.mock_mcp.http_app.return_value = self.mock_http_app

        self.mock_start = MagicMock()
        self.mock_uvicorn_run = MagicMock()

        self.mock_load_global_config = MagicMock(return_value={})

        with ExitStack() as stack:
            stack.enter_context(patch.dict("sys.modules", {"fastmcp": MagicMock()}))
            stack.enter_context(patch("src.mcp_server.start_server", self.mock_start))
            stack.enter_context(patch("src.mcp_server.stop_server", MagicMock()))
            stack.enter_context(patch("src.mcp_server.mcp", self.mock_mcp))
            stack.enter_context(patch("src.mcp_server._health_check", MagicMock()))
            stack.enter_context(patch("src.config.load_bees_config", return_value=None))
            stack.enter_context(patch("src.config.load_global_config", self.mock_load_global_config))
            stack.enter_context(patch("src.mcp_undertaker.UndertakerScheduler"))
            stack.enter_context(patch("uvicorn.run", self.mock_uvicorn_run))
            yield

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

        self.mock_uvicorn_run.assert_called_once()
        _, kwargs = self.mock_uvicorn_run.call_args
        assert kwargs.get("host") == "127.0.0.1"
        assert kwargs.get("port") == 8000

    # ------------------------------------------------------------------
    # Test 2 — custom host/port forwarded to uvicorn.run
    # ------------------------------------------------------------------

    def test_http_host_port_forwarded(self):
        """--host 0.0.0.0 --port 9000 is forwarded verbatim to uvicorn.run()."""
        self._run_http(host="0.0.0.0", port=9000)

        self.mock_uvicorn_run.assert_called_once()
        _, kwargs = self.mock_uvicorn_run.call_args
        assert kwargs.get("host") == "0.0.0.0"
        assert kwargs.get("port") == 9000

    # ------------------------------------------------------------------
    # Test 3 — start_server() called before uvicorn.run()
    # ------------------------------------------------------------------

    def test_http_calls_start_server(self):
        """start_server() is called before uvicorn.run() on the --http path."""
        call_order = []
        self.mock_start.side_effect = lambda: call_order.append("start_server")
        self.mock_uvicorn_run.side_effect = lambda *a, **kw: call_order.append("uvicorn.run")

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

        self.mock_http_app.add_route.assert_called_once()
        route_path = self.mock_http_app.add_route.call_args[0][0]
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

                mock_scheduler_cls.assert_called_once_with(mock_config, self.tmp_path)

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
        self.mock_load_global_config.return_value = global_config
        self._run_http(port=args_port)

        _, kwargs = self.mock_uvicorn_run.call_args
        assert kwargs.get("port") == expected_port


# ---------------------------------------------------------------------------
# TestTestConfigFlag
# ---------------------------------------------------------------------------


class TestTestConfigFlag:
    """Tests for the --test-config flag in bees serve."""

    @pytest.fixture(autouse=True)
    def _patch_http_deps(self, monkeypatch, tmp_path):
        """Patch all server startup dependencies for every test in this class."""
        monkeypatch.setattr("src.cli.get_repo_root_from_path", lambda p: tmp_path)
        self.tmp_path = tmp_path

        mock_mcp = MagicMock()
        mock_mcp.http_app.return_value = MagicMock()
        self.mock_uvicorn_run = MagicMock()

        with ExitStack() as stack:
            stack.enter_context(patch.dict("sys.modules", {"fastmcp": MagicMock()}))
            stack.enter_context(patch("src.mcp_server.start_server"))
            stack.enter_context(patch("src.mcp_server.stop_server", MagicMock()))
            stack.enter_context(patch("src.mcp_server.mcp", mock_mcp))
            stack.enter_context(patch("src.mcp_server._health_check", MagicMock()))
            stack.enter_context(patch("src.config.load_bees_config", return_value=None))
            stack.enter_context(patch("src.config.load_global_config", return_value={}))
            stack.enter_context(patch("src.mcp_undertaker.UndertakerScheduler"))
            stack.enter_context(patch("uvicorn.run", self.mock_uvicorn_run))
            yield

    # --- Happy path tests ---

    def test_file_path_calls_override(self, tmp_path):
        """--test-config /path/to/file.json reads file and calls set_test_config_override."""
        config = {"schema_version": "2.0", "scopes": {"/repo": {"hives": {}}}}
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

        mock_override.assert_called_once_with({"schema_version": "2.0", "scopes": {}})

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
            set_test_config_override({"schema_version": "2.0", "scopes": {}})

            save_global_config({"scopes": {"/op1": {"hives": {}}}, "schema_version": "2.0"})
            save_global_config({"scopes": {"/op2": {"hives": {}}}, "schema_version": "2.0"})
            save_global_config({"scopes": {"/op3": {"hives": {}}}, "schema_version": "2.0"})

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
            set_test_config_override({"schema_version": "2.0", "scopes": {}})

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
