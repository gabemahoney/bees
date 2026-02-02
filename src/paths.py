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
        ticket_id: Ticket ID string (must have hive prefix, e.g., 'backend.bees-abc1')

    Returns:
        tuple[str, str]: (hive_name, base_id)

    Raises:
        ValueError: If ticket_id is None, empty string, or lacks hive prefix (no dot separator)
    """
    if ticket_id is None:
        raise ValueError("ticket_id cannot be None")

    if not ticket_id or not ticket_id.strip():
        raise ValueError("ticket_id cannot be empty")

    # Require hive-prefixed format
    if '.' not in ticket_id:
        raise ValueError(
            f"Invalid ticket ID '{ticket_id}': must have hive prefix (e.g., 'hive_name.bees-abc'). "
            f"Legacy unprefixed IDs are no longer supported."
        )

    # Split on first dot only
    hive_name, _, base_id = ticket_id.partition('.')
    return (hive_name, base_id)


def get_ticket_path(ticket_id: str, ticket_type: TicketType) -> Path:
    """
    Get the full file path for a ticket based on its ID.

    All tickets are stored in flat structure at hive root directory.
    Ticket type is stored in YAML frontmatter, not in directory structure.

    Args:
        ticket_id: The ticket ID (e.g., "backend.bees-250")
        ticket_type: The type of ticket (no longer used for path resolution, kept for API compatibility)

    Returns:
        Path object pointing to the ticket's markdown file in hive root

    Raises:
        ValueError: If ticket_id is empty or hive not found in config

    Examples:
        >>> get_ticket_path("backend.bees-250", "epic")
        PosixPath('/path/to/backend/backend.bees-250.md')
    """
    if not ticket_id:
        raise ValueError("ticket_id cannot be empty")

    # Parse ticket ID to extract hive name (raises ValueError if unprefixed)
    hive_name, base_id = _parse_ticket_id_for_path(ticket_id)

    # Load config to get hive path
    from .config import load_bees_config
    config = load_bees_config()

    if not config or hive_name not in config.hives:
        raise ValueError(f"Hive '{hive_name}' not found in config")

    # Use hive root directory from config - flat storage, no subdirectories
    # Path structure: {hive_path}/{hive_name}.bees-abc1.md
    base_dir = Path(config.hives[hive_name].path)
    return base_dir / f"{ticket_id}.md"


def ensure_ticket_directory_exists(hive_name: str) -> None:
    """
    Ensure the hive root directory exists, creating it if necessary.

    With flat storage, all tickets are stored in hive root, so we only need
    to ensure the hive directory itself exists (no type-specific subdirectories).

    Args:
        hive_name: Name of the hive (required)

    Raises:
        ValueError: If hive_name is not provided
    """
    if not hive_name:
        raise ValueError("hive_name is required")

    hive_dir = Path.cwd() / hive_name
    hive_dir.mkdir(parents=True, exist_ok=True)


def infer_ticket_type_from_id(ticket_id: str) -> TicketType | None:
    """
    Infer ticket type from its ID by reading YAML frontmatter from ticket file.

    With flat storage, all tickets are in hive root. Type is determined from
    the 'type' field in the YAML frontmatter.

    Requires hive-prefixed IDs (e.g., 'hive_name.bees-abc1').

    Args:
        ticket_id: The ticket ID (must have hive prefix, e.g., "backend.bees-250")

    Returns:
        The ticket type ('epic', 'task', or 'subtask') if found, None if not found

    Examples:
        >>> infer_ticket_type_from_id("backend.bees-250")
        'epic'

        >>> infer_ticket_type_from_id("nonexistent-id")
        None
    """
    if not ticket_id:
        return None

    try:
        # Parse ticket ID to extract hive name (raises ValueError if unprefixed)
        hive_name, base_id = _parse_ticket_id_for_path(ticket_id)
    except ValueError:
        # Invalid ticket ID format
        return None

    # Load config to get hive path
    from .config import load_bees_config
    config = load_bees_config()

    if not config or hive_name not in config.hives:
        return None

    # Check hive root directory for ticket file
    base_dir = Path(config.hives[hive_name].path)
    ticket_path = base_dir / f"{ticket_id}.md"

    if not ticket_path.exists():
        return None

    # Read YAML frontmatter to get type
    try:
        import yaml
        with open(ticket_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # Parse YAML frontmatter (between --- delimiters)
            if content.startswith('---\n'):
                parts = content.split('---\n', 2)
                if len(parts) >= 2:
                    frontmatter = yaml.safe_load(parts[1])
                    if isinstance(frontmatter, dict):
                        # Check for bees_version field to confirm it's a valid ticket
                        if 'bees_version' not in frontmatter:
                            return None
                        ticket_type = frontmatter.get('type')
                        if ticket_type in ('epic', 'task', 'subtask'):
                            return ticket_type
    except Exception:
        # If we can't read or parse the file, return None
        pass

    return None




def list_tickets(ticket_type: TicketType | None = None) -> list[Path]:
    """
    List all ticket files from all configured hives, optionally filtered by type.

    With flat storage, scans hive root directories (not subdirectories).
    If ticket_type is specified, filters by reading YAML frontmatter.

    Args:
        ticket_type: Optional ticket type to filter by. If None, returns all tickets.

    Returns:
        List of Path objects pointing to ticket markdown files across all hives

    Examples:
        >>> list_tickets("epic")
        [PosixPath('/path/to/backend/backend.bees-250.md'), ...]

        >>> list_tickets()  # All tickets from all hives
        [PosixPath('backend/backend.bees-250.md'), ...]
    """
    from .config import load_bees_config

    all_tickets = []

    # Load hive configuration
    config = load_bees_config()

    if not config or not config.hives:
        # No hives configured - return empty list
        return []

    # Iterate all hives
    for hive_name, hive_config in config.hives.items():
        hive_path = Path(hive_config.path)

        if not hive_path.exists():
            continue

        # Scan hive root for all .md files (flat storage, no subdirectories)
        # glob("*.md") only matches files directly in hive_path, not in subdirectories
        ticket_files = list(hive_path.glob("*.md"))

        # Explicitly skip /eggs and /evicted subdirectories (they should already be excluded by glob)
        excluded_dirs = {'eggs', 'evicted'}
        ticket_files = [f for f in ticket_files if f.parent.name not in excluded_dirs and f.parent == hive_path]

        # Check YAML frontmatter for bees_version and optionally filter by type
        import yaml
        for ticket_file in ticket_files:
            try:
                with open(ticket_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.startswith('---\n'):
                        parts = content.split('---\n', 2)
                        if len(parts) >= 2:
                            frontmatter = yaml.safe_load(parts[1])
                            if isinstance(frontmatter, dict):
                                # Only include files with bees_version field (valid tickets)
                                if 'bees_version' not in frontmatter:
                                    continue
                                # Filter by type if specified
                                if ticket_type is None or frontmatter.get('type') == ticket_type:
                                    all_tickets.append(ticket_file)
            except Exception:
                # Skip files we can't parse
                continue

    return sorted(all_tickets)
