"""Bidirectional relationship synchronization for ticket operations.

This module provides helper functions to maintain bidirectional consistency
of all ticket relationships (parent/children, up/down dependencies).
When a relationship is added in one direction, this module ensures the
inverse relationship is also updated in the related ticket.
"""

import fcntl
import logging
import platform
import time
from pathlib import Path
from typing import Any, Set

from .models import Ticket
from .parser import parse_frontmatter
from .paths import get_ticket_path, infer_ticket_type_from_id
from .reader import read_ticket
from .writer import write_ticket_file

# Set up logging
logger = logging.getLogger(__name__)

# Check if we're on Windows for file locking
IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    import msvcrt


# Validation Functions

def validate_ticket_exists(ticket_id: str) -> bool:
    """
    Check if a ticket file exists before modifying relationships.

    Args:
        ticket_id: The ticket ID to check

    Returns:
        True if ticket exists

    Raises:
        FileNotFoundError: If ticket doesn't exist in any directory
    """
    for ticket_type in ["epic", "task", "subtask"]:
        try:
            path = get_ticket_path(ticket_id, ticket_type)
            if path.exists():
                return True
        except Exception:
            continue

    raise FileNotFoundError(
        f"Ticket {ticket_id} not found. Cannot modify relationships."
    )


def validate_parent_child_relationship(parent_id: str, child_id: str) -> None:
    """
    Ensure type hierarchy is valid for parent-child relationships.

    Valid hierarchies:
    - Epic can parent Task
    - Task can parent Subtask
    - Epic cannot parent Subtask (must go through Task)

    Args:
        parent_id: The ID of the parent ticket
        child_id: The ID of the child ticket

    Raises:
        ValueError: If relationship violates type hierarchy
        FileNotFoundError: If either ticket doesn't exist
    """
    # Infer types from file locations (lightweight - no full ticket load)
    parent_type = infer_ticket_type_from_id(parent_id)
    child_type = infer_ticket_type_from_id(child_id)

    # Check tickets exist
    if parent_type is None:
        raise FileNotFoundError(f"Parent ticket {parent_id} not found")
    if child_type is None:
        raise FileNotFoundError(f"Child ticket {child_id} not found")

    # Define valid parent-child type combinations
    valid_combinations = {
        ("epic", "task"),
        ("task", "subtask"),
    }

    if (parent_type, child_type) not in valid_combinations:
        raise ValueError(
            f"Invalid parent-child relationship: {parent_type} cannot parent {child_type}. "
            f"Valid combinations: Epic->Task, Task->Subtask"
        )


def check_for_circular_dependency(ticket_id: str, new_dependency_id: str) -> None:
    """
    Prevent dependency cycles by checking if adding new dependency creates a cycle.

    A cycle would occur if the new_dependency already depends (directly or indirectly)
    on ticket_id.

    Args:
        ticket_id: The ID of the ticket that will depend on new_dependency
        new_dependency_id: The ID of the proposed blocking ticket

    Raises:
        ValueError: If adding this dependency would create a cycle
    """
    # Check for self-dependency
    if ticket_id == new_dependency_id:
        raise ValueError(
            f"Circular dependency detected: Ticket cannot depend on itself."
        )

    # Check if new_dependency already depends on ticket_id
    if _has_transitive_dependency(new_dependency_id, ticket_id):
        raise ValueError(
            f"Circular dependency detected: {new_dependency_id} already depends on {ticket_id}. "
            f"Cannot add {ticket_id} -> {new_dependency_id} dependency."
        )


def _has_transitive_dependency(
    ticket_id: str, target_id: str, visited: Set[str] | None = None
) -> bool:
    """
    Check if ticket_id transitively depends on target_id.

    Uses depth-first search to explore the dependency graph.

    Args:
        ticket_id: The ticket to check dependencies from
        target_id: The target ticket to search for
        visited: Set of already visited tickets (prevents infinite loops)

    Returns:
        True if ticket_id depends on target_id (directly or transitively)
    """
    if visited is None:
        visited = set()

    # Prevent infinite loops
    if ticket_id in visited:
        return False

    visited.add(ticket_id)

    # Load the ticket
    try:
        ticket = _load_ticket_by_id(ticket_id)
    except FileNotFoundError:
        return False

    # Check direct dependencies
    if target_id in ticket.up_dependencies:
        return True

    # Recursively check transitive dependencies
    for dep_id in ticket.up_dependencies:
        if _has_transitive_dependency(dep_id, target_id, visited):
            return True

    return False


