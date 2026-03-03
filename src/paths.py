"""Path resolution utilities for ticket file management."""

import os
from collections.abc import Generator
from pathlib import Path

from .id_utils import is_ticket_id, normalize_hive_name
from .reader import get_ticket_type, read_ticket
from .types import TicketType


def iter_ticket_files(hive_root: Path) -> Generator[Path, None, None]:
    """Yield all ticket .md files in a hive using selective directory traversal.

    Only recurses into directories whose names match the ticket ID pattern,
    naturally excluding /cemetery, eggs/, .hive/, evicted/, and any future
    special directories.

    Yields:
        Path objects for files matching {ticket_id}/{ticket_id}.md pattern.
        Skips index.md files.
    """
    for dirpath, dirs, files in os.walk(hive_root):
        # Only recurse into ticket-ID subdirectories
        dirs[:] = sorted(d for d in dirs if is_ticket_id(d))

        dir_name = Path(dirpath).name
        if is_ticket_id(dir_name):
            md_name = f"{dir_name}.md"
            if md_name in files:
                yield Path(dirpath) / md_name


def iter_ticket_files_deep(hive_root: Path) -> Generator[Path, None, None]:
    """Yield all ticket .md files, including misplaced ones.

    Broader traversal for the linter: enters all directories except hidden
    ones (naturally excludes .hive/), finding tickets even in wrong locations
    or with non-standard directory names. Only yields files matching the
    {dirname}/{dirname}.md naming convention.

    Use iter_ticket_files() for normal operations on well-structured hives.
    Use this function when scanning for misplaced or invalid tickets.
    """
    for dirpath, dirs, files in os.walk(hive_root):
        # Skip hidden directories (.hive, etc.), evicted/, and /cemetery
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in ("evicted", "cemetery"))

        dir_name = Path(dirpath).name
        md_name = f"{dir_name}.md"
        if md_name in files:
            yield Path(dirpath) / md_name


def build_ticket_path_map(ticket_ids: set[str]) -> dict[str, tuple[str, Path]]:
    """Walk all hives once to find paths for multiple tickets.

    Returns {ticket_id: (hive_name, path)} for all found tickets.
    """
    from .config import load_bees_config

    config = load_bees_config()
    if not config or not config.hives:
        return {}
    result: dict[str, tuple[str, Path]] = {}
    needed = set(ticket_ids)
    for hive_name, hive_config in config.hives.items():
        if not needed:
            break
        hive_path = Path(hive_config.path)
        if not hive_path.exists():
            continue
        for tid in list(needed):
            candidate = compute_ticket_path(tid, hive_path)
            if candidate.exists():
                result[tid] = (hive_name, candidate)
                needed.discard(tid)
    return result


def compute_ticket_path(ticket_id: str, hive_root: Path) -> Path:
    """Compute the expected filesystem path for a ticket without any directory scan.

    Since child IDs encode the full parent hierarchy, the path is fully deterministic:

        b.abc        → hive_root/b.abc/b.abc.md
        t1.abc.de    → hive_root/b.abc/t1.abc.de/t1.abc.de.md
        t2.abc.de.fg → hive_root/b.abc/t1.abc.de/t2.abc.de.fg/t2.abc.de.fg.md

    No filesystem access is performed — call ``.exists()`` on the result to check.
    """
    if "." not in ticket_id:
        raise ValueError(f"Malformed ticket ID (no dot separator): {ticket_id!r}")
    dot_idx = ticket_id.index(".")
    prefix = ticket_id[:dot_idx]  # "b", "t1", "t2", …
    short_id = ticket_id[dot_idx + 1 :]  # "abc", "abc.de", "abc.de.fg", …
    segments = short_id.split(".")

    # Start at hive root, then descend through the bee directory
    path = hive_root / f"b.{segments[0]}"

    if prefix != "b":
        tier_num = int(prefix[1:])
        for level in range(1, tier_num + 1):
            level_id = f"t{level}." + ".".join(segments[: level + 1])
            path = path / level_id

    return path / f"{ticket_id}.md"


