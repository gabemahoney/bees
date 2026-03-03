"""
Bidirectional Relationship Synchronization Module

This module handles bidirectional relationship synchronization for the Bees ticket
management system. It ensures that when tickets are created or updated with
relationships (parent/child, dependencies), the related tickets are automatically
updated to maintain consistency.

The module provides:
- _update_bidirectional_relationships(): Main entry point for syncing relationships
- 8 helper functions for specific relationship operations:
  - _add_child_to_parent() / _remove_child_from_parent()
  - _set_parent_on_child() / _remove_parent_from_child()
  - _add_to_down_dependencies() / _remove_from_down_dependencies()
  - _add_to_up_dependencies() / _remove_from_up_dependencies()

Used by:
- create_ticket: To establish initial bidirectional relationships
- update_ticket: To sync changes when relationships are modified
- delete_ticket: To clean up references when tickets are deleted

Architecture:
This is a discrete subsystem isolated for maintainability. The relationship sync
logic is complex (~400-500 lines) and used across multiple operations, so separating
it improves code organization and makes the logic easier to understand and test.
"""

import logging
from dataclasses import asdict
from pathlib import Path

from .config import load_bees_config
from .id_utils import ticket_type_from_prefix
from .paths import compute_ticket_path, get_ticket_path, infer_ticket_type_from_id
from .reader import read_ticket
from .writer import write_ticket_file

logger = logging.getLogger(__name__)


