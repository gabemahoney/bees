"""
Ticket CRUD Operations for Bees MCP Server

This module contains the core ticket create, read, update, and delete operations
extracted from mcp_server.py. These functions handle:
- Ticket creation (_create_ticket)
- Ticket updates (_update_ticket)
- Ticket deletion (_delete_ticket)
- Ticket retrieval (_show_ticket)

All operations include validation and error handling. Create and update operations include
bidirectional relationship sync. Delete operations use a two-phase bottom-up algorithm and
do not modify relationship fields in surviving tickets.
"""

import logging
import os
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from . import cache
from .config import (
    _parse_child_tiers_data,
    _serialize_child_tiers,
    _validate_status_values,
    find_matching_scope,
    load_bees_config,
    load_global_config,
    resolve_child_tiers_for_hive,
    resolve_egg_resolver,
    resolve_egg_resolver_timeout,
    resolve_status_values_for_hive,
    save_global_config,
)
from .id_utils import (
    is_ticket_id,
    is_valid_ticket_id,
    normalize_hive_name,
    parent_id_from_ticket_id,
    resolve_tier_info,
    ticket_type_from_prefix,
)
from .mcp_relationships import (
    _add_to_down_dependencies,
    _add_to_up_dependencies,
    _remove_child_from_parent,
    _remove_from_down_dependencies,
    _remove_from_up_dependencies,
    _update_bidirectional_relationships,
)
from .paths import build_ticket_path_map, compute_ticket_path, get_ticket_path
from .reader import read_ticket
from .repo_utils import get_repo_root_from_path  # noqa: F401 - kept for monkeypatching in tests
from .ticket_factory import create_bee, create_child_tier
from .validator import ValidationError, validate_ticket_type
from .writer import write_ticket_file

# Logger
logger = logging.getLogger(__name__)

# Sentinel value for unset optional parameters
_UNSET: Literal["__UNSET__"] = "__UNSET__"


def find_hive_for_ticket(ticket_id: str) -> str | None:
    """
    Scan all configured hives to find which one contains the given ticket.

    This is a fallback mechanism used when callers do not provide a hive_name parameter.
    Provides O(n) scanning across all hives to locate a ticket by its ID.

    Scans recursively for hierarchical storage pattern: {ticket_id}/{ticket_id}.md

    Args:
        ticket_id: The ticket ID to search for (e.g., 'b.Amx', 't1.X4F2')

    Returns:
        str: The hive name (normalized) if ticket found, None otherwise

    Example:
        >>> find_hive_for_ticket('b.Amx')
        'backend'
        >>> find_hive_for_ticket('nonexistent.id')
        None
    """
    config = load_bees_config()
    if not config or not config.hives:
        return None

    for hive_name, hive_config in config.hives.items():
        hive_path = Path(hive_config.path)
        try:
            if compute_ticket_path(ticket_id, hive_path).exists():
                return hive_name
        except ValueError:
            continue

    return None


def validate_parent_tier_relationship(
    ticket_type: str, parent_id: str | None, parent_type: str | None, hive_name: str | None = None
) -> bool:
    """
    Validate that parent ticket type matches expected tier hierarchy.

    Tier hierarchy rules:
    - bee (t0): No parent allowed
    - t1: Parent must be bee (t0)
    - t2: Parent must be t1
    - t3: Parent must be t2
    - etc.

    Args:
        ticket_type: Type of ticket being created (bee, t1, t2, etc.)
        parent_id: Parent ticket ID (can be None for bees)
        parent_type: Type of parent ticket (bee, t1, t2, etc.)
        hive_name: Optional hive name for per-hive child_tiers resolution

    Returns:
        True if validation passes

    Raises:
        ValueError: If parent type does not match expected tier for ticket_type
    """
    from .config import resolve_child_tiers_for_hive

    config = load_bees_config()

    # Bees cannot have parents (existing behavior)
    if ticket_type == "bee":
        if parent_id is not None:
            error_msg = "Bees cannot have a parent"
            logger.error(error_msg)
            raise ValueError(error_msg)
        return True

    # Resolve child_tiers based on hive_name
    if hive_name is not None:
        child_tiers = resolve_child_tiers_for_hive(hive_name, config)
    else:
        # When hive_name is None, use scope-level config.child_tiers
        # If config.child_tiers is None (not configured), default to {}
        child_tiers = config.child_tiers if config and config.child_tiers is not None else {}

    # For child tiers (t1, t2, t3...), validate against config
    if child_tiers and ticket_type in child_tiers:
        # Determine expected parent tier
        # t1 -> t0 (bee), t2 -> t1, t3 -> t2, etc.
        if ticket_type == "t1":
            expected_parent = "t0"  # t0 = bee
        else:
            # Extract tier number and calculate parent
            tier_num = int(ticket_type[1:])
            expected_parent = f"t{tier_num - 1}"

        # All child tiers require a parent
        if parent_type is None:
            expected_display = "bee" if expected_parent == "t0" else expected_parent
            error_msg = f"{ticket_type} ticket must have {expected_display} parent, got None"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Map t0 to "bee" for comparison
        actual_parent = "t0" if parent_type == "bee" else parent_type

        if actual_parent != expected_parent:
            # Format error message with user-friendly names
            expected_display = "bee" if expected_parent == "t0" else expected_parent
            actual_display = "bee" if parent_type == "bee" else parent_type
            error_msg = f"{ticket_type} ticket must have {expected_display} parent, got {actual_display}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    return True


def _validate_dep_list(
    dep_ids: list[str],
    ticket_type: str,
    *,
    context_label: str | None = None,
) -> None:
    """Validate that all dependency ticket IDs exist and are the same type.

    Args:
        dep_ids: List of dependency ticket IDs to validate.
        ticket_type: Expected ticket type for all dependencies.
        context_label: Label used in cross-type error messages. Defaults to
            ``"ticket type '<ticket_type>'"``.

    Raises:
        ValueError: If a dependency does not exist or is the wrong type.
    """
    config = load_bees_config()
    hive_paths = [Path(hc.path) for hc in config.hives.values()] if config and config.hives else []
    for dep_id in dep_ids:
        dep_type = ticket_type_from_prefix(dep_id)
        if not any(compute_ticket_path(dep_id, hp).exists() for hp in hive_paths):
            error_msg = f"Dependency ticket does not exist: {dep_id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        if dep_type != ticket_type:
            subject = context_label if context_label else f"ticket type '{ticket_type}'"
            error_msg = (
                f"Cross-type dependency not allowed: {subject} "
                f"cannot depend on {dep_id} (type {dep_type})"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)


def _validate_hive_path(hive_path: Path) -> None:
    """Validate that a hive path exists, is a directory, and is writable.

    Raises:
        ValueError: If the path cannot be resolved, does not exist, is not a
            directory, or is not writable.
    """
    try:
        hive_resolved_path = hive_path.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        error_msg = f"Failed to resolve hive path '{hive_path}': {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from None

    if not hive_resolved_path.exists():
        error_msg = (
            f"Hive path does not exist: '{hive_resolved_path}'. "
            "Please create the directory before creating tickets."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not hive_resolved_path.is_dir():
        error_msg = f"Hive path is not a directory: '{hive_resolved_path}'. Path must be a directory, not a file."
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not os.access(hive_resolved_path, os.W_OK):
        error_msg = f"Hive directory is not writable: '{hive_resolved_path}'. Please check directory permissions."
        logger.error(error_msg)
        raise ValueError(error_msg)


def _validate_status_value(status: str, normalized_hive: str, config=None) -> None:
    """Validate status against configured status_values for the hive."""
    status_values = resolve_status_values_for_hive(normalized_hive, config)
    if status_values is not None and status not in status_values:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(status_values)}")