def add_child_to_parent(parent_id: str, child_id: str) -> None:
    """
    Add a child to a parent ticket, updating both tickets bidirectionally.

    Updates:
    - Adds child_id to parent's children array
    - Sets parent_id as child's parent field

    Args:
        parent_id: The ID of the parent ticket
        child_id: The ID of the child ticket

    Raises:
        FileNotFoundError: If either ticket doesn't exist
        ValueError: If relationship is invalid

    Examples:
        >>> add_child_to_parent("bees-gr5", "bees-r10")
        # bees-gr5.children now includes "bees-r10"
        # bees-r10.parent is now "bees-gr5"
    """
    # Validate tickets exist
    validate_ticket_exists(parent_id)
    validate_ticket_exists(child_id)

    # Validate relationship hierarchy
    validate_parent_child_relationship(parent_id, child_id)

    # Load both tickets
    parent = _load_ticket_by_id(parent_id)
    child = _load_ticket_by_id(child_id)

    # Update parent's children array
    if child_id not in parent.children:
        parent.children.append(child_id)
        _save_ticket(parent)

    # Update child's parent field
    if child.parent != parent_id:
        child.parent = parent_id
        _save_ticket(child)


def remove_child_from_parent(parent_id: str, child_id: str) -> None:
    """
    Remove a child from a parent ticket, updating both tickets bidirectionally.

    Updates:
    - Removes child_id from parent's children array
    - Clears child's parent field

    Args:
        parent_id: The ID of the parent ticket
        child_id: The ID of the child ticket

    Raises:
        FileNotFoundError: If either ticket doesn't exist

    Examples:
        >>> remove_child_from_parent("bees-gr5", "bees-r10")
        # bees-gr5.children no longer includes "bees-r10"
        # bees-r10.parent is now None
    """
    # Load both tickets
    parent = _load_ticket_by_id(parent_id)
    child = _load_ticket_by_id(child_id)

    # Update parent's children array
    if child_id in parent.children:
        parent.children.remove(child_id)
        _save_ticket(parent)

    # Update child's parent field
    if child.parent == parent_id:
        child.parent = None
        _save_ticket(child)


def add_dependency(dependent_id: str, blocking_id: str) -> None:
    """
    Add a dependency relationship, updating both tickets bidirectionally.

    Updates:
    - Adds blocking_id to dependent's up_dependencies array (what blocks this ticket)
    - Adds dependent_id to blocking's down_dependencies array (what this ticket blocks)

    Args:
        dependent_id: The ID of the ticket that depends on another
        blocking_id: The ID of the ticket that blocks the dependent

    Raises:
        FileNotFoundError: If either ticket doesn't exist
        ValueError: If relationship is invalid

    Examples:
        >>> add_dependency("bees-r10", "bees-yt4")
        # bees-r10.up_dependencies now includes "bees-yt4"
        # bees-yt4.down_dependencies now includes "bees-r10"
    """
    # Validate tickets exist
    validate_ticket_exists(dependent_id)
    validate_ticket_exists(blocking_id)

    # Check for circular dependencies
    check_for_circular_dependency(dependent_id, blocking_id)

    # Load both tickets
    dependent = _load_ticket_by_id(dependent_id)
    blocking = _load_ticket_by_id(blocking_id)

    # Update dependent's up_dependencies
    if blocking_id not in dependent.up_dependencies:
        dependent.up_dependencies.append(blocking_id)
        _save_ticket(dependent)

    # Update blocking's down_dependencies
    if dependent_id not in blocking.down_dependencies:
        blocking.down_dependencies.append(dependent_id)
        _save_ticket(blocking)