def _find_hive_for_ticket(ticket_id: str) -> str | None:
    """
    Local helper to find which hive contains a ticket.
    Scans all configured hives recursively to locate the ticket file.
    Uses hierarchical storage pattern: {ticket_id}/{ticket_id}.md

    Args:
        ticket_id: The ticket ID to search for

    Returns:
        str: The hive name if found, None otherwise
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


def _requires_parent(ticket_type: str) -> bool:
    """Determine if a ticket type requires a parent based on child_tiers config.

    Args:
        ticket_type: The ticket type to check (e.g., "bee", "t1", "t2")

    Returns:
        True if the ticket type requires a parent, False otherwise

    Logic:
        - "bee" (root tier) never requires a parent
        - Any tier in child_tiers (t1, t2, t3...) requires a parent
        - Unknown ticket types return False (permissive default)

    Examples:
        >>> _requires_parent("bee")
        False
        >>> _requires_parent("t1")  # Assuming child_tiers = {"t1": ..., "t2": ...}
        True
        >>> _requires_parent("unknown")
        False
    """
    # Bee (root tier) never requires parent
    if ticket_type == "bee":
        return False

    # Load config to check child_tiers
    config = load_bees_config()

    # If config doesn't exist or child_tiers is empty, return False for unknown types
    if config is None or not config.child_tiers:
        return False

    # Check if ticket_type is in child_tiers (t1, t2, t3...)
    if ticket_type in config.child_tiers:
        return True

    # Unknown types don't require parents (permissive default)
    return False


def _update_bidirectional_relationships(
    new_ticket_id: str,
    parent: str | None = None,
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    hive_name: str | None = None,
) -> None:
    """
    Update related tickets to maintain bidirectional consistency.

    When creating a ticket with relationships, this function updates the related
    tickets to include references back to the newly created ticket.

    Args:
        new_ticket_id: The ID of the newly created ticket
        parent: Parent ticket ID (if set, add new_ticket_id to parent's children)
        children: List of child ticket IDs (if set, add new_ticket_id to each child's parent)
        up_dependencies: List of blocking ticket IDs (add new_ticket_id to their down_dependencies)
        down_dependencies: List of blocked ticket IDs (add new_ticket_id to their up_dependencies)

    Raises:
        ValueError: If any related ticket doesn't exist
        FileNotFoundError: If related ticket file cannot be found
    """
    # Update parent's children array
    if parent:
        parent_type = ticket_type_from_prefix(parent)
        if hive_name is not None:
            # Fast path: caller provided hive context, skip expensive hive scan
            try:
                ticket_path = get_ticket_path(parent, parent_type, hive_name)
            except FileNotFoundError:
                raise ValueError(f"Parent ticket not found: {parent}") from None
            parent_hive = hive_name
        else:
            # Slow path: scan all hives to locate the parent
            parent_type = infer_ticket_type_from_id(parent)
            if not parent_type:
                raise ValueError(f"Parent ticket not found: {parent}")
            parent_hive = _find_hive_for_ticket(parent)
            if not parent_hive:
                raise ValueError(f"Parent ticket hive not found: {parent}")
            ticket_path = get_ticket_path(parent, parent_type, parent_hive)

        parent_ticket = read_ticket(parent, file_path=ticket_path)

        # Add new ticket to parent's children if not already present
        if parent_ticket.children is None:
            parent_ticket.children = []
        if new_ticket_id not in parent_ticket.children:
            parent_ticket.children.append(new_ticket_id)

        # Write updated parent ticket
        frontmatter_data = asdict(parent_ticket)
        # Remove description from frontmatter - it belongs in the body only
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=parent,
            ticket_type=parent_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or "",
            hive_name=parent_hive,
        )
        logger.info(f"Updated parent {parent} to include child {new_ticket_id}")

    # Update children's parent field (if setting children during creation)
    if children:
        for child_id in children:
            if hive_name is not None:
                # Fast path: caller provided hive context
                ticket_type = ticket_type_from_prefix(child_id)
                try:
                    ticket_path = get_ticket_path(child_id, ticket_type, hive_name)
                except FileNotFoundError:
                    raise ValueError(f"Child ticket not found: {child_id}") from None
                child_hive = hive_name
            else:
                # Slow path: scan all hives
                ticket_type = infer_ticket_type_from_id(child_id)
                if not ticket_type:
                    raise ValueError(f"Child ticket not found: {child_id}")
                child_hive = _find_hive_for_ticket(child_id)
                if not child_hive:
                    raise ValueError(f"Child ticket hive not found: {child_id}")
                ticket_path = get_ticket_path(child_id, ticket_type, child_hive)
            child_ticket = read_ticket(child_id, file_path=ticket_path)

            # Set parent on child ticket
            child_ticket.parent = new_ticket_id

            # Write updated child ticket
            frontmatter_data = asdict(child_ticket)
            # Remove description from frontmatter - it belongs in the body only
            frontmatter_data.pop("description", None)
            write_ticket_file(
                ticket_id=child_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=child_ticket.description or "",
                hive_name=child_hive,
            )
            logger.info(f"Updated child {child_id} to have parent {new_ticket_id}")

    # Update up_dependencies (blocking tickets) - add new ticket to their down_dependencies
    if up_dependencies:
        for blocking_ticket_id in up_dependencies:
            if hive_name is not None:
                # Fast path: caller provided hive context
                ticket_type = ticket_type_from_prefix(blocking_ticket_id)
                try:
                    ticket_path = get_ticket_path(blocking_ticket_id, ticket_type, hive_name)
                except FileNotFoundError:
                    raise ValueError(f"Dependency ticket not found: {blocking_ticket_id}") from None
                blocking_hive = hive_name
            else:
                # Slow path: scan all hives
                ticket_type = infer_ticket_type_from_id(blocking_ticket_id)
                if not ticket_type:
                    raise ValueError(f"Dependency ticket not found: {blocking_ticket_id}")
                blocking_hive = _find_hive_for_ticket(blocking_ticket_id)
                if not blocking_hive:
                    raise ValueError(f"Dependency ticket hive not found: {blocking_ticket_id}")
                ticket_path = get_ticket_path(blocking_ticket_id, ticket_type, blocking_hive)
            blocking_ticket = read_ticket(blocking_ticket_id, file_path=ticket_path)

            # Add new ticket to blocking ticket's down_dependencies
            if blocking_ticket.down_dependencies is None:
                blocking_ticket.down_dependencies = []
            if new_ticket_id not in blocking_ticket.down_dependencies:
                blocking_ticket.down_dependencies.append(new_ticket_id)

            # Write updated blocking ticket
            frontmatter_data = asdict(blocking_ticket)
            # Remove description from frontmatter - it belongs in the body only
            frontmatter_data.pop("description", None)
            write_ticket_file(
                ticket_id=blocking_ticket_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=blocking_ticket.description or "",
                hive_name=blocking_hive,
            )
            logger.info(f"Updated blocking ticket {blocking_ticket_id} to include {new_ticket_id} in down_dependencies")

    # Update down_dependencies (blocked tickets) - add new ticket to their up_dependencies
    if down_dependencies:
        for blocked_ticket_id in down_dependencies:
            if hive_name is not None:
                # Fast path: caller provided hive context
                ticket_type = ticket_type_from_prefix(blocked_ticket_id)
                try:
                    ticket_path = get_ticket_path(blocked_ticket_id, ticket_type, hive_name)
                except FileNotFoundError:
                    raise ValueError(f"Dependency ticket not found: {blocked_ticket_id}") from None
                blocked_hive = hive_name
            else:
                # Slow path: scan all hives
                ticket_type = infer_ticket_type_from_id(blocked_ticket_id)
                if not ticket_type:
                    raise ValueError(f"Dependency ticket not found: {blocked_ticket_id}")
                blocked_hive = _find_hive_for_ticket(blocked_ticket_id)
                if not blocked_hive:
                    raise ValueError(f"Dependency ticket hive not found: {blocked_ticket_id}")
                ticket_path = get_ticket_path(blocked_ticket_id, ticket_type, blocked_hive)
            blocked_ticket = read_ticket(blocked_ticket_id, file_path=ticket_path)

            # Add new ticket to blocked ticket's up_dependencies
            if blocked_ticket.up_dependencies is None:
                blocked_ticket.up_dependencies = []
            if new_ticket_id not in blocked_ticket.up_dependencies:
                blocked_ticket.up_dependencies.append(new_ticket_id)

            # Write updated blocked ticket
            frontmatter_data = asdict(blocked_ticket)
            # Remove description from frontmatter - it belongs in the body only
            frontmatter_data.pop("description", None)
            write_ticket_file(
                ticket_id=blocked_ticket_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=blocked_ticket.description or "",
                hive_name=blocked_hive,
            )
            logger.info(f"Updated blocked ticket {blocked_ticket_id} to include {new_ticket_id} in up_dependencies")


def _remove_child_from_parent(child_id: str, parent_id: str, hive_name: str | None = None) -> None:
    """Remove child_id from parent's children array."""
    if hive_name is not None:
        parent_type = ticket_type_from_prefix(parent_id)
        try:
            parent_path = get_ticket_path(parent_id, parent_type, hive_name)
        except FileNotFoundError:
            logger.warning(f"Parent ticket not found: {parent_id}")
            return
    else:
        parent_type = infer_ticket_type_from_id(parent_id)
        if not parent_type:
            logger.warning(f"Parent ticket not found: {parent_id}")
            return
        hive_name = _find_hive_for_ticket(parent_id)
        if not hive_name:
            logger.warning(f"Parent ticket hive not found: {parent_id}")
            return
        parent_path = get_ticket_path(parent_id, parent_type, hive_name)
    parent_ticket = read_ticket(parent_id, file_path=parent_path)

    if parent_ticket.children and child_id in parent_ticket.children:
        parent_ticket.children.remove(child_id)

        frontmatter_data = asdict(parent_ticket)
        # Remove description from frontmatter - it belongs in the body only
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=parent_id,
            ticket_type=parent_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or "",
            hive_name=hive_name,
        )
        logger.info(f"Removed {child_id} from parent {parent_id}'s children")


def _add_child_to_parent(child_id: str, parent_id: str, hive_name: str | None = None) -> None:
    """Add child_id to parent's children array."""
    if hive_name is not None:
        # Fast path: caller provided hive context
        parent_type = ticket_type_from_prefix(parent_id)
        try:
            parent_path = get_ticket_path(parent_id, parent_type, hive_name)
        except FileNotFoundError:
            raise ValueError(f"Parent ticket not found: {parent_id}") from None
        parent_hive = hive_name
    else:
        # Slow path: scan all hives
        parent_type = infer_ticket_type_from_id(parent_id)
        if not parent_type:
            raise ValueError(f"Parent ticket not found: {parent_id}")
        parent_hive = _find_hive_for_ticket(parent_id)
        if not parent_hive:
            raise ValueError(f"Parent ticket hive not found: {parent_id}")
        parent_path = get_ticket_path(parent_id, parent_type, parent_hive)

    parent_ticket = read_ticket(parent_id, file_path=parent_path)

    if parent_ticket.children is None:
        parent_ticket.children = []
    if child_id not in parent_ticket.children:
        parent_ticket.children.append(child_id)

        frontmatter_data = asdict(parent_ticket)
        # Remove description from frontmatter - it belongs in the body only
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=parent_id,
            ticket_type=parent_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or "",
            hive_name=parent_hive,
        )
        logger.info(f"Added {child_id} to parent {parent_id}'s children")


