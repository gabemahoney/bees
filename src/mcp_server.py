"""
MCP Server for Bees Ticket Management System

Provides FastMCP server infrastructure with tool registration for ticket operations.
"""

import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from fastmcp import FastMCP
from .ticket_factory import create_epic, create_task, create_subtask
from .reader import read_ticket
from .writer import write_ticket_file
from .paths import infer_ticket_type_from_id, get_ticket_path
from .query_storage import save_query, load_query, list_queries, validate_query
from .query_parser import QueryValidationError
from .pipeline import PipelineEvaluator
from .index_generator import generate_index

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Bees Ticket Management Server")

# Server state
_server_running = False


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


def start_server() -> Dict[str, Any]:
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

        return {
            "status": "running",
            "name": "Bees Ticket Management Server",
            "version": "0.1.0"
        }
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        _server_running = False
        raise


def stop_server() -> Dict[str, Any]:
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

        return {
            "status": "stopped",
            "name": "Bees Ticket Management Server"
        }
    except Exception as e:
        logger.error(f"Failed to stop server: {e}")
        raise


def _health_check() -> Dict[str, Any]:
    """
    Check the health status of the MCP server.

    Returns:
        dict: Health status including server state and readiness
    """
    return {
        "status": "healthy" if _server_running else "stopped",
        "server_running": _server_running,
        "name": "Bees Ticket Management Server",
        "version": "0.1.0",
        "ready": _server_running
    }


# Register the health_check tool with FastMCP
health_check = mcp.tool()(_health_check)


# Tool stubs - implementations will be added in later tasks

def _create_ticket(
    ticket_type: str,
    title: str,
    description: str = "",
    parent: str | None = None,
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    labels: list[str] | None = None,
    owner: str | None = None,
    priority: int | None = None,
    status: str | None = None
) -> Dict[str, Any]:
    """
    Create a new ticket (epic, task, or subtask).

    Args:
        ticket_type: Type of ticket to create - must be 'epic', 'task', or 'subtask'
        title: Title of the ticket (required)
        description: Detailed description of the ticket
        parent: Parent ticket ID (required for subtasks, optional for tasks, not allowed for epics)
        children: List of child ticket IDs
        up_dependencies: List of ticket IDs that this ticket depends on (blocking tickets)
        down_dependencies: List of ticket IDs that depend on this ticket
        labels: List of label strings
        owner: Owner/assignee of the ticket
        priority: Priority level (typically 0-4)
        status: Status of the ticket (e.g., 'open', 'in_progress', 'completed')

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
                status=status or "open"
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
                status=status or "open"
            )
        elif ticket_type == "subtask":
            ticket_id = create_subtask(
                title=title,
                parent=parent,
                description=description,
                labels=labels,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                owner=owner,
                priority=priority,
                status=status or "open"
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


# Register the create_ticket tool with FastMCP
create_ticket = mcp.tool()(_create_ticket)


# Sentinel value to distinguish "not provided" from "explicitly set to None"
_UNSET = object()

def _update_ticket(
    ticket_id: str,
    title: str | None = _UNSET,
    description: str | None = _UNSET,
    parent: str | None = _UNSET,
    children: list[str] | None = _UNSET,
    up_dependencies: list[str] | None = _UNSET,
    down_dependencies: list[str] | None = _UNSET,
    labels: list[str] | None = _UNSET,
    owner: str | None = _UNSET,
    priority: int | None = _UNSET,
    status: str | None = _UNSET
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

    Returns:
        dict: Updated ticket information

    Raises:
        ValueError: If ticket_id doesn't exist or validation fails

    Note:
        When updating relationships (parent, children, dependencies), the change
        is automatically reflected bidirectionally in related tickets.
    """
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

    if children is not _UNSET:
        for child_id in children:
            child_type = infer_ticket_type_from_id(child_id)
            if not child_type:
                error_msg = f"Child ticket does not exist: {child_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if up_dependencies is not _UNSET:
        for dep_id in up_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if down_dependencies is not _UNSET:
        for dep_id in down_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Check for circular dependencies if both up and down are being updated
    if up_dependencies is not _UNSET and down_dependencies is not _UNSET:
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            error_msg = f"Circular dependency detected: ticket cannot both depend on and be depended on by the same tickets: {circular_deps}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Update basic fields (non-relationship fields)
    if title is not _UNSET:
        if not title.strip():
            error_msg = "Ticket title cannot be empty"
            logger.error(error_msg)
            raise ValueError(error_msg)
        ticket.title = title

    if description is not _UNSET:
        ticket.description = description

    if labels is not _UNSET:
        ticket.labels = labels

    if owner is not _UNSET:
        ticket.owner = owner

    if priority is not _UNSET:
        ticket.priority = priority

    if status is not _UNSET:
        ticket.status = status

    # Handle relationship updates with bidirectional consistency
    # Track old relationships to determine what changed
    old_parent = ticket.parent
    old_children = set(ticket.children or [])
    old_up_deps = set(ticket.up_dependencies or [])
    old_down_deps = set(ticket.down_dependencies or [])

    # Update relationship fields if provided
    if parent is not _UNSET:
        ticket.parent = parent if parent else None
    if children is not _UNSET:
        ticket.children = children
    if up_dependencies is not _UNSET:
        ticket.up_dependencies = up_dependencies
    if down_dependencies is not _UNSET:
        ticket.down_dependencies = down_dependencies

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