async def _create_ticket(
    ticket_type: str,
    title: str,
    hive_name: str,
    description: str = "",
    parent: str | None = None,
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None = None,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """
    Create a new ticket (bee or dynamic tier type).

    Args:
        ticket_type: Type of ticket to create - 'bee' or tier type (t1, t2, t3...) from child_tiers config.
        title: Title of the ticket (required)
        hive_name: Hive name determining storage location (required, e.g., "backend" stores in backend hive)
        description: Detailed description of the ticket
        parent: Parent ticket ID (required for tier types, not allowed for bees)
        children: List of child ticket IDs
        up_dependencies: List of ticket IDs that this ticket depends on (blocking tickets)
        down_dependencies: List of ticket IDs that depend on this ticket
        tags: List of tag strings
        status: Status of the ticket (e.g., 'open', 'in_progress', 'completed')
        egg: Optional egg data
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Created ticket information including ticket_id

    Raises:
        ValueError: If ticket_type is invalid or validation fails
    """
    # Validate title is not empty
    if not title or not title.strip():
        error_msg = "Ticket title cannot be empty"
        logger.error(error_msg)
        return {"status": "error", "error_type": "invalid_title", "message": error_msg}

    # Validate hive_name (required parameter)
    if not hive_name or not hive_name.strip():
        error_msg = "hive_name is required and cannot be empty"
        logger.error(error_msg)
        return {"status": "error", "error_type": "hive_not_found", "message": error_msg}

    # Check if hive_name contains at least one alphanumeric character
    if not re.search(r"[a-zA-Z0-9]", hive_name):
        error_msg = f"Invalid hive_name: '{hive_name}'. Hive name must contain at least one alphanumeric character"
        logger.error(error_msg)
        return {"status": "error", "error_type": "hive_not_found", "message": error_msg}

    # Validate hive exists in config
    # Design Decision: create_ticket is STRICT and does not attempt hive recovery via scan_for_hive.
    # Rationale:
    #   - Write operations (create/update/delete) should be explicit and fail fast
    #   - Consistency: update_ticket and delete_ticket also fail fast without recovery attempts
    #   - scan_for_hive is a recovery mechanism for read operations, not normal write flows
    #   - Creating tickets requires explicit hive specification to avoid ambiguity
    # See docs/architecture/ for full architectural rationale
    normalized_hive = normalize_hive_name(hive_name)
    logger.info(f"create_ticket: Using repo root: {resolved_root}")

    # Validate ticket_type against config (supports tier IDs and friendly names)
    try:
        validate_ticket_type(ticket_type, normalized_hive)
    except ValidationError as e:
        return {"status": "error", "error_type": "invalid_ticket_type", "message": str(e)}

    # Resolve friendly names to canonical tier IDs (e.g. "Task" -> "t1")
    type_prefix, _ = resolve_tier_info(ticket_type, normalized_hive)
    if type_prefix == "b":
        ticket_type = "bee"
    else:
        ticket_type = type_prefix

    config = load_bees_config()

    # Enforce bees-only hive restriction
    try:
        child_tiers = resolve_child_tiers_for_hive(normalized_hive, config)
    except ValueError as e:
        return {"status": "error", "error_type": "hive_not_found", "message": str(e)}
    if child_tiers == {} and ticket_type != "bee":
        return {
            "status": "error",
            "error_type": "invalid_ticket_type",
            "message": f"Hive '{hive_name}' is configured as bees-only. Only bee (t0) tickets can be created.",
        }
    logger.info(f"create_ticket: Config hives: {list(config.hives.keys()) if config else 'None'}")
    logger.info(f"create_ticket: Looking for hive: '{normalized_hive}'")

    if not config or normalized_hive not in config.hives:
        available_hives = list(config.hives.keys()) if config else []

        error_msg = (
            f"Hive '{hive_name}' (normalized: '{normalized_hive}') not found in config.\n"
            f"  Repo root (from MCP context): {resolved_root}\n"
            f"  Available hives: {available_hives}\n"
            "\n"
            "Please create the hive first using colonize_hive in the correct repository.\n"
            "If the hive directory exists but isn't registered, run colonize_hive to register it."
        )

        logger.error(error_msg)
        return {"status": "error", "error_type": "hive_not_found", "message": error_msg}

    # Validate hive path exists and is writable
    hive_path = Path(config.hives[normalized_hive].path)
    try:
        _validate_hive_path(hive_path)
    except ValueError as e:
        return {"status": "error", "error_type": "hive_not_found", "message": str(e)}

    # Validate parent-child tier hierarchy (basic validation before existence check)
    # This validates bee cannot have parent without needing to check if parent exists
    if ticket_type == "bee" and parent:
        error_msg = "Bees cannot have a parent"
        logger.error(error_msg)
        return {"status": "error", "error_type": "invalid_parent", "message": error_msg}

    # Validate parent ticket exists
    # Use a single stat on the deterministic path instead of reading/parsing YAML.
    # The type is encoded in the ID prefix (b.→bee, t1.→t1) and parents always
    # live in the same hive as their children.
    parent_type = None
    if parent:
        if not compute_ticket_path(parent, hive_path).exists():
            error_msg = f"Parent ticket does not exist: {parent}"
            logger.error(error_msg)
            return {"status": "error", "error_type": "invalid_parent", "message": error_msg}
        _prefix = parent.split(".", 1)[0]
        parent_type = "bee" if _prefix == "b" else _prefix

    # Validate parent-child tier hierarchy (full validation after parent type known)
    try:
        validate_parent_tier_relationship(ticket_type, parent, parent_type, normalized_hive)
    except ValueError as e:
        return {"status": "error", "error_type": "invalid_parent", "message": str(e)}

    # Validate dependency tickets exist
    if up_dependencies:
        try:
            _validate_dep_list(up_dependencies, ticket_type)
        except ValueError as e:
            return {"status": "error", "error_type": "invalid_dependency", "message": str(e)}

    if down_dependencies:
        try:
            _validate_dep_list(down_dependencies, ticket_type)
        except ValueError as e:
            return {"status": "error", "error_type": "invalid_dependency", "message": str(e)}

    # Validate children tickets exist
    if children:
        for child_id in children:
            if not compute_ticket_path(child_id, hive_path).exists():
                error_msg = f"Child ticket does not exist: {child_id}"
                logger.error(error_msg)
                return {"status": "error", "error_type": "invalid_dependency", "message": error_msg}

    # Check for circular dependencies
    if up_dependencies and down_dependencies:
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            error_msg = (
                "Circular dependency detected: ticket cannot both depend on and be depended on "
                f"by the same tickets: {circular_deps}"
            )
            logger.error(error_msg)
            return {"status": "error", "error_type": "circular_dependency", "message": error_msg}

    # Validate status against configured status_values
    if status is not None:
        try:
            _validate_status_value(status, normalized_hive, config)
        except ValueError as e:
            return {"status": "error", "error_type": "invalid_status", "message": str(e)}
    elif resolve_status_values_for_hive(normalized_hive, config) is not None:
        return {
            "status": "error",
            "error_type": "status_required",
            "message": "status is required when status_values are configured for this hive",
        }

    # Call appropriate factory function based on ticket type
    try:
        if ticket_type == "bee":
            ticket_id, guid = create_bee(
                title=title,
                description=description,
                tags=tags,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                status=status,
                hive_name=hive_name,
                egg=egg,
            )
        else:
            # Handle dynamic tier types (t1, t2, t3, etc.)
            # These are validated by validate_ticket_type() against config.child_tiers
            # All child tiers require a parent, similar to task/subtask
            if parent is None:
                error_msg = f"{ticket_type} tickets require a parent"
                logger.error(error_msg)
                return {"status": "error", "error_type": "invalid_parent", "message": error_msg}

            ticket_id, guid = create_child_tier(
                ticket_type=ticket_type,
                title=title,
                parent=parent,
                description=description,
                tags=tags,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                status=status,
                hive_name=hive_name,
            )

        logger.info(f"Successfully created {ticket_type} ticket: {ticket_id}")
        cache.evict(ticket_id)

        # Update bidirectional relationships in related tickets
        _update_bidirectional_relationships(
            new_ticket_id=ticket_id,
            parent=parent,
            children=children,
            up_dependencies=up_dependencies,
            down_dependencies=down_dependencies,
            hive_name=normalized_hive,
        )

        return {
            "status": "success",
            "ticket_id": ticket_id,
            "ticket_type": ticket_type,
            "title": title,
            "guid": guid,
        }

    except Exception as e:
        import traceback

        logger.error(f"Failed to create {ticket_type} ticket: {e}")
        logger.error(f"Full traceback:\n{''.join(traceback.format_exc())}")
        return {"status": "error", "error_type": "create_failed", "message": str(e)}


def _apply_tag_ops(
    ticket: Any,
    add_tags: list[str] | None,
    remove_tags: list[str] | None,
) -> None:
    """Apply add_tags and remove_tags mutations to a ticket in-place."""
    if add_tags:
        existing = set(ticket.tags or [])
        for tag in dict.fromkeys(add_tags):
            if tag not in existing:
                ticket.tags = (ticket.tags or []) + [tag]
                existing.add(tag)
    if remove_tags:
        remove_set = set(dict.fromkeys(remove_tags))
        ticket.tags = [tag for tag in (ticket.tags or []) if tag not in remove_set]


def _log_raise(msg: str) -> None:
    """Log an error and raise ValueError."""
    logger.error(msg)
    raise ValueError(msg)


def _validate_deps(dep_ids: list[str], ticket_id: str, ticket_type: str) -> None:
    """Validate that all dependency IDs exist and match ticket_type."""
    config = load_bees_config()
    hive_paths = [Path(hc.path) for hc in config.hives.values()] if config and config.hives else []
    for dep_id in dep_ids:
        dep_type = ticket_type_from_prefix(dep_id)
        if not any(compute_ticket_path(dep_id, hp).exists() for hp in hive_paths):
            _log_raise(f"Dependency ticket does not exist: {dep_id}")
        if dep_type != ticket_type:
            _log_raise(
                f"Cross-type dependency not allowed: {ticket_id} (type {ticket_type}) "
                f"cannot depend on {dep_id} (type {dep_type})"
            )


def _resolve_hive(ticket_id: str, hive_name: str | None) -> str:
    """Resolve hive for a ticket, raising ValueError on failure."""
    if hive_name:
        config = load_bees_config()
        if not config or hive_name not in config.hives:
            _log_raise(f"Hive '{hive_name}' not found in configuration")
        return hive_name
    resolved = find_hive_for_ticket(ticket_id)
    if not resolved:
        _log_raise(f"Ticket not found in any configured hive: {ticket_id}")
    return resolved  # type: ignore[return-value]


async def _update_ticket_batch(
    ticket_ids_raw: list[str],
    status: str | None | Literal["__UNSET__"],
    add_tags: list[str] | None,
    remove_tags: list[str] | None,
    title: str | None | Literal["__UNSET__"],
    description: str | None | Literal["__UNSET__"],
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None,
    tags: list[str] | None,
    up_dependencies: list[str] | None,
    down_dependencies: list[str] | None,
    hive_name: str | None,
) -> dict[str, Any]:
    """Batch-update multiple tickets with status, add_tags, and remove_tags."""
    if not ticket_ids_raw:
        return {"status": "success", "updated": [], "not_found": [], "failed": []}

    ticket_ids = list(dict.fromkeys(ticket_ids_raw))

    # Fail-fast: non-batchable fields must not be set
    NON_BATCHABLE = {
        "title": title,
        "description": description,
        "egg": egg,
        "tags": tags,
        "up_dependencies": up_dependencies,
        "down_dependencies": down_dependencies,
    }
    for field_name, value in NON_BATCHABLE.items():
        if value is not _UNSET:
            return {
                "status": "error",
                "error_type": "invalid_field",
                "message": f"Field '{field_name}' is not supported for batch updates (list ticket_id)",
            }

    # If hive_name provided, validate config once before the loop
    if hive_name:
        config = load_bees_config()
        if not config or hive_name not in config.hives:
            return {
                "status": "error",
                "error_type": "hive_not_found",
                "message": f"Hive '{hive_name}' not found in configuration",
            }

    updated: list[str] = []
    not_found: list[str] = []
    failed: list[dict[str, str]] = []

    # Build path map once if hive_name not provided (avoids per-ticket walks)
    if not hive_name:
        path_map = build_ticket_path_map(set(ticket_ids))
    else:
        path_map = None

    for tid in ticket_ids:
        # Resolve hive for this ticket
        if hive_name:
            resolved_hive = hive_name
        else:
            if tid not in path_map:
                not_found.append(tid)
                continue
            resolved_hive, ticket_path = path_map[tid]

        try:
            # Read existing ticket (use cached path when available)
            if hive_name:
                ticket_type = ticket_type_from_prefix(tid)
                _batch_hp = Path(config.hives[resolved_hive].path)
                if not compute_ticket_path(tid, _batch_hp).exists():
                    failed.append({"id": tid, "reason": f"Ticket does not exist: {tid}"})
                    continue
                ticket_path = get_ticket_path(tid, ticket_type, resolved_hive)

            ticket = read_ticket(tid, file_path=ticket_path)

            # Validate status against configured status_values
            if status is not _UNSET and status is not None:
                try:
                    _validate_status_value(status, resolved_hive)
                except ValueError as e:
                    failed.append({"id": tid, "reason": str(e)})
                    continue

            # Apply status
            if status is not _UNSET:
                ticket.status = status  # type: ignore[assignment]

            # Apply add_tags / remove_tags
            _apply_tag_ops(ticket, add_tags, remove_tags)

            # Write updated ticket
            frontmatter_data = asdict(ticket)
            frontmatter_data.pop("description", None)
            write_ticket_file(
                ticket_id=tid,
                ticket_type=ticket.type,
                frontmatter_data=frontmatter_data,
                body=ticket.description or "",
                hive_name=resolved_hive,
                file_path=ticket_path,
            )
            cache.evict(tid)
            logger.info(f"Successfully updated ticket: {tid}")
            updated.append(tid)

        except Exception as e:
            logger.error(f"Failed to update ticket {tid}: {e}")
            failed.append({"id": tid, "reason": str(e)})

    return {"status": "success", "updated": updated, "not_found": not_found, "failed": failed}


async def _update_ticket_single(
    ticket_id: str,
    title: str | None | Literal["__UNSET__"],
    description: str | None | Literal["__UNSET__"],
    up_dependencies: list[str] | None,
    down_dependencies: list[str] | None,
    tags: list[str] | None,
    add_tags: list[str] | None,
    remove_tags: list[str] | None,
    status: str | None | Literal["__UNSET__"],
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None,
    hive_name: str | None,
    resolved_root: Path | None,
) -> dict[str, Any]:
    """Update a single ticket with any combination of fields."""
    # Resolve hive and validate ticket existence with a single config load.
    ticket_type = ticket_type_from_prefix(ticket_id)
    if hive_name:
        _upd_config = load_bees_config()
        if not _upd_config or hive_name not in _upd_config.hives:
            return {
                "status": "error",
                "error_type": "hive_not_found",
                "message": f"Hive '{hive_name}' not found in configuration",
            }
        resolved_hive = hive_name
        _upd_hp = Path(_upd_config.hives[resolved_hive].path)
        if not compute_ticket_path(ticket_id, _upd_hp).exists():
            error_msg = f"Ticket does not exist: {ticket_id}"
            logger.error(error_msg)
            return {"status": "error", "error_type": "ticket_not_found", "message": error_msg}
    else:
        # find_hive_for_ticket already verifies existence via compute_ticket_path
        resolved_hive = find_hive_for_ticket(ticket_id)
        if not resolved_hive:
            return {
                "status": "error",
                "error_type": "ticket_not_found",
                "message": f"Ticket not found in any configured hive: {ticket_id}",
            }

    # Read existing ticket
    ticket_path = get_ticket_path(ticket_id, ticket_type, resolved_hive)
    try:
        ticket = read_ticket(ticket_id, file_path=ticket_path)
    except FileNotFoundError:
        error_msg = f"Ticket file not found: {ticket_id}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "ticket_not_found", "message": error_msg}
    except Exception as e:
        error_msg = f"Failed to read ticket {ticket_id}: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "read_error", "message": error_msg}

    # Validate relationship ticket IDs exist
    if up_dependencies is not _UNSET and up_dependencies is not None:
        try:
            _validate_deps(up_dependencies, ticket_id, ticket_type)
        except ValueError as e:
            return {"status": "error", "error_type": "invalid_dependency", "message": str(e)}

    if down_dependencies is not _UNSET and down_dependencies is not None:
        try:
            _validate_deps(down_dependencies, ticket_id, ticket_type)
        except ValueError as e:
            return {"status": "error", "error_type": "invalid_dependency", "message": str(e)}

    # Check for circular dependencies if both up and down are being updated
    if (
        up_dependencies is not _UNSET
        and up_dependencies is not None
        and down_dependencies is not _UNSET
        and down_dependencies is not None
    ):
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            error_msg = (
                "Circular dependency detected: ticket cannot both depend on and be depended on "
                f"by the same tickets: {circular_deps}"
            )
            logger.error(error_msg)
            return {"status": "error", "error_type": "circular_dependency", "message": error_msg}

    # Update basic fields (non-relationship fields)
    if title is not _UNSET:
        if title is None or not title.strip():
            error_msg = "Ticket title cannot be empty"
            logger.error(error_msg)
            return {"status": "error", "error_type": "invalid_title", "message": error_msg}
        ticket.title = title

    if description is not _UNSET:
        # description can be None or empty string
        ticket.description = description if description else ""

    if tags is not _UNSET:
        # tags can be None (which means empty list)
        assert tags != _UNSET  # Type narrowing
        ticket.tags = tags if tags is not None else []

    if status is not _UNSET and status is not None:
        try:
            _validate_status_value(status, resolved_hive)
        except ValueError as e:
            return {"status": "error", "error_type": "invalid_status", "message": str(e)}

    if status is not _UNSET:
        ticket.status = status  # type: ignore[assignment]

    if egg is not _UNSET:
        ticket.egg = egg

    # Apply add_tags / remove_tags
    _apply_tag_ops(ticket, add_tags, remove_tags)

    # Handle relationship updates with bidirectional consistency
    # Track old relationships to determine what changed
    old_up_deps = set(ticket.up_dependencies or [])
    old_down_deps = set(ticket.down_dependencies or [])

    # Update relationship fields if provided
    if up_dependencies is not _UNSET:
        assert up_dependencies != _UNSET  # Type narrowing
        ticket.up_dependencies = up_dependencies if up_dependencies is not None else []
    if down_dependencies is not _UNSET:
        assert down_dependencies != _UNSET  # Type narrowing
        ticket.down_dependencies = down_dependencies if down_dependencies is not None else []

    # Write updated ticket
    frontmatter_data = asdict(ticket)
    # Remove description from frontmatter - it belongs in the body only
    frontmatter_data.pop("description", None)
    write_ticket_file(
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        frontmatter_data=frontmatter_data,
        body=ticket.description or "",
        hive_name=resolved_hive,
    )
    cache.evict(ticket_id)

    # Sync bidirectional relationships
    new_up_deps = set(ticket.up_dependencies or [])
    new_down_deps = set(ticket.down_dependencies or [])

    # Handle up_dependencies changes
    if up_dependencies is not _UNSET:
        removed_up = old_up_deps - new_up_deps
        added_up = new_up_deps - old_up_deps

        for dep_id in removed_up:
            _remove_from_down_dependencies(ticket_id, dep_id, hive_name=resolved_hive)

        for dep_id in added_up:
            _add_to_down_dependencies(ticket_id, dep_id, hive_name=resolved_hive)

    # Handle down_dependencies changes
    if down_dependencies is not _UNSET:
        removed_down = old_down_deps - new_down_deps
        added_down = new_down_deps - old_down_deps

        for dep_id in removed_down:
            _remove_from_up_dependencies(ticket_id, dep_id, hive_name=resolved_hive)

        for dep_id in added_down:
            _add_to_up_dependencies(ticket_id, dep_id, hive_name=resolved_hive)

    logger.info(f"Successfully updated ticket: {ticket_id}")

    return {"status": "success", "updated": [ticket_id], "not_found": [], "failed": []}


async def _update_ticket(
    ticket_id: str | list[str],
    title: str | None | Literal["__UNSET__"] = _UNSET,
    description: str | None | Literal["__UNSET__"] = _UNSET,
    up_dependencies: list[str] | None = _UNSET,  # type: ignore[assignment]  # _UNSET sentinel; Literal excluded to prevent MCP schema conflict
    down_dependencies: list[str] | None = _UNSET,  # type: ignore[assignment]  # _UNSET sentinel; Literal excluded to prevent MCP schema conflict
    tags: list[str] | None = _UNSET,  # type: ignore[assignment]  # _UNSET sentinel; Literal excluded to prevent MCP schema conflict
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    status: str | None | Literal["__UNSET__"] = _UNSET,
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None = _UNSET,  # type: ignore[assignment]  # _UNSET sentinel
    hive_name: str | None = None,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """
    Update one or more existing tickets.

    Supports two call signatures:

    **Single update** (``ticket_id`` is a ``str``):
        Updates one ticket with any combination of fields.
        Returns ``{"status": "success", "updated": [ticket_id], "not_found": [], "failed": []}``.

    **Batch update** (``ticket_id`` is a ``list[str]``):
        Updates multiple tickets applying status, add_tags, and remove_tags to each.
        Non-batchable fields (``title``, ``description``, ``egg``, ``tags``,
        ``up_dependencies``, ``down_dependencies``) raise ``ValueError`` if set.
        Returns ``{"status": "success", "updated": [...], "not_found": [...], "failed": [...]}``.
        An empty list returns success immediately with all arrays empty.

    Args:
        ticket_id: ID of the ticket to update (str), or list of IDs for batch update (list[str])
        title: New title for the ticket (single mode only)
        description: New description for the ticket (single mode only)
        up_dependencies: New list of blocking dependency ticket IDs (single mode only)
        down_dependencies: New list of dependent ticket IDs (single mode only)
        tags: New list of tags, full replace (single mode only)
        add_tags: Tags to add to the ticket (additive, deduplicates)
        remove_tags: Tags to remove from the ticket
        status: New status
        egg: New egg data (arbitrary structured data, single mode only)
        hive_name: Optional hive name for O(1) lookup. If not provided, scans all hives.
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: ``{"status": "success", "updated": [...], "not_found": [...], "failed": [...]}``

    Raises:
        ValueError: If non-batchable fields used in batch mode, or validation fails

    Note:
        When updating dependencies, the change is automatically reflected
        bidirectionally in related tickets.
        Operation order per ticket: ``tags`` full-replace first, then ``add_tags``,
        then ``remove_tags``. If a tag appears in both ``add_tags`` and
        ``remove_tags``, it ends up removed.
    """
    if isinstance(ticket_id, list):
        return await _update_ticket_batch(
            ticket_ids_raw=ticket_id,
            status=status,
            add_tags=add_tags,
            remove_tags=remove_tags,
            title=title,
            description=description,
            egg=egg,
            tags=tags,
            up_dependencies=up_dependencies,
            down_dependencies=down_dependencies,
            hive_name=hive_name,
        )
    return await _update_ticket_single(
        ticket_id=ticket_id,
        title=title,
        description=description,
        up_dependencies=up_dependencies,
        down_dependencies=down_dependencies,
        tags=tags,
        add_tags=add_tags,
        remove_tags=remove_tags,
        status=status,
        egg=egg,
        hive_name=hive_name,
        resolved_root=resolved_root,
    )


def _bulk_tier_sort_key(ticket_id: str) -> int:
    """Return sort key for tier ordering: b. = 0, t1. = 1, t2. = 2, etc."""
    prefix = ticket_id.split(".")[0]
    if prefix == "b":
        return 0
    if prefix.startswith("t") and prefix[1:].isdigit():
        return int(prefix[1:])
    return 999


def _collect_deletion_set(ticket_id: str, hive_name: str) -> list[str]:
    """Collect all ticket IDs in a subtree for bottom-up deletion.

    Traverses the filesystem directory structure using os.scandir — no YAML
    parsing. Returns IDs ordered leaves-first so callers can delete without
    orphaning child directories.

    Args:
        ticket_id: Root ticket of the subtree to collect.
        hive_name: Hive that contains the ticket (used for path resolution).

    Returns:
        List of ticket IDs ordered for bottom-up deletion (leaves first,
        *ticket_id* last).

    Raises:
        ValueError: If the root ticket does not exist.
    """
    _del_config = load_bees_config()
    _del_hp = Path(_del_config.hives[hive_name].path) if _del_config and hive_name in _del_config.hives else None

    if _del_hp is None or not compute_ticket_path(ticket_id, _del_hp).exists():
        raise ValueError(f"Ticket does not exist: {ticket_id}")

    result: list[str] = []
    stack: list[str] = [ticket_id]

    while stack:
        current_id = stack.pop()
        ticket_dir = compute_ticket_path(current_id, _del_hp).parent

        # Scan for child ticket directories — no YAML parsing needed.
        try:
            with os.scandir(ticket_dir) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False) and is_ticket_id(entry.name):
                        stack.append(entry.name)
        except FileNotFoundError:
            pass  # Directory already gone; still record for cache eviction

        result.append(current_id)

    result.reverse()
    return result


def _clean_external_dependencies(deletion_ids: list[str], resolved_hive: str) -> None:
    """Remove deleted subtree from external tickets' dependency fields before deletion.

    For every ticket in *deletion_ids*, removes references to that ticket from
    the ``up_dependencies`` / ``down_dependencies`` arrays of tickets that are
    **outside** the deletion set.  Tickets inside the set are skipped (they are
    being deleted anyway).

    Args:
        deletion_ids: Ordered list of ticket IDs to be deleted (from
            ``_collect_deletion_set``).
        resolved_hive: Hive that contains all tickets in the deletion set.

    Raises:
        ValueError: If reading a ticket in the deletion set fails (other than
            FileNotFoundError), or if updating an external ticket fails (other
            than FileNotFoundError, which is silently skipped).
    """
    deletion_set = set(deletion_ids)
    _clean_config = load_bees_config()
    _clean_hp = (
        Path(_clean_config.hives[resolved_hive].path)
        if _clean_config and resolved_hive in _clean_config.hives
        else None
    )
    for tid in deletion_ids:
        t_type = ticket_type_from_prefix(tid)
        if _clean_hp is None or not compute_ticket_path(tid, _clean_hp).exists():
            continue

        t_path = get_ticket_path(tid, t_type, resolved_hive)
        try:
            ticket = read_ticket(tid, file_path=t_path)
        except FileNotFoundError:
            continue
        except Exception as e:
            error_msg = f"Failed to read ticket {tid} during dependency cleanup: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e

        for dep_id in (ticket.up_dependencies or []):
            if dep_id in deletion_set:
                continue
            try:
                _remove_from_down_dependencies(tid, dep_id, hive_name=resolved_hive)
            except FileNotFoundError:
                pass
            except Exception as e:
                error_msg = f"Failed to clean down_dependencies for {dep_id}: {e}"
                logger.error(error_msg)
                raise ValueError(error_msg) from e

        for dep_id in (ticket.down_dependencies or []):
            if dep_id in deletion_set:
                continue
            try:
                _remove_from_up_dependencies(tid, dep_id, hive_name=resolved_hive)
            except FileNotFoundError:
                pass
            except Exception as e:
                error_msg = f"Failed to clean up_dependencies for {dep_id}: {e}"
                logger.error(error_msg)
                raise ValueError(error_msg) from e

    logger.info(f"Cleanup phase complete: dependency references removed for {len(deletion_ids)} ticket(s)")


def _delete_one_core(
    ticket_id: str,
    resolved_hive: str,
    hive_path: Path | None,
    delete_with_dependencies: bool = False,
    skip_parent_cleanup: bool = False,
) -> str | None:
    """Delete a single ticket and its subtree atomically.

    Shared core logic used by both the single-delete and bulk-delete paths
    in ``_delete_ticket``.

    When ``delete_with_dependencies`` is True, first collects the full subtree
    and cleans external dependency references before deletion.  Otherwise
    deletes the root directory tree directly via ``shutil.rmtree``.

    Args:
        ticket_id: The ticket to delete.
        resolved_hive: Already-resolved hive name.
        hive_path: Path to the hive root directory (safety guard).
        delete_with_dependencies: Whether to clean external dependency
            references before deletion (default: False).

    Returns:
        The root ticket type string.

    Raises:
        ValueError: On any read/delete error.
    """
    root_ticket_type = ticket_type_from_prefix(ticket_id)
    if hive_path is None or not compute_ticket_path(ticket_id, hive_path).exists():
        error_msg = f"Ticket does not exist: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        root_path = get_ticket_path(ticket_id, root_ticket_type, resolved_hive)
    except FileNotFoundError:
        logger.warning(f"Ticket directory already missing, skipping: {ticket_id}")
        return root_ticket_type

    root_dir = root_path.parent

    # Safety guard: never delete the hive root directory
    if hive_path and root_dir == hive_path:
        error_msg = f"Cannot delete hive root directory: {root_dir}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # ── Optional: dependency cleanup when configured ──────────────
    deletion_ids: list[str] | None = None
    if delete_with_dependencies:
        deletion_ids = _collect_deletion_set(ticket_id, resolved_hive)
        _clean_external_dependencies(deletion_ids, resolved_hive)

    # Compute parent from ticket ID for backlink cleanup (no I/O needed)
    parent_id = parent_id_from_ticket_id(ticket_id)

    # ── Atomic filesystem deletion ────────────────────────────────
    # Collect ticket IDs for cache eviction before rmtree removes the files
    if deletion_ids is not None:
        ids_to_evict = deletion_ids
    else:
        ids_to_evict = [
            ticket_file.stem
            for ticket_file in root_dir.rglob("*.md")
            if is_valid_ticket_id(ticket_file.stem)
        ]

    try:
        shutil.rmtree(root_dir)
        for tid in ids_to_evict:
            cache.evict(tid)
        logger.info(f"Deleted ticket directory: {root_dir}")
    except FileNotFoundError:
        logger.warning(f"Directory already removed, skipping: {root_dir}")
    except Exception as e:
        error_msg = f"Failed to delete ticket directory {root_dir}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e

    # ── Parent Backlink Cleanup ───────────────────────────────────
    if parent_id and not skip_parent_cleanup:
        try:
            _remove_child_from_parent(ticket_id, parent_id, hive_name=resolved_hive)
            logger.info(f"Removed {ticket_id} from parent {parent_id} children array")
        except FileNotFoundError:
            pass

    return root_ticket_type


async def _delete_ticket(
    ticket_ids: str | list[str],
    hive_name: str | None = None,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """Delete one or more tickets and their subtrees.

    Supports two call signatures:

    **Single delete** (``ticket_ids`` is a ``str``):
        Deletes one ticket and its entire subtree atomically via
        ``shutil.rmtree``.  Returns ``{status, ticket_id, ticket_type, message}``.

    **Bulk delete** (``ticket_ids`` is a ``list[str]``):
        Iterates the list and applies the same algorithm to each ID.
        Returns ``{status, deleted, not_found, failed}``.
        An empty list returns success immediately with all arrays empty.

    Dependency cleanup is controlled by the global config key
    ``delete_with_dependencies`` (boolean, default ``False``).  When ``True``,
    external dependency references are removed from surviving tickets before
    the filesystem deletion.

    Args:
        ticket_ids: Single ticket ID (str) or list of ticket IDs (list[str]).
            When str, backward-compatible single-delete behavior.
            When list, bulk deletion of multiple independent tickets.
        hive_name: Optional hive name for O(1) lookup. If not provided, scans all hives.
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        Single mode (str input):
            dict with ``status``, ``ticket_id``, ``ticket_type``, and ``message`` keys.
        Bulk mode (list input):
            dict with ``status``, ``deleted``, ``not_found``, and ``failed`` keys.

    Raises:
        ValueError: If a ticket doesn't exist, the hive is invalid, or a
            read/delete error occurs.

    Note:
        When a ticket is deleted:
        - All child tickets are deleted (cascade behaviour)
        - The entire directory subtree under each ticket is removed atomically
        - Hive root directory is never deleted (safety guard)
        - Dependency cleanup is opt-in via global config ``delete_with_dependencies: true``
    """
    # ── Routing: str → single-delete, list → bulk-delete ────
    if isinstance(ticket_ids, str):
        ticket_id = ticket_ids

        # Resolve hive_name: use provided value or scan all hives
        if hive_name:
            resolved_hive = hive_name
            config = load_bees_config()
            if not config or resolved_hive not in config.hives:
                error_msg = f"Hive '{resolved_hive}' not found in configuration"
                logger.error(error_msg)
                return {"status": "error", "error_type": "hive_not_found", "message": error_msg}
        else:
            resolved_hive = find_hive_for_ticket(ticket_id)
            if not resolved_hive:
                error_msg = f"Ticket not found in any configured hive: {ticket_id}"
                logger.error(error_msg)
                return {"status": "error", "error_type": "ticket_not_found", "message": error_msg}
            config = load_bees_config()

        hive_path = Path(config.hives[resolved_hive].path) if config else None
        delete_with_dependencies = load_global_config().get("delete_with_dependencies", False)
        try:
            root_ticket_type = _delete_one_core(
                ticket_id, resolved_hive, hive_path, delete_with_dependencies
            )
        except ValueError as e:
            return {"status": "error", "error_type": "delete_failed", "message": str(e)}

        return {
            "status": "success",
            "ticket_id": ticket_id,
            "ticket_type": root_ticket_type,
            "message": f"Successfully deleted ticket {ticket_id}",
        }

    # ── Bulk-delete path (ticket_ids is list[str]) ───────────────
    if not ticket_ids:
        return {"status": "success", "deleted": [], "not_found": [], "failed": []}

    # Load config once for the entire bulk operation
    config = load_bees_config()
    if hive_name:
        if not config or hive_name not in config.hives:
            return {
                "status": "error",
                "error_type": "hive_not_found",
                "message": f"Hive '{hive_name}' not found in configuration",
            }

    # Sort by tier so ancestors are processed before descendants.
    # This ensures a parent's rmtree removes child directories first;
    # children encountered afterwards land in not_found rather than failed.
    sorted_ids = sorted(ticket_ids, key=_bulk_tier_sort_key)
    delete_with_dependencies = load_global_config().get("delete_with_dependencies", False)

    deleted: list[str] = []
    not_found: list[str] = []
    failed: list[dict[str, str]] = []
    # Track (child_id, resolved_hive) for batch parent cleanup after the loop
    deleted_with_hive: list[tuple[str, str]] = []

    for bulk_id in sorted_ids:
        if hive_name:
            resolved_hive = hive_name
        else:
            resolved_hive = find_hive_for_ticket(bulk_id)
            if not resolved_hive:
                not_found.append(bulk_id)
                continue

        hive_path = Path(config.hives[resolved_hive].path) if config else None

        # If the ticket no longer exists on disk (removed by an ancestor's rmtree),
        # treat it as not_found rather than a failure.
        if hive_path is None or not compute_ticket_path(bulk_id, hive_path).exists():
            not_found.append(bulk_id)
            continue

        try:
            _delete_one_core(
                bulk_id, resolved_hive, hive_path, delete_with_dependencies, skip_parent_cleanup=True
            )
            deleted.append(bulk_id)
            deleted_with_hive.append((bulk_id, resolved_hive))
        except Exception as e:
            logger.error(f"Bulk delete failed for {bulk_id}: {e}")
            failed.append({"id": bulk_id, "reason": str(e)})

    # ── Batch parent backlink cleanup ────────────────────────────
    # Group deleted children by their parent so each parent is read/written once.
    parent_to_children: dict[tuple[str, str], list[str]] = {}
    for child_id, child_hive in deleted_with_hive:
        pid = parent_id_from_ticket_id(child_id)
        if pid:
            key = (pid, child_hive)
            parent_to_children.setdefault(key, []).append(child_id)

    for (pid, pid_hive), child_ids in parent_to_children.items():
        pid_type = ticket_type_from_prefix(pid)
        try:
            pid_path = get_ticket_path(pid, pid_type, pid_hive)
        except FileNotFoundError:
            continue
        parent_ticket = read_ticket(pid, file_path=pid_path)
        if not parent_ticket.children:
            continue
        for child_id in child_ids:
            if child_id in parent_ticket.children:
                parent_ticket.children.remove(child_id)
        frontmatter_data = asdict(parent_ticket)
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=pid,
            ticket_type=pid_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or "",
            hive_name=pid_hive,
        )
        cache.evict(pid)
        logger.info(f"Batch removed {child_ids} from parent {pid} children array")

    return {"status": "success", "deleted": deleted, "not_found": not_found, "failed": failed}


async def _show_ticket(
    ticket_ids: list[str], resolved_root: Path | None = None
) -> dict[str, Any]:
    """
    Retrieve and return ticket data for one or more ticket IDs.

    Args:
        ticket_ids: List of ticket IDs to retrieve (e.g., ['b.Amx', 'b.Xyz'])
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Bulk response with ticket data
            {
                "status": "success",
                "tickets": [
                    {
                        "ticket_id": str,
                        "ticket_type": str,
                        "title": str,
                        "description": str,
                        "tags": list[str],
                        "parent": str | None,
                        "children": list[str] | None,
                        "up_dependencies": list[str] | None,
                        "down_dependencies": list[str] | None,
                        "ticket_status": str,
                        "created_at": str,
                        "schema_version": str,
                        "egg": any,
                        "guid": str
                    },
                    ...
                ],
                "not_found": ["b.missing"],
                "errors": [{"id": "b.xxx", "reason": "egg resolver timed out: ..."}]
            }

        `not_found` contains IDs of tickets that could not be located or read.
        `errors` contains IDs of tickets that were found but failed during egg resolution.

    Example:
        >>> _show_ticket(['b.Amx', 'b.Xyz'])
        {'status': 'success', 'tickets': [{...}, {...}], 'not_found': [], 'errors': []}
    """
    # Local import to avoid circular dependency (mcp_egg_ops imports find_hive_for_ticket from here)
    from .mcp_egg_ops import _default_resolver, _invoke_custom_resolver  # noqa: PLC0415

    if not ticket_ids:
        return {"status": "success", "tickets": [], "not_found": [], "errors": []}

    tickets = []
    not_found = []
    errors = []

    config = load_bees_config()

    # Validate IDs first; separate valid from invalid/empty
    valid_ids = []
    for ticket_id in ticket_ids:
        if not ticket_id or not ticket_id.strip():
            not_found.append(ticket_id)
            continue
        if not is_valid_ticket_id(ticket_id):
            return {
                "status": "error",
                "error_type": "invalid_ticket_id",
                "message": f"Invalid ticket ID format: {ticket_id!r}",
            }
        valid_ids.append(ticket_id)

    # Single walk across all hives to resolve paths for every ticket
    path_map = build_ticket_path_map(set(valid_ids))

    for ticket_id in valid_ids:
        try:
            if ticket_id not in path_map:
                not_found.append(ticket_id)
                continue

            resolved_hive, ticket_path = path_map[ticket_id]
            ticket = read_ticket(ticket_id, file_path=ticket_path)

            # Resolve egg for bee tickets via resolver pipeline
            if ticket.type == "bee":
                try:
                    egg_resolver = resolve_egg_resolver(resolved_hive, config)
                    if egg_resolver is None:
                        resolved_egg = _default_resolver(ticket.egg)
                    else:
                        if resolved_root is None:
                            raise ValueError(
                                "resolved_root is required when a custom egg resolver is configured"
                            )
                        timeout = resolve_egg_resolver_timeout(resolved_hive, config)
                        resolved_egg = await _invoke_custom_resolver(
                            egg_resolver, ticket.egg, resolved_root, timeout
                        )
                except Exception as e:
                    logger.error(f"Egg resolver failed for {ticket_id}: {e}")
                    errors.append({"id": ticket_id, "reason": str(e)})
                    resolved_egg = ticket.egg
            else:
                resolved_egg = ticket.egg

            ticket_data = {
                "ticket_id": ticket.id,
                "ticket_type": ticket.type,
                "title": ticket.title,
                "description": ticket.description,
                "tags": ticket.tags,
                "parent": ticket.parent,
                "children": ticket.children,
                "up_dependencies": ticket.up_dependencies,
                "down_dependencies": ticket.down_dependencies,
                "ticket_status": ticket.status,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "schema_version": ticket.schema_version,
                "egg": resolved_egg,
                "guid": ticket.guid,
            }
            tickets.append(ticket_data)
            logger.info(f"Successfully retrieved ticket: {ticket_id}")

        except (ValueError, FileNotFoundError):
            logger.warning(f"Ticket not found or unreadable, adding to not_found: {ticket_id}")
            not_found.append(ticket_id)

    return {"status": "success", "tickets": tickets, "not_found": not_found, "errors": errors}


async def _get_types(
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """Get raw child_tiers from all three configuration levels independently.

    Reads child_tiers directly from global config, scope config, and each
    hive's config without inheritance resolution. Returns raw stored values
    at each level — not the resolved/effective values.

    Args:
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Raw child_tiers at each configuration level:
            {
                "status": "success",
                "global": dict | null,
                "scope": dict | null,
                "hives": {
                    "normalized_name": dict | null,
                    ...
                }
            }

        When no scope matches resolved_root:
            {
                "status": "error",
                "error_type": "no_matching_scope",
                "message": "No scope pattern matches repo root '...'"
            }

        The "hives" dict contains every registered hive in the matched scope.
        Hives without explicit child_tiers appear with null value.
        Keys are normalized hive names.
    """
    global_config = load_global_config()

    # Read global-level child_tiers (raw)
    global_child_tiers = global_config.get("child_tiers", None)

    # Find matching scope
    pattern_key = find_matching_scope(resolved_root, global_config)
    if pattern_key is None:
        return {
            "status": "error",
            "error_type": "no_matching_scope",
            "message": f"No scope pattern matches repo root '{resolved_root}'",
        }

    scope_block = global_config["scopes"][pattern_key]

    # Read scope-level child_tiers (raw)
    scope_child_tiers = scope_block.get("child_tiers", None)

    # Read hive-level child_tiers for every hive (raw)
    hives_child_tiers: dict[str, dict | None] = {}
    hives_data = scope_block.get("hives", {})
    for hive_key in hives_data:
        normalized = normalize_hive_name(hive_key)
        hives_child_tiers[normalized] = hives_data[hive_key].get("child_tiers", None)

    return {
        "status": "success",
        "global": global_child_tiers,
        "scope": scope_child_tiers,
        "hives": hives_child_tiers,
    }


async def _set_types(
    scope: str,
    hive_name: str | None = None,
    child_tiers: dict | None = None,
    unset: bool = False,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """Set or unset child_tiers configuration at the specified scope level.

    Args:
        scope: Target scope — "global", "repo_scope", or "hive"
        hive_name: Hive name (required when scope="hive")
        child_tiers: Child tiers dict to write (required when unset=False)
        unset: If True, remove child_tiers key from the target level
        resolved_root: Pre-resolved repo root path (required for non-global scopes)

    Returns:
        dict: Success or error response
    """
    # --- Phase 1: Parameter validation (before any config load) ---
    valid_scopes = {"global", "repo_scope", "hive"}
    if scope not in valid_scopes:
        return {
            "status": "error",
            "error_type": "invalid_scope",
            "message": f"Invalid scope '{scope}'. Must be one of: global, repo_scope, hive",
        }

    if child_tiers is not None and unset:
        return {
            "status": "error",
            "error_type": "conflicting_params",
            "message": "Cannot specify both child_tiers and unset=True",
        }

    if child_tiers is None and not unset:
        return {
            "status": "error",
            "error_type": "missing_child_tiers",
            "message": "Must provide child_tiers or set unset=True",
        }

    if scope == "hive" and not hive_name:
        return {
            "status": "error",
            "error_type": "missing_hive_name",
            "message": "hive_name is required when scope='hive'",
        }

    # --- Phase 2: Validate child_tiers (before config load) ---
    if not unset:
        try:
            parsed = _parse_child_tiers_data(child_tiers)
        except ValueError as e:
            return {
                "status": "error",
                "error_type": "invalid_child_tiers",
                "message": str(e),
            }

    # --- Phase 3: Load config and perform write ---
    global_config = load_global_config()

    if scope == "global":
        if unset:
            global_config.pop("child_tiers", None)
        else:
            global_config["child_tiers"] = _serialize_child_tiers(parsed)
        save_global_config(global_config)
        if unset:
            return {"status": "success", "scope": "global"}
        else:
            return {"status": "success", "scope": "global", "child_tiers": global_config["child_tiers"]}

    elif scope == "repo_scope":
        pattern_key = find_matching_scope(resolved_root, global_config)
        if pattern_key is None:
            return {
                "status": "error",
                "error_type": "no_matching_scope",
                "message": f"No scope pattern matches repo root '{resolved_root}'",
            }
        scope_block = global_config["scopes"][pattern_key]
        if unset:
            scope_block.pop("child_tiers", None)
        else:
            scope_block["child_tiers"] = _serialize_child_tiers(parsed)
        save_global_config(global_config)
        if unset:
            return {"status": "success", "scope": "repo_scope"}
        else:
            return {"status": "success", "scope": "repo_scope", "child_tiers": scope_block["child_tiers"]}

    else:  # scope == "hive"
        normalized = normalize_hive_name(hive_name)
        # Resolve the matching scope for this repo first, then look up the hive within it
        pattern_key = find_matching_scope(resolved_root, global_config)
        if pattern_key is None:
            return {
                "status": "error",
                "error_type": "no_matching_scope",
                "message": f"No scope pattern matches repo root '{resolved_root}'",
            }
        hives = global_config["scopes"][pattern_key].get("hives", {})
        if normalized not in hives:
            return {
                "status": "error",
                "error_type": "hive_not_found",
                "message": f"Hive '{normalized}' not found in configuration",
            }
        hive_entry = hives[normalized]
        if unset:
            hive_entry.pop("child_tiers", None)
        else:
            hive_entry["child_tiers"] = _serialize_child_tiers(parsed)
        save_global_config(global_config)
        if unset:
            return {"status": "success", "scope": "hive", "hive_name": normalized}
        else:
            return {
                "status": "success",
                "scope": "hive",
                "hive_name": normalized,
                "child_tiers": hive_entry["child_tiers"],
            }


async def _get_status_values(
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """Get raw status_values from all three configuration levels independently.

    Reads status_values directly from global config, scope config, and each
    hive's config without inheritance resolution. Returns raw stored values
    at each level — not the resolved/effective values.

    Args:
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Raw status_values at each configuration level:
            {
                "status": "success",
                "global": list[str] | null,
                "scope": list[str] | null,
                "hives": {
                    "normalized_name": list[str] | null,
                    ...
                }
            }

        When no scope matches resolved_root:
            {
                "status": "error",
                "error_type": "no_matching_scope",
                "message": "No scope pattern matches repo root '...'"
            }

        The "hives" dict contains every registered hive in the matched scope.
        Hives without explicit status_values appear with null value.
        Keys are normalized hive names.
    """
    global_config = load_global_config()

    # Read global-level status_values (raw)
    global_status_values = global_config.get("status_values", None)

    # Find matching scope
    pattern_key = find_matching_scope(resolved_root, global_config)
    if pattern_key is None:
        return {
            "status": "error",
            "error_type": "no_matching_scope",
            "message": f"No scope pattern matches repo root '{resolved_root}'",
        }

    scope_block = global_config["scopes"][pattern_key]

    # Read scope-level status_values (raw)
    scope_status_values = scope_block.get("status_values", None)

    # Read hive-level status_values for every hive (raw)
    hives_status: dict[str, list[str] | None] = {}
    hives_data = scope_block.get("hives", {})
    for hive_key in hives_data:
        normalized = normalize_hive_name(hive_key)
        hives_status[normalized] = hives_data[hive_key].get("status_values", None)

    return {
        "status": "success",
        "global": global_status_values,
        "scope": scope_status_values,
        "hives": hives_status,
    }


async def _set_status_values(
    scope: str,
    hive_name: str | None = None,
    status_values: list[str] | None = None,
    unset: bool = False,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """Set or unset status_values configuration at the specified scope level.

    Args:
        scope: Target scope — "global", "repo_scope", or "hive"
        hive_name: Hive name (required when scope="hive")
        status_values: List of allowed status strings to write (required when unset=False)
        unset: If True, remove status_values key from the target level
        resolved_root: Pre-resolved repo root path (required for non-global scopes)

    Returns:
        dict: Success or error response
    """
    # --- Phase 1: Parameter validation (before any config load) ---
    valid_scopes = {"global", "repo_scope", "hive"}
    if scope not in valid_scopes:
        return {
            "status": "error",
            "error_type": "invalid_scope",
            "message": f"Invalid scope '{scope}'. Must be one of: global, repo_scope, hive",
        }

    if status_values is not None and unset:
        return {
            "status": "error",
            "error_type": "conflicting_params",
            "message": "Cannot specify both status_values and unset=True",
        }

    if status_values is None and not unset:
        return {
            "status": "error",
            "error_type": "missing_status_values",
            "message": "Must provide status_values or set unset=True",
        }

    if scope == "hive" and not hive_name:
        return {
            "status": "error",
            "error_type": "missing_hive_name",
            "message": "hive_name is required when scope='hive'",
        }

    # --- Phase 2: Validate status_values (before config load) ---
    # Treat empty list identically to unset=True
    if not unset and status_values == []:
        unset = True
        status_values = None

    if not unset:
        try:
            _validate_status_values(status_values, "status_values")
        except ValueError as e:
            return {
                "status": "error",
                "error_type": "invalid_status_values",
                "message": str(e),
            }
        # Silently deduplicate, preserving first occurrence
        status_values = list(dict.fromkeys(status_values))

    # --- Phase 3: Load config and perform write ---
    global_config = load_global_config()

    if scope == "global":
        if unset:
            global_config.pop("status_values", None)
        else:
            global_config["status_values"] = status_values
        save_global_config(global_config)
        if unset:
            return {"status": "success", "scope": "global"}
        else:
            return {"status": "success", "scope": "global", "status_values": status_values}

    elif scope == "repo_scope":
        pattern_key = find_matching_scope(resolved_root, global_config)
        if pattern_key is None:
            return {
                "status": "error",
                "error_type": "no_matching_scope",
                "message": f"No scope pattern matches repo root '{resolved_root}'",
            }
        scope_block = global_config["scopes"][pattern_key]
        if unset:
            scope_block.pop("status_values", None)
        else:
            scope_block["status_values"] = status_values
        save_global_config(global_config)
        if unset:
            return {"status": "success", "scope": "repo_scope"}
        else:
            return {"status": "success", "scope": "repo_scope", "status_values": status_values}

    else:  # scope == "hive"
        normalized = normalize_hive_name(hive_name)
        pattern_key = find_matching_scope(resolved_root, global_config)
        if pattern_key is None:
            return {
                "status": "error",
                "error_type": "no_matching_scope",
                "message": f"No scope pattern matches repo root '{resolved_root}'",
            }
        hives = global_config["scopes"][pattern_key].get("hives", {})
        if normalized not in hives:
            return {
                "status": "error",
                "error_type": "hive_not_found",
                "message": f"Hive '{normalized}' not found in configuration",
            }
        hive_entry = hives[normalized]
        if unset:
            # Store null explicitly so hive overrides scope/global inheritance
            hive_entry["status_values"] = None
        else:
            hive_entry["status_values"] = status_values
        save_global_config(global_config)
        if unset:
            return {"status": "success", "scope": "hive", "hive_name": normalized}
        else:
            return {
                "status": "success",
                "scope": "hive",
                "hive_name": normalized,
                "status_values": status_values,
            }
