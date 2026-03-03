"""
MCP Server for Bees Ticket Management System

Provides FastMCP server infrastructure with tool registration for ticket operations.
This module owns the MCP adapter layer: resolving repo_root from context and
injecting it into the pure core functions.
"""

import logging
from pathlib import Path
from typing import Any, Literal

from fastmcp import Context, FastMCP

from .config import load_bees_config  # noqa: F401 - re-exported for test mocking
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
    description: str = "",
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

    Args:
        ticket_type: Tier type — "bee" (top-level) or a child tier by ID ("t1", "t2")
                     or friendly name ("Task", "Epic"). Use get_types to see configured tiers.
        title: Short title for the ticket.
        hive: Hive to create the ticket in. Use list_hives to see available hives.
        description: Optional markdown body.
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
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _create_ticket(
            ticket_type=ticket_type,
            title=title,
            hive_name=hive,
            description=description,
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
    ticket_id: str | list[str],
    title: str | None | Literal["__UNSET__"] = _UNSET,
    description: str | None | Literal["__UNSET__"] = _UNSET,
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

    Supports single update (ticket_id as str) or batch update (ticket_id as list[str]).
    Batch mode only allows status, add_tags, and remove_tags — other fields raise ValueError.

    Args:
        ticket_id: Ticket ID to update, or list of IDs for batch update.
        title: New title (single mode only).
        description: New markdown body (single mode only).
        up_deps: Full replacement list of blocking ticket IDs (single mode only).
        down_deps: Full replacement list of dependent ticket IDs (single mode only).
        tags: Full replacement list of tags (single mode only).
        add_tags: Tags to add (single and batch).
        remove_tags: Tags to remove (single and batch).
        status: New status value (single and batch).
        egg: New egg data (single mode only). Only supported on bee tickets.
        hive: Optional hive name for faster lookup.

    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _update_ticket(
            ticket_id=ticket_id,
            title=title,
            description=description,
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
    if scope == "global":
        return await _set_types(
            scope="global",
            hive_name=None,
            child_tiers=child_tiers,
            unset=unset,
            resolved_root=None,
        )
    else:
        if ctx:
            resolved_root = await resolve_repo_root(ctx, repo_root)
        else:
            resolved_root = get_repo_root_from_path(Path.cwd())
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
    if scope == "global":
        return await _set_status_values(
            scope="global",
            hive_name=None,
            status_values=status_values,
            unset=unset,
            resolved_root=None,
        )
    else:
        if ctx:
            resolved_root = await resolve_repo_root(ctx, repo_root)
        else:
            resolved_root = get_repo_root_from_path(Path.cwd())
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

    return await _colonize_hive(
        name=name,
        path=path,
        child_tiers=child_tiers,
        repo_root=resolved_root,
        egg_resolver=egg_resolver,
        egg_resolver_timeout=egg_resolver_timeout,
    )


@mcp.tool()
async def list_hives(
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """List all available hives."""
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
    with repo_root_context(resolved_root):
        return await _abandon_hive(hive_name=hive, resolved_root=resolved_root)


@mcp.tool()
async def rename_hive(
    old_name: str,
    new_name: str,
    rename_folder: bool = True,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Rename a hive and optionally its folder on disk. Ticket IDs are not affected.

    Args:
        old_name: Current hive name.
        new_name: New hive name.
        rename_folder: If True (default), also renames the folder on disk to match the new normalized hive name.
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return await _rename_hive(
            old_name=old_name, new_name=new_name, resolved_root=resolved_root, rename_folder=rename_folder
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

    Args:
        name: Name for the query (used to execute it later).
        query_yaml: YAML string representing the query pipeline.
        scope: Where to store the query — "global" (all repos) or "repo" (current repo only).
               Defaults to "global".
    """
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    with repo_root_context(resolved_root):
        return _add_named_query(name=name, query_yaml=query_yaml, scope=scope, resolved_root=resolved_root)


@mcp.tool()
async def execute_named_query(
    query_name: str,
    ctx: Context | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Execute a registered named query.

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
    """Execute a YAML query pipeline.

    Each stage is a list of terms. Stages execute sequentially — results from
    stage N are passed into stage N+1 as the working set to filter or traverse.

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

    Args:
        query_yaml: YAML string — a list of stages, each stage a list of terms.
                    Example: "- [type=bee, status=open]\\n- [children]"
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
                        "query_yaml": "- ['status=finished']"
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
    with repo_root_context(resolved_root):
        return await _clone_bee(
            bee_id=bee_id,
            destination_hive=hive,
            force=force,
            resolved_root=resolved_root,
        )


if __name__ == "__main__":
    logger.info("Running Bees MCP Server directly")
    start_server()
    mcp.run()