def _remove_parent_from_child(child_id: str, hive_name: str | None = None) -> None:
    """Remove parent field from child ticket."""
    if hive_name is not None:
        child_type = ticket_type_from_prefix(child_id)
        try:
            child_path = get_ticket_path(child_id, child_type, hive_name)
        except FileNotFoundError:
            logger.warning(f"Child ticket not found: {child_id}")
            return
    else:
        child_type = infer_ticket_type_from_id(child_id)
        if not child_type:
            logger.warning(f"Child ticket not found: {child_id}")
            return
        hive_name = _find_hive_for_ticket(child_id)
        if not hive_name:
            logger.warning(f"Child ticket hive not found: {child_id}")
            return
        child_path = get_ticket_path(child_id, child_type, hive_name)
    child_ticket = read_ticket(child_id, file_path=child_path)

    # Child tiers must always have a parent (validation requirement)
    # So we can't unlink child tiers - they remain orphaned pointing to deleted parent
    if _requires_parent(child_type):
        logger.warning(f"Cannot unlink {child_type} {child_id} - this ticket type requires a parent")
        return

    if child_ticket.parent:
        child_ticket.parent = None

        frontmatter_data = asdict(child_ticket)
        # Remove description from frontmatter - it belongs in the body only
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=child_id,
            ticket_type=child_type,
            frontmatter_data=frontmatter_data,
            body=child_ticket.description or "",
            hive_name=hive_name,
        )
        logger.info(f"Removed parent from child {child_id}")


