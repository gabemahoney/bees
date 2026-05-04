"""CLI entry point for the bees ticket management system.

All commands write JSON to stdout. Exit codes:
  0 = success (result["status"] == "success")
  1 = known error (result["status"] == "error")
  2 = usage/argument error
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .config import GLOBAL_SCHEMA_VERSION, check_queen_write_access, load_global_config, set_config_path, set_test_config_override
from .constants import BODY_MAX_LENGTH
from .mcp_clone_bee import _clone_bee
from .mcp_hive_ops import _abandon_hive, _list_hives, _rename_hive, _sanitize_hive, colonize_hive_core
from .mcp_index_ops import _generate_index
from .mcp_move_bee import _move_bee
from .mcp_query_ops import (
    _add_named_query,
    _delete_named_query,
    _execute_freeform_query,
    _execute_named_query,
    _list_named_queries,
)
from .mcp_resolver_ops import _get_resolvers, _set_resolver
from .mcp_ticket_ops import (
    _append_ticket_body,
    _create_ticket,
    _delete_ticket,
    _get_status_values,
    _get_types,
    _set_status_values,
    _set_types,
    _show_ticket,
    _update_ticket,
)
from .mcp_undertaker import _undertaker
from .migrations.runner import preview_pending_migrations, run_pending_migrations
from .repo_context import repo_root_context
from .repo_utils import get_repo_root_from_path
from .setup_claude import handle_setup_claude_cli
from .sting import handle_sting

logger = logging.getLogger(__name__)

# Sentinel for update-ticket: absent flag = "do not change"
_UNSET = "__UNSET__"


class BeesArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that writes usage errors as JSON to stdout."""

    def error(self, message):
        json.dump({"status": "error", "message": message}, sys.stdout)
        print()
        sys.exit(2)


def parse_json_arg(value, arg_name):
    """Parse a JSON string argument. 'null' -> None."""
    if value == "null":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"Invalid JSON for {arg_name}: {value}") from exc


# ---------------------------------------------------------------------------
# Shared handler helpers
# ---------------------------------------------------------------------------

def _output_result(result: dict) -> None:
    """Write JSON result to stdout and exit with appropriate code."""
    json.dump(result, sys.stdout)
    print()
    sys.exit(0 if result.get("status") == "success" else 1)


def _run_in_repo(coro, root: Path | None = None) -> dict:
    """Resolve repo root, set context, and run an async coroutine."""
    resolved = root if root is not None else get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved):
        return asyncio.run(coro)


def _guard_queen_write_cli(root: Path) -> bool:
    """Output permission_denied and return True if queen lacks write access."""
    if write_err := check_queen_write_access(root, load_global_config()):
        _output_result(write_err)
        return True
    return False


def _reject_oversized_body_cli(arg_name: str, value: str) -> None:
    """Reject body/chunk values that exceed the BODY_MAX_LENGTH cap.

    Shared by ``handle_append_ticket_body`` (for ``--chunk``) and, in Epic 5,
    by ``handle_create_ticket`` / ``handle_update_ticket`` (for ``--body``).
    Mirrors the MCP-side ``maxLength=BODY_MAX_LENGTH`` schema enforcement so
    the CLI surface returns the same kind of structured rejection without
    invoking the core ticket I/O path.

    On oversized input: write a single-line error to stderr that names the
    offending flag, the cap (10000), the actual size, and points the caller
    at ``bees append-ticket-body`` as the chunked alternative. Then exit
    non-zero. On in-bounds input: return without side effects.
    """
    if len(value) <= BODY_MAX_LENGTH:
        return
    print(
        f"Error: {arg_name} is {len(value)} characters, which exceeds the "
        f"10000 character cap. Use 'bees append-ticket-body --ticket-id <id> "
        f"--chunk <text>' to write large bodies in chunks of up to 10000 "
        f"characters each.",
        file=sys.stderr,
    )
    sys.exit(1)