def find_ticket_file(hive_root: Path, ticket_id: str, deep: bool = False) -> Path | None:
    """Find a specific ticket's .md file using selective directory traversal.

    Returns the first matching {ticket_id}/{ticket_id}.md file found.

    Args:
        hive_root: Root path of the hive to search
        ticket_id: Ticket ID to find
        deep: If False (default), only enters ticket-ID directories.
              If True, enters all non-hidden directories (for finding misplaced tickets).

    Returns:
        Path to the ticket's .md file, or None if not found
    """
    for dirpath, dirs, files in os.walk(hive_root):
        if deep:
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("evicted", "cemetery")]
        else:
            dirs[:] = [d for d in dirs if is_ticket_id(d)]

        if Path(dirpath).name == ticket_id:
            md_name = f"{ticket_id}.md"
            if md_name in files:
                return Path(dirpath) / md_name

    return None


def get_ticket_path(ticket_id: str, ticket_type: TicketType, hive_name: str) -> Path:
    """
    Get the full file path for a ticket based on its ID and hive name.

    Tickets are stored in hierarchical directory structure where each ticket
    has its own directory: {ticket_id}/{ticket_id}.md

    For existing tickets, scans the hive recursively to find the ticket file.
    For new tickets (file doesn't exist), use compute_ticket_directory() instead.

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx", "t1.X4F2")
        ticket_type: The type of ticket (kept for API compatibility)
        hive_name: The hive name for storage location (required)

    Returns:
        Path object pointing to the ticket's markdown file

    Raises:
        ValueError: If ticket_id is empty or hive not found in config
        FileNotFoundError: If ticket file doesn't exist in the hive

    Examples:
        >>> get_ticket_path("b.Amx", "bee", "backend")
        PosixPath('/path/to/backend/b.Amx/b.Amx.md')
    """
    if not ticket_id:
        raise ValueError("ticket_id cannot be empty")

    if not hive_name:
        raise ValueError("hive_name cannot be empty")

    # Normalize hive_name for config lookup (handles display names like "Back End" -> "back_end")
    normalized_hive = normalize_hive_name(hive_name)

    # Load config to get hive path
    from .config import load_bees_config

    config = load_bees_config()

    if not config or normalized_hive not in config.hives:
        raise ValueError(f"Hive '{hive_name}' (normalized: '{normalized_hive}') not found in config")

    base_dir = Path(config.hives[normalized_hive].path)

    result = compute_ticket_path(ticket_id, base_dir)
    if result.exists():
        return result

    raise FileNotFoundError(f"Ticket file for '{ticket_id}' not found in hive '{hive_name}'")


