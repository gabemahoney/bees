"""
Test helper utilities for the Bees ticket management system.

This module provides reusable test utilities that reduce duplication across
test files and ensure consistent patterns for common operations like creating
test tickets and writing ticket files.

Usage:
    from tests.helpers import setup_child_tiers, make_ticket, write_ticket_file
"""

from pathlib import Path

from src.config import ChildTierConfig, load_bees_config, save_bees_config
from src.id_utils import generate_guid
from tests.test_constants import (
    TICKET_ID_TEST_BEE,
)


def write_corrupt_ticket(hive_dir: Path, ticket_id: str) -> None:
    """Write a malformed YAML ticket file to the hive (missing required fields).

    Creates a ticket directory with a .md file that has only id and type —
    missing title, schema_version, guid, egg, and other required fields.
    Used to test that operations succeed when a hive contains corrupt siblings.

    Note: ``ticket_id`` must conform to ID_CHARSET (``123456789abcdefghijkmnopqrstuvwxyz``).
    Callers are responsible for passing a valid, correctly-formatted ticket ID.
    """
    ticket_dir = hive_dir / ticket_id
    ticket_dir.mkdir(parents=True, exist_ok=True)
    (ticket_dir / f"{ticket_id}.md").write_text(
        "---\n"
        f"id: {ticket_id}\n"
        "type: bee\n"
        "# Missing title, ticket_status, schema_version, guid, egg\n"
        "---\n"
        "Corrupt ticket body.\n"
    )


def _default_guid_for_id(ticket_id: str) -> str:
    """Generate a valid GUID for a ticket ID by extracting its short_id."""
    short_id = ticket_id.split(".", 1)[1] if "." in ticket_id else ticket_id
    return generate_guid(short_id)


def setup_hive_child_tiers(hive_name: str, tier_config: dict[str, tuple[str, str]]) -> None:
    """
    Configure child_tiers on a specific hive entry in .bees/config.json.

    This sets hive-level child_tiers, which takes priority over scope-level
    child_tiers in the three-level resolution chain:
    hive → scope → global → bees-only.

    Args:
        hive_name: The normalized hive name (must already exist in config)
        tier_config: Dictionary mapping tier IDs to (singular, plural) name tuples.
                    Use {} for bees-only (stops fallthrough to scope/global).
                    Example: {"t1": ("Epic", "Epics"), "t2": ("Task", "Tasks")}

    Raises:
        RuntimeError: If config cannot be loaded
        KeyError: If hive_name is not found in the config
    """
    config = load_bees_config()
    if config is None:
        raise RuntimeError("Failed to load bees config")
    if hive_name not in config.hives:
        raise KeyError(f"Hive '{hive_name}' not found in config. Available: {list(config.hives.keys())}")

    # Build ChildTierConfig objects for the hive-level override
    hive_tiers = {
        tier_id: ChildTierConfig(singular, plural) for tier_id, (singular, plural) in tier_config.items()
    }

    # Set child_tiers on the HiveConfig object directly
    config.hives[hive_name].child_tiers = hive_tiers
    save_bees_config(config)


def setup_child_tiers(tier_config: dict[str, tuple[str, str]]) -> None:
    """
    Configure child_tiers in .bees/config.json for testing tier hierarchies.

    This helper eliminates repeated boilerplate of loading config, setting
    child_tiers, and saving config. Use this when tests need specific tier
    configurations beyond the default 2-tier (bee→task→subtask) structure.

    Args:
        tier_config: Dictionary mapping tier IDs to (singular, plural) name tuples
                    Example: {"t1": ("Task", "Tasks"), "t2": ("Subtask", "Subtasks")}

    Raises:
        RuntimeError: If config cannot be loaded

    Example:
        >>> # Configure 3-tier hierarchy: bee → Epic (t1) → Feature (t2) → Story (t3)
        >>> setup_child_tiers({
        ...     "t1": ("Epic", "Epics"),
        ...     "t2": ("Feature", "Features"),
        ...     "t3": ("Story", "Stories")
        ... })
        >>> # Now can create tickets with types "t1", "t2", "t3"

        >>> # Configure bees-only system (no child tiers)
        >>> setup_child_tiers({})
    """
    config = load_bees_config()
    if config is None:
        raise RuntimeError("Failed to load bees config")
    config.child_tiers = {
        tier_id: ChildTierConfig(singular, plural) for tier_id, (singular, plural) in tier_config.items()
    }
    save_bees_config(config)




