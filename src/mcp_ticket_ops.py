"""
Ticket CRUD Operations for Bees MCP Server

This module contains the core ticket create, read, update, and delete operations
extracted from mcp_server.py. These functions handle:
- Ticket creation (_create_ticket)
- Ticket updates (_update_ticket)
- Ticket deletion (_delete_ticket)
- Ticket retrieval (_show_ticket)

All operations include validation, error handling, and bidirectional relationship sync.
"""

import logging
import re
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal
from fastmcp import Context

from .ticket_factory import create_epic, create_task, create_subtask
from .reader import read_ticket
from .writer import write_ticket_file
from .paths import infer_ticket_type_from_id, get_ticket_path
from .config import load_bees_config
from .id_utils import normalize_hive_name
from .mcp_id_utils import parse_hive_from_ticket_id
from .mcp_repo_utils import get_repo_root_from_path, get_repo_root
from .mcp_relationships import (
    _update_bidirectional_relationships,
    _add_child_to_parent,
    _remove_child_from_parent,
    _set_parent_on_child,
    _remove_parent_from_child,
    _add_to_down_dependencies,
    _remove_from_down_dependencies,
    _add_to_up_dependencies,
    _remove_from_up_dependencies
)

# Logger
logger = logging.getLogger(__name__)

# Sentinel value for unset optional parameters
_UNSET: Literal["__UNSET__"] = "__UNSET__"


