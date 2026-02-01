"""Path resolution utilities for ticket file management."""

import os
from pathlib import Path

from .types import TicketType

# Base directory for all tickets - points to consuming project's /tickets directory
# This assumes the consuming project has a /tickets directory in its root
TICKETS_DIR = Path.cwd() / "tickets"


def _parse_ticket_id_for_path(ticket_id: str) -> tuple[str, str]:
    """
    Parse ticket ID to extract hive name and base ID for path resolution.

    This is a local copy of parse_ticket_id() to avoid circular imports
    between paths.py and mcp_server.py.

    Args:
        ticket_id: Ticket ID string (e.g., 'backend.bees-abc1' or 'bees-abc1')

    Returns:
        tuple[str, str]: (hive_name, base_id) where hive_name is empty string for legacy IDs

    Raises:
        ValueError: If ticket_id is None or empty string
    """
    if ticket_id is None:
        raise ValueError("ticket_id cannot be None")

    if not ticket_id or not ticket_id.strip():
        raise ValueError("ticket_id cannot be empty")

    # Split on first dot only
    if '.' in ticket_id:
        hive_name, _, base_id = ticket_id.partition('.')
        return (hive_name, base_id)
    else:
        # Legacy format without hive prefix
        return ('', ticket_id)


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

    Supports both hive-prefixed IDs (hive_name.bees-abc1) and legacy IDs (bees-abc1).
    For hive-prefixed IDs, constructs paths to hive-specific directories.
    For legacy IDs, uses the default tickets directory.

    Args:
        ticket_id: The ticket ID (e.g., "backend.bees-250" or "bees-250")
        ticket_type: The type of ticket ("epic", "task", or "subtask")

    Returns:
        Path object pointing to the ticket's markdown file

    Raises:
        ValueError: If ticket_type is not valid or ticket_id is empty

    Examples:
        >>> get_ticket_path("backend.bees-250", "epic")
        PosixPath('/path/to/backend/epics/backend.bees-250.md')
        >>> get_ticket_path("bees-250", "epic")
        PosixPath('/path/to/tickets/epics/bees-250.md')
    """
    if not ticket_id:
        raise ValueError("ticket_id cannot be empty")

    # Parse ticket ID to extract hive name
    hive_name, base_id = _parse_ticket_id_for_path(ticket_id)

    # Determine base directory based on whether this is a hive-prefixed ID
    if hive_name:
        # Hive-prefixed ID: use hive-specific directory
        # Path structure: /path/to/{hive_name}/epics/{hive_name}.bees-abc1.md
        base_dir = Path.cwd() / hive_name
    else:
        # Legacy ID: use default tickets directory
        base_dir = TICKETS_DIR

    # Map ticket type to subdirectory (plural form)
    type_to_dir = {
        "epic": "epics",
        "task": "tasks",
        "subtask": "subtasks"
    }

    if ticket_type not in type_to_dir:
        raise ValueError(
            f"Invalid ticket type: {ticket_type}. Must be one of {set(type_to_dir.keys())}"
        )

    directory = base_dir / type_to_dir[ticket_type]
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

    Supports both hive-prefixed IDs (hive_name.bees-abc1) and legacy IDs (bees-abc1).
    Uses parsed hive name to route to correct hive directory.

    Args:
        ticket_id: The ticket ID (e.g., "backend.bees-250" or "bees-250")

    Returns:
        The ticket type ('epic', 'task', or 'subtask') if found, None if not found

    Examples:
        >>> infer_ticket_type_from_id("backend.bees-250")
        'epic'

        >>> infer_ticket_type_from_id("bees-250")
        'epic'

        >>> infer_ticket_type_from_id("nonexistent-id")
        None
    """
    if not ticket_id:
        return None

    # Parse ticket ID to extract hive name
    hive_name, base_id = _parse_ticket_id_for_path(ticket_id)

    # Determine base directory based on whether this is a hive-prefixed ID
    if hive_name:
        # Hive-prefixed ID: check hive-specific directories
        base_dir = Path.cwd() / hive_name
    else:
        # Legacy ID: check default tickets directory
        base_dir = TICKETS_DIR

    # Map ticket type to subdirectory (plural form)
    type_to_dir = {
        "epic": "epics",
        "task": "tasks",
        "subtask": "subtasks"
    }

    # Check each ticket type directory
    for ticket_type, subdir in type_to_dir.items():
        directory = base_dir / subdir
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