def _read_body_file_arg(arg_name: str, path: str) -> str:
    """Read body text for a ``--body-file`` / ``--chunk-file`` CLI flag.

    The flag eliminates ``$(cat ...)`` shell substitution, which agentic
    harnesses (Claude Code) otherwise prompt on. Future call sites:
    ``handle_create_ticket`` (Task 2 of Epic 1), ``handle_update_ticket``
    (Epic 2), and ``handle_append_ticket_body`` (Epic 3).

    Behavior:
      - ``path == "-"``: read all of ``sys.stdin`` as UTF-8 and return it.
      - File-not-found, OS/permission error, and UTF-8 decode error each
        write a single-line ``Error:`` message to stderr that names
        ``arg_name`` and ``path``, then exit with status 1.
      - Otherwise return the decoded UTF-8 contents verbatim. No length
        check, trimming, or normalization is performed; callers continue
        to invoke ``_reject_oversized_body_cli`` on the return value.
    """
    if path == "-":
        try:
            return sys.stdin.read()
        except UnicodeDecodeError as exc:
            print(
                f"Error: {arg_name} could not decode stdin as UTF-8 ({path}): {exc}",
                file=sys.stderr,
            )
            sys.exit(1)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        print(
            f"Error: {arg_name} file not found: {path}",
            file=sys.stderr,
        )
        sys.exit(1)
    except OSError as exc:
        print(
            f"Error: {arg_name} could not read {path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(
            f"Error: {arg_name} could not decode {path} as UTF-8: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


def _configure_file_logging() -> Path:
    """Redirect root logger to ~/.bees/mcp.log (file-only). Returns log path."""
    log_path = Path.home() / ".bees" / "mcp.log"
    log_path.parent.mkdir(exist_ok=True)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    file_handler = logging.FileHandler(log_path, mode="a")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.INFO)
    return log_path


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_create_ticket(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    if args.body_file is not None:
        args.body = _read_body_file_arg("--body-file", args.body_file)
    if args.body is not None:
        _reject_oversized_body_cli("--body-file" if args.body_file is not None else "--body", args.body)
    result = _run_in_repo(
        _create_ticket(
            ticket_type=args.ticket_type,
            title=args.title,
            hive_name=args.hive,
            body=args.body or "",
            parent=args.parent,
            children=parse_json_arg(args.children, "--children") if args.children is not None else None,
            up_dependencies=parse_json_arg(args.up_deps, "--up-deps") if args.up_deps is not None else None,
            down_dependencies=parse_json_arg(args.down_deps, "--down-deps") if args.down_deps is not None else None,
            tags=parse_json_arg(args.tags, "--tags") if args.tags is not None else None,
            status=args.status,
            reference_materials=parse_json_arg(args.reference_materials, "--reference-materials") if args.reference_materials is not None else None,
        ),
        root=root,
    )
    _output_result(result)


def handle_show_ticket(args):
    root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(root):
        result = asyncio.run(_show_ticket(ticket_ids=args.ids, resolved_root=root))
    _output_result(result)


def handle_update_ticket(args):
    if args.parent is not _UNSET:
        _output_result({"status": "error", "error_type": "parent_immutable", "message": "parent cannot be changed after ticket creation"})  # noqa: E501
        return

    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return

    if args.body_file is not None:
        args.body = _read_body_file_arg("--body-file", args.body_file)

    if args.body is not _UNSET and args.body is not None:
        _reject_oversized_body_cli("--body-file" if args.body_file is not None else "--body", args.body)

    # Build kwargs: only pass fields that were explicitly provided (not _UNSET)
    ticket_ids = args.ids[0] if len(args.ids) == 1 else args.ids
    kwargs = {
        "ticket_ids": ticket_ids,
    }

    if args.title is not _UNSET:
        kwargs["title"] = args.title
    if args.body is not _UNSET:
        kwargs["body"] = args.body
    if args.status is not _UNSET:
        kwargs["status"] = args.status
    if args.tags is not _UNSET:
        kwargs["tags"] = parse_json_arg(args.tags, "--tags")
    if args.up_deps is not _UNSET:
        kwargs["up_dependencies"] = parse_json_arg(args.up_deps, "--up-deps")
    if args.down_deps is not _UNSET:
        kwargs["down_dependencies"] = parse_json_arg(args.down_deps, "--down-deps")
    if args.reference_materials is not _UNSET:
        kwargs["reference_materials"] = parse_json_arg(args.reference_materials, "--reference-materials")
    if args.add_tags is not _UNSET:
        kwargs["add_tags"] = parse_json_arg(args.add_tags, "--add-tags")
    if args.remove_tags is not _UNSET:
        kwargs["remove_tags"] = parse_json_arg(args.remove_tags, "--remove-tags")
    if args.hive is not _UNSET:
        kwargs["hive_name"] = args.hive

    with repo_root_context(root):
        result = asyncio.run(_update_ticket(**kwargs))
    _output_result(result)


def handle_delete_ticket(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    ticket_ids = args.ids
    result = _run_in_repo(
        _delete_ticket(
            ticket_ids=ticket_ids,
            hive_name=args.hive if args.hive is not None else None,
        ),
        root=root,
    )
    _output_result(result)


def handle_append_ticket_body(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    if args.chunk_file is not None:
        args.chunk = _read_body_file_arg("--chunk-file", args.chunk_file)
    _reject_oversized_body_cli("--chunk-file" if args.chunk_file is not None else "--chunk", args.chunk)
    result = _run_in_repo(
        _append_ticket_body(
            ticket_id=args.ticket_id,
            chunk=args.chunk,
            hive_name=args.hive,
        ),
        root=root,
    )
    _output_result(result)


def handle_get_types(args):
    root = get_repo_root_from_path(Path.cwd())
    result = _run_in_repo(_get_types(resolved_root=root))
    _output_result(result)


def handle_get_status_values(args):
    root = get_repo_root_from_path(Path.cwd())
    result = _run_in_repo(_get_status_values(resolved_root=root))
    _output_result(result)


def handle_set_types(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    if args.scope == "global":
        result = asyncio.run(
            _set_types(
                scope="global", hive_name=None, child_tiers=args.child_tiers, unset=args.unset, resolved_root=None
            )
        )
    else:
        with repo_root_context(root):
            result = asyncio.run(
                _set_types(
                    scope=args.scope, hive_name=args.hive, child_tiers=args.child_tiers,
                    unset=args.unset, resolved_root=root,
                )
            )
    _output_result(result)


def handle_set_status_values(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    if args.scope == "global":
        result = asyncio.run(
            _set_status_values(
                scope="global", hive_name=None, status_values=args.status_values, unset=args.unset, resolved_root=None
            )
        )
    else:
        with repo_root_context(root):
            result = asyncio.run(
                _set_status_values(
                    scope=args.scope,
                    hive_name=args.hive,
                    status_values=args.status_values,
                    unset=args.unset,
                    resolved_root=root,
                )
            )
    _output_result(result)


# ---------------------------------------------------------------------------
# Query handlers
# ---------------------------------------------------------------------------

def handle_add_named_query(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _add_named_query(name=args.query_name, query_yaml=args.query_yaml, scope=args.scope, resolved_root=root)
    _output_result(result)


def handle_execute_named_query(args):
    root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(root):
        result = asyncio.run(_execute_named_query(query_name=args.query_name, resolved_root=root))
    _output_result(result)


def handle_execute_freeform_query(args):
    root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(root):
        result = asyncio.run(_execute_freeform_query(query_yaml=args.query_yaml, resolved_root=root))
    _output_result(result)


def handle_delete_named_query(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _delete_named_query(name=args.query_name, resolved_root=root)
    _output_result(result)


def handle_list_named_queries(args):
    root = get_repo_root_from_path(Path.cwd())
    result = _list_named_queries(resolved_root=root)
    _output_result(result)


# ---------------------------------------------------------------------------
# Hive handlers
# ---------------------------------------------------------------------------

def handle_colonize_hive(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    parsed_child_tiers = parse_json_arg(args.child_tiers, "--child-tiers") if args.child_tiers is not None else None
    parsed_allowed_resolvers = parse_json_arg(args.allowed_resolvers, "--allowed-resolvers") if args.allowed_resolvers is not None else None  # noqa: E501
    parsed_status_values = None
    status_values_explicitly_null = False
    if args.status_values is not None:
        parsed_status_values = parse_json_arg(args.status_values, "--status-values")
        if parsed_status_values is None:
            status_values_explicitly_null = True
    result = _run_in_repo(
        colonize_hive_core(
            name=args.name,
            path=args.path,
            child_tiers=parsed_child_tiers,
            scope=args.scope,
            description=args.description,
            allowed_resolvers=parsed_allowed_resolvers,
            status_values=parsed_status_values,
            status_values_explicitly_null=status_values_explicitly_null,
        ),
        root=root,
    )
    _output_result(result)


def handle_list_hives(args):
    result = _run_in_repo(_list_hives())
    _output_result(result)


def handle_abandon_hive(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _run_in_repo(_abandon_hive(hive_name=args.hive), root=root)
    _output_result(result)


def handle_rename_hive(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _run_in_repo(
        _rename_hive(old_name=args.old_name, new_name=args.new_name, rename_folder=args.rename_folder,
                     description=args.description),
        root=root,
    )
    _output_result(result)


def handle_sanitize_hive(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _run_in_repo(_sanitize_hive(hive_name=args.hive), root=root)
    _output_result(result)


# ---------------------------------------------------------------------------
# Utility handlers
# ---------------------------------------------------------------------------

def handle_generate_index(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _run_in_repo(_generate_index(hive_name=args.hive), root=root)
    _output_result(result)


def handle_move_bee(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _run_in_repo(_move_bee(bee_ids=args.ids, destination_hive=args.hive, force=args.force), root=root)
    _output_result(result)


def handle_clone_bee(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _run_in_repo(_clone_bee(bee_id=args.bee_id, destination_hive=args.hive, force=args.force), root=root)
    _output_result(result)


def handle_update_config(args):
    if args.details:
        result = preview_pending_migrations()
    else:
        result = run_pending_migrations()
    _output_result(result)


def handle_set_resolver(args):
    result = _set_resolver(
        name=args.name,
        path=args.path,
        timeout=args.timeout,
        unset=args.unset,
    )
    _output_result(result)


def handle_get_resolvers(args):
    result = _get_resolvers()
    _output_result(result)


def handle_undertaker(args):
    root = get_repo_root_from_path(Path.cwd())
    if _guard_queen_write_cli(root):
        return
    result = _run_in_repo(
        _undertaker(
            hive_name=args.hive,
            query_yaml=args.query_yaml,
            query_name=args.query_name,
        ),
        root=root,
    )
    _output_result(result)


# ---------------------------------------------------------------------------
# Shared --test-config resolution helper
# ---------------------------------------------------------------------------


def _resolve_test_config(value: str) -> dict:
    """Resolve --test-config value to a config dict. Exits on error."""
    if value == "":
        return {"schema_version": GLOBAL_SCHEMA_VERSION, "scopes": {}}
    elif value.startswith("{"):
        try:
            resolved = json.loads(value)
        except json.JSONDecodeError as e:
            print(f"Error: --test-config value is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        config_path = Path(value)
        if not config_path.exists():
            print(f"Error: --test-config file not found: {value}", file=sys.stderr)
            sys.exit(1)
        try:
            resolved = json.loads(config_path.read_text())
        except json.JSONDecodeError as e:
            print(f"Error: --test-config file contains invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)
    if (
        not isinstance(resolved, dict)
        or "schema_version" not in resolved
        or "scopes" not in resolved
    ):
        print("Error: --test-config config must have 'schema_version' and 'scopes' keys.", file=sys.stderr)
        sys.exit(1)
    return resolved


# ---------------------------------------------------------------------------
# Serve handler
# ---------------------------------------------------------------------------


def handle_serve(args):
    # [serve] guard: fastmcp must be importable before we pull in mcp_server
    try:
        import fastmcp  # noqa: F401
    except ImportError:
        json.dump(
            {
                "status": "error",
                "message": (
                    "Missing required dependency: fastmcp. "
                    "Install with: pip install bees-cli[serve]"
                ),
            },
            sys.stdout,
        )
        print()
        sys.exit(1)

    # Neither flag supplied → print usage and exit
    if not args.stdio and not args.http:
        # args lives on the serve subparser; re-parse to get usage from it
        args.serve_parser.print_usage()
        sys.exit(2)

    if args.config and args.test_config is not None:
        print("Error: --config and --test-config are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    if args.config:
        set_config_path(args.config)

    if args.test_config is not None:
        set_test_config_override(_resolve_test_config(args.test_config))
        logger.info("Test mode active: running with in-memory config, no changes will be persisted")

    if args.http:
        # Reconfigure logging to file-only (required for clean HTTP server output)
        _configure_file_logging()

        # Deferred imports — must not happen at module level to avoid pulling
        # uvicorn/starlette/fastmcp at CLI load time.
        try:
            import uvicorn
            from starlette.requests import Request
            from starlette.responses import JSONResponse

            from .config import load_bees_config, load_global_config
            from .mcp_server import _health_check, mcp, start_server, stop_server
            from .mcp_undertaker import UndertakerScheduler
        except ImportError as e:
            logger.error(f"Failed to start server: Missing dependency - {e}")
            logger.error("Please install required dependencies with: poetry install")
            sys.exit(1)

        # Nested helpers defined here to avoid top-level starlette/logging deps
        async def health_endpoint(request: Request) -> JSONResponse:
            try:
                health_data = _health_check()
                return JSONResponse(content=health_data, status_code=200)
            except Exception as exc:
                logger.error(f"Health check failed: {exc}")
                return JSONResponse(
                    content={"status": "error", "message": str(exc)}, status_code=500
                )

        def setup_http_routes(app):
            app.add_route("/health", health_endpoint, methods=["GET", "POST"])
            logger.info("HTTP routes configured: /health")
            logger.info("MCP endpoint /mcp provided by FastMCP")

        def setup_signal_handlers(shutdown_callback):
            import signal as _signal

            def _handler(signum, frame):
                logger.info(f"Received signal {signum}, shutting down gracefully...")
                shutdown_callback()

            _signal.signal(_signal.SIGINT, _handler)
            _signal.signal(_signal.SIGTERM, _handler)

        effective_port = (
            args.port if args.port is not None else load_global_config().get("http", {}).get("port", 8000)
        )

        try:
            repo_root = get_repo_root_from_path(Path.cwd())

            with repo_root_context(repo_root):
                logger.info("Validating bees config schema...")
                try:
                    bees_config = load_bees_config()
                    if bees_config is not None:
                        tier_count = len(bees_config.child_tiers) if bees_config.child_tiers else 0
                        logger.info(
                            f"Bees config validated successfully: {tier_count} tier(s) configured"
                        )
                        for hive_name, hive_cfg in bees_config.hives.items():
                            has_seconds = hive_cfg.undertaker_schedule_seconds is not None
                            has_qy = hive_cfg.undertaker_schedule_query_yaml is not None
                            has_qn = hive_cfg.undertaker_schedule_query_name is not None
                            has_any = (
                                has_seconds
                                or has_qy
                                or has_qn
                                or hive_cfg.undertaker_schedule_log_path is not None
                            )
                            if not has_any:
                                continue
                            if not has_seconds:
                                raise ValueError(
                                    f"Hive '{hive_name}' undertaker_schedule requires interval_seconds"
                                )
                            if has_qy and has_qn:
                                raise ValueError(
                                    f"Hive '{hive_name}' undertaker_schedule must specify "
                                    f"query_yaml or query_name, not both"
                                )
                            if not has_qy and not has_qn:
                                raise ValueError(
                                    f"Hive '{hive_name}' undertaker_schedule requires "
                                    f"query_yaml or query_name"
                                )
                            if hive_cfg.undertaker_schedule_log_path:
                                log_parent = Path(hive_cfg.undertaker_schedule_log_path).parent
                                if not log_parent.exists():
                                    raise ValueError(
                                        f"Hive '{hive_name}' undertaker_schedule.log_path parent "
                                        f"directory does not exist: {log_parent}"
                                    )
                            logger.info(
                                f"Hive '{hive_name}' undertaker schedule: "
                                f"every {hive_cfg.undertaker_schedule_seconds}s"
                            )
                    else:
                        logger.info("No bees config found - operating in default mode")
                except ValueError as e:
                    logger.error("=" * 60)
                    logger.error("INVALID BEES CONFIGURATION")
                    logger.error("=" * 60)
                    logger.error(f"Configuration validation failed: {e}")
                    logger.error("")
                    logger.error("Fix ~/.bees/config.json to resolve validation errors.")
                    logger.error("See documentation for child_tiers schema requirements:")
                    logger.error("  - Keys must be t1, t2, t3... with no gaps")
                    logger.error("  - Values must be [] or [singular, plural]")
                    logger.error("  - Friendly names must be unique across tiers")
                    logger.error("=" * 60)
                    sys.exit(2)

                logger.info("=" * 60)
                logger.info("Bees MCP Server")
                logger.info("=" * 60)
                logger.info(f"Host: {args.host}")
                logger.info(f"Port: {effective_port}")
                logger.info("=" * 60)

                start_server()

                undertaker_scheduler = None
                if bees_config is not None:
                    undertaker_scheduler = UndertakerScheduler(bees_config, repo_root)

                http_app = mcp.http_app()
                setup_http_routes(http_app)

                if undertaker_scheduler is not None and undertaker_scheduler.active:
                    undertaker_scheduler.start()

                def _shutdown():
                    if undertaker_scheduler is not None:
                        undertaker_scheduler.stop()
                    stop_server()

                setup_signal_handlers(_shutdown)

                logger.info(f"Launching HTTP server on {args.host}:{effective_port}...")
                logger.info("MCP Server is running. Press Ctrl+C to stop.")

                uvicorn.run(http_app, host=args.host, port=effective_port, log_level="info")

        except FileNotFoundError as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
        except OSError as e:
            if "Address already in use" in str(e) or e.errno == 48:
                logger.error(f"Failed to start server: Port {effective_port} is already in use")
                logger.error(
                    f"Please stop the other service using port {effective_port} or use a different port"
                )
            elif "Permission denied" in str(e) or e.errno == 13:
                logger.error(
                    f"Failed to start server: Permission denied for {args.host}:{effective_port}"
                )
                logger.error(
                    "Try using a port number above 1024 or run with appropriate permissions"
                )
            else:
                logger.error(f"Failed to start server: Network error - {e}")
                logger.error(f"Check that {args.host}:{effective_port} is a valid address")
            sys.exit(1)
        except RuntimeError as e:
            logger.error(f"Failed to start server: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            sys.exit(1)
        return

    # --stdio path
    # Reconfigure logging to file-only (required for stdio MCP compatibility)
    _configure_file_logging()

    # Deferred import — must not happen at module level to avoid pulling fastmcp
    # at CLI load time.  The [serve] guard above ensures fastmcp is present before
    # this import executes (mcp_server imports fastmcp at its module level).
    from .mcp_server import mcp, start_server  # noqa: PLC0415

    try:
        repo_root = get_repo_root_from_path(Path.cwd())
        with repo_root_context(repo_root):
            start_server()
            mcp.run(transport="stdio")
    except Exception as exc:
        logger.error(f"stdio transport error: {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------

def build_parser():
    parser = BeesArgumentParser(
        prog="bees",
        description="Bees ticket management CLI. All commands output JSON to stdout, including errors. Exit 0 on success, exit 1 on error.",  # noqa: E501
    )
    subparsers = parser.add_subparsers(
        title="commands",
        parser_class=BeesArgumentParser,
    )

    # --- create-ticket ---
    p_create = subparsers.add_parser("create-ticket", help="Create a new ticket")
    p_create.add_argument("--ticket-type", required=True, dest="ticket_type", help='Ticket type: "bee" for top-level, or child tier by ID ("t1", "t2") or friendly name. Run get-types to see configured tiers.')  # noqa: E501
    p_create.add_argument("--title", required=True, help="Ticket title")
    p_create.add_argument("--hive", required=True, help="Hive to create the ticket in. Run list-hives to see available hives.")  # noqa: E501
    p_create_body = p_create.add_mutually_exclusive_group()
    p_create_body.add_argument("--body", default=None, help="Ticket body (markdown). Capped at 10000 characters; for larger bodies, create the ticket with the first 10000-character chunk and use 'bees append-ticket-body' to write the rest in chunks of up to 10000 characters each. Alternative: pass --body-file PATH when shell substitution is awkward.")  # noqa: E501
    p_create_body.add_argument("--body-file", dest="body_file", default=None, metavar="PATH", help="Read body from a UTF-8 file (use '-' for stdin); same 10000 character cap as --body, with oversized input pointed at 'bees append-ticket-body'.")  # noqa: E501
    p_create.add_argument("--parent", default=None, help="Parent ticket ID. Required for child-tier tickets; omit for bees. Parent's children field is updated automatically.")  # noqa: E501
    p_create.add_argument("--children", default=None, metavar="JSON", help="JSON array of child IDs to link. Bidirectional — child tickets' parent field is set automatically.")  # noqa: E501
    p_create.add_argument("--up-deps", default=None, dest="up_deps", metavar="JSON", help="JSON array of ticket IDs that must be resolved BEFORE this one.")  # noqa: E501
    p_create.add_argument("--down-deps", default=None, dest="down_deps", metavar="JSON", help="JSON array of ticket IDs this ticket must be resolved BEFORE.")  # noqa: E501
    p_create.add_argument("--tags", default=None, metavar="JSON", help='JSON array of tag strings e.g. \'["bug","urgent"]\'')  # noqa: E501
    p_create.add_argument("--status", default=None, help="Ticket status. Freeform unless the hive has status_values configured, in which case must be one of the allowed values.")  # noqa: E501
    p_create.add_argument("--reference-materials", default=None, dest="reference_materials", metavar="JSON", help="JSON list of reference material dicts. Tracks external resources related to the ticket. Only supported on bee (top-level) tickets.")  # noqa: E501
    p_create.set_defaults(func=handle_create_ticket)

    # --- show-ticket ---
    p_show = subparsers.add_parser("show-ticket", help="Retrieve one or more tickets")
    p_show.add_argument("--ids", required=True, nargs="+", metavar="ID", help="One or more ticket IDs (e.g. b.amx t1.nha)")  # noqa: E501
    p_show.set_defaults(func=handle_show_ticket)

    # --- update-ticket ---
    p_update = subparsers.add_parser(
        "update-ticket",
        help="Update an existing ticket",
        description=(
            "Update an existing ticket's fields. Only provided flags are changed; omitted flags\n"
            "are left as-is. Pass null to JSON fields to clear them (e.g. --tags null)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_update.add_argument("--ids", required=True, nargs="+", metavar="ID", help="One or more ticket IDs to update")
    p_update.add_argument("--title", default=_UNSET, help="New title")
    p_update_body = p_update.add_mutually_exclusive_group()
    p_update_body.add_argument("--body", default=_UNSET, help="New body (markdown). Capped at 10000 characters; for larger bodies, set the body to the first 10000-character chunk and use 'bees append-ticket-body' to write the rest in chunks of up to 10000 characters each. Alternative: pass --body-file PATH when shell substitution is awkward.")  # noqa: E501
    p_update_body.add_argument("--body-file", dest="body_file", default=None, metavar="PATH", help="Read new body from a UTF-8 file (use '-' for stdin); same 10000 character cap as --body, with oversized input pointed at 'bees append-ticket-body'.")  # noqa: E501
    p_update.add_argument("--status", default=_UNSET, help="New status")
    p_update.add_argument("--tags", default=_UNSET, dest="tags", metavar="JSON", help="Full replacement tag list as JSON array (null to clear)")  # noqa: E501
    p_update.add_argument("--up-deps", default=_UNSET, dest="up_deps", metavar="JSON", help="Full replacement list of ticket IDs that must be resolved BEFORE this one (null to clear)")  # noqa: E501
    p_update.add_argument("--down-deps", default=_UNSET, dest="down_deps", metavar="JSON", help="Full replacement list of ticket IDs this ticket must be resolved BEFORE (null to clear)")  # noqa: E501
    p_update.add_argument("--reference-materials", default=_UNSET, dest="reference_materials", metavar="JSON", help="JSON list of reference material dicts tracking external resources. Bee tickets only. (null to clear)")  # noqa: E501
    p_update.add_argument("--add-tags", default=_UNSET, dest="add_tags", metavar="JSON", help="JSON array of tags to add")  # noqa: E501
    p_update.add_argument("--remove-tags", default=_UNSET, dest="remove_tags", metavar="JSON", help="JSON array of tags to remove")  # noqa: E501
    p_update.add_argument("--hive", default=_UNSET, help="Hive name for faster lookup (optional)")
    p_update.add_argument("--parent", default=_UNSET, help="Not supported: parent is immutable after ticket creation")
    p_update.set_defaults(func=handle_update_ticket)

    # --- delete-ticket ---
    p_delete = subparsers.add_parser(
        "delete-ticket",
        help="Delete one or more tickets",
        description="Delete one or more tickets. Deletion cascades — all child tickets are deleted too.",
    )
    p_delete.add_argument("--ids", required=True, nargs="+", metavar="ID", help="One or more ticket IDs (e.g. b.amx t1.nha)")  # noqa: E501
    p_delete.add_argument("--hive", default=None, help="Hive name for faster lookup (optional)")
    p_delete.set_defaults(func=handle_delete_ticket)

    # --- append-ticket-body ---
    p_append_body = subparsers.add_parser(
        "append-ticket-body",
        help="Append a chunk to an existing ticket body. Use this when --body would exceed the 10000 character cap on create-ticket / update-ticket: split the body into chunks of up to 10000 characters each and call this subcommand once per chunk.",  # noqa: E501
        description=(
            "Append a chunk to an existing ticket's body. Each call concatenates --chunk\n"
            "onto the end of the existing body with no separator. Use this whenever the\n"
            "full body would exceed 10000 characters on create-ticket / update-ticket:\n"
            "create the ticket with the first 10000-character chunk, then call\n"
            "append-ticket-body repeatedly with subsequent chunks of up to 10000 characters\n"
            "each. Empty chunks are accepted as no-ops."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_append_body.add_argument(
        "--ticket-id",
        required=True,
        dest="ticket_id",
        metavar="ID",
        help="ID of the existing ticket whose body will be appended to (e.g. b.amx, t1.nha).",
    )
    p_append_chunk = p_append_body.add_mutually_exclusive_group(required=True)
    p_append_chunk.add_argument(
        "--chunk",
        metavar="TEXT",
        help="Text to append to the ticket body (required: one of --chunk or --chunk-file). Must be 10000 characters or fewer; pass an empty string for a no-op. To write bodies larger than 10000 characters, call this subcommand repeatedly with successive chunks. Alternative: pass --chunk-file PATH when shell substitution is awkward.",  # noqa: E501
    )
    p_append_chunk.add_argument(
        "--chunk-file",
        dest="chunk_file",
        default=None,
        metavar="PATH",
        help="Read the chunk text from a UTF-8 file (use '-' for stdin); same 10000-character per-chunk cap as --chunk. Alternative to --chunk for harnesses where shell substitution / quoting is awkward.",  # noqa: E501
    )
    p_append_body.add_argument(
        "--hive",
        default=None,
        metavar="NAME",
        help="Hive name for O(1) ticket lookup (optional).",
    )
    p_append_body.set_defaults(func=handle_append_ticket_body)

    # --- get-types ---
    p_types = subparsers.add_parser(
        "get-types",
        help="Show configured child tiers for all hives",
        description=(
            "Show configured child tiers for all hives. Returns child tier configuration at global, repo,"
            " and hive levels. Use this to see valid --ticket-type values for create-ticket. No arguments required."
        ),
    )
    p_types.set_defaults(func=handle_get_types)

    # --- set-types ---
    p_set_types = subparsers.add_parser(
        "set-types",
        help="Set or unset child tier configuration",
        description="Configure the child tier hierarchy at global, repo, or hive scope.",
    )
    p_set_types.add_argument(
        "--scope", required=True, choices=["global", "repo_scope", "hive"], help='Target scope: "global", "repo_scope", or "hive"'  # noqa: E501
    )
    p_set_types.add_argument("--hive", default=None, help="Hive name (required when --scope=hive)")
    p_set_types.add_argument(
        "--child-tiers",
        default=None,
        dest="child_tiers",
        type=lambda v: parse_json_arg(v, "--child-tiers"),
        help='Child tiers as JSON dict mapping tier keys to [singular, plural] names. e.g. {"t1": ["Epic","Epics"], "t2": ["Task","Tasks"]}. Pass {} for bees-only.',  # noqa: E501
    )
    p_set_types.add_argument(
        "--unset", action="store_true", default=False, help="Remove child tier config from the target scope"
    )
    p_set_types.set_defaults(func=handle_set_types)

    # --- set-status-values ---
    p_set_status_values = subparsers.add_parser(
        "set-status-values",
        help="Set or unset allowed status values",
        description=(
            "Configure allowed status values at global, repo, or hive scope."
            " If no status values are configured, any string is accepted."
        ),
    )
    p_set_status_values.add_argument(
        "--scope", required=True, choices=["global", "repo_scope", "hive"], help='Target scope: "global", "repo_scope", or "hive"'  # noqa: E501
    )
    p_set_status_values.add_argument("--hive", default=None, help="Hive name (required when --scope=hive)")
    p_set_status_values.add_argument(
        "--status-values",
        default=None,
        dest="status_values",
        type=lambda v: parse_json_arg(v, "--status-values"),
        help='JSON array of allowed status strings e.g. \'["open","in_progress","done"]\'',
    )
    p_set_status_values.add_argument(
        "--unset", action="store_true", default=False, help="Remove status value config from the target scope"
    )
    p_set_status_values.set_defaults(func=handle_set_status_values)

    # --- get-status-values ---
    p_get_status_values = subparsers.add_parser(
        "get-status-values",
        help="Show configured status values at all scope levels",
        description=(
            "Show configured status values at all scope levels (global, repo, and per-hive)."
            " Levels with nothing defined inherit from upper levels. No arguments required."
        ),
    )
    p_get_status_values.set_defaults(func=handle_get_status_values)

    # --- add-named-query ---
    p_anq = subparsers.add_parser(
        "add-named-query",
        help="Register a named query",
        description="Save a query for reuse. Accepts a YAML dict with a 'stages' key.",  # noqa: E501
    )
    p_anq.add_argument("--query-name", required=True, metavar="NAME", help="Name for the query (used to execute it later)")  # noqa: E501
    p_anq.add_argument("--query-yaml", required=True, dest="query_yaml", metavar="YAML", help='YAML dict with a "stages" key. Example: "stages:\\n  - [type=bee, status=pupa]\\n  - [children]"')  # noqa: E501
    p_anq.add_argument("--scope", choices=["global", "repo"], default="global", help='Where to store the query: "global" (all repos) or "repo" (repo scope). Default: global')  # noqa: E501
    p_anq.set_defaults(func=handle_add_named_query)

    # --- execute-named-query ---
    p_enq = subparsers.add_parser(
        "execute-named-query",
        help="Execute a registered named query",
        description="Execute a saved named query. Use list-named-queries to see available queries.",
    )
    p_enq.add_argument("--query-name", required=True, metavar="NAME", help="Name of the query to execute")
    p_enq.set_defaults(func=handle_execute_named_query)

    # --- execute-freeform-query ---
    p_efq = subparsers.add_parser(
        "execute-freeform-query",
        help="Execute an ad-hoc YAML query",
        description=(
            "Execute a YAML query pipeline against tickets.\n\n"
            "The query must be a YAML dict with a 'stages' key. Each stage is a list of\n"
            "terms. Stages execute sequentially — results from stage N are passed into\n"
            "stage N+1 as the working set to filter or traverse.\n\n"
            "Example:\n"
            "  stages:\n"
            "    - [type=bee, status=pupa]\n"
            "    - [children]\n\n"
            "Search stages — filter tickets (AND logic within stage):\n"
            "  type=bee | type=t1 | type=t2 ...   exact match on ticket type\n"
            "  status=<value>                      exact match on status\n"
            "  title~<regex>                       regex match on title\n"
            "  tag~<regex>                         regex match on any tag\n"
            "  id=<ticket_id>                      exact match on ticket ID\n"
            "  parent=<ticket_id>                  exact match on parent\n"
            "  guid=<guid>                         exact match on GUID\n"
            "  hive=<name>                         exact match on hive name\n"
            "  hive~<regex>                        regex match on hive name\n\n"
            "Graph stages — traverse relationships from current result set:\n"
            "  parent              get parent of each ticket\n"
            "  children            get children of each ticket\n"
            "  up_dependencies     get upstream blockers of each ticket\n"
            "  down_dependencies   get downstream dependents of each ticket"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_efq.add_argument("--query-yaml", required=True, dest="query_yaml", metavar="YAML", help='YAML dict with a "stages" key. Example: "stages:\\n  - [type=bee, status=pupa]\\n  - [children]"')  # noqa: E501
    p_efq.set_defaults(func=handle_execute_freeform_query)

    # --- delete-named-query ---
    p_dnq = subparsers.add_parser(
        "delete-named-query",
        help="Delete a named query",
        description="Delete a saved named query by name.",
    )
    p_dnq.add_argument("--query-name", required=True, metavar="NAME", help="Name of the query to delete")
    p_dnq.set_defaults(func=handle_delete_named_query)

    # --- list-named-queries ---
    p_lnq = subparsers.add_parser(
        "list-named-queries",
        help="List all saved named queries accessible from this repo",
        description="List all saved named queries accessible from this repo. No arguments required.",
    )
    p_lnq.set_defaults(func=handle_list_named_queries)

    # --- colonize-hive ---
    p_colonize = subparsers.add_parser(
        "colonize-hive",
        help="Create and register a new hive",
        description="Create and register a new hive. A hive is a directory where related tickets are stored.",
    )
    p_colonize.add_argument("--name", required=False, default=None, help='Display name for the hive (e.g. "Back End"). Normalized internally. Optional when a .hive/identity.json marker exists at the target path.')  # noqa: E501
    p_colonize.add_argument("--path", required=True, metavar="PATH", help="Absolute path where the hive will be created. Does not need to exist.")  # noqa: E501
    p_colonize.add_argument("--child-tiers", default=None, dest="child_tiers", metavar="JSON", help='Optional per-hive tier config as JSON dict mapping tier keys to [singular, plural] names. e.g. {"t1": ["Epic","Epics"], "t2": ["Task","Tasks"]}. Pass {} for bees-only. Inherits from global config if omitted.')  # noqa: E501
    p_colonize.add_argument("--scope", default=None, metavar="PATTERN", help="Register this hive under the given scope pattern (e.g. /projects/**) instead of the repo root.")  # noqa: E501
    p_colonize.add_argument("--description", default=None, metavar="TEXT", help="Optional short description of the hive's purpose.")  # noqa: E501
    p_colonize.add_argument("--status-values", default=None, dest="status_values", metavar="JSON", help='Optional JSON array of allowed status strings (e.g. \'["open","in_progress","done"]\'). Pass "null" to explicitly disable status enforcement for this hive. Inherits from scope/global config if omitted.')  # noqa: E501
    p_colonize.add_argument("--allowed-resolvers", default=None, dest="allowed_resolvers", metavar="JSON", help='Optional JSON list of resolver names permitted for this hive (e.g. ["my_resolver","default"]). Each name must exist in the resolver registry or be "default".')  # noqa: E501
    p_colonize.set_defaults(func=handle_colonize_hive)

    # --- list-hives ---
    p_list_hives = subparsers.add_parser(
        "list-hives",
        help="List all registered hives",
        description=(
            "List all registered hives. Each hive entry includes the owning"
            " scope pattern. No arguments required."
        ),
    )
    p_list_hives.set_defaults(func=handle_list_hives)

    # --- abandon-hive ---
    p_abandon = subparsers.add_parser(
        "abandon-hive",
        help="Stop tracking a hive without deleting files",
        description=(
            "Unregister a hive without deleting its files."
            " The hive can be re-registered later with colonize-hive."
        ),
    )
    p_abandon.add_argument("--hive", required=True, metavar="NAME", help="Display name or normalized name of the hive to abandon")  # noqa: E501
    p_abandon.set_defaults(func=handle_abandon_hive)

    # --- rename-hive ---
    p_rename = subparsers.add_parser(
        "rename-hive",
        help="Rename a hive",
        description="Rename a hive and optionally its folder on disk. Ticket IDs are not affected.",
    )
    p_rename.add_argument("--old-name", required=True, metavar="OLD_NAME", help="Current hive name")
    p_rename.add_argument("--new-name", required=True, metavar="NEW_NAME", help="New hive name")
    p_rename.add_argument(
        "--no-rename-folder",
        dest="rename_folder",
        action="store_false",
        default=True,
        help="Skip renaming the folder on disk (only update config and .hive marker)",
    )
    p_rename.add_argument("--description", default=None, metavar="TEXT", help="Optional new description for the hive.")
    p_rename.set_defaults(func=handle_rename_hive)

    # --- sanitize-hive ---
    p_sanitize = subparsers.add_parser(
        "sanitize-hive",
        help="Validate and auto-fix malformed tickets in a hive",
        description=(
            "Validate and auto-fix malformed tickets in a hive."
            " Returns a list of errors it cannot fix automatically."
        ),
    )
    p_sanitize.add_argument("--hive", required=True, metavar="NAME", help="Display name or normalized name of the hive to sanitize")  # noqa: E501
    p_sanitize.set_defaults(func=handle_sanitize_hive)

    # --- generate-index ---
    p_index = subparsers.add_parser(
        "generate-index",
        help="Generate markdown index of tickets",
        description="Generate index.md files for hives. Omit --hive to generate for all hives.",
    )
    p_index.add_argument("--hive", default=None, help="Hive name to generate index for (omit for all hives)")
    p_index.set_defaults(func=handle_generate_index)

    # --- move-bee ---
    p_move = subparsers.add_parser(
        "move-bee",
        help="Move bee tickets to a different hive",
        description=(
            "Move bee tickets to a different hive. Only bee tickets can be moved."
            " Cemetery is never a valid destination — use undertaker instead."
        ),
    )
    p_move.add_argument("--ids", required=True, nargs="+", metavar="ID", help="One or more bee ticket IDs (e.g. b.amx b.x4f)")  # noqa: E501
    p_move.add_argument("--hive", required=True, metavar="HIVE", help="Destination hive name (friendly or normalized)")
    p_move.add_argument("--force", action="store_true", default=False, help="Skip cross-hive compatibility checks (bypass status/tier mismatch errors).")  # noqa: E501
    p_move.set_defaults(func=handle_move_bee)

    # --- clone ---
    p_clone = subparsers.add_parser(
        "clone",
        help="Clone a bee and its entire subtree with fresh IDs",
        description="Clone a bee ticket and its entire subtree. Creates a deep copy with fresh IDs. Cross-references within the cloned tree are remapped to the new IDs; references to tickets outside the tree are copied as-is.",  # noqa: E501
    )
    p_clone.add_argument("--bee-id", required=True, metavar="ID", help="Source bee ticket ID to clone (e.g. b.amx)")
    p_clone.add_argument("--hive", metavar="HIVE", default=None, help="Destination hive name (friendly or normalized). Defaults to source hive.")  # noqa: E501
    p_clone.add_argument("--force", action="store_true", default=False, help="Skip compatibility check when cloning cross-hive.")  # noqa: E501
    p_clone.set_defaults(func=handle_clone_bee)

    # --- undertaker ---
    p_undertaker = subparsers.add_parser(
        "undertaker",
        help="Archive bee tickets matching a query",
        description="Archive bee tickets matching a query into the hive's /cemetery directory. Provide either --query-yaml or --query-name, not both.",  # noqa: E501
    )
    p_undertaker.add_argument("--hive", required=True, metavar="HIVE", help="Hive to operate on")
    undertaker_group = p_undertaker.add_mutually_exclusive_group()
    undertaker_group.add_argument("--query-yaml", default=None, dest="query_yaml", metavar="YAML", help="Ad-hoc YAML query string (run execute-freeform-query -h for syntax) — mutually exclusive with --query-name")  # noqa: E501
    undertaker_group.add_argument("--query-name", default=None, dest="query_name", metavar="NAME", help="Name of a saved named query (run list-named-queries to see available) — mutually exclusive with --query-yaml")  # noqa: E501
    p_undertaker.set_defaults(func=handle_undertaker)

    # --- update-config ---
    p_update_config = subparsers.add_parser(
        "update-config",
        help="Apply pending schema migrations to the global bees config",
        description="Apply all pending schema migrations to the global bees configuration. No arguments required.",
    )
    p_update_config.add_argument("--details", action="store_true", default=False, help="Show pending migrations without applying them")
    p_update_config.set_defaults(func=handle_update_config)

    # --- set-resolver ---
    p_set_resolver = subparsers.add_parser(
        "set-resolver",
        help="Register, update, or remove a named resolver in the global registry",
        description=(
            "Register or update a resolver script under a name in the global registry, "
            "or remove it with --unset. The convention section is extracted automatically "
            "from the script's module docstring."
        ),
    )
    p_set_resolver.add_argument("--name", required=True, help="Resolver name (cannot be 'default')")
    p_set_resolver.add_argument("--path", default=None, metavar="PATH", help="Absolute path to the resolver script (required unless --unset)")  # noqa: E501
    p_set_resolver.add_argument("--timeout", default=None, type=float, metavar="SECONDS", help="Optional timeout in seconds for the resolver")  # noqa: E501
    p_set_resolver.add_argument("--unset", action="store_true", default=False, help="Remove the resolver from the registry")  # noqa: E501
    p_set_resolver.set_defaults(func=handle_set_resolver)

    # --- get-resolvers ---
    p_get_resolvers = subparsers.add_parser(
        "get-resolvers",
        help="List all registered resolvers plus the built-in default",
        description="List all registered resolvers plus the built-in default. No arguments required.",
    )
    p_get_resolvers.set_defaults(func=handle_get_resolvers)

    # --- sting ---
    p_sting = subparsers.add_parser("sting", help="Output bees context for Claude Code sessions")
    p_sting.set_defaults(func=handle_sting)

    # --- setup ---
    p_setup = subparsers.add_parser("setup", help="Configure integrations")
    setup_sub = p_setup.add_subparsers(title="targets", parser_class=BeesArgumentParser)

    # --- setup claude ---
    p_claude = setup_sub.add_parser("claude", help="Configure Claude Code integration")
    claude_sub = p_claude.add_subparsers(title="modes", parser_class=BeesArgumentParser)

    # --- setup claude cli ---
    p_cli_mode = claude_sub.add_parser("cli", help="Install sting hooks only")
    p_cli_mode.add_argument("--remove", action="store_true", default=False, help="Remove hooks")
    p_cli_mode.add_argument("--project", action="store_true", default=False, help="Write to .claude/settings.local.json")  # noqa: E501
    p_cli_mode.set_defaults(func=handle_setup_claude_cli)

    # --- serve ---
    p_serve = subparsers.add_parser("serve", help="Start the MCP server")
    transport_group = p_serve.add_mutually_exclusive_group()
    transport_group.add_argument(
        "--stdio",
        action="store_true",
        default=False,
        help="Run MCP server over stdio transport",
    )
    transport_group.add_argument(
        "--http",
        action="store_true",
        default=False,
        help="Run MCP server over HTTP transport",
    )
    p_serve.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help="Host to bind the HTTP server to (default: 127.0.0.1)",
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="Port to bind the HTTP server to (default: 8000)",
    )
    p_serve.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to bees config file",
    )
    p_serve.add_argument(
        "--test-config",
        nargs="?",
        const="",
        default=None,
        dest="test_config",
        metavar="PATH_OR_JSON",
        help="Run with ephemeral in-memory config (no disk writes). "
             "Accepts a file path, inline JSON starting with '{', or no value for empty config.",
    )
    p_serve.set_defaults(func=handle_serve, serve_parser=p_serve)

    # Register --test-config and --config on every non-serve subparser so that
    # main() can enforce mutual exclusion and activate the override before dispatch.
    _non_serve_parsers = [
        p_create, p_show, p_update, p_delete, p_append_body,
        p_types, p_set_types, p_set_status_values, p_get_status_values,
        p_anq, p_enq, p_efq, p_dnq, p_lnq,
        p_colonize, p_list_hives, p_abandon, p_rename, p_sanitize,
        p_index, p_move, p_clone, p_undertaker, p_update_config, p_set_resolver, p_get_resolvers, p_sting, p_cli_mode,
    ]
    for _p in _non_serve_parsers:
        _p.add_argument("--test-config", nargs="?", const="", default=None, dest="test_config")
        _p.add_argument("--config", default=None)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_usage()
        sys.exit(2)
    # For non-serve subcommands: enforce --test-config/--config mutual exclusion
    # and activate in-memory override before dispatch.
    # serve handles this itself in handle_serve().
    if args.func != handle_serve:
        if getattr(args, "config", None) and getattr(args, "test_config", None) is not None:
            print("Error: --config and --test-config are mutually exclusive.", file=sys.stderr)
            sys.exit(1)
        if getattr(args, "config", None):
            set_config_path(args.config)
        elif getattr(args, "test_config", None) is not None:
            resolved = _resolve_test_config(args.test_config)
            set_test_config_override(resolved)
            logger.info("Test mode active: running with in-memory config, no changes will be persisted")
    args.func(args)


if __name__ == "__main__":
    main()