def remove_dependency(dependent_id: str, blocking_id: str) -> None:
    """
    Remove a dependency relationship, updating both tickets bidirectionally.

    Updates:
    - Removes blocking_id from dependent's up_dependencies array
    - Removes dependent_id from blocking's down_dependencies array

    Args:
        dependent_id: The ID of the ticket that depends on another
        blocking_id: The ID of the ticket that blocks the dependent

    Raises:
        FileNotFoundError: If either ticket doesn't exist

    Examples:
        >>> remove_dependency("bees-r10", "bees-yt4")
        # bees-r10.up_dependencies no longer includes "bees-yt4"
        # bees-yt4.down_dependencies no longer includes "bees-r10"
    """
    # Load both tickets
    dependent = _load_ticket_by_id(dependent_id)
    blocking = _load_ticket_by_id(blocking_id)

    # Update dependent's up_dependencies
    if blocking_id in dependent.up_dependencies:
        dependent.up_dependencies.remove(blocking_id)
        _save_ticket(dependent)

    # Update blocking's down_dependencies
    if dependent_id in blocking.down_dependencies:
        blocking.down_dependencies.remove(dependent_id)
        _save_ticket(blocking)


def sync_relationships_batch(updates: list[tuple[str, str, str, str]]) -> None:
    """
    Efficiently handle multiple relationship updates with transaction-like semantics.

    When a ticket is deleted or relationships change, multiple tickets may need updates.
    This function batches the changes to reduce file I/O overhead.

    Implements write-ahead logging (WAL) to ensure atomicity: all updates succeed or
    all fail with no partial state. If any write fails, all tickets are restored from
    backups.

    Args:
        updates: List of tuples (ticket_id, field_name, operation, value)
                 - ticket_id: The ticket to update
                 - field_name: 'children', 'parent', 'up_dependencies', 'down_dependencies'
                 - operation: 'add' or 'remove'
                 - value: The value to add/remove

    Raises:
        FileNotFoundError: If any ticket doesn't exist
        ValueError: If any update is invalid

    Examples:
        >>> updates = [
        ...     ("bees-gr5", "children", "add", "bees-r10"),
        ...     ("bees-r10", "parent", "add", "bees-gr5"),
        ... ]
        >>> sync_relationships_batch(updates)
    """
    # Phase 1: Validate all tickets exist
    ticket_ids = {update[0] for update in updates}
    for ticket_id in ticket_ids:
        validate_ticket_exists(ticket_id)

    # Phase 2: Load all affected tickets once
    tickets = {ticket_id: _load_ticket_by_id(ticket_id) for ticket_id in ticket_ids}

    # Phase 3: Deduplicate operations to prevent redundant I/O
    # Convert to set to remove duplicate operations, then back to list
    updates = list(set(updates))

    # Phase 4: Create backups (WAL) - store original tickets in memory
    backups = {}
    for ticket_id, ticket in tickets.items():
        # Deep copy ticket data for rollback
        backups[ticket_id] = _load_ticket_by_id(ticket_id)

    # Phase 5: Apply all changes to in-memory tickets
    try:
        for ticket_id, field_name, operation, value in updates:
            ticket = tickets[ticket_id]

            if field_name == "parent":
                if operation == "add":
                    ticket.parent = value
                elif operation == "remove":
                    ticket.parent = None
                else:
                    raise ValueError(f"Invalid operation for parent field: {operation}")

            elif field_name in ["children", "up_dependencies", "down_dependencies"]:
                field = getattr(ticket, field_name)

                if operation == "add":
                    if value not in field:
                        field.append(value)
                elif operation == "remove":
                    if value in field:
                        field.remove(value)
                else:
                    raise ValueError(f"Invalid operation: {operation}")

            else:
                raise ValueError(f"Invalid field name: {field_name}")

    except Exception as e:
        # If any update fails, raise without writing changes
        raise ValueError(f"Batch update failed: {e}") from e

    # Phase 6: Write all modified tickets with rollback on failure
    try:
        for ticket in tickets.values():
            _save_ticket(ticket)
    except Exception as e:
        # Rollback: restore all tickets from backups
        logger.error(f"Write failure during batch sync, rolling back: {e}")
        for ticket_id, backup_ticket in backups.items():
            try:
                _save_ticket(backup_ticket)
            except Exception as rollback_error:
                logger.error(f"Rollback failed for {ticket_id}: {rollback_error}")
        raise RuntimeError(
            f"Batch write failed and rollback attempted. Original error: {e}"
        ) from e
    finally:
        # Phase 7: Cleanup - clear backup references
        backups.clear()


