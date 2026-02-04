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
from datetime import datetime
from .reader import read_ticket
from .writer import write_ticket_file
from .paths import infer_ticket_type_from_id, get_ticket_path

logger = logging.getLogger(__name__)


def _update_bidirectional_relationships(
    new_ticket_id: str,
    parent: str | None = None,
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None
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
        ticket_type = infer_ticket_type_from_id(parent)
        if not ticket_type:
            raise ValueError(f"Parent ticket not found: {parent}")

        ticket_path = get_ticket_path(parent, ticket_type)
        parent_ticket = read_ticket(ticket_path)

        # Add new ticket to parent's children if not already present
        if parent_ticket.children is None:
            parent_ticket.children = []
        if new_ticket_id not in parent_ticket.children:
            parent_ticket.children.append(new_ticket_id)

        # Write updated parent ticket
        frontmatter_data = asdict(parent_ticket)
        frontmatter_data["updated_at"] = datetime.now()
        write_ticket_file(
            ticket_id=parent,
            ticket_type=ticket_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or ""
        )
        logger.info(f"Updated parent {parent} to include child {new_ticket_id}")

    # Update children's parent field (if setting children during creation)
    if children:
        for child_id in children:
            ticket_type = infer_ticket_type_from_id(child_id)
            if not ticket_type:
                raise ValueError(f"Child ticket not found: {child_id}")

            ticket_path = get_ticket_path(child_id, ticket_type)
            child_ticket = read_ticket(ticket_path)

            # Set parent on child ticket
            child_ticket.parent = new_ticket_id

            # Write updated child ticket
            frontmatter_data = asdict(child_ticket)
            frontmatter_data["updated_at"] = datetime.now()
            write_ticket_file(
                ticket_id=child_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=child_ticket.description or ""
            )
            logger.info(f"Updated child {child_id} to have parent {new_ticket_id}")

    # Update up_dependencies (blocking tickets) - add new ticket to their down_dependencies
    if up_dependencies:
        for blocking_ticket_id in up_dependencies:
            ticket_type = infer_ticket_type_from_id(blocking_ticket_id)
            if not ticket_type:
                raise ValueError(f"Dependency ticket not found: {blocking_ticket_id}")

            ticket_path = get_ticket_path(blocking_ticket_id, ticket_type)
            blocking_ticket = read_ticket(ticket_path)

            # Add new ticket to blocking ticket's down_dependencies
            if blocking_ticket.down_dependencies is None:
                blocking_ticket.down_dependencies = []
            if new_ticket_id not in blocking_ticket.down_dependencies:
                blocking_ticket.down_dependencies.append(new_ticket_id)

            # Write updated blocking ticket
            frontmatter_data = asdict(blocking_ticket)
            frontmatter_data["updated_at"] = datetime.now()
            write_ticket_file(
                ticket_id=blocking_ticket_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=blocking_ticket.description or ""
            )
            logger.info(f"Updated blocking ticket {blocking_ticket_id} to include {new_ticket_id} in down_dependencies")

    # Update down_dependencies (blocked tickets) - add new ticket to their up_dependencies
    if down_dependencies:
        for blocked_ticket_id in down_dependencies:
            ticket_type = infer_ticket_type_from_id(blocked_ticket_id)
            if not ticket_type:
                raise ValueError(f"Dependency ticket not found: {blocked_ticket_id}")

            ticket_path = get_ticket_path(blocked_ticket_id, ticket_type)
            blocked_ticket = read_ticket(ticket_path)

            # Add new ticket to blocked ticket's up_dependencies
            if blocked_ticket.up_dependencies is None:
                blocked_ticket.up_dependencies = []
            if new_ticket_id not in blocked_ticket.up_dependencies:
                blocked_ticket.up_dependencies.append(new_ticket_id)

            # Write updated blocked ticket
            frontmatter_data = asdict(blocked_ticket)
            frontmatter_data["updated_at"] = datetime.now()
            write_ticket_file(
                ticket_id=blocked_ticket_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=blocked_ticket.description or ""
            )
            logger.info(f"Updated blocked ticket {blocked_ticket_id} to include {new_ticket_id} in up_dependencies")


def _remove_child_from_parent(child_id: str, parent_id: str) -> None:
    """Remove child_id from parent's children array."""
    parent_type = infer_ticket_type_from_id(parent_id)
    if not parent_type:
        logger.warning(f"Parent ticket not found: {parent_id}")
        return

    parent_path = get_ticket_path(parent_id, parent_type)
    parent_ticket = read_ticket(parent_path)

    if parent_ticket.children and child_id in parent_ticket.children:
        parent_ticket.children.remove(child_id)
        parent_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(parent_ticket)
        write_ticket_file(
            ticket_id=parent_id,
            ticket_type=parent_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or ""
        )
        logger.info(f"Removed {child_id} from parent {parent_id}'s children")


def _add_child_to_parent(child_id: str, parent_id: str) -> None:
    """Add child_id to parent's children array."""
    parent_type = infer_ticket_type_from_id(parent_id)
    if not parent_type:
        raise ValueError(f"Parent ticket not found: {parent_id}")

    parent_path = get_ticket_path(parent_id, parent_type)
    parent_ticket = read_ticket(parent_path)

    if parent_ticket.children is None:
        parent_ticket.children = []
    if child_id not in parent_ticket.children:
        parent_ticket.children.append(child_id)
        parent_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(parent_ticket)
        write_ticket_file(
            ticket_id=parent_id,
            ticket_type=parent_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or ""
        )
        logger.info(f"Added {child_id} to parent {parent_id}'s children")


def _remove_parent_from_child(child_id: str) -> None:
    """Remove parent field from child ticket."""
    child_type = infer_ticket_type_from_id(child_id)
    if not child_type:
        logger.warning(f"Child ticket not found: {child_id}")
        return

    child_path = get_ticket_path(child_id, child_type)
    child_ticket = read_ticket(child_path)

    # Subtasks must always have a parent (validation requirement)
    # So we can't unlink subtasks - they remain orphaned pointing to deleted parent
    if child_type == "subtask":
        logger.warning(f"Cannot unlink subtask {child_id} - subtasks require a parent")
        return

    if child_ticket.parent:
        child_ticket.parent = None
        child_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(child_ticket)
        write_ticket_file(
            ticket_id=child_id,
            ticket_type=child_type,
            frontmatter_data=frontmatter_data,
            body=child_ticket.description or ""
        )
        logger.info(f"Removed parent from child {child_id}")


def _set_parent_on_child(parent_id: str, child_id: str) -> None:
    """Set parent field on child ticket."""
    child_type = infer_ticket_type_from_id(child_id)
    if not child_type:
        raise ValueError(f"Child ticket not found: {child_id}")

    child_path = get_ticket_path(child_id, child_type)
    child_ticket = read_ticket(child_path)

    child_ticket.parent = parent_id
    child_ticket.updated_at = datetime.now()

    frontmatter_data = asdict(child_ticket)
    write_ticket_file(
        ticket_id=child_id,
        ticket_type=child_type,
        frontmatter_data=frontmatter_data,
        body=child_ticket.description or ""
    )
    logger.info(f"Set parent {parent_id} on child {child_id}")


def _remove_from_down_dependencies(ticket_id: str, blocking_ticket_id: str) -> None:
    """Remove ticket_id from blocking_ticket's down_dependencies."""
    blocking_type = infer_ticket_type_from_id(blocking_ticket_id)
    if not blocking_type:
        logger.warning(f"Blocking ticket not found: {blocking_ticket_id}")
        return

    blocking_path = get_ticket_path(blocking_ticket_id, blocking_type)
    blocking_ticket = read_ticket(blocking_path)

    if blocking_ticket.down_dependencies and ticket_id in blocking_ticket.down_dependencies:
        blocking_ticket.down_dependencies.remove(ticket_id)
        blocking_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(blocking_ticket)
        write_ticket_file(
            ticket_id=blocking_ticket_id,
            ticket_type=blocking_type,
            frontmatter_data=frontmatter_data,
            body=blocking_ticket.description or ""
        )
        logger.info(f"Removed {ticket_id} from {blocking_ticket_id}'s down_dependencies")


def _add_to_down_dependencies(ticket_id: str, blocking_ticket_id: str) -> None:
    """Add ticket_id to blocking_ticket's down_dependencies."""
    blocking_type = infer_ticket_type_from_id(blocking_ticket_id)
    if not blocking_type:
        raise ValueError(f"Blocking ticket not found: {blocking_ticket_id}")

    blocking_path = get_ticket_path(blocking_ticket_id, blocking_type)
    blocking_ticket = read_ticket(blocking_path)

    if blocking_ticket.down_dependencies is None:
        blocking_ticket.down_dependencies = []
    if ticket_id not in blocking_ticket.down_dependencies:
        blocking_ticket.down_dependencies.append(ticket_id)
        blocking_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(blocking_ticket)
        write_ticket_file(
            ticket_id=blocking_ticket_id,
            ticket_type=blocking_type,
            frontmatter_data=frontmatter_data,
            body=blocking_ticket.description or ""
        )
        logger.info(f"Added {ticket_id} to {blocking_ticket_id}'s down_dependencies")


def _remove_from_up_dependencies(ticket_id: str, blocked_ticket_id: str) -> None:
    """Remove ticket_id from blocked_ticket's up_dependencies."""
    blocked_type = infer_ticket_type_from_id(blocked_ticket_id)
    if not blocked_type:
        logger.warning(f"Blocked ticket not found: {blocked_ticket_id}")
        return

    blocked_path = get_ticket_path(blocked_ticket_id, blocked_type)
    blocked_ticket = read_ticket(blocked_path)

    if blocked_ticket.up_dependencies and ticket_id in blocked_ticket.up_dependencies:
        blocked_ticket.up_dependencies.remove(ticket_id)
        blocked_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(blocked_ticket)
        write_ticket_file(
            ticket_id=blocked_ticket_id,
            ticket_type=blocked_type,
            frontmatter_data=frontmatter_data,
            body=blocked_ticket.description or ""
        )
        logger.info(f"Removed {ticket_id} from {blocked_ticket_id}'s up_dependencies")


def _add_to_up_dependencies(ticket_id: str, blocked_ticket_id: str) -> None:
    """Add ticket_id to blocked_ticket's up_dependencies."""
    blocked_type = infer_ticket_type_from_id(blocked_ticket_id)
    if not blocked_type:
        raise ValueError(f"Blocked ticket not found: {blocked_ticket_id}")

    blocked_path = get_ticket_path(blocked_ticket_id, blocked_type)
    blocked_ticket = read_ticket(blocked_path)

    if blocked_ticket.up_dependencies is None:
        blocked_ticket.up_dependencies = []
    if ticket_id not in blocked_ticket.up_dependencies:
        blocked_ticket.up_dependencies.append(ticket_id)
        blocked_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(blocked_ticket)
        write_ticket_file(
            ticket_id=blocked_ticket_id,
            ticket_type=blocked_type,
            frontmatter_data=frontmatter_data,
            body=blocked_ticket.description or ""
        )
        logger.info(f"Added {ticket_id} to {blocked_ticket_id}'s up_dependencies")
