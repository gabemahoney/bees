"""
Ticket ID parsing utilities for Bees ticket management system.

This module provides foundational utilities for parsing ticket IDs and extracting
type prefixes. These functions are used throughout the codebase and are extracted
here to prevent circular dependencies.

Ticket ID Format:
- New format: {type_prefix}.{shortID} (e.g., b.amx, t1.abc.de, t2.abc.de.fg)
- Bee IDs: b.XXX (3-char shortID, no internal periods)
- Tier IDs: t{N}.XXX(.YY)+ (3-char base + N two-char segments separated by periods)
"""


def parse_ticket_id(ticket_id: str) -> tuple[str, str]:
    """
    Parse a ticket ID to extract type prefix and shortID.

    Splits ticket IDs on the first dot to extract type prefix and shortID.
    The shortID for tier tickets contains internal periods (e.g., "abc.de").

    Args:
        ticket_id: Ticket ID string (e.g., 'b.amx', 't1.abc.de', 't2.abc.de.fg')

    Returns:
        tuple[str, str]: (type_prefix, short_id)
        - "b.amx" -> ("b", "amx")
        - "t1.abc.de" -> ("t1", "abc.de")
        - "t2.abc.de.fg" -> ("t2", "abc.de.fg")

    Raises:
        ValueError: If ticket_id is None, empty, or malformed

    Example:
        >>> parse_ticket_id('b.amx')
        ('b', 'amx')
        >>> parse_ticket_id('t1.abc.de')
        ('t1', 'abc.de')
        >>> parse_ticket_id('t2.abc.de.fg')
        ('t2', 'abc.de.fg')
    """
    # Handle None and empty string
    if ticket_id is None:
        raise ValueError("ticket_id cannot be None")

    if not ticket_id or not ticket_id.strip():
        raise ValueError("ticket_id cannot be empty")

    # Split on first dot only
    if "." not in ticket_id:
        raise ValueError(f"Invalid ticket_id format: {ticket_id}. Expected format: {{prefix}}.{{shortID}}")

    type_prefix, _, short_id = ticket_id.partition(".")
    if not type_prefix or not short_id:
        raise ValueError(f"Invalid ticket_id format: {ticket_id}. Both prefix and shortID required.")

    return (type_prefix, short_id)


def parse_type_from_ticket_id(ticket_id: str) -> str:
    """
    Extract ticket type from ticket ID.

    Converts type prefix to canonical type string:
    - "b" -> "bee"
    - "t1" -> "t1"
    - "t2" -> "t2"
    - etc.

    Args:
        ticket_id: Ticket ID string (e.g., 'b.amx', 't1.abc.de', 't2.abc.de.fg')

    Returns:
        str: Canonical type string ("bee", "t1", "t2", etc.)

    Raises:
        ValueError: If ticket_id is malformed

    Example:
        >>> parse_type_from_ticket_id('b.amx')
        'bee'
        >>> parse_type_from_ticket_id('t1.abc.de')
        't1'
        >>> parse_type_from_ticket_id('t2.abc.de.fg')
        't2'
    """
    type_prefix, _ = parse_ticket_id(ticket_id)

    if type_prefix == "b":
        return "bee"
    else:
        return type_prefix