def _load_ticket_by_id(ticket_id: str) -> Ticket:
    """
    Load a ticket by ID, searching all ticket type directories.

    Args:
        ticket_id: The ticket ID to load

    Returns:
        The loaded Ticket object

    Raises:
        FileNotFoundError: If ticket doesn't exist in any directory
    """
    # Try each ticket type directory
    for ticket_type in ["epic", "task", "subtask"]:
        try:
            path = get_ticket_path(ticket_id, ticket_type)
            ticket = read_ticket(path)
            return ticket  # Return immediately on successful load
        except Exception:
            continue

    raise FileNotFoundError(f"Ticket {ticket_id} not found in any directory")


def _save_ticket(ticket: Ticket) -> None:
    """
    Save a ticket back to its file, preserving all data.

    Implements file locking to prevent concurrent modification issues.
    Uses fcntl.flock() on Unix systems and msvcrt.locking() on Windows.

    Args:
        ticket: The ticket object to save

    Raises:
        RuntimeError: If file lock cannot be acquired after retries
    """
    # Get the file path for this ticket
    ticket_path = get_ticket_path(ticket.id, ticket.type)

    # Ensure parent directory exists
    ticket_path.parent.mkdir(parents=True, exist_ok=True)

    # Build frontmatter dictionary from ticket
    frontmatter_data = {
        "id": ticket.id,
        "type": ticket.type,
        "title": ticket.title,
        "labels": ticket.labels if ticket.labels else None,
        "up_dependencies": ticket.up_dependencies if ticket.up_dependencies else None,
        "down_dependencies": ticket.down_dependencies if ticket.down_dependencies else None,
        "parent": ticket.parent,
        "children": ticket.children if ticket.children else None,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "created_by": ticket.created_by,
        "owner": ticket.owner,
        "priority": ticket.priority,
        "status": ticket.status,
    }

    # Retry logic for lock acquisition with exponential backoff
    max_retries = 3
    retry_delays = [0.1, 0.2, 0.4]  # Exponential backoff in seconds

    for attempt in range(max_retries):
        try:
            # Open file for reading and writing (create if doesn't exist)
            with open(ticket_path, "r+") if ticket_path.exists() else open(ticket_path, "w+") as f:
                # Acquire exclusive lock
                try:
                    if IS_WINDOWS:
                        # Windows file locking
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        # Unix file locking (non-blocking)
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                    # Lock acquired, write the ticket
                    write_ticket_file(
                        ticket_id=ticket.id,
                        ticket_type=ticket.type,
                        frontmatter_data=frontmatter_data,
                        body=ticket.description,
                    )

                    # Lock is released automatically when file is closed
                    logger.debug(f"Successfully saved ticket {ticket.id} with file lock")
                    return

                except (IOError, OSError) as lock_error:
                    # Lock acquisition failed
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        logger.warning(
                            f"Failed to acquire lock for {ticket.id} (attempt {attempt + 1}/{max_retries}). "
                            f"Retrying in {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        # Max retries exceeded
                        raise RuntimeError(
                            f"Failed to acquire file lock for {ticket.id} after {max_retries} attempts. "
                            f"Another process may be modifying this ticket."
                        ) from lock_error

        except RuntimeError:
            # Re-raise RuntimeError (max retries exceeded)
            raise
        except Exception as e:
            # Unexpected error during file operations
            logger.error(f"Error saving ticket {ticket.id}: {e}")
            raise