# Register the update_ticket tool with FastMCP
update_ticket = mcp.tool()(_update_ticket)


def _delete_ticket(
    ticket_id: str,
    cascade: bool = False
) -> Dict[str, Any]:
    """
    Delete a ticket and clean up relationships in related tickets.

    Args:
        ticket_id: ID of the ticket to delete (required)
        cascade: If True, recursively delete all child tickets. If False and ticket
                has children, the operation will fail or unlink children (default: False)

    Returns:
        dict: Deletion status and information about cleaned relationships

    Raises:
        ValueError: If ticket_id doesn't exist or deletion validation fails

    Note:
        When a ticket is deleted:
        - It's removed from parent's children array
        - It's removed from all dependency arrays in related tickets
        - If cascade=True, all child tickets are recursively deleted
        - If cascade=False and children exist, deletion may be prevented
    """
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

    # Handle children tickets based on cascade parameter
    if ticket.children:
        if cascade:
            # Recursively delete all child tickets
            for child_id in ticket.children:
                try:
                    _delete_ticket(child_id, cascade=True)
                    logger.info(f"Cascade deleted child ticket: {child_id}")
                except Exception as e:
                    logger.warning(f"Failed to cascade delete child {child_id}: {e}")
        else:
            # Unlink children by removing parent reference
            for child_id in ticket.children:
                _remove_parent_from_child(child_id)
                logger.info(f"Unlinked child {child_id} from parent {ticket_id}")

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


# Register the delete_ticket tool with FastMCP
delete_ticket = mcp.tool()(_delete_ticket)


def _add_named_query(
    name: str,
    query_yaml: str,
    validate: bool = True
) -> Dict[str, Any]:
    """
    Register a new named query for reuse.

    Args:
        name: Name for the query (used to execute it later)
        query_yaml: YAML string representing the query structure
        validate: Whether to validate query (set False for parameterized queries with placeholders)

    Returns:
        dict: Success status and query information

    Raises:
        ValueError: If query structure is invalid or name is invalid

    Example:
        query_yaml = '''
        - - type=task
          - label~beta
        - - parent
        '''
    """
    # Validate name is not empty
    if not name or not name.strip():
        error_msg = "Query name cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate and save query
    try:
        # This will validate structure and raise QueryValidationError if invalid (unless validate=False)
        save_query(name.strip(), query_yaml, validate)
        logger.info(f"Successfully registered named query: {name}")

        return {
            "status": "success",
            "query_name": name.strip(),
            "message": f"Query '{name}' registered successfully"
        }

    except QueryValidationError as e:
        error_msg = f"Invalid query structure: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to save query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


