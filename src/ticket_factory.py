"""Factory functions for creating tickets with YAML frontmatter."""

from datetime import datetime
from pathlib import Path
from typing import Any

from .config import load_bees_config
from .constants import SCHEMA_VERSION
from .id_utils import (
    generate_child_tier_id,
    generate_guid,
    generate_unique_ticket_id,
    is_valid_ticket_id,
    normalize_hive_name,
)
from .paths import compute_ticket_path
from .writer import write_ticket_file


def _write_bee(
    ticket_id: str,
    title: str,
    hive_name: str,
    description: str = "",
    tags: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    status: str | None = None,
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None = None,
    guid: str | None = None,
) -> tuple[str, str]:
    """
    Internal: build frontmatter and write a bee ticket file.

    Callers are responsible for supplying a valid, already-resolved ticket_id.
    Returns (ticket_id, guid) tuple.
    """
    frontmatter_data: dict[str, Any] = {
        "id": ticket_id,
        "type": "bee",
        "title": title,
        "tags": tags or [],
        "up_dependencies": up_dependencies or [],
        "down_dependencies": down_dependencies or [],
        "status": status,
        "created_at": datetime.now(),
        "schema_version": SCHEMA_VERSION,
        "egg": egg,
    }
    short_id = ticket_id.split(".", 1)[1] if "." in ticket_id else ticket_id
    frontmatter_data["guid"] = guid if guid is not None else generate_guid(short_id)

    # Compute bee file path directly (O(1)) — bees always live at hive_root/ticket_id/ticket_id.md
    config = load_bees_config()
    normalized_hive = normalize_hive_name(hive_name)
    if not config or normalized_hive not in config.hives:
        raise ValueError(f"Hive '{hive_name}' not found in configuration")
    hive_path = Path(config.hives[normalized_hive].path)
    bee_file_path = hive_path / ticket_id / f"{ticket_id}.md"

    write_ticket_file(
        ticket_id=ticket_id,
        ticket_type="bee",
        frontmatter_data=frontmatter_data,
        body=description,
        hive_name=hive_name,
        file_path=bee_file_path,
    )
    return ticket_id, frontmatter_data["guid"]


def _write_child_tier(
    ticket_id: str,
    ticket_type: str,
    title: str,
    parent: str,
    hive_name: str,
    description: str = "",
    tags: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    status: str | None = None,
    guid: str | None = None,
) -> tuple[str, str]:
    """
    Internal: build frontmatter and write a child-tier ticket file.

    Callers are responsible for supplying a valid, already-resolved ticket_id.
    Parent backlink is NOT updated here — callers must handle bidirectional
    relationships (e.g. via _update_bidirectional_relationships).
    Returns (ticket_id, guid) tuple.
    """
    frontmatter_data: dict[str, Any] = {
        "id": ticket_id,
        "type": ticket_type,
        "title": title,
        "parent": parent,
        "tags": tags or [],
        "up_dependencies": up_dependencies or [],
        "down_dependencies": down_dependencies or [],
        "status": status,
        "created_at": datetime.now(),
        "schema_version": SCHEMA_VERSION,
    }
    short_id = ticket_id.split(".", 1)[1] if "." in ticket_id else ticket_id
    frontmatter_data["guid"] = guid if guid is not None else generate_guid(short_id)

    write_ticket_file(
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        frontmatter_data=frontmatter_data,
        body=description,
        hive_name=hive_name,
    )
    return ticket_id, frontmatter_data["guid"]


def create_bee(
    title: str,
    hive_name: str,
    description: str = "",
    tags: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    status: str | None = None,
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None = None,
    guid: str | None = None,
) -> tuple[str, str]:
    """
    Create a Bee ticket with YAML frontmatter.

    Args:
        title: Bee title (required)
        description: Bee description
        tags: List of tag strings
        up_dependencies: List of ticket IDs that block this bee
        down_dependencies: List of ticket IDs that this bee blocks
        status: Status string (default: "open")
        hive_name: Hive name determining storage location (required, e.g., "backend" stores in backend hive)

    Returns:
        (ticket_id, guid) tuple

    Raises:
        ValueError: If required fields are missing or invalid

    Examples:
        >>> bee_id, guid = create_bee(
        ...     title="Implement Auth System",
        ...     description="Build user authentication",
        ...     tags=["security", "backend"],
        ...     hive_name="backend",
        ... )
        >>> bee_id.startswith("b.")
        True
        >>> bee_id, guid = create_bee(
        ...     title="Frontend Dashboard",
        ...     hive_name="frontend",
        ... )
        >>> bee_id.startswith("b.")
        True
    """
    if not title:
        raise ValueError("Bee title is required")

    ticket_id = generate_unique_ticket_id("bee", hive_name=hive_name)
    return _write_bee(
        ticket_id=ticket_id,
        title=title,
        hive_name=hive_name,
        description=description,
        tags=tags,
        up_dependencies=up_dependencies,
        down_dependencies=down_dependencies,
        status=status,
        egg=egg,
        guid=guid,
    )


