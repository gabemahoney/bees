"""
MCP Server for Bees Ticket Management System

Provides FastMCP server infrastructure with tool registration for ticket operations.
This module owns the MCP adapter layer: resolving repo_root from context and
injecting it into the pure core functions.
"""

import logging
from pathlib import Path
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from pydantic import Field

from .config import (  # noqa: F401 - re-exported for test mocking
    check_queen_write_access,
    load_bees_config,
    load_global_config,
)
from .constants import BODY_MAX_LENGTH
from .mcp_clone_bee import _clone_bee
from .mcp_hive_ops import (
    _abandon_hive,
    _colonize_hive,
    _list_hives,
    _rename_hive,
    _sanitize_hive,
    colonize_hive_core,  # noqa: F401 - re-exported
)
from .mcp_hive_utils import scan_for_hive, validate_hive_path  # noqa: F401 - re-exported
from .mcp_index_ops import _generate_index
from .mcp_move_bee import _move_bee
from .mcp_query_ops import (
    _add_named_query,
    _delete_named_query,
    _execute_freeform_query,
    _execute_named_query,
    _list_named_queries,
)
from .mcp_roots import get_client_repo_root, get_repo_root, resolve_repo_root  # noqa: F401 - re-exported
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
from .mcp_resolver_ops import _get_resolvers, _set_resolver
from .mcp_undertaker import _undertaker
from .migrations.runner import run_pending_migrations
from .repo_context import repo_root_context
from .repo_utils import get_repo_root_from_path  # noqa: F401 - re-exported

# Ensure log directory exists
log_dir = Path.home() / ".bees"
log_dir.mkdir(exist_ok=True)

# Configure logging to file for MCP stdio compatibility
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=log_dir / "mcp.log",
    filemode="a",
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    "bees",
    instructions=(
        "IMPORTANT: When this MCP server is available, ALWAYS use these MCP tools "
        "instead of running `bees` CLI commands via Bash. MCP tools return structured "
        "data directly and are the preferred interface for all ticket and hive operations. "
        "Never invoke the `bees` CLI (e.g. `bees show`, `bees list`, `bees update`) when "
        "an equivalent MCP tool exists — use the tool instead."
    ),
)

# Server state
_server_running = False

# Sentinel for __UNSET__ pattern
_UNSET: Literal["__UNSET__"] = "__UNSET__"


def _guard_queen_write(resolved_root: Path) -> dict | None:
    """Return permission_denied error dict if queen lacks write access, else None."""
    return check_queen_write_access(resolved_root, load_global_config())


def _read_file_content(param_name: str, path: str) -> str:
    """Read a file and return its UTF-8 decoded content.

    Args:
        param_name: Name of the parameter (used in error messages, e.g. "body_file").
        path: Absolute or relative path to the file to read.

    Raises:
        ValueError: If path is "-", the file is not found, cannot be read, or
                    is not valid UTF-8, or if the content exceeds BODY_MAX_LENGTH.
    """
    if path == "-":
        raise ValueError(
            f"{param_name} does not support stdin ('-') in MCP context; pass the content inline instead"
        )
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        raise ValueError(f"{param_name} file not found: {path}") from None
    except OSError as exc:
        raise ValueError(f"{param_name} could not read {path}: {exc}") from exc
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{param_name} could not decode {path} as UTF-8: {exc}") from exc
    if len(content) > BODY_MAX_LENGTH:
        raise ValueError(
            f"{param_name} is {len(content)} characters, which exceeds the "
            f"{BODY_MAX_LENGTH} character cap. Use append_ticket_body to write "
            f"large bodies in chunks of up to {BODY_MAX_LENGTH} characters each."
        )
    return content


# ── Server lifecycle ──────────────────────────────────────────────────────────

def start_server() -> dict[str, Any]:
    """
    Start the MCP server.

    Returns:
        dict: Server status information
    """
    global _server_running

    try:
        logger.info("Starting Bees MCP Server...")
        _server_running = True
        logger.info("Bees MCP Server started successfully")

        return {"status": "running", "name": "bees", "version": "0.1.0"}
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        _server_running = False
        raise