def compute_ticket_directory(ticket_id: str, parent_id: str | None, hive_name: str) -> Path:
    """
    Compute the target directory path for a ticket within a hive.

    Used for new ticket creation to determine where the ticket directory should be created.

    Hierarchical structure:
    - Bees (no parent): {hive_root}/{ticket_id}/
    - Children (with parent): {parent_dir}/{ticket_id}/

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx", "t1.X4F2")
        parent_id: The parent ticket ID (None for bees at root level)
        hive_name: The hive name for storage location

    Returns:
        Path object pointing to the ticket's directory

    Raises:
        ValueError: If ticket_id is empty or hive not found in config
        FileNotFoundError: If parent ticket doesn't exist (for child tickets)

    Examples:
        >>> compute_ticket_directory("b.Amx", None, "backend")
        PosixPath('/path/to/backend/b.Amx')

        >>> compute_ticket_directory("t1.X4F2", "b.Amx", "backend")
        PosixPath('/path/to/backend/b.Amx/t1.X4F2')
    """
    if not ticket_id:
        raise ValueError("ticket_id cannot be empty")

    if not hive_name:
        raise ValueError("hive_name cannot be empty")

    # Normalize hive_name for config lookup
    normalized_hive = normalize_hive_name(hive_name)

    # Load config to get hive path
    from .config import load_bees_config

    config = load_bees_config()

    if not config or normalized_hive not in config.hives:
        raise ValueError(f"Hive '{hive_name}' (normalized: '{normalized_hive}') not found in config")

    base_dir = Path(config.hives[normalized_hive].path)

    # If no parent, ticket directory is at hive root
    if parent_id is None:
        return base_dir / ticket_id

    # If parent exists, find parent's directory and nest under it
    try:
        # Use a dummy type since we're just finding the path
        parent_path = get_ticket_path(parent_id, "bee", hive_name)
        parent_dir = parent_path.parent
        return parent_dir / ticket_id
    except FileNotFoundError as err:
        raise FileNotFoundError(f"Parent ticket '{parent_id}' not found in hive '{hive_name}'") from err


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

    Searches all configured hives recursively to find the ticket file using
    the hierarchical pattern {ticket_id}/{ticket_id}.md. Type is determined
    from the 'type' field in the YAML frontmatter.

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx", "t1.X4F2")

    Returns:
        The ticket type ('bee', 't1', 't2', etc.) if found, None if not found

    Examples:
        >>> infer_ticket_type_from_id("b.Amx")
        'bee'

        >>> infer_ticket_type_from_id("nonexistent.id")
        None
    """
    if not ticket_id:
        return None

    return get_ticket_type(ticket_id)


def list_tickets(ticket_type: TicketType | None = None) -> list[Path]:
    """
    List all ticket files from all configured hives, optionally filtered by type.

    Scans hive directories recursively for hierarchical ticket storage.
    Excludes special directories (eggs, evicted, .hive) and index.md files.
    Only includes files matching the pattern {ticket_id}/{ticket_id}.md.

    Args:
        ticket_type: Optional ticket type to filter by. If None, returns all tickets.
                    Valid types: "bee" or any tier from child_tiers config (t1, t2, t3, etc.)

    Returns:
        List of Path objects pointing to ticket markdown files across all hives

    Raises:
        ValueError: If ticket_type is not a valid type according to child_tiers config

    Examples:
        >>> list_tickets("bee")
        [PosixPath('/path/to/backend/b.Amx/b.Amx.md'), ...]

        >>> list_tickets("t1")  # Filter by tier
        [PosixPath('/path/to/backend/b.Amx/t1.X4F2/t1.X4F2.md'), ...]

        >>> list_tickets()  # All tickets from all hives
        [PosixPath('backend/b.Amx/b.Amx.md'), ...]
    """
    from .config import load_bees_config

    all_tickets = []

    # Load hive configuration
    config = load_bees_config()

    if not config or not config.hives:
        # No hives configured - return empty list
        return []

    # Validate ticket_type if provided
    if ticket_type is not None:
        from .validator import BASE_TIER

        # Build valid types: base tier + tier IDs + friendly names
        valid_types = {BASE_TIER}
        if config.child_tiers:
            # Add tier IDs (t1, t2, t3...)
            valid_types.update(config.child_tiers.keys())

            # Add friendly names (singular/plural if provided)
            for tier_config in config.child_tiers.values():
                if tier_config.singular:
                    valid_types.add(tier_config.singular)
                if tier_config.plural:
                    valid_types.add(tier_config.plural)

        if ticket_type not in valid_types:
            available = ", ".join(sorted(valid_types))
            raise ValueError(f"Invalid ticket type '{ticket_type}'. Valid types for this configuration: {available}")

    # Iterate all hives
    for _hive_name, hive_config in config.hives.items():
        hive_path = Path(hive_config.path)

        if not hive_path.exists():
            continue

        # Selective traversal: only enters ticket-ID directories
        ticket_files = list(iter_ticket_files(hive_path))

        for ticket_file in ticket_files:
            try:
                ticket_id = ticket_file.stem
                ticket = read_ticket(ticket_id, file_path=ticket_file)
                if ticket_type is None or ticket.type == ticket_type:
                    all_tickets.append(ticket_file)
            except Exception as e:
                import warnings

                warnings.warn(f"Failed to load ticket {ticket_file}: {e}. Skipping.", stacklevel=2)
                continue

    return sorted(all_tickets)