def create_child_tier(
    ticket_type: str,
    title: str,
    parent: str,
    hive_name: str,
    description: str = "",
    tags: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    status: str | None = None,
    guid: str | None = None,
) -> tuple[str, str]:
    """
    Create a child tier ticket (t1, t2, t3, etc.) with YAML frontmatter.

    This generic function handles creation of any dynamic tier type configured
    in the child_tiers config. It accepts the ticket_type as a parameter.

    Args:
        ticket_type: Type of tier ticket (e.g., "t1", "t2", "t3")
        title: Ticket title (required)
        parent: Parent ticket ID (required for all child tiers)
        hive_name: Hive name to prefix the ID with (required)
        description: Ticket description
        tags: List of tag strings
        up_dependencies: List of ticket IDs that block this ticket
        down_dependencies: List of ticket IDs that this ticket blocks
        status: Status string (default: "open")

    Returns:
        (ticket_id, guid) tuple

    Raises:
        ValueError: If required fields are missing or invalid

    Examples:
        >>> t1_id, guid = create_child_tier(
        ...     ticket_type="t1",
        ...     title="Build login feature",
        ...     parent="b.Amx",
        ...     hive_name="backend",
        ... )
        >>> t1_id.startswith("t1.")
        True
    """
    if not title:
        raise ValueError(f"{ticket_type} title is required")
    if not parent:
        raise ValueError(f"{ticket_type} parent is required")

    config = load_bees_config()
    normalized_hive = normalize_hive_name(hive_name)
    hive_path = Path(config.hives[normalized_hive].path)
    parent_file = compute_ticket_path(parent, hive_path)
    if not parent_file.exists():
        raise ValueError(f"Parent ticket not found: {parent}")
    ticket_id = generate_child_tier_id(parent_id=parent, parent_dir=parent_file.parent)

    return _write_child_tier(
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        title=title,
        parent=parent,
        hive_name=hive_name,
        description=description,
        tags=tags,
        up_dependencies=up_dependencies,
        down_dependencies=down_dependencies,
        status=status,
        guid=guid,
    )


def _create_bee_with_id(
    ticket_id: str,
    title: str,
    hive_name: str,
    **kwargs: Any,
) -> tuple[str, str]:
    """
    Private helper for tests: create a bee ticket with a specific ID.

    Validates ticket_id before delegating to the core write logic.
    Not part of the public API — do not use in production code.

    Args:
        ticket_id: Explicit ticket ID to use (must pass is_valid_ticket_id)
        title: Bee title (required)
        hive_name: Hive name (required)
        **kwargs: Forwarded to _write_bee's optional parameters

    Raises:
        ValueError: If ticket_id is invalid
    """
    if not is_valid_ticket_id(ticket_id):
        raise ValueError(f"Invalid ticket_id: {ticket_id!r}")

    return _write_bee(
        ticket_id=ticket_id,
        title=title,
        hive_name=hive_name,
        description=kwargs.pop("description", ""),
        tags=kwargs.pop("tags", None),
        up_dependencies=kwargs.pop("up_dependencies", None),
        down_dependencies=kwargs.pop("down_dependencies", None),
        status=kwargs.pop("status", None),
        egg=kwargs.pop("egg", None),
        guid=kwargs.pop("guid", None),
    )


def _create_child_tier_with_id(
    ticket_id: str,
    ticket_type: str,
    title: str,
    parent: str,
    hive_name: str,
    **kwargs: Any,
) -> tuple[str, str]:
    """
    Private helper for tests: create a child-tier ticket with a specific ID.

    Validates ticket_id before delegating to the core write logic.
    Not part of the public API — do not use in production code.

    Args:
        ticket_id: Explicit ticket ID to use (must pass is_valid_ticket_id)
        ticket_type: Tier type (e.g. "t1", "t2")
        title: Ticket title (required)
        parent: Parent ticket ID (required)
        hive_name: Hive name (required)
        **kwargs: Forwarded to _write_child_tier's optional parameters

    Raises:
        ValueError: If ticket_id is invalid
    """
    if not is_valid_ticket_id(ticket_id):
        raise ValueError(f"Invalid ticket_id: {ticket_id!r}")

    return _write_child_tier(
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        title=title,
        parent=parent,
        hive_name=hive_name,
        description=kwargs.pop("description", ""),
        tags=kwargs.pop("tags", None),
        up_dependencies=kwargs.pop("up_dependencies", None),
        down_dependencies=kwargs.pop("down_dependencies", None),
        status=kwargs.pop("status", None),
        guid=kwargs.pop("guid", None),
    )
