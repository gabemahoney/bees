"""ID generation and validation utilities for tickets."""

import random
import re
import string
from pathlib import Path


# ID format: bees-<3 alphanumeric chars> OR {hive_name}.bees-<3 alphanumeric chars>
# Examples: bees-250, bees-abc, bees-9pw, backend.bees-abc, my_hive.bees-123
ID_PATTERN = re.compile(r"^([a-z_][a-z0-9_]*\.)?bees-[a-z0-9]{3}$")
CHARSET = string.ascii_lowercase + string.digits


def normalize_hive_name(hive_name: str) -> str:
    """
    Normalize hive name to lowercase with underscores.

    Args:
        hive_name: The hive name to normalize

    Returns:
        Normalized hive name (lowercase, spaces/hyphens converted to underscores)

    Examples:
        >>> normalize_hive_name("BackEnd")
        'backend'
        >>> normalize_hive_name("My Hive")
        'my_hive'
        >>> normalize_hive_name("front-end")
        'front_end'
    """
    # Replace spaces and hyphens with underscores, convert to lowercase
    normalized = hive_name.lower().replace(' ', '_').replace('-', '_')
    # Remove any characters that aren't alphanumeric or underscore
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    # Ensure it starts with a letter or underscore
    if normalized and not normalized[0].isalpha() and normalized[0] != '_':
        normalized = '_' + normalized
    return normalized


def generate_ticket_id(hive_name: str) -> str:
    """
    Generate a unique short alphanumeric ticket ID.

    Format: {hive_name}.bees-<3 random alphanumeric chars>
    Examples: backend.bees-abc, my_hive.bees-250

    Args:
        hive_name: Required hive name to prefix the ID with

    Returns:
        A unique ticket ID string with hive prefix

    Raises:
        ValueError: If hive_name normalizes to an empty string

    Note:
        This function generates random IDs but does not check for collisions.
        Use generate_unique_ticket_id() for collision detection.
    """
    suffix = ''.join(random.choices(CHARSET, k=3))
    base_id = f"bees-{suffix}"

    normalized = normalize_hive_name(hive_name)
    if not normalized:
        raise ValueError(f"hive_name '{hive_name}' normalizes to empty string")

    return f"{normalized}.{base_id}"


def is_valid_ticket_id(ticket_id: str) -> bool:
    """
    Validate that a ticket ID matches the required format.

    Args:
        ticket_id: The ID string to validate

    Returns:
        True if the ID is valid, False otherwise

    Examples:
        >>> is_valid_ticket_id("bees-250")
        True
        >>> is_valid_ticket_id("backend.bees-abc")
        True
        >>> is_valid_ticket_id("bees-ABC")  # uppercase not allowed
        False
        >>> is_valid_ticket_id("bees-1234")  # too long
        False
    """
    if not ticket_id or not isinstance(ticket_id, str):
        return False
    return bool(ID_PATTERN.match(ticket_id))


def generate_unique_ticket_id(hive_name: str, existing_ids: set[str] | None = None, max_attempts: int = 100) -> str:
    """
    Generate a unique ticket ID with collision detection.

    Args:
        hive_name: Required hive name to prefix the ID with
        existing_ids: Optional set of existing IDs to check against
        max_attempts: Maximum number of generation attempts before raising error

    Returns:
        A unique ticket ID string with hive prefix

    Raises:
        RuntimeError: If unable to generate unique ID within max_attempts
        ValueError: If hive_name normalizes to an empty string

    Examples:
        >>> existing = {"backend.bees-250", "backend.bees-abc"}
        >>> new_id = generate_unique_ticket_id("backend", existing)
        >>> new_id not in existing
        True
        >>> new_id.startswith("backend.bees-")
        True
    """
    if existing_ids is None:
        existing_ids = set()

    for _ in range(max_attempts):
        ticket_id = generate_ticket_id(hive_name=hive_name)
        if ticket_id not in existing_ids:
            return ticket_id

    raise RuntimeError(
        f"Failed to generate unique ticket ID after {max_attempts} attempts. "
        "This is extremely unlikely with the current ID space."
    )


def extract_existing_ids_from_directory(tickets_dir: Path) -> set[str]:
    """
    Extract all existing ticket IDs from ticket files in a directory.

    With flat storage, scans hive root directory directly (no subdirectories).

    Args:
        tickets_dir: Path to the hive root directory

    Returns:
        Set of existing ticket IDs found in filenames

    Examples:
        >>> extract_existing_ids_from_directory(Path("backend"))
        {'backend.bees-250', 'backend.bees-abc', 'backend.bees-9pw'}
    """
    existing_ids = set()

    # Scan hive root directory for .md files
    if tickets_dir.exists():
        for md_file in tickets_dir.glob("*.md"):
            # Extract ID from filename (without .md extension)
            filename = md_file.stem
            if is_valid_ticket_id(filename):
                existing_ids.add(filename)

    return existing_ids


def extract_existing_ids_from_all_hives() -> set[str]:
    """
    Extract all existing ticket IDs from all configured hives.

    Scans all hive directories defined in .bees/config.json and collects
    all ticket IDs across all hives.

    Returns:
        Set of existing ticket IDs found across all hives

    Examples:
        >>> extract_existing_ids_from_all_hives()
        {'backend.bees-250', 'frontend.bees-abc', 'backend.bees-9pw'}
    """
    from pathlib import Path

    existing_ids = set()

    # Import here to avoid circular dependency
    try:
        from .config import load_bees_config
    except ImportError:
        # If config module not available, return empty set
        return existing_ids

    # Load hive configuration
    config = load_bees_config()

    if not config or not config.hives:
        # No hives configured - return empty set
        return existing_ids

    # Scan each hive directory
    for hive_name, hive_config in config.hives.items():
        hive_path = Path(hive_config.path)

        if not hive_path.exists():
            continue

        # Extract IDs from this hive's directory
        hive_ids = extract_existing_ids_from_directory(hive_path)
        existing_ids.update(hive_ids)

    return existing_ids
