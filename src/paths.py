"""Path resolution utilities for ticket file management."""

import os
from pathlib import Path

from .types import TicketType

# Base directory for all tickets - points to consuming project's /tickets directory
# This assumes the consuming project has a /tickets directory in its root
TICKETS_DIR = Path.cwd() / "tickets"


def get_ticket_directory(ticket_type: TicketType) -> Path:
    """
    Get the directory path for a given ticket type.

    Args:
        ticket_type: The type of ticket ("epic", "task", or "subtask")

    Returns:
        Path object pointing to the appropriate subdirectory

    Raises:
        ValueError: If ticket_type is not one of the valid types

    Examples:
        >>> get_ticket_directory("epic")
        PosixPath('/path/to/tickets/epics')
    """
    valid_types = {"epic", "task", "subtask"}

    if ticket_type not in valid_types:
        raise ValueError(
            f"Invalid ticket type: {ticket_type}. Must be one of {valid_types}"
        )

    # Map ticket type to subdirectory (plural form)
    type_to_dir = {
        "epic": "epics",
        "task": "tasks",
        "subtask": "subtasks"
    }

    return TICKETS_DIR / type_to_dir[ticket_type]


def get_ticket_path(ticket_id: str, ticket_type: TicketType) -> Path:
    """
    Get the full file path for a ticket based on its ID and type.

    Args:
        ticket_id: The ticket ID (e.g., "bees-250")
        ticket_type: The type of ticket ("epic", "task", or "subtask")

    Returns:
        Path object pointing to the ticket's markdown file

    Raises:
        ValueError: If ticket_type is not valid or ticket_id is empty

    Examples:
        >>> get_ticket_path("bees-250", "epic")
        PosixPath('/path/to/tickets/epics/bees-250.md')
    """
    if not ticket_id:
        raise ValueError("ticket_id cannot be empty")

    directory = get_ticket_directory(ticket_type)
    return directory / f"{ticket_id}.md"


def ensure_ticket_directory_exists(ticket_type: TicketType) -> None:
    """
    Ensure the directory for a ticket type exists, creating it if necessary.

    Args:
        ticket_type: The type of ticket ("epic", "task", or "subtask")

    Raises:
        ValueError: If ticket_type is not valid
    """
    directory = get_ticket_directory(ticket_type)
    directory.mkdir(parents=True, exist_ok=True)


def infer_ticket_type_from_id(ticket_id: str) -> TicketType | None:
    """
    Infer ticket type from its ID by checking which directory contains the ticket file.

    Args:
        ticket_id: The ticket ID (e.g., "bees-250")

    Returns:
        The ticket type ('epic', 'task', or 'subtask') if found, None if not found

    Examples:
        >>> infer_ticket_type_from_id("bees-250")
        'epic'

        >>> infer_ticket_type_from_id("nonexistent-id")
        None
    """
    if not ticket_id:
        return None

    # Check each ticket type directory
    for ticket_type in ["epic", "task", "subtask"]:
        directory = get_ticket_directory(ticket_type)
        ticket_path = directory / f"{ticket_id}.md"
        if ticket_path.exists():
            return ticket_type

    return None


def get_index_path() -> Path:
    """
    Get the path to the index.md file.

    Returns:
        Path object pointing to index.md in the tickets directory

    Examples:
        >>> get_index_path()
        PosixPath('/path/to/tickets/index.md')
    """
    return TICKETS_DIR / "index.md"


def list_tickets(ticket_type: TicketType | None = None) -> list[Path]:
    """
    List all ticket files, optionally filtered by type.

    Args:
        ticket_type: Optional ticket type to filter by. If None, returns all tickets.

    Returns:
        List of Path objects pointing to ticket markdown files

    Examples:
        >>> list_tickets("epic")
        [PosixPath('/path/to/tickets/epics/bees-250.md'), ...]

        >>> list_tickets()  # All tickets from all types
        [PosixPath('tickets/epics/bees-250.md'), PosixPath('tickets/tasks/bees-jty.md'), ...]
    """
    if ticket_type:
        directory = get_ticket_directory(ticket_type)
        return sorted(directory.glob("*.md"))

    # Return all tickets from all types
    all_tickets = []
    for ttype in ["epic", "task", "subtask"]:
        directory = get_ticket_directory(ttype)
        if directory.exists():
            all_tickets.extend(directory.glob("*.md"))

    return sorted(all_tickets)