def _set_parent_on_child(parent_id: str, child_id: str, hive_name: str | None = None) -> None:
    """Set parent field on child ticket."""
    if hive_name is not None:
        child_type = ticket_type_from_prefix(child_id)
        try:
            child_path = get_ticket_path(child_id, child_type, hive_name)
        except FileNotFoundError:
            raise ValueError(f"Child ticket not found: {child_id}") from None
    else:
        child_type = infer_ticket_type_from_id(child_id)
        if not child_type:
            raise ValueError(f"Child ticket not found: {child_id}")
        hive_name = _find_hive_for_ticket(child_id)
        if not hive_name:
            raise ValueError(f"Child ticket hive not found: {child_id}")
        child_path = get_ticket_path(child_id, child_type, hive_name)
    child_ticket = read_ticket(child_id, file_path=child_path)

    child_ticket.parent = parent_id

    frontmatter_data = asdict(child_ticket)
    # Remove description from frontmatter - it belongs in the body only
    frontmatter_data.pop("description", None)
    write_ticket_file(
        ticket_id=child_id,
        ticket_type=child_type,
        frontmatter_data=frontmatter_data,
        body=child_ticket.description or "",
        hive_name=hive_name,
    )
    logger.info(f"Set parent {parent_id} on child {child_id}")


def _remove_from_down_dependencies(ticket_id: str, blocking_ticket_id: str, hive_name: str | None = None) -> None:
    """Remove ticket_id from blocking_ticket's down_dependencies."""
    if hive_name is not None:
        blocking_type = ticket_type_from_prefix(blocking_ticket_id)
        try:
            blocking_path = get_ticket_path(blocking_ticket_id, blocking_type, hive_name)
        except FileNotFoundError:
            logger.warning(f"Blocking ticket not found: {blocking_ticket_id}")
            return
    else:
        blocking_type = infer_ticket_type_from_id(blocking_ticket_id)
        if not blocking_type:
            logger.warning(f"Blocking ticket not found: {blocking_ticket_id}")
            return
        hive_name = _find_hive_for_ticket(blocking_ticket_id)
        if not hive_name:
            logger.warning(f"Blocking ticket hive not found: {blocking_ticket_id}")
            return
        blocking_path = get_ticket_path(blocking_ticket_id, blocking_type, hive_name)
    blocking_ticket = read_ticket(blocking_ticket_id, file_path=blocking_path)

    if blocking_ticket.down_dependencies and ticket_id in blocking_ticket.down_dependencies:
        blocking_ticket.down_dependencies.remove(ticket_id)

        frontmatter_data = asdict(blocking_ticket)
        # Remove description from frontmatter - it belongs in the body only
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=blocking_ticket_id,
            ticket_type=blocking_type,
            frontmatter_data=frontmatter_data,
            body=blocking_ticket.description or "",
            hive_name=hive_name,
        )
        logger.info(f"Removed {ticket_id} from {blocking_ticket_id}'s down_dependencies")