# ============================================================================
# EPIC 3 DATA FACTORIES: Ticket Object and File Factories
# ============================================================================


def make_ticket(
    id: str = TICKET_ID_TEST_BEE,
    title: str = "Test Ticket",
    type: str = "bee",
    status: str = "open",
    tags: list[str] | None = None,
    children: list[str] | None = None,
    parent: str | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    created_at: str | None = None,
    schema_version: str = "0.1",
    egg=None,
    guid: str | None = "__AUTO__",
):
    """
    Create a Ticket object with sensible defaults.

    This factory eliminates verbose inline Ticket() constructions that repeat
    all 14+ fields. Only specify fields that matter for your test. Replaces
    patterns like:

        # Before (11 lines):
        ticket = Ticket(
            id="b.ep1", title="Epic One", type="bee", status="open",
            tags=[], children=["t1.xyz"], parent=None,
            up_dependencies=[], down_dependencies=[],
            created_at="2024-01-01T00:00:00+00:00",
            schema_version="0.1", egg=None
        )

        # After (1 line):
        ticket = make_ticket(id="b.ep1", title="Epic One", children=["t1.xyz"])

    Args:
        id: Ticket ID (default: TICKET_ID_TEST_BEE = "b.abc")
        title: Ticket title (default: "Test Ticket")
        type: Ticket type - "bee", "t1", "t2", or tier ID (default: "bee")
        status: Ticket status (default: "open")
        tags: List of tag strings (default: None = [])
        children: List of child ticket IDs (default: None = [])
        parent: Parent ticket ID (default: None)
        up_dependencies: List of blocking ticket IDs (default: None = [])
        down_dependencies: List of blocked ticket IDs (default: None = [])
        created_at: Creation timestamp ISO format (default: "2024-01-01T00:00:00+00:00")
        schema_version: Schema version (default: "0.1")
        egg: Egg field value (default: None). Can be string, dict, list, or any JSON-serializable type.
        guid: GUID string (default: "__AUTO__" = auto-generate from id). Pass None to omit.

    Returns:
        Ticket: Ticket object with all fields populated

    Example:
        >>> # Minimal bee
        >>> ticket = make_ticket(id=TICKET_ID_TEST_BEE, title="My Bee")

        >>> # Task with parent and dependencies
        >>> ticket = make_ticket(
        ...     id=TICKET_ID_HELPER_TASK_XYZ1,
        ...     title="My Task",
        ...     type="t1",
        ...     parent=TICKET_ID_TEST_BEE,
        ...     up_dependencies=[TICKET_ID_HELPER_TASK_DEP]
        ... )

        >>> # Custom fields
        >>> ticket = make_ticket(
        ...     id=TICKET_ID_HELPER_BEE_GHI,
        ...     title="High Priority",
        ...     tags=["urgent", "bug"]
        ... )

        >>> # Bee with egg field
        >>> ticket = make_ticket(
        ...     id="b.egg",
        ...     title="Egg Bee",
        ...     egg="https://example.com/spec.md"
        ... )
    """
    from src.models import Ticket

    resolved_guid = _default_guid_for_id(id) if guid == "__AUTO__" else guid

    return Ticket(
        id=id,
        title=title,
        type=type,
        status=status,
        tags=tags if tags is not None else [],
        children=children if children is not None else [],
        parent=parent,
        up_dependencies=up_dependencies if up_dependencies is not None else [],
        down_dependencies=down_dependencies if down_dependencies is not None else [],
        created_at=created_at or "2024-01-01T00:00:00+00:00",
        schema_version=schema_version,
        egg=egg,
        guid=resolved_guid,
    )