async def _create_ticket(
    ticket_type: str,
    title: str,
    hive_name: str,
    description: str = "",
    parent: str | None = None,
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    labels: list[str] | None = None,
    owner: str | None = None,
    priority: int | None = None,
    status: str | None = None,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Create a new ticket (epic, task, or subtask).

    Args:
        ticket_type: Type of ticket to create - must be 'epic', 'task', or 'subtask'
        title: Title of the ticket (required)
        hive_name: Hive name to prefix the ID with (required, e.g., "backend" -> "backend.bees-abc")
        description: Detailed description of the ticket
        parent: Parent ticket ID (required for subtasks, optional for tasks, not allowed for epics)
        children: List of child ticket IDs
        up_dependencies: List of ticket IDs that this ticket depends on (blocking tickets)
        down_dependencies: List of ticket IDs that depend on this ticket
        labels: List of label strings
        owner: Owner/assignee of the ticket
        priority: Priority level (typically 0-4)
        status: Status of the ticket (e.g., 'open', 'in_progress', 'completed')
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Created ticket information including ticket_id

    Raises:
        ValueError: If ticket_type is invalid or validation fails
    """
    # Validate ticket_type
    if ticket_type not in ["epic", "task", "subtask"]:
        error_msg = f"Invalid ticket_type: {ticket_type}. Must be 'epic', 'task', or 'subtask'"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate title is not empty
    if not title or not title.strip():
        error_msg = "Ticket title cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive_name (required parameter)
    if not hive_name or not hive_name.strip():
        error_msg = "hive_name is required and cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if hive_name contains at least one alphanumeric character
    if not re.search(r'[a-zA-Z0-9]', hive_name):
        error_msg = f"Invalid hive_name: '{hive_name}'. Hive name must contain at least one alphanumeric character"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive exists in config
    # Design Decision: create_ticket is STRICT and does not attempt hive recovery via scan_for_hive.
    # Rationale:
    #   - Write operations (create/update/delete) should be explicit and fail fast
    #   - Consistency: update_ticket and delete_ticket also fail fast without recovery attempts
    #   - scan_for_hive is a recovery mechanism for read operations, not normal write flows
    #   - Creating tickets requires explicit hive specification to avoid ambiguity
    # See docs/architecture/ for full architectural rationale
    normalized_hive = normalize_hive_name(hive_name)

    # Get client's repo root from MCP context
    if ctx:
        repo_root = await get_repo_root(ctx)
        if not repo_root:
            # Roots protocol unavailable - cannot determine client repo
            error_msg = (
                "Cannot determine client repository root - MCP roots protocol unavailable. "
                "The bees MCP server cannot fall back to server's working directory since it "
                "runs in a different repository than the client. Please ensure your MCP client "
                "supports the roots protocol (list_roots)."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.info(f"create_ticket: Using repo root from MCP context: {repo_root}")
    else:
        # Non-MCP call (tests, CLI)
        repo_root = get_repo_root_from_path(Path.cwd())
        logger.info(f"create_ticket: Using repo root from cwd: {repo_root}")

    config = load_bees_config(repo_root)
    config_path = repo_root / '.bees/config.json'
    logger.info(f"create_ticket: Loaded config from {config_path}")
    logger.info(f"create_ticket: Config exists: {config_path.exists()}")
    logger.info(f"create_ticket: Config hives: {list(config.hives.keys()) if config else 'None'}")
    logger.info(f"create_ticket: Looking for hive: '{normalized_hive}'")

    if not config or normalized_hive not in config.hives:
        # Provide helpful error message guiding users to create hive first
        # Note: We intentionally do NOT attempt recovery via scan_for_hive (see design decision above)
        config_path = repo_root / '.bees/config.json'
        available_hives = list(config.hives.keys()) if config else []

        # Enhanced error message to help diagnose MCP context issues
        cwd = Path.cwd()
        error_msg = (
            f"Hive '{hive_name}' (normalized: '{normalized_hive}') not found in config.\n"
            f"  Repo root (from MCP context): {repo_root}\n"
            f"  Config path: {config_path}\n"
            f"  MCP server cwd: {cwd}\n"
            f"  Available hives in this config: {available_hives}\n"
        )

        # If MCP server cwd != repo_root, this may indicate a context issue
        if ctx and cwd != repo_root:
            # Check if there's a config in cwd that has the hive
            cwd_config_path = cwd / '.bees/config.json'
            if cwd_config_path.exists():
                cwd_config = load_bees_config(cwd)
                if cwd_config:
                    error_msg += (
                        f"\n"
                        f"NOTE: MCP server is running from {cwd} but detected client repo at {repo_root}.\n"
                        f"  Config also found at: {cwd_config_path}\n"
                        f"  Hives in MCP server repo: {list(cwd_config.hives.keys())}\n"
                        f"\n"
                        f"This suggests a possible MCP context issue where the client repo root\n"
                        f"was not correctly detected. The hive may have been created in a different repo.\n"
                    )

        error_msg += (
            f"\n"
            f"Please create the hive first using colonize_hive in the correct repository.\n"
            f"If the hive directory exists but isn't registered, run colonize_hive to register it."
        )

        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive path exists and is writable
    hive_path = Path(config.hives[normalized_hive].path)

    # Resolve symlinks to get the actual path
    try:
        resolved_path = hive_path.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        error_msg = f"Failed to resolve hive path '{hive_path}': {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if path exists
    if not resolved_path.exists():
        error_msg = f"Hive path does not exist: '{resolved_path}'. Please create the directory before creating tickets."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if path is a directory
    if not resolved_path.is_dir():
        error_msg = f"Hive path is not a directory: '{resolved_path}'. Path must be a directory, not a file."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Test write permissions by attempting to create and remove a test file
    test_file = resolved_path / f".write_test_{uuid.uuid4().hex[:8]}"
    try:
        test_file.touch()
        test_file.unlink()
    except PermissionError as e:
        error_msg = f"Hive directory is not writable: '{resolved_path}'. Please check directory permissions."
        logger.error(error_msg)
        raise ValueError(error_msg)
    except OSError as e:
        error_msg = f"Failed to write to hive directory '{resolved_path}': {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate parent requirements
    if ticket_type == "epic" and parent:
        error_msg = "Epics cannot have a parent"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if ticket_type == "subtask" and not parent:
        error_msg = "Subtasks must have a parent"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate parent ticket exists
    if parent:
        parent_type = infer_ticket_type_from_id(parent)
        if not parent_type:
            error_msg = f"Parent ticket does not exist: {parent}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Validate dependency tickets exist
    if up_dependencies:
        for dep_id in up_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if down_dependencies:
        for dep_id in down_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Validate children tickets exist
    if children:
        for child_id in children:
            child_type = infer_ticket_type_from_id(child_id)
            if not child_type:
                error_msg = f"Child ticket does not exist: {child_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Check for circular dependencies
    if up_dependencies and down_dependencies:
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            error_msg = f"Circular dependency detected: ticket cannot both depend on and be depended on by the same tickets: {circular_deps}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Call appropriate factory function based on ticket type
    try:
        if ticket_type == "epic":
            ticket_id = create_epic(
                title=title,
                description=description,
                labels=labels,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                owner=owner,
                priority=priority,
                status=status or "open",
                hive_name=hive_name,
                repo_root=repo_root
            )
        elif ticket_type == "task":
            ticket_id = create_task(
                title=title,
                description=description,
                parent=parent,
                labels=labels,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                owner=owner,
                priority=priority,
                status=status or "open",
                hive_name=hive_name,
                repo_root=repo_root
            )
        elif ticket_type == "subtask":
            # Type checker: parent is guaranteed to be str due to validation at line 236-239
            assert parent is not None, "Subtask parent validated above"
            ticket_id = create_subtask(
                title=title,
                parent=parent,
                description=description,
                labels=labels,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                owner=owner,
                priority=priority,
                status=status or "open",
                hive_name=hive_name,
                repo_root=repo_root
            )
        else:
            # Should never reach here due to earlier validation
            raise ValueError(f"Invalid ticket_type: {ticket_type}")

        logger.info(f"Successfully created {ticket_type} ticket: {ticket_id}")

        # Update bidirectional relationships in related tickets
        _update_bidirectional_relationships(
            new_ticket_id=ticket_id,
            parent=parent,
            children=children,
            up_dependencies=up_dependencies,
            down_dependencies=down_dependencies
        )

        return {
            "status": "success",
            "ticket_id": ticket_id,
            "ticket_type": ticket_type,
            "title": title
        }

    except Exception as e:
        logger.error(f"Failed to create {ticket_type} ticket: {e}")
        raise


async def _update_ticket(
    ticket_id: str,
    title: str | None | Literal["__UNSET__"] = _UNSET,
    description: str | None | Literal["__UNSET__"] = _UNSET,
    parent: str | None | Literal["__UNSET__"] = _UNSET,
    children: list[str] | None | Literal["__UNSET__"] = _UNSET,
    up_dependencies: list[str] | None | Literal["__UNSET__"] = _UNSET,
    down_dependencies: list[str] | None | Literal["__UNSET__"] = _UNSET,
    labels: list[str] | None | Literal["__UNSET__"] = _UNSET,
    owner: str | None | Literal["__UNSET__"] = _UNSET,
    priority: int | None | Literal["__UNSET__"] = _UNSET,
    status: str | None | Literal["__UNSET__"] = _UNSET,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Update an existing ticket.

    Args:
        ticket_id: ID of the ticket to update (required)
        title: New title for the ticket
        description: New description for the ticket
        parent: New parent ticket ID (or None to remove parent)
        children: New list of child ticket IDs
        up_dependencies: New list of blocking dependency ticket IDs
        down_dependencies: New list of dependent ticket IDs
        labels: New list of labels
        owner: New owner/assignee
        priority: New priority level
        status: New status
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Updated ticket information

    Raises:
        ValueError: If ticket_id doesn't exist or validation fails

    Note:
        When updating relationships (parent, children, dependencies), the change
        is automatically reflected bidirectionally in related tickets.
    """
    # Parse hive from ticket_id
    hive_prefix = parse_hive_from_ticket_id(ticket_id)

    # Return error if hive prefix is None (malformed ID)
    if hive_prefix is None:
        error_msg = f"Malformed ticket ID: '{ticket_id}'. Expected format: hive_name.bees-xxxx"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive exists in config using normalize_name for lookup
    normalized_hive = normalize_hive_name(hive_prefix)
    config = load_bees_config()
    if not config or normalized_hive not in config.hives:
        error_msg = f"Unknown hive: '{hive_prefix}' (normalized: '{normalized_hive}'). Hive not found in config."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate ticket exists
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        error_msg = f"Ticket does not exist: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Read existing ticket
    ticket_path = get_ticket_path(ticket_id, ticket_type)
    try:
        ticket = read_ticket(ticket_path)
    except FileNotFoundError:
        error_msg = f"Ticket file not found: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to read ticket {ticket_id}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate relationship ticket IDs exist
    if parent is not _UNSET and parent:  # Check if parent is provided and not empty/None
        parent_type = infer_ticket_type_from_id(parent)
        if not parent_type:
            error_msg = f"Parent ticket does not exist: {parent}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    if children is not _UNSET and children is not None:
        for child_id in children:
            child_type = infer_ticket_type_from_id(child_id)
            if not child_type:
                error_msg = f"Child ticket does not exist: {child_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if up_dependencies is not _UNSET and up_dependencies is not None:
        for dep_id in up_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if down_dependencies is not _UNSET and down_dependencies is not None:
        for dep_id in down_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Check for circular dependencies if both up and down are being updated
    if (up_dependencies is not _UNSET and up_dependencies is not None and
        down_dependencies is not _UNSET and down_dependencies is not None):
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            error_msg = f"Circular dependency detected: ticket cannot both depend on and be depended on by the same tickets: {circular_deps}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Update basic fields (non-relationship fields)
    if title is not _UNSET:
        if title is None or not title.strip():
            error_msg = "Ticket title cannot be empty"
            logger.error(error_msg)
            raise ValueError(error_msg)
        ticket.title = title

    if description is not _UNSET:
        # description can be None or empty string
        ticket.description = description if description else ""

    if labels is not _UNSET:
        # labels can be None (which means empty list)
        assert labels != _UNSET  # Type narrowing
        ticket.labels = labels if labels is not None else []

    if owner is not _UNSET:
        ticket.owner = owner  # type: ignore[assignment]

    if priority is not _UNSET:
        assert priority != _UNSET  # Type narrowing
        ticket.priority = priority

    if status is not _UNSET:
        ticket.status = status  # type: ignore[assignment]

    # Handle relationship updates with bidirectional consistency
    # Track old relationships to determine what changed
    old_parent = ticket.parent
    old_children = set(ticket.children or [])
    old_up_deps = set(ticket.up_dependencies or [])
    old_down_deps = set(ticket.down_dependencies or [])

    # Update relationship fields if provided
    if parent is not _UNSET:
        ticket.parent = parent if parent else None  # type: ignore[assignment]
    if children is not _UNSET:
        assert children != _UNSET  # Type narrowing
        ticket.children = children if children is not None else []
    if up_dependencies is not _UNSET:
        assert up_dependencies != _UNSET  # Type narrowing
        ticket.up_dependencies = up_dependencies if up_dependencies is not None else []
    if down_dependencies is not _UNSET:
        assert down_dependencies != _UNSET  # Type narrowing
        ticket.down_dependencies = down_dependencies if down_dependencies is not None else []

    # Update timestamp
    ticket.updated_at = datetime.now()

    # Write updated ticket
    frontmatter_data = asdict(ticket)
    write_ticket_file(
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        frontmatter_data=frontmatter_data,
        body=ticket.description or ""
    )

    # Sync bidirectional relationships
    new_parent = ticket.parent
    new_children = set(ticket.children or [])
    new_up_deps = set(ticket.up_dependencies or [])
    new_down_deps = set(ticket.down_dependencies or [])

    # Handle parent changes
    if parent is not _UNSET:
        # Remove from old parent's children
        if old_parent and old_parent != new_parent:
            _remove_child_from_parent(ticket_id, old_parent)

        # Add to new parent's children
        if new_parent:
            _add_child_to_parent(ticket_id, new_parent)

    # Handle children changes
    if children is not _UNSET:
        removed_children = old_children - new_children
        added_children = new_children - old_children

        for child_id in removed_children:
            _remove_parent_from_child(child_id)

        for child_id in added_children:
            _set_parent_on_child(ticket_id, child_id)

    # Handle up_dependencies changes
    if up_dependencies is not _UNSET:
        removed_up = old_up_deps - new_up_deps
        added_up = new_up_deps - old_up_deps

        for dep_id in removed_up:
            _remove_from_down_dependencies(ticket_id, dep_id)

        for dep_id in added_up:
            _add_to_down_dependencies(ticket_id, dep_id)

    # Handle down_dependencies changes
    if down_dependencies is not _UNSET:
        removed_down = old_down_deps - new_down_deps
        added_down = new_down_deps - old_down_deps

        for dep_id in removed_down:
            _remove_from_up_dependencies(ticket_id, dep_id)

        for dep_id in added_down:
            _add_to_up_dependencies(ticket_id, dep_id)

    logger.info(f"Successfully updated ticket: {ticket_id}")

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "ticket_type": ticket_type,
        "title": ticket.title
    }


