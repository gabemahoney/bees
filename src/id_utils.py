"""ID generation and validation utilities for tickets."""

import random
import re
import string
from pathlib import Path


# ID format: bees-<3 alphanumeric chars>
# Examples: bees-250, bees-abc, bees-9pw
ID_PATTERN = re.compile(r"^bees-[a-z0-9]{3}$")
CHARSET = string.ascii_lowercase + string.digits


def generate_ticket_id() -> str:
    """
    Generate a unique short alphanumeric ticket ID.

    Format: bees-<3 random alphanumeric chars>
    Examples: bees-250, bees-abc, bees-9pw

    Returns:
        A unique ticket ID string

    Note:
        This function generates random IDs but does not check for collisions.
        Use generate_unique_ticket_id() for collision detection.
    """
    suffix = ''.join(random.choices(CHARSET, k=3))
    return f"bees-{suffix}"


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
        >>> is_valid_ticket_id("bees-ABC")  # uppercase not allowed
        False
        >>> is_valid_ticket_id("bees-1234")  # too long
        False
    """
    if not ticket_id or not isinstance(ticket_id, str):
        return False
    return bool(ID_PATTERN.match(ticket_id))


def generate_unique_ticket_id(existing_ids: set[str] | None = None, max_attempts: int = 100) -> str:
    """
    Generate a unique ticket ID with collision detection.

    Args:
        existing_ids: Optional set of existing IDs to check against
        max_attempts: Maximum number of generation attempts before raising error

    Returns:
        A unique ticket ID string

    Raises:
        RuntimeError: If unable to generate unique ID within max_attempts

    Examples:
        >>> existing = {"bees-250", "bees-abc"}
        >>> new_id = generate_unique_ticket_id(existing)
        >>> new_id not in existing
        True
    """
    if existing_ids is None:
        existing_ids = set()

    for _ in range(max_attempts):
        ticket_id = generate_ticket_id()
        if ticket_id not in existing_ids:
            return ticket_id

    raise RuntimeError(
        f"Failed to generate unique ticket ID after {max_attempts} attempts. "
        "This is extremely unlikely with the current ID space."
    )


def extract_existing_ids_from_directory(tickets_dir: Path) -> set[str]:
    """
    Extract all existing ticket IDs from ticket files in a directory.

    Args:
        tickets_dir: Path to the tickets directory (containing epics/, tasks/, subtasks/)

    Returns:
        Set of existing ticket IDs found in filenames

    Examples:
        >>> extract_existing_ids_from_directory(Path("tickets"))
        {'bees-250', 'bees-abc', 'bees-9pw'}
    """
    existing_ids = set()

    for subdir in ["epics", "tasks", "subtasks"]:
        subdir_path = tickets_dir / subdir
        if subdir_path.exists():
            for md_file in subdir_path.glob("*.md"):
                # Extract ID from filename (without .md extension)
                filename = md_file.stem
                if is_valid_ticket_id(filename):
                    existing_ids.add(filename)

    return existing_ids