def write_ticket_file(
    directory: Path,
    id: str,
    title: str = "Test Ticket",
    type: str = "bee",
    status: str = "open",
    body: str = "",
    egg=None,
    omit_egg: bool = False,
    children: list[str] | None = None,
    parent: str | None = None,
    **overrides,
) -> Path:
    """
    Write a ticket markdown file with YAML frontmatter to disk.

    This factory eliminates verbose inline YAML blocks that appear in tests.
    Replaces patterns like:

        # Before (15 lines):
        ticket_content = '''---
        id: b.abc
        schema_version: '0.1'
        title: Backend Epic
        type: bee
        status: open
        tags: []
        children: []
        up_dependencies: []
        down_dependencies: []
        created_at: '2024-01-01T00:00:00+00:00'
        egg: null
        ---
        Backend bee description
        '''
        (backend_dir / f"{ticket_id}.md").write_text(ticket_content)

        # After (1 line):
        write_ticket_file(backend_dir, "b.abc", title="Backend Epic")

    Args:
        directory: Directory to write ticket file into
        id: Ticket ID (used for filename and frontmatter)
        title: Ticket title (default: "Test Ticket")
        type: Ticket type (default: "bee")
        status: Ticket status (default: "open")
        body: Optional markdown body content after frontmatter (default: "")
        egg: Egg field value for bee tickets (default: None). Only included in frontmatter
             for bee tickets. Child tier tickets (t1, t2, t3) do NOT get egg field.
        omit_egg: If True, omit egg field from bee ticket frontmatter (default: False).
                  Used for testing malformed bee tickets that are missing the required egg field.
        **overrides: Additional frontmatter fields to override defaults
                    (parent, children, tags, dependencies, etc.)

    Returns:
        Path: Path to created ticket file

    Example:
        >>> # Minimal bee file
        >>> path = write_ticket_file(hive_dir, TICKET_ID_TEST_BEE, title="My Bee")

        >>> # Task with parent
        >>> path = write_ticket_file(
        ...     hive_dir,
        ...     TICKET_ID_HELPER_TASK_XYZ1,
        ...     title="My Task",
        ...     type="t1",
        ...     parent=TICKET_ID_TEST_BEE
        ... )

        >>> # With custom body
        >>> path = write_ticket_file(
        ...     hive_dir,
        ...     TICKET_ID_HELPER_BEE_GHI,
        ...     title="Documented Ticket",
        ...     body="## Details\\n\\nAdditional information here."
        ... )

        >>> # With relationships
        >>> path = write_ticket_file(
        ...     hive_dir,
        ...     TICKET_ID_HELPER_TASK_JKL,
        ...     title="Blocked Task",
        ...     type="t1",
        ...     parent=TICKET_ID_TEST_BEE,
        ...     up_dependencies=[TICKET_ID_HELPER_TASK_XYZ1]
        ... )

        >>> # Bee with egg field
        >>> path = write_ticket_file(
        ...     hive_dir,
        ...     "b.egg",
        ...     title="Egg Bee",
        ...     egg="https://example.com/spec.md"
        ... )

        >>> # Bee WITHOUT egg field (for testing malformed tickets)
        >>> path = write_ticket_file(
        ...     hive_dir,
        ...     "b.bad",
        ...     title="Malformed Bee",
        ...     omit_egg=True
        ... )
    """
    # Build frontmatter with defaults + overrides
    short_id = id.split(".", 1)[1] if "." in id else id
    frontmatter = {
        "id": id,
        "schema_version": "0.1",
        "title": title,
        "type": type,
        "status": status,
        "tags": [],
        "children": [],
        "up_dependencies": [],
        "down_dependencies": [],
        "created_at": "2024-01-01T00:00:00+00:00",
        "guid": generate_guid(short_id),
    }

    # Include egg field ONLY for bee tickets (not child tier tickets)
    # Unless omit_egg=True (for testing malformed tickets)
    if type == "bee" and not omit_egg:
        frontmatter["egg"] = egg

    # Apply explicit children/parent params (override defaults when provided)
    if children is not None:
        frontmatter["children"] = children
    if parent is not None:
        frontmatter["parent"] = parent

    # Apply overrides
    frontmatter.update(overrides)

    # Format YAML
    yaml_lines = ["---"]
    for key, value in frontmatter.items():
        if value is None:
            yaml_lines.append(f"{key}: null")
        elif isinstance(value, str):
            # Always quote schema_version to ensure it stays as string "0.1" not float 0.1
            # Quote values with special characters
            if key == "schema_version" or ":" in value or value.startswith("'"):
                yaml_lines.append(f"{key}: '{value}'")
            else:
                yaml_lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            if not value:
                yaml_lines.append(f"{key}: []")
            else:
                yaml_lines.append(f"{key}:")
                for item in value:
                    yaml_lines.append(f"  - {item}")
        else:
            yaml_lines.append(f"{key}: {value}")
    yaml_lines.append("---")

    # Add body if provided
    if body:
        yaml_lines.append("")
        yaml_lines.append(body)
    else:
        yaml_lines.append("")
        yaml_lines.append(f"{title} body content.")

    # Write to file in hierarchical structure: {ticket_id}/{ticket_id}.md
    ticket_dir = directory / id
    ticket_dir.mkdir(parents=True, exist_ok=True)
    ticket_file = ticket_dir / f"{id}.md"
    ticket_file.write_text("\n".join(yaml_lines))

    return ticket_file
