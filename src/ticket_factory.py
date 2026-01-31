"""Factory functions for creating tickets with YAML frontmatter."""

from datetime import datetime
from pathlib import Path

from .id_utils import generate_unique_ticket_id, extract_existing_ids_from_directory
from .paths import TICKETS_DIR
from .types import TicketType
from .writer import write_ticket_file


def create_epic(
    title: str,
    description: str = "",
    labels: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    owner: str | None = None,
    priority: int | None = None,
    status: str = "open",
    ticket_id: str | None = None,
) -> str:
    """
    Create an Epic ticket with YAML frontmatter.

    Args:
        title: Epic title (required)
        description: Epic description
        labels: List of label strings
        up_dependencies: List of ticket IDs that block this epic
        down_dependencies: List of ticket IDs that this epic blocks
        owner: Owner email or username
        priority: Priority level (0-4)
        status: Status string (default: "open")
        ticket_id: Optional specific ID to use (auto-generated if not provided)

    Returns:
        The created ticket ID

    Raises:
        ValueError: If required fields are missing or invalid

    Examples:
        >>> epic_id = create_epic(
        ...     title="Implement Auth System",
        ...     description="Build user authentication",
        ...     labels=["security", "backend"],
        ... )
        >>> epic_id.startswith("bees-")
        True
    """
    if not title:
        raise ValueError("Epic title is required")

    # Generate unique ID if not provided
    if ticket_id is None:
        existing_ids = extract_existing_ids_from_directory(TICKETS_DIR)
        ticket_id = generate_unique_ticket_id(existing_ids)

    # Build frontmatter data
    frontmatter_data = {
        "id": ticket_id,
        "type": "epic",
        "title": title,
        "description": description,
        "labels": labels or [],
        "up_dependencies": up_dependencies or [],
        "down_dependencies": down_dependencies or [],
        "status": status,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }

    # Add optional fields
    if owner:
        frontmatter_data["owner"] = owner
    if priority is not None:
        frontmatter_data["priority"] = priority

    # Write ticket file
    write_ticket_file(
        ticket_id=ticket_id,
        ticket_type="epic",
        frontmatter_data=frontmatter_data,
        body=description,
    )

    return ticket_id


def create_task(
    title: str,
    description: str = "",
    parent: str | None = None,
    labels: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    owner: str | None = None,
    priority: int | None = None,
    status: str = "open",
    ticket_id: str | None = None,
) -> str:
    """
    Create a Task ticket with YAML frontmatter.

    Args:
        title: Task title (required)
        description: Task description
        parent: Parent epic ID (optional for tasks)
        labels: List of label strings
        up_dependencies: List of ticket IDs that block this task
        down_dependencies: List of ticket IDs that this task blocks
        owner: Owner email or username
        priority: Priority level (0-4)
        status: Status string (default: "open")
        ticket_id: Optional specific ID to use (auto-generated if not provided)

    Returns:
        The created ticket ID

    Raises:
        ValueError: If required fields are missing or invalid

    Examples:
        >>> task_id = create_task(
        ...     title="Build login API",
        ...     parent="bees-250",
        ...     labels=["backend"],
        ... )
        >>> task_id.startswith("bees-")
        True
    """
    if not title:
        raise ValueError("Task title is required")

    # Generate unique ID if not provided
    if ticket_id is None:
        existing_ids = extract_existing_ids_from_directory(TICKETS_DIR)
        ticket_id = generate_unique_ticket_id(existing_ids)

    # Build frontmatter data
    frontmatter_data = {
        "id": ticket_id,
        "type": "task",
        "title": title,
        "description": description,
        "labels": labels or [],
        "up_dependencies": up_dependencies or [],
        "down_dependencies": down_dependencies or [],
        "status": status,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }

    # Add optional fields
    if parent:
        frontmatter_data["parent"] = parent
    if owner:
        frontmatter_data["owner"] = owner
    if priority is not None:
        frontmatter_data["priority"] = priority

    # Write ticket file
    write_ticket_file(
        ticket_id=ticket_id,
        ticket_type="task",
        frontmatter_data=frontmatter_data,
        body=description,
    )

    return ticket_id


def create_subtask(
    title: str,
    parent: str,
    description: str = "",
    labels: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    owner: str | None = None,
    priority: int | None = None,
    status: str = "open",
    ticket_id: str | None = None,
) -> str:
    """
    Create a Subtask ticket with YAML frontmatter.

    Args:
        title: Subtask title (required)
        parent: Parent task ID (required for subtasks)
        description: Subtask description
        labels: List of label strings
        up_dependencies: List of ticket IDs that block this subtask
        down_dependencies: List of ticket IDs that this subtask blocks
        owner: Owner email or username
        priority: Priority level (0-4)
        status: Status string (default: "open")
        ticket_id: Optional specific ID to use (auto-generated if not provided)

    Returns:
        The created ticket ID

    Raises:
        ValueError: If required fields are missing or invalid

    Examples:
        >>> subtask_id = create_subtask(
        ...     title="Write login endpoint",
        ...     parent="bees-abc",
        ...     labels=["backend"],
        ... )
        >>> subtask_id.startswith("bees-")
        True
    """
    if not title:
        raise ValueError("Subtask title is required")
    if not parent:
        raise ValueError("Subtask parent is required")

    # Generate unique ID if not provided
    if ticket_id is None:
        existing_ids = extract_existing_ids_from_directory(TICKETS_DIR)
        ticket_id = generate_unique_ticket_id(existing_ids)

    # Build frontmatter data
    frontmatter_data = {
        "id": ticket_id,
        "type": "subtask",
        "title": title,
        "description": description,
        "parent": parent,
        "labels": labels or [],
        "up_dependencies": up_dependencies or [],
        "down_dependencies": down_dependencies or [],
        "status": status,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }

    # Add optional fields
    if owner:
        frontmatter_data["owner"] = owner
    if priority is not None:
        frontmatter_data["priority"] = priority

    # Write ticket file
    write_ticket_file(
        ticket_id=ticket_id,
        ticket_type="subtask",
        frontmatter_data=frontmatter_data,
        body=description,
    )

    return ticket_id