def _add_to_down_dependencies(ticket_id: str, blocking_ticket_id: str, hive_name: str | None = None) -> None:
    """Add ticket_id to blocking_ticket's down_dependencies."""
    if hive_name is not None:
        blocking_type = ticket_type_from_prefix(blocking_ticket_id)
        try:
            blocking_path = get_ticket_path(blocking_ticket_id, blocking_type, hive_name)
        except FileNotFoundError:
            raise ValueError(f"Blocking ticket not found: {blocking_ticket_id}") from None
    else:
        blocking_type = infer_ticket_type_from_id(blocking_ticket_id)
        if not blocking_type:
            raise ValueError(f"Blocking ticket not found: {blocking_ticket_id}")
        hive_name = _find_hive_for_ticket(blocking_ticket_id)
        if not hive_name:
            raise ValueError(f"Blocking ticket hive not found: {blocking_ticket_id}")
        blocking_path = get_ticket_path(blocking_ticket_id, blocking_type, hive_name)
    blocking_ticket = read_ticket(blocking_ticket_id, file_path=blocking_path)

    if blocking_ticket.down_dependencies is None:
        blocking_ticket.down_dependencies = []
    if ticket_id not in blocking_ticket.down_dependencies:
        blocking_ticket.down_dependencies.append(ticket_id)

        frontmatter_data = asdict(blocking_ticket)
        # Remove description from frontmatter - it belongs in the body only
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=blocking_ticket_id,
            ticket_type=blocking_type,
            frontmatter_data=frontmatter_data,
            body=blocking_ticket.description or "",
            hive_name=hive_name,
        )
        logger.info(f"Added {ticket_id} to {blocking_ticket_id}'s down_dependencies")


def _remove_from_up_dependencies(ticket_id: str, blocked_ticket_id: str, hive_name: str | None = None) -> None:
    """Remove ticket_id from blocked_ticket's up_dependencies."""
    if hive_name is not None:
        blocked_type = ticket_type_from_prefix(blocked_ticket_id)
        try:
            blocked_path = get_ticket_path(blocked_ticket_id, blocked_type, hive_name)
        except FileNotFoundError:
            logger.warning(f"Blocked ticket not found: {blocked_ticket_id}")
            return
    else:
        blocked_type = infer_ticket_type_from_id(blocked_ticket_id)
        if not blocked_type:
            logger.warning(f"Blocked ticket not found: {blocked_ticket_id}")
            return
        hive_name = _find_hive_for_ticket(blocked_ticket_id)
        if not hive_name:
            logger.warning(f"Blocked ticket hive not found: {blocked_ticket_id}")
            return
        blocked_path = get_ticket_path(blocked_ticket_id, blocked_type, hive_name)
    blocked_ticket = read_ticket(blocked_ticket_id, file_path=blocked_path)

    if blocked_ticket.up_dependencies and ticket_id in blocked_ticket.up_dependencies:
        blocked_ticket.up_dependencies.remove(ticket_id)

        frontmatter_data = asdict(blocked_ticket)
        # Remove description from frontmatter - it belongs in the body only
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=blocked_ticket_id,
            ticket_type=blocked_type,
            frontmatter_data=frontmatter_data,
            body=blocked_ticket.description or "",
            hive_name=hive_name,
        )
        logger.info(f"Removed {ticket_id} from {blocked_ticket_id}'s up_dependencies")


def _add_to_up_dependencies(ticket_id: str, blocked_ticket_id: str, hive_name: str | None = None) -> None:
    """Add ticket_id to blocked_ticket's up_dependencies."""
    if hive_name is not None:
        blocked_type = ticket_type_from_prefix(blocked_ticket_id)
        try:
            blocked_path = get_ticket_path(blocked_ticket_id, blocked_type, hive_name)
        except FileNotFoundError:
            raise ValueError(f"Blocked ticket not found: {blocked_ticket_id}") from None
    else:
        blocked_type = infer_ticket_type_from_id(blocked_ticket_id)
        if not blocked_type:
            raise ValueError(f"Blocked ticket not found: {blocked_ticket_id}")
        hive_name = _find_hive_for_ticket(blocked_ticket_id)
        if not hive_name:
            raise ValueError(f"Blocked ticket hive not found: {blocked_ticket_id}")
        blocked_path = get_ticket_path(blocked_ticket_id, blocked_type, hive_name)
    blocked_ticket = read_ticket(blocked_ticket_id, file_path=blocked_path)

    if blocked_ticket.up_dependencies is None:
        blocked_ticket.up_dependencies = []
    if ticket_id not in blocked_ticket.up_dependencies:
        blocked_ticket.up_dependencies.append(ticket_id)

        frontmatter_data = asdict(blocked_ticket)
        # Remove description from frontmatter - it belongs in the body only
        frontmatter_data.pop("description", None)
        write_ticket_file(
            ticket_id=blocked_ticket_id,
            ticket_type=blocked_type,
            frontmatter_data=frontmatter_data,
            body=blocked_ticket.description or "",
            hive_name=hive_name,
        )
        logger.info(f"Added {ticket_id} to {blocked_ticket_id}'s up_dependencies")
