"""ID generation and validation utilities for tickets."""

import os
import random
import re
from pathlib import Path

from src.constants import GUID_LENGTH, ID_CHARSET

# New ID format: {type_prefix}.{shortID}
# Examples: b.amx, t1.abc.de, t2.abc.de.fg
# Pattern: b.XXX (3 chars) OR t{N}.XXX(.YY)+ (3-char base + N two-char segments separated by periods)
# Charset: 1-9, a-k, m-z (lowercase only; excludes 0, O, I, l, and all uppercase)
ID_PATTERN = re.compile(r"^(b\.[1-9a-km-z]{3}|t(\d+)\.[1-9a-km-z]{3}(\.[1-9a-km-z]{2})+)$")


def normalize_hive_name(hive_name: str) -> str:
    """
    Normalize hive name to lowercase with underscores.

    NOTE: This function is still used for hive name normalization in config and file operations,
    but is no longer used for ID generation (IDs no longer contain hive names).

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
    normalized = hive_name.lower().replace(" ", "_").replace("-", "_")
    # Remove any characters that aren't alphanumeric or underscore
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    # Ensure it starts with a letter or underscore
    if normalized and not normalized[0].isalpha() and normalized[0] != "_":
        normalized = "_" + normalized
    return normalized


def resolve_tier_info(ticket_type: str, hive_name: str | None = None) -> tuple[str, int]:
    """
    Map ticket type to type prefix and shortID length.

    Args:
        ticket_type: Type string - "bee", "t1", "t2", etc., or friendly names from child_tiers config
        hive_name: Optional hive name for per-hive child_tiers resolution

    Returns:
        tuple[str, int]: (type_prefix, shortID_length)
        - Bee (t0): ("b", 3)
        - t1: ("t1", 5)
        - t2: ("t2", 7)
        - t{N}: ("t{N}", 3 + N*2)

    Raises:
        ValueError: If ticket_type is invalid or not configured

    Examples:
        >>> resolve_tier_info("bee")
        ("b", 3)
        >>> resolve_tier_info("t1")
        ("t1", 5)
        >>> resolve_tier_info("Task")  # if t1 has friendly name "Task"
        ("t1", 5)
    """
    # Handle "bee" (tier 0)
    if ticket_type == "bee":
        return ("b", 3)

    # Check if it's already a tier ID (t1, t2, t3...)
    tier_pattern = re.compile(r"^t(\d+)$")
    match = tier_pattern.match(ticket_type)
    if match:
        tier_num = int(match.group(1))
        length = 3 + (tier_num * 2)
        return (ticket_type, length)

    # Not a tier ID, check if it's a friendly name
    try:
        from .config import load_bees_config, resolve_child_tiers_for_hive
    except ImportError:
        raise ValueError(f"Invalid ticket_type: {ticket_type}. Must be 'bee' or 't{{N}}' format.") from None

    config = load_bees_config()

    # Resolve child_tiers based on hive_name
    if hive_name is not None:
        # Per-hive resolution
        child_tiers = resolve_child_tiers_for_hive(hive_name, config)
    else:
        # Backward compatibility: use scope-level child_tiers
        child_tiers = config.child_tiers if config else None

    if not child_tiers:
        raise ValueError(f"Invalid ticket_type: {ticket_type}. No child_tiers configured.")

    # Search for friendly name in child_tiers
    for tier_key, tier_config in child_tiers.items():
        if ticket_type == tier_config.singular or ticket_type == tier_config.plural:
            # Found it - extract tier number from tier_key
            match = tier_pattern.match(tier_key)
            if match:
                tier_num = int(match.group(1))
                length = 3 + (tier_num * 2)
                return (tier_key, length)

    raise ValueError(
        f"Invalid ticket_type: {ticket_type}. Must be 'bee', a tier ID like 't1', "
        "or a friendly name from child_tiers config."
    )


def generate_ticket_id(ticket_type: str, hive_name: str | None = None) -> str:
    """
    Generate a ticket ID with type-prefixed format.

    Format: {type_prefix}.{shortID}
    Examples: b.amx, t1.abc.de, t2.abc.de.fg

    Args:
        ticket_type: Ticket type - "bee", "t1", "t2", etc., or friendly name from child_tiers
        hive_name: Optional hive name for per-hive child_tiers resolution

    Returns:
        A ticket ID string with type prefix and random shortID

    Raises:
        ValueError: If ticket_type is invalid

    Note:
        This function generates random IDs but does not check for collisions.
        Use generate_unique_ticket_id() for collision detection.

    Examples:
        >>> generate_ticket_id("bee")  # Returns something like "b.amx"
        "b.amx"
        >>> generate_ticket_id("t1")  # Returns something like "t1.abc.de"
        "t1.abc.de"
    """
    prefix, length = resolve_tier_info(ticket_type, hive_name=hive_name)
    chars = "".join(random.choices(ID_CHARSET, k=length))
    if length == 3:
        return f"{prefix}.{chars}"
    segments = [chars[0:3]] + [chars[3 + i * 2 : 5 + i * 2] for i in range((length - 3) // 2)]
    return f"{prefix}." + ".".join(segments)


def ticket_type_from_prefix(ticket_id: str) -> str:
    """Derive ticket type from ID prefix without filesystem access.

    Args:
        ticket_id: A ticket ID string (e.g., "b.abc", "t1.abc.de", "t2.abc.de.fg")

    Returns:
        The ticket type string: "bee" for bee tickets, "t1"/"t2"/etc. for child tiers

    Examples:
        >>> ticket_type_from_prefix("b.abc")
        'bee'
        >>> ticket_type_from_prefix("t1.abc.de")
        't1'
        >>> ticket_type_from_prefix("t2.abc.de.fg")
        't2'
    """
    prefix = ticket_id.split(".", 1)[0]
    return "bee" if prefix == "b" else prefix


def generate_guid(short_id: str) -> str:
    """
    Generate a GUID starting with the given short_id.

    The GUID is composed of the short_id followed by random characters
    from ID_CHARSET to fill the remaining length up to GUID_LENGTH.

    Args:
        short_id: The ticket's short ID (e.g., "amx" from "b.amx")

    Returns:
        A 22-character string starting with short_id, all chars in ID_CHARSET

    Examples:
        >>> guid = generate_guid("amx")
        >>> len(guid) == 32
        True
        >>> guid.startswith("amx")
        True
    """
    short_id = short_id.replace(".", "")
    remaining = GUID_LENGTH - len(short_id)
    suffix = "".join(random.choices(ID_CHARSET, k=remaining))
    return short_id + suffix


_TICKET_ID_DIR_PATTERN = re.compile(r"^(b\.[1-9a-km-z]+|t\d+\.[1-9a-km-z]{3}(\.[1-9a-km-z]{2})*)$")


def is_ticket_id(name: str) -> bool:
    """Check if a string looks like a ticket ID.

    Uses a relaxed pattern for directory traversal filtering — matches the
    general ticket ID format (b.XXX or t{N}.XXX) and enforces the ID charset
    (1-9, a-k, m-z) but does not enforce length constraints. Use is_valid_ticket_id()
    for strict validation.

    Args:
        name: String to check (typically a directory name)

    Returns:
        True if name matches the ticket ID format
    """
    return bool(_TICKET_ID_DIR_PATTERN.match(name))


def is_valid_ticket_id(ticket_id: str) -> bool:
    """
    Validate that a ticket ID matches the required format.

    Validates both format and length constraints:
    - b.XXX must have exactly 3-char shortID
    - t{N}.{shortID} must have shortID length = 3 + N*2

    Args:
        ticket_id: The ID string to validate

    Returns:
        True if the ID is valid, False otherwise

    Examples:
        >>> is_valid_ticket_id("b.amx")
        True
        >>> is_valid_ticket_id("t1.abc.de")  # 3+2 non-period chars for tier 1
        True
        >>> is_valid_ticket_id("t2.abc.de.fg")  # 3+2+2 non-period chars for tier 2
        True
        >>> is_valid_ticket_id("b.amx9")  # wrong length for bee
        False
    """
    if not ticket_id or not isinstance(ticket_id, str):
        return False

    # Check basic pattern
    match = ID_PATTERN.match(ticket_id)
    if not match:
        return False

    # Validate length constraints
    if ticket_id.startswith("b."):
        # Bee must have 3-char shortID
        short_id = ticket_id[2:]  # everything after "b."
        return len(short_id) == 3

    elif ticket_id.startswith("t"):
        # Extract tier number and shortID
        prefix, _, short_id = ticket_id.partition(".")
        if not prefix.startswith("t"):
            return False

        try:
            tier_num = int(prefix[1:])  # extract number from "t1", "t2", etc.
            expected_length = 3 + (tier_num * 2)
            return len(short_id.replace(".", "")) == expected_length
        except ValueError:
            return False

    return False


def parent_id_from_ticket_id(ticket_id: str) -> str | None:
    """Compute parent ticket ID from a ticket ID without any file I/O.

    Args:
        ticket_id: A ticket ID string (e.g., "b.abc", "t1.abc.de", "t2.abc.de.fg")

    Returns:
        Parent ticket ID, or None if the ticket is a bee (has no parent in the ID)

    Examples:
        >>> parent_id_from_ticket_id("b.abc")
        None
        >>> parent_id_from_ticket_id("t1.abc.de")
        'b.abc'
        >>> parent_id_from_ticket_id("t2.abc.de.fg")
        't1.abc.de'
        >>> parent_id_from_ticket_id("t3.abc.de.fg.hi")
        't2.abc.de.fg'
    """
    prefix = ticket_id.split(".", 1)[0]
    if prefix == "b":
        return None
    tier_num = int(prefix[1:])
    # Strip the last dot-segment
    parent_id = ticket_id.rsplit(".", 1)[0]
    # Decrement tier prefix: t1 → b, tN → t(N-1)
    if tier_num == 1:
        new_prefix = "b"
    else:
        new_prefix = f"t{tier_num - 1}"
    # Replace the old prefix with the new one
    _, _, rest = parent_id.partition(".")
    return f"{new_prefix}.{rest}"


def generate_child_tier_id(parent_id: str, parent_dir: Path) -> str:
    """
    Generate a child tier ticket ID hierarchically derived from parent_id.

    Child short ID = parent_short_id + 2 random characters from ID_CHARSET.
    Uniqueness is claimed optimistically by creating the child directory inside
    parent_dir. If the directory already exists, a new suffix is tried.

    Args:
        parent_id: Full parent ticket ID (e.g., "b.abc", "t1.abcde")
        parent_dir: Directory containing the parent ticket's files

    Returns:
        A full child ticket ID string (e.g., "t1.abcXY", "t2.abcdeXY")

    Raises:
        RuntimeError: If all 1,156 possible child IDs are exhausted

    Examples:
        >>> generate_child_tier_id("b.abc", parent_dir)  # returns "t1.abc.xy"
        "t1.abc.xy"
        >>> generate_child_tier_id("t1.abc.de", parent_dir)  # returns "t2.abc.de.xy"
        "t2.abc.de.xy"
    """
    parent_short_id = parent_id.split(".", 1)[1]
    prefix = parent_id.split(".", 1)[0]
    parent_tier_num = 0 if prefix == "b" else int(prefix[1:])
    child_prefix = f"t{parent_tier_num + 1}"

    for _ in range(100):
        suffix = "".join(random.choices(ID_CHARSET, k=2))
        child_short_id = parent_short_id + "." + suffix
        child_full_id = f"{child_prefix}.{child_short_id}"
        child_dir = parent_dir / child_full_id
        try:
            child_dir.mkdir()
            return child_full_id
        except FileExistsError:
            continue

    raise RuntimeError(
        f"Parent {parent_id!r} has reached capacity: 100 attempts failed to find a unique child ID."
    )


def generate_unique_ticket_id(
    ticket_type: str,
    max_attempts: int = 100,
    hive_name: str | None = None,
) -> str:
    """
    Generate a unique ticket ID with collision detection.

    Fast path: stats the expected path in each hive (O(H) per attempt).
    After 2 collisions the ID space is considered dense and falls back to
    building a full exclusion set from os.listdir once, then doing O(1) lookups.
    Checks all directory entry names at each hive root (not just valid ticket IDs)
    to prevent collisions with user-created dirs.

    Args:
        ticket_type: Ticket type - "bee", "t1", "t2", etc., or friendly name from child_tiers
        max_attempts: Maximum number of generation attempts before raising error
        hive_name: Optional hive name for per-hive child_tiers resolution

    Returns:
        A unique ticket ID string with type prefix

    Raises:
        RuntimeError: If unable to generate unique ID within max_attempts
        ValueError: If ticket_type is invalid

    Examples:
        >>> new_id = generate_unique_ticket_id("bee", hive_name="backend")
        >>> new_id.startswith("b.")
        True
    """
    try:
        from .config import load_bees_config
        from .paths import compute_ticket_path
    except ImportError:
        load_bees_config = None  # type: ignore[assignment]
        compute_ticket_path = None  # type: ignore[assignment]

    config = load_bees_config() if load_bees_config is not None else None
    hive_paths = []
    if config and config.hives:
        hive_paths = [Path(hc.path) for hc in config.hives.values() if Path(hc.path).exists()]

    collisions = 0
    existing: set[str] | None = None  # built lazily after COLLISION_THRESHOLD misses

    for _ in range(max_attempts):
        ticket_id = generate_ticket_id(ticket_type=ticket_type, hive_name=hive_name)

        if existing is not None:
            # Dense ID space: use pre-built exclusion set for O(1) lookup
            if ticket_id not in existing:
                return ticket_id
        else:
            # Fast path: stat the expected path in each hive — O(H) total
            taken = compute_ticket_path is not None and any(
                compute_ticket_path(ticket_id, hp).parent.exists() for hp in hive_paths
            )
            if not taken:
                return ticket_id
            collisions += 1
            if collisions >= 2:
                # Two collisions — ID space is dense. Build exclusion set once and switch.
                existing = set()
                for hp in hive_paths:
                    existing.update(os.listdir(hp))

    raise RuntimeError("Too many bees.")