def stop_server() -> dict[str, Any]:
    """
    Stop the MCP server.

    Returns:
        dict: Server status information
    """
    global _server_running

    try:
        logger.info("Stopping Bees MCP Server...")
        _server_running = False
        logger.info("Bees MCP Server stopped successfully")

        return {"status": "stopped", "name": "bees"}
    except Exception as e:
        logger.error(f"Failed to stop server: {e}")
        raise


def _health_check() -> dict[str, Any]:
    """
    Check the health status of the MCP server.

    Returns:
        dict: Health status including server state and readiness
    """
    return {
        "status": "healthy" if _server_running else "stopped",
        "server_running": _server_running,
        "name": "bees",
        "version": "0.1.0",
        "ready": _server_running,
    }


# ── Tool registrations (adapter layer) ───────────────────────────────────────

@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check the health status of the MCP server."""
    return _health_check()


@mcp.tool()
async def create_ticket(
    ticket_type: str,
    title: str,
    hive: str,
    body: Annotated[str, Field(max_length=BODY_MAX_LENGTH)] = "",
    body_file: str | None = None,
    parent: str | None = None,
    children: list[str] | None = None,
    up_deps: list[str] | None = None,
    down_deps: list[str] | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    ctx: Context | None = None,
    repo_root: str | None = None,
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None = None,
) -> dict[str, Any]:
    """Create a new ticket in a hive.

    For bodies longer than 10000 characters, create the ticket with a short
    stub body and then loop `append_ticket_body` to add the rest in chunks
    each no larger than 10000 characters. Oversized inline bodies will be
    refused by the input schema (`maxLength=10000` on `body`).

    Args:
        ticket_type: Tier type — "bee" (top-level) or a child tier by ID ("t1", "t2")
                     or friendly name ("Task", "Epic"). Use get_types to see configured tiers.
        title: Short title for the ticket.
        hive: Hive to create the ticket in. Use list_hives to see available hives.
        body: Optional markdown body. Must be at most 10000 characters; for
              longer bodies use a short stub here and loop `append_ticket_body`.
              Mutually exclusive with body_file.
        body_file: Path to a file whose UTF-8 contents are used as the body.
                   Mutually exclusive with body. File must be at most 10000 characters.
        parent: Parent ticket ID. Required for child-tier tickets; omit for bees.
                The parent ticket's children field is updated automatically.
        children: Child ticket IDs to link at creation time. Bidirectional relationship
                  is updated automatically — the child tickets' parent field will be set.
        up_deps: Ticket IDs that must be resolved before this one.
        down_deps: Ticket IDs that this one must be resolved before.
        tags: List of string tags.
        status: Freeform if no status_values are configured for the hive; otherwise must be
                one of the hive's configured values. Required when status_values are configured.
        egg: Tracks external resources related to the ticket (any JSON-compatible value).
             Only supported on bee (t0) tickets.

    """
    if body_file is not None and body != "":
        raise ValueError("body and body_file are mutually exclusive")
    if body_file is not None:
        body = _read_file_content("body_file", body_file)
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _create_ticket(
            ticket_type=ticket_type,
            title=title,
            hive_name=hive,
            body=body,
            parent=parent,
            children=children,
            up_dependencies=up_deps,
            down_dependencies=down_deps,
            tags=tags,
            status=status,
            egg=egg,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def update_ticket(
    ticket_ids: str | list[str],
    title: str | None | Literal["__UNSET__"] = _UNSET,
    body: Annotated[str, Field(max_length=BODY_MAX_LENGTH)] | None | Literal["__UNSET__"] = _UNSET,
    body_file: str | None = None,
    up_deps: list[str] | None = _UNSET,  # type: ignore[assignment]
    down_deps: list[str] | None = _UNSET,  # type: ignore[assignment]
    tags: list[str] | None = _UNSET,  # type: ignore[assignment]
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    status: str | None | Literal["__UNSET__"] = _UNSET,
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None = _UNSET,  # type: ignore[assignment]
    ctx: Context | None = None,
    repo_root: str | None = None,
    hive: str | None = None,
) -> dict[str, Any]:
    """Update one or more existing tickets.

    Supports single update (ticket_ids as str) or batch update (ticket_ids as list[str]).
    Batch mode only allows status, add_tags, and remove_tags — other fields raise ValueError.

    For bodies longer than 10000 characters, update the ticket with a short
    stub body and then loop `append_ticket_body` to add the rest in chunks
    each no larger than 10000 characters. Oversized inline bodies will be
    refused by the input schema (`maxLength=10000` on `body`).

    Args:
        ticket_ids: Ticket ID to update, or list of IDs for batch update.
        title: New title (single mode only).
        body: New markdown body (single mode only). Must be at most 10000
              characters when provided as a string; for longer bodies use a
              short stub here and loop `append_ticket_body`.
              Mutually exclusive with body_file.
        body_file: Path to a file whose UTF-8 contents are used as the body
                   (single mode only). Mutually exclusive with body.
                   File must be at most 10000 characters.
        up_deps: Full replacement list of blocking ticket IDs (single mode only).
        down_deps: Full replacement list of dependent ticket IDs (single mode only).
        tags: Full replacement list of tags (single mode only).
        add_tags: Tags to add (single and batch).
        remove_tags: Tags to remove (single and batch).
        status: New status value (single and batch).
        egg: New egg data (single mode only). Only supported on bee tickets.
        hive: Optional hive name for faster lookup.

    """
    if body_file is not None and body != _UNSET:
        raise ValueError("body and body_file are mutually exclusive")
    if body_file is not None:
        body = _read_file_content("body_file", body_file)
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _update_ticket(
            ticket_ids=ticket_ids,
            title=title,
            body=body,
            up_dependencies=up_deps,
            down_dependencies=down_deps,
            tags=tags,
            add_tags=add_tags,
            remove_tags=remove_tags,
            status=status,
            egg=egg,
            hive_name=hive,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def append_ticket_body(
    ticket_id: str,
    chunk: Annotated[str, Field(max_length=BODY_MAX_LENGTH)] | None = None,
    chunk_file: str | None = None,
    hive: str | None = None,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Append a chunk of text to the end of an existing ticket's body.

    Bodies larger than 10000 characters (Unicode codepoints, not bytes,
    not lines) must be split across calls: first create or update the
    ticket with a short stub body, then loop `append_ticket_body` with
    chunks each no larger than 10000 characters.

    Use this tool to build up a ticket body in multiple calls. Call order
    is preserved exactly as submitted from a single caller: chunks are
    concatenated to the end of the current body in the order you invoke
    this tool, with no separator, no newline, and no framing injected by
    the server. Empty `chunk` is a valid no-op success and is therefore
    safe inside idempotent retry loops. The cap is measured in characters
    (Unicode codepoints), not bytes and not lines.

    Workflow: call `create_ticket` (or `update_ticket`) with a short stub
    body first, then loop `append_ticket_body` with chunks each no larger
    than 10000 characters. Only the `body` field is touched; every other
    frontmatter field (tags, status, guid, created_at, parent, children,
    up_dependencies, down_dependencies, egg) is preserved unchanged.

    Args:
        ticket_id: The ticket whose body is being appended to.
        chunk: The text to append. May be the empty string. Must be at
               most 10000 characters. Mutually exclusive with chunk_file.
        chunk_file: Path to a file whose UTF-8 contents are appended.
                    Mutually exclusive with chunk. File must be at most
                    10000 characters.
        hive: Optional hive name for faster O(1) lookup.
    """
    if chunk is not None and chunk_file is not None:
        raise ValueError("chunk and chunk_file are mutually exclusive")
    if chunk is None and chunk_file is None:
        raise ValueError("Either chunk or chunk_file must be provided")
    if chunk_file is not None:
        chunk = _read_file_content("chunk_file", chunk_file)
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _append_ticket_body(
            ticket_id=ticket_id,
            chunk=chunk,
            hive_name=hive,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def delete_ticket(
    ticket_ids: str | list[str],
    ctx: Context | None = None,
    repo_root: str | None = None,
    hive: str | None = None,
) -> dict[str, Any]:
    """Delete one or more tickets and their child subtrees.

    Supports single delete (ticket_ids as str) or bulk delete (ticket_ids as list[str]).
    Deletion cascades — all child tickets are deleted along with the root.

    Dependency cleanup is controlled by the global config key
    ``delete_with_dependencies`` (boolean, default False).

    Args:
        ticket_ids: Ticket ID to delete, or list of IDs for bulk delete.
        hive: Optional hive name for faster lookup.

    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _delete_ticket(
            ticket_ids=ticket_ids,
            hive_name=hive,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def show_ticket(
    ticket_ids: list[str],
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Retrieve one or more tickets by ID.

    Args:
        ticket_ids: List of ticket IDs to retrieve (e.g., ["b.amx", "b.xyz"]).
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _show_ticket(
            ticket_ids=ticket_ids,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def get_types(
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Shows allowed ticket types for all available hives."""
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _get_types(
            resolved_root=resolved_root,
        )


@mcp.tool()
async def set_types(
    scope: str,
    ctx: Context | None = None,
    repo_root: str | None = None,
    hive: str | None = None,
    child_tiers: dict | None = None,
    unset: bool = False,
) -> dict[str, Any]:
    """Set or unset the ticket tier configuration at a given scope.

    Configures the tier hierarchy (e.g., t1 → t2 → t3) at global,
    repo_scope, or hive level.

    Args:
        scope: Target scope — "global", "repo_scope", or "hive".
        hive: Required when scope="hive".
        child_tiers: Dict mapping tier keys to [singular, plural] names.
                     e.g. {"t1": ["t1", "t1s"], "t2": ["t2", "t2s"]}
                     Pass {} for bees-only (no child tiers). Required unless unset=True.
        unset: If True, removes child_tiers from the target scope.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    if scope == "global":
        return await _set_types(
            scope="global",
            hive_name=None,
            child_tiers=child_tiers,
            unset=unset,
            resolved_root=None,
        )
    else:
        with repo_root_context(resolved_root):
            return await _set_types(
                scope=scope,
                hive_name=hive,
                child_tiers=child_tiers,
                unset=unset,
                resolved_root=resolved_root,
            )


@mcp.tool()
async def set_status_values(
    scope: str,
    ctx: Context | None = None,
    repo_root: str | None = None,
    hive: str | None = None,
    status_values: list[str] | None = None,
    unset: bool = False,
) -> dict[str, Any]:
    """Set or unset the allowed status values at a given scope.

    Configures which status strings are valid for tickets at global, repo_scope,
    or hive level. If no status_values are configured, any string is accepted.

    Args:
        scope: Target scope — "global", "repo_scope", or "hive".
        hive: Required when scope="hive".
        status_values: List of allowed status strings (e.g., ["open", "in_progress", "closed"]).
                       Required unless unset=True.
        unset: If True, removes status_values from the target scope.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    if scope == "global":
        return await _set_status_values(
            scope="global",
            hive_name=None,
            status_values=status_values,
            unset=unset,
            resolved_root=None,
        )
    else:
        with repo_root_context(resolved_root):
            return await _set_status_values(
                scope=scope,
                hive_name=hive,
                status_values=status_values,
                unset=unset,
                resolved_root=resolved_root,
            )


@mcp.tool()
async def get_status_values(
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Get the configured status values at all scope levels (global, repo_scope, and per-hive).

    Shows what is explicitly set at each level. Levels with nothing defined inherit from upper levels.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _get_status_values(
            resolved_root=resolved_root,
        )


@mcp.tool()
async def colonize_hive(
    name: str,
    path: str,
    child_tiers: dict[str, list] | None = None,
    egg_resolver: str | None = None,
    egg_resolver_timeout: int | float | None = None,
    scope: str | None = None,
    description: str | None = None,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Create and register a new hive. A hive is a directory where a group of related tickets are stored.

    Always ask the user for the hive name and path if not explicitly provided.

    Args:
        name: Display name for the hive (e.g., "Back End"). Normalized internally.
        path: Absolute path where the hive will be created. Does not need to exist.
        child_tiers: Optional per-hive tier config. Inherits from scope/global if omitted.
                     Pass {} for bees-only.
        egg_resolver: Optional path to an egg resolver script for this hive.
        egg_resolver_timeout: Optional timeout in seconds for the egg resolver script.
        scope: Optional scope pattern to register the hive under (e.g. /projects/**).
               When provided, the hive is placed under this explicit scope instead of
               the auto-detected scope for the repo root.
        description: Optional short description of the hive's purpose.
    """
    # Special colonize_hive fallback logic:
    # 1. Try MCP Roots protocol via get_repo_root(ctx)
    # 2. If roots succeeds, validate the hive path is within that repo
    # 3. If hive path is outside detected repo, fall back to path-based detection
    # 4. If roots fails entirely, use path-based detection
    hive_path = Path(path)
    resolved_root = None

    if ctx:
        try:
            roots_root = await get_repo_root(ctx)
            if roots_root:
                logger.info(f"colonize_hive adapter: Got repo root from MCP context: {roots_root}")
                # Verify the hive path is within the detected repo root
                try:
                    hive_path.resolve(strict=False).relative_to(roots_root.resolve())
                    resolved_root = roots_root
                except ValueError:
                    # Hive path is outside detected repo root — use hive path
                    logger.warning(
                        f"colonize_hive adapter: Hive path {hive_path} outside repo root {roots_root}, "
                        "using hive path"
                    )
                    resolved_root = get_repo_root_from_path(hive_path)
            else:
                logger.warning("colonize_hive adapter: Roots protocol unavailable, using hive path")
                resolved_root = get_repo_root_from_path(hive_path)
        except Exception:
            resolved_root = get_repo_root_from_path(hive_path)
    elif repo_root:
        resolved_root = Path(repo_root)
    else:
        resolved_root = get_repo_root_from_path(hive_path)

    if err := _guard_queen_write(resolved_root):
        return err

    return await _colonize_hive(
        name=name,
        path=path,
        child_tiers=child_tiers,
        repo_root=resolved_root,
        egg_resolver=egg_resolver,
        egg_resolver_timeout=egg_resolver_timeout,
        scope=scope,
        description=description,
    )


@mcp.tool()
async def list_hives(
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """List all available hives.

    Returns a merged union of hives from all matching scopes. Each hive entry
    includes a 'scope' field with the owning scope pattern.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _list_hives(resolved_root=resolved_root)


@mcp.tool()
async def abandon_hive(
    hive: str,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Stop tracking a hive without deleting its ticket files.

    Removes the hive from the registry but leaves all files intact on disk.
    The hive can be re-registered later with colonize_hive.

    Args:
        hive: Display name or normalized name of the hive to abandon.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _abandon_hive(hive_name=hive, resolved_root=resolved_root)


@mcp.tool()
async def rename_hive(
    old_name: str,
    new_name: str,
    rename_folder: bool = True,
    description: str | None = None,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Rename a hive and optionally its folder on disk. Ticket IDs are not affected.

    Args:
        old_name: Current hive name.
        new_name: New hive name.
        rename_folder: If True (default), also renames the folder on disk to match the new normalized hive name.
        description: Optional new description for the hive.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _rename_hive(
            old_name=old_name, new_name=new_name, resolved_root=resolved_root, rename_folder=rename_folder,
            description=description,
        )


@mcp.tool()
async def sanitize_hive(
    hive: str,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Validate and auto-fix malformed tickets in a hive.

    Returns a list of errors it cannot fix automatically — these will need to be
    resolved by you or the user.

    Args:
        hive: Display name or normalized name of the hive to sanitize.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _sanitize_hive(hive_name=hive, resolved_root=resolved_root)


@mcp.tool()
async def add_named_query(
    name: str,
    query_yaml: str,
    scope: str = "global",
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Register a named query for reuse. See execute_freeform_query for query syntax.

    The query YAML may include an optional "report" key (list of field names).
    When present, execute_named_query will return "tickets" (list of dicts)
    instead of "ticket_ids" (list of strings). See execute_freeform_query for
    valid report fields and excluded fields.

    Args:
        name: Name for the query (used to execute it later).
        query_yaml: YAML dict with a "stages" key and optional "report" key.
                    Example: "stages:\\n  - [type=bee, status=pupa]\\n  - [children]"
                    With report: "stages:\\n  - [status=worker]\\nreport: [title, ticket_status]"
        scope: Where to store the query — "global" (all repos) or "repo" (current repo only).
               Defaults to "global".
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return _add_named_query(name=name, query_yaml=query_yaml, scope=scope, resolved_root=resolved_root)


@mcp.tool()
async def execute_named_query(
    query_name: str,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Execute a registered named query by name.

    Queries are registered with add_named_query and stored as a dict with a
    "stages" key (and optional "report" key). See execute_freeform_query for
    the full query syntax and report projection reference.

    If the named query was registered with a "report" key, the response
    includes "tickets" (list of dicts). Otherwise it includes "ticket_ids"
    (list of strings).

    Args:
        query_name: Name of the query to execute.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _execute_named_query(
            query_name=query_name,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def execute_freeform_query(
    query_yaml: str,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Execute a YAML query pipeline without saving it.

    The query must be a YAML dict with a "stages" key. Each stage is a list of
    terms. Stages execute sequentially — results from stage N are passed into
    stage N+1 as the working set to filter or traverse.

    Example:
        stages:
          - [type=bee, status=pupa]
          - [children]

    Search stages — filter tickets (AND logic within stage):
        type=bee | type=t1 | type=t2 ...   exact match on ticket type
        status=<value>                      exact match on status
        title~<regex>                       regex match on title
        tag~<regex>                         regex match on any tag
        id=<ticket_id>                      exact match on ticket ID
        parent=<ticket_id>                  exact match on parent
        guid=<guid>                         exact match on GUID
        hive=<name>                         exact match on hive name
        hive~<regex>                        regex match on hive name

    Graph stages — traverse relationships from current result set:
        parent              get parent of each ticket
        children            get children of each ticket
        up_dependencies     get upstream blockers of each ticket
        down_dependencies   get downstream dependents of each ticket

    Report projection (optional):
        Add a "report" key with a list of field names to return structured
        ticket data instead of a plain ID list. ticket_id is always included
        automatically and should not be listed.

        Valid fields: ticket_type, ticket_status, title, tags, parent,
            children, up_dependencies, down_dependencies, created_at,
            schema_version, guid, hive

        Excluded fields:
            body, egg    — not available in query results; use show_ticket

        Example:
            stages:
              - [status=worker]
            report: [title, ticket_status]

        Without report → response includes "ticket_ids" (list of strings).
        With report    → response includes "tickets" (list of dicts, one per
                         match, sorted by ticket_id, null values included).

    Args:
        query_yaml: YAML dict with a "stages" key containing a list of stages.
                    Example: "stages:\\n  - [type=bee, status=pupa]\\n  - [children]"
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _execute_freeform_query(
            query_yaml=query_yaml,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def delete_named_query(
    name: str,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Delete a named query by name. Searches all scopes (global first, then repo).

    Args:
        name: Name of the query to delete
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return _delete_named_query(name=name, resolved_root=resolved_root)


@mcp.tool()
async def list_named_queries(
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """List named queries accessible from the current repo scope and global."""
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return _list_named_queries(resolved_root=resolved_root)


@mcp.tool()
async def generate_index(
    hive: str | None = None,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Generate index.md pages for hives.

    Args:
        hive: Optional hive name. If omitted, generates for all hives.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _generate_index(
            hive_name=hive,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def undertaker(
    hive: str,
    query_yaml: str | None = None,
    query_name: str | None = None,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Archive bee tickets matching a query into the hive's /cemetery directory.

    Args:
        hive: Hive to operate on (required)
        query_yaml: YAML string for freeform query (mutually exclusive with query_name)
        query_name: Name of a registered query (mutually exclusive with query_yaml)

    To schedule automatic archiving, add an undertaker_schedule block to the hive
    in ~/.bees/config.json:
        {
            "hives": {
                "example_hive": {
                    "undertaker_schedule": {
                        "interval_seconds": 60,
                        "query_yaml": "stages:\\n  - ['status=finished']"
                    }
                }
            }
        }
    Use query_name instead of query_yaml to reference a named query.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _undertaker(
            hive_name=hive,
            query_yaml=query_yaml,
            query_name=query_name,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def move_bee(
    bee_ids: list[str],
    hive: str,
    force: bool = False,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Move bee tickets to a different hive.

    Only bee tickets can be moved. Cemetery is never a valid destination — use undertaker instead.

    Args:
        bee_ids: Bee ticket IDs to move (e.g., ["b.amx", "b.x4f"]).
        hive: Friendly or normalized name of the destination hive (e.g., "Back End" or "back_end").
        force: When True, skip cross-hive compatibility checks (bypass status/tier mismatch errors).

    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _move_bee(
            bee_ids=bee_ids,
            destination_hive=hive,
            force=force,
            resolved_root=resolved_root,
        )


@mcp.tool()
async def clone_bee(
    bee_id: str,
    hive: str | None = None,
    force: bool = False,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Clone a bee ticket and its entire subtree.

    Creates a deep copy with fresh IDs. Cross-references within the cloned
    tree are remapped to the new IDs; references to tickets outside the
    tree are copied as-is.

    Args:
        bee_id: Bee ticket ID to clone (e.g. b.amx, b. prefix required).
        hive: Destination hive name. Defaults to source hive.
        force: Skip compatibility check for cross-hive clones.

    Returns:
        {"status": "success", "ticket_id": "<new-id>", "written": N, "failed": [...]}
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    if err := _guard_queen_write(resolved_root):
        return err
    with repo_root_context(resolved_root):
        return await _clone_bee(
            bee_id=bee_id,
            destination_hive=hive,
            force=force,
            resolved_root=resolved_root,
        )


@mcp.tool()
def set_resolver(
    name: str,
    path: str | None = None,
    timeout: float | None = None,
    unset: bool = False,
) -> dict[str, Any]:
    """Register, update, or remove a named resolver in the global registry.

    In register/update mode (unset=False): registers the script at *path* under
    *name*, extracting the RESOLVER CONVENTION section from its module docstring
    automatically. The *path* must exist on disk.

    In unset mode (unset=True): removes *name* from the registry. Fails if the
    resolver is still referenced by any hive's allowed_resolvers.

    The name "default" is reserved and cannot be used.

    Args:
        name: Resolver name. Cannot be "default".
        path: Absolute path to the resolver script. Required unless unset=True.
        timeout: Optional timeout in seconds for this resolver.
        unset: If True, remove the resolver instead of registering/updating it.
    """
    return _set_resolver(name=name, path=path, timeout=timeout, unset=unset)


@mcp.tool()
def get_resolvers() -> dict[str, Any]:
    """Return all registered resolvers plus the built-in default.

    Each entry includes: name, path, timeout, convention, built_in.
    The "default" entry (built_in=True) is always first and represents the
    inline resolver used when no custom resolver is configured for a hive.
    """
    return _get_resolvers()


@mcp.tool()
def update_config() -> dict[str, Any]:
    """Apply pending schema migrations to the global bees configuration.

    IMPORTANT: Before calling this tool, you MUST ask the user for explicit
    confirmation. This tool modifies the global bees configuration. It is safe
    to run when migrations are already up to date (it will be a no-op), but
    it writes to disk and should not be called without user awareness.

    Applies all pending migration hops from the migration manifest to the
    global config file (~/.bees/config.json), persisting schema_version after
    each successful hop so that partial failures leave the config at the last
    successfully applied version.

    No repo_root or hive context is required — this operates on the global
    bees config only.

    Returns:
        On success with no pending migrations:
            {"status": "success", "message": "Already up to date", "version": "<current>"}
        On success with applied migrations:
            {"status": "success", "message": "Applied N migration(s)",
             "applied_hops": [{"from_version": "...", "to_version": "..."}],
             "final_version": "<new_version>"}
    """
    return run_pending_migrations()


if __name__ == "__main__":
    logger.info("Running Bees MCP Server directly")
    start_server()
    mcp.run()