# Register the add_named_query tool with FastMCP
add_named_query = mcp.tool()(_add_named_query)


def _execute_query(
    query_name: str,
    params: str | None = None
) -> Dict[str, Any]:
    """
    Execute a named query with optional parameter substitution.

    Args:
        query_name: Name of the registered query to execute
        params: JSON string of parameters for variable substitution (e.g., '{"status": "open", "label": "beta"}')

    Returns:
        dict: Query results with list of matching ticket IDs and metadata

    Raises:
        ValueError: If query name not found or execution fails

    Example:
        execute_query("open_tasks", '{"status": "open"}')
        execute_query("beta_work_items", '{"label": "beta"}')
    """
    # Load query by name
    try:
        stages = load_query(query_name)
    except KeyError:
        error_msg = f"Query not found: {query_name}"
        logger.error(error_msg)
        available = list_queries()
        if available:
            error_msg += f". Available queries: {', '.join(available)}"
        else:
            error_msg += ". No queries registered yet."
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to load query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Perform parameter substitution if params provided
    if params:
        import json
        try:
            params_dict = json.loads(params)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in params: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        stages = _substitute_query_params(stages, params_dict)

    # Execute query using pipeline evaluator
    try:
        evaluator = PipelineEvaluator()
        result_ids = evaluator.execute_query(stages)

        logger.info(f"Query '{query_name}' returned {len(result_ids)} tickets")

        return {
            "status": "success",
            "query_name": query_name,
            "result_count": len(result_ids),
            "ticket_ids": sorted(result_ids)
        }

    except Exception as e:
        error_msg = f"Failed to execute query '{query_name}': {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def _substitute_query_params(stages: list, params: Dict[str, str]) -> list:
    """Substitute parameters in query stages.

    Replaces {param_name} placeholders with actual values.

    Args:
        stages: List of stages with potential placeholders
        params: Dictionary of parameter name -> value mappings

    Returns:
        List of stages with substituted values

    Raises:
        ValueError: If required parameter is missing
    """
    import re

    substituted_stages = []

    for stage in stages:
        substituted_stage = []
        for term in stage:
            # Find all {param} placeholders in term
            placeholders = re.findall(r'\{(\w+)\}', term)

            # Check all required params are provided
            for placeholder in placeholders:
                if placeholder not in params:
                    raise ValueError(
                        f"Missing required parameter: {placeholder}. "
                        f"Provided: {', '.join(params.keys())}"
                    )

            # Substitute all placeholders
            substituted_term = term
            for param_name, param_value in params.items():
                substituted_term = substituted_term.replace(
                    f"{{{param_name}}}",
                    str(param_value)
                )

            substituted_stage.append(substituted_term)

        substituted_stages.append(substituted_stage)

    return substituted_stages


# Register the execute_query tool with FastMCP
execute_query = mcp.tool()(_execute_query)


def _generate_index(
    status: str | None = None,
    type: str | None = None
) -> Dict[str, Any]:
    """
    Generate markdown index of all tickets with optional filters.

    Scans the tickets directory and creates a formatted markdown index.
    Optionally filters tickets by status and/or type.

    Args:
        status: Optional status filter (e.g., 'open', 'completed')
        type: Optional type filter (e.g., 'epic', 'task', 'subtask')

    Returns:
        dict: Response with status and generated markdown index

    Example:
        result = _generate_index()
        result = _generate_index(status='open')
        result = _generate_index(type='epic')
        result = _generate_index(status='open', type='task')
    """
    try:
        index_markdown = generate_index(
            status_filter=status,
            type_filter=type
        )
        logger.info(f"Successfully generated ticket index (status={status}, type={type})")
        return {
            "status": "success",
            "markdown": index_markdown
        }
    except Exception as e:
        error_msg = f"Failed to generate index: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


# Register the generate_index tool with FastMCP
generate_index_tool = mcp.tool()(_generate_index)


if __name__ == "__main__":
    logger.info("Running Bees MCP Server directly")
    start_server()
    mcp.run()
