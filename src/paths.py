"""Path resolution utilities for ticket file management."""

import os
from pathlib import Path

from .types import TicketType



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


def get_ticket_directory(ticket_type: TicketType, hive_name: str | None = None) -> Path:
    """
    Get the directory path for a given ticket type within a hive.

    NOTE: This function is deprecated for most use cases. Use get_ticket_path()
    with a hive-prefixed ticket ID instead.

    Args:
        ticket_type: The type of ticket ("epic", "task", or "subtask")
        hive_name: Name of the hive (required)

    Returns:
        Path object pointing to the appropriate subdirectory in the hive

    Raises:
        ValueError: If ticket_type is not valid or hive_name is not provided

    Examples:
        >>> get_ticket_directory("epic", "backend")
        PosixPath('/path/to/backend/epics')
    """
    valid_types = {"epic", "task", "subtask"}

    if ticket_type not in valid_types:
        raise ValueError(
            f"Invalid ticket type: {ticket_type}. Must be one of {valid_types}"
        )

    if not hive_name:
        raise ValueError(
            "hive_name is required. Legacy tickets/ directory is no longer supported."
        )

    # Map ticket type to subdirectory (plural form)
    type_to_dir = {
        "epic": "epics",
        "task": "tasks",
        "subtask": "subtasks"
    }

    return Path.cwd() / hive_name / type_to_dir[ticket_type]


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

    # Require hive-prefixed ID
    if not hive_name:
        raise ValueError(
            f"Invalid ticket ID '{ticket_id}': must have hive prefix (e.g., 'hive_name.bees-abc'). "
            f"Legacy unprefixed IDs are no longer supported."
        )

    # Hive-prefixed ID: use hive-specific directory
    # Path structure: /path/to/{hive_name}/epics/{hive_name}.bees-abc1.md
    base_dir = Path.cwd() / hive_name

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


def ensure_ticket_directory_exists(ticket_type: TicketType, hive_name: str | None = None) -> None:
    """
    Ensure the directory for a ticket type exists within a hive, creating it if necessary.

    NOTE: This function is deprecated. The write_ticket_file() function in writer.py
    automatically creates directories as needed using target_path.parent.mkdir().

    Args:
        ticket_type: The type of ticket ("epic", "task", or "subtask")
        hive_name: Name of the hive (required)

    Raises:
        ValueError: If ticket_type is not valid or hive_name is not provided
    """
    directory = get_ticket_directory(ticket_type, hive_name)
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

    # Require hive-prefixed ID
    if not hive_name:
        return None

    # Hive-prefixed ID: check hive-specific directories
    base_dir = Path.cwd() / hive_name

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




def list_tickets(ticket_type: TicketType | None = None) -> list[Path]:
    """
    List all ticket files from all configured hives, optionally filtered by type.

    Scans all hive directories defined in .bees/config.json for ticket files.

    Args:
        ticket_type: Optional ticket type to filter by. If None, returns all tickets.

    Returns:
        List of Path objects pointing to ticket markdown files across all hives

    Examples:
        >>> list_tickets("epic")
        [PosixPath('/path/to/backend/epics/backend.bees-250.md'), ...]

        >>> list_tickets()  # All tickets from all hives
        [PosixPath('backend/epics/backend.bees-250.md'), ...]
    """
    from .config import load_bees_config

    all_tickets = []

    # Load hive configuration
    config = load_bees_config()

    if not config or not config.hives:
        # No hives configured - return empty list
        return []

    # Map ticket type to subdirectory (plural form)
    type_to_dir = {
        "epic": "epics",
        "task": "tasks",
        "subtask": "subtasks"
    }

    # Iterate all hives
    for hive_name, hive_config in config.hives.items():
        hive_path = Path(hive_config.path)

        if not hive_path.exists():
            continue

        # Determine which ticket types to scan
        if ticket_type:
            types_to_scan = [ticket_type]
        else:
            types_to_scan = ["epic", "task", "subtask"]

        # Scan each ticket type directory
        for ttype in types_to_scan:
            ticket_dir = hive_path / type_to_dir[ttype]
            if ticket_dir.exists():
                all_tickets.extend(ticket_dir.glob("*.md"))

    return sorted(all_tickets)