async def _delete_ticket(
    ticket_id: str,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Delete a ticket and clean up relationships in related tickets.

    Deletion always cascades to children - deleting a parent ticket will
    recursively delete all child tickets and grandchildren in the entire subtree.

    Args:
        ticket_id: ID of the ticket to delete (required)
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Deletion status and information about cleaned relationships

    Raises:
        ValueError: If ticket_id doesn't exist or deletion validation fails

    Note:
        When a ticket is deleted:
        - It's removed from parent's children array
        - It's removed from all dependency arrays in related tickets
        - All child tickets are recursively deleted (cascade behavior)
        - The entire subtree under this ticket is deleted
    """
    # Parse hive from ticket_id
    hive_prefix = parse_hive_from_ticket_id(ticket_id)

    # Return error if hive prefix is None (malformed ID)
    if hive_prefix is None:
        error_msg = f"Malformed ticket ID: '{ticket_id}'. Expected format: hive_name.bees-xxxx"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive exists in config using normalize_name for lookup
    normalized_hive = normalize_hive_name(hive_prefix)

    # Get repo root
    if ctx:
        repo_root = await get_repo_root(ctx)
        if not repo_root:
            raise ValueError("Cannot determine client repository root - MCP roots protocol unavailable")
    else:
        repo_root = get_repo_root_from_path(Path.cwd())

    config = load_bees_config(repo_root)
    if not config or normalized_hive not in config.hives:
        error_msg = f"Hive '{hive_prefix}' not found in configuration"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate ticket exists
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        error_msg = f"Ticket does not exist: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Read ticket to get relationships
    ticket_path = get_ticket_path(ticket_id, ticket_type)
    try:
        ticket = read_ticket(ticket_path)
    except FileNotFoundError:
        error_msg = f"Ticket file not found: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to read ticket {ticket_id}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Recursively delete all child tickets (always cascade)
    if ticket.children:
        for child_id in ticket.children:
            try:
                await _delete_ticket(child_id, ctx)
                logger.info(f"Cascade deleted child ticket: {child_id}")
            except Exception as e:
                logger.warning(f"Failed to cascade delete child {child_id}: {e}")

    # Clean up parent's children array
    if ticket.parent:
        _remove_child_from_parent(ticket_id, ticket.parent)
        logger.info(f"Removed {ticket_id} from parent {ticket.parent}'s children array")

    # Clean up dependencies in related tickets
    # Remove from blocking tickets' down_dependencies
    if ticket.up_dependencies:
        for blocking_ticket_id in ticket.up_dependencies:
            _remove_from_down_dependencies(ticket_id, blocking_ticket_id)
            logger.info(f"Removed {ticket_id} from {blocking_ticket_id}'s down_dependencies")

    # Remove from blocked tickets' up_dependencies
    if ticket.down_dependencies:
        for blocked_ticket_id in ticket.down_dependencies:
            _remove_from_up_dependencies(ticket_id, blocked_ticket_id)
            logger.info(f"Removed {ticket_id} from {blocked_ticket_id}'s up_dependencies")

    # Delete the ticket file
    try:
        ticket_path.unlink()
        logger.info(f"Deleted ticket file: {ticket_path}")
    except Exception as e:
        error_msg = f"Failed to delete ticket file {ticket_path}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "ticket_type": ticket_type,
        "message": f"Successfully deleted ticket {ticket_id}"
    }


async def _show_ticket(ticket_id: str, ctx: Context | None = None) -> Dict[str, Any]:
    """
    Retrieve and return ticket data by ticket ID.

    Args:
        ticket_id: The ID of the ticket to retrieve (e.g., 'backend.bees-abc1')
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Ticket data including all fields
            {
                "status": "success",
                "ticket_id": str,
                "ticket_type": str,
                "title": str,
                "description": str,
                "labels": list[str],
                "parent": str | None,
                "children": list[str] | None,
                "up_dependencies": list[str] | None,
                "down_dependencies": list[str] | None,
                "owner": str | None,
                "priority": int | None,
                "ticket_status": str,
                "created_at": str,
                "updated_at": str,
                "created_by": str | None,
                "bees_version": str
            }

    Raises:
        ValueError: If ticket doesn't exist or ticket_id is malformed

    Example:
        >>> _show_ticket('backend.bees-abc1')
        {'status': 'success', 'ticket_id': 'backend.bees-abc1', ...}
    """
    # Validate ticket_id is not empty
    if not ticket_id or not ticket_id.strip():
        error_msg = "ticket_id cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Parse hive from ticket_id
    hive_prefix = parse_hive_from_ticket_id(ticket_id)

    # Return error if hive prefix is None (malformed ID)
    if hive_prefix is None:
        error_msg = f"Malformed ticket ID: '{ticket_id}'. Expected format: hive_name.bees-xxxx"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive exists in config using normalize_name for lookup
    normalized_hive = normalize_hive_name(hive_prefix)

    # Get repo root
    if ctx:
        repo_root = await get_repo_root(ctx)
        if not repo_root:
            raise ValueError("Cannot determine client repository root - MCP roots protocol unavailable")
    else:
        repo_root = get_repo_root_from_path(Path.cwd())

    config = load_bees_config(repo_root)
    if not config or normalized_hive not in config.hives:
        error_msg = f"Hive '{hive_prefix}' (normalized: '{normalized_hive}') not found in configuration"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Infer ticket type from ID
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        error_msg = f"Ticket does not exist: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Get ticket path and read ticket
    ticket_path = get_ticket_path(ticket_id, ticket_type)
    try:
        ticket = read_ticket(ticket_path)
    except FileNotFoundError:
        error_msg = f"Ticket file not found: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to read ticket {ticket_id}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Convert ticket to dict for JSON serialization
    ticket_data = {
        "status": "success",
        "ticket_id": ticket.id,
        "ticket_type": ticket.type,
        "title": ticket.title,
        "description": ticket.description,
        "labels": ticket.labels,
        "parent": ticket.parent,
        "children": ticket.children,
        "up_dependencies": ticket.up_dependencies,
        "down_dependencies": ticket.down_dependencies,
        "owner": ticket.owner,
        "priority": ticket.priority,
        "ticket_status": ticket.status,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "created_by": ticket.created_by,
        "bees_version": ticket.bees_version
    }

    logger.info(f"Successfully retrieved ticket: {ticket_id}")
    return ticket_data
