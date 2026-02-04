"""
Ticket ID parsing utilities for Bees ticket management system.

This module provides foundational utilities for parsing ticket IDs and extracting
hive prefixes. These functions are used throughout the codebase and are extracted
here to prevent circular dependencies.

Ticket ID Format:
- New format: hive_name.bees-abc1 (with hive prefix)
- Legacy format: bees-abc1 (without hive prefix)
"""


def parse_ticket_id(ticket_id: str) -> tuple[str, str]:
    """
    Parse a ticket ID to extract hive name and base ID.

    Splits ticket IDs on the first dot to extract hive prefix and base ID.
    For new format IDs (hive_name.bees-abc1), returns (hive_name, bees-abc1).
    For legacy format IDs (bees-abc1), returns ('', bees-abc1).

    Args:
        ticket_id: Ticket ID string (e.g., 'backend.bees-abc1' or 'bees-abc1')

    Returns:
        tuple[str, str]: (hive_name, base_id) where hive_name is empty string for legacy IDs

    Raises:
        ValueError: If ticket_id is None or empty string

    Example:
        >>> parse_ticket_id('backend.bees-abc1')
        ('backend', 'bees-abc1')
        >>> parse_ticket_id('bees-abc1')
        ('', 'bees-abc1')
        >>> parse_ticket_id('multi.dot.bees-xyz9')
        ('multi', 'dot.bees-xyz9')
    """
    # Handle None and empty string
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


def parse_hive_from_ticket_id(ticket_id: str) -> str | None:
    """
    Extract hive prefix from a ticket ID.

    Splits ticket_id on first dot to extract the hive name prefix.
    For prefixed IDs (backend.bees-abc1), returns the hive name (backend).
    For unprefixed IDs (bees-abc1), returns None (malformed/legacy format).

    Args:
        ticket_id: Ticket ID string (e.g., 'backend.bees-abc1')

    Returns:
        str | None: Hive name prefix, or None if no dot found (malformed ID)

    Example:
        >>> parse_hive_from_ticket_id('backend.bees-abc1')
        'backend'
        >>> parse_hive_from_ticket_id('bees-abc1')
        None
        >>> parse_hive_from_ticket_id('multi.dot.bees-xyz9')
        'multi'
    """
    # Split on first dot only
    if '.' in ticket_id:
        hive_name, _, _ = ticket_id.partition('.')
        return hive_name
    else:
        # No dot found - malformed ID
        return None
