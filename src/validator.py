"""Validator for ticket schema compliance."""

from typing import Any

__all__ = [
    "validate_structure",
    "validate_ticket_type",
    "validate_child_tier_parent",
    "validate_subtask_parent",  # Legacy alias for validate_child_tier_parent
    "validate_field_types",
    "validate_ticket_business",
    "validate_ticket",  # Legacy alias for validate_ticket_business
    "validate_id_format",
    "ValidationError",
]


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


# Base tier that's always valid (t0)
BASE_TIER = "bee"


def validate_ticket_type(ticket_type: str, hive_name: str | None = None) -> None:
    """
    Validate ticket type against base tier and config child_tiers.

    Valid types:
    - "bee" (always valid, it's t0)
    - Tier IDs from config (t1, t2, t3...)
    - Friendly names from config (singular/plural if provided)

    Args:
        ticket_type: The ticket type to validate
        hive_name: Optional hive name for per-hive child_tiers resolution

    Raises:
        ValidationError: If type is not valid
    """
    if not isinstance(ticket_type, str):
        raise ValidationError(f"Field 'type' must be string, got {type(ticket_type)}")

    # "bee" is always valid (t0 base tier)
    if ticket_type == BASE_TIER:
        return

    # Load config to check child_tiers
    from .config import load_bees_config, resolve_child_tiers_for_hive

    config = load_bees_config()

    # Resolve child_tiers based on hive_name
    if hive_name is not None:
        child_tiers = resolve_child_tiers_for_hive(hive_name, config)
    else:
        # When hive_name is None, use scope-level config.child_tiers
        # If config.child_tiers is None (not configured), default to {}
        child_tiers = config.child_tiers if config and config.child_tiers is not None else {}

    # Build valid types from tier IDs and friendly names
    valid_types = {BASE_TIER}
    if child_tiers:
        # Add tier IDs (t1, t2, t3...)
        valid_types.update(child_tiers.keys())

        # Add friendly names (singular/plural if provided)
        for tier_config in child_tiers.values():
            if tier_config.singular:
                valid_types.add(tier_config.singular)
            if tier_config.plural:
                valid_types.add(tier_config.plural)

    if ticket_type not in valid_types:
        sorted_types = sorted(valid_types)
        types_str = ", ".join(sorted_types)
        if hive_name is not None:
            raise ValidationError(f"Invalid type: {ticket_type} for hive '{hive_name}'. Must be one of: {types_str}")
        else:
            raise ValidationError(f"Invalid type: {ticket_type}. Must be one of: {types_str}")


def validate_child_tier_parent(data: dict[str, Any], hive_name: str | None = None) -> None:
    """
    Validate that child tier tickets have a parent.

    All child tiers (t1, t2, t3...) require a parent. Only "bee" (t0) can have no parent.

    Args:
        data: Ticket frontmatter dictionary
        hive_name: Optional hive name for per-hive child_tiers resolution

    Raises:
        ValidationError: If child tier has no parent
    """
    ticket_type = data.get("type")

    # "bee" (t0) never requires a parent
    if ticket_type == BASE_TIER:
        return

    # Load config to check if this is a child tier
    from .config import load_bees_config, resolve_child_tiers_for_hive

    config = load_bees_config()

    # Resolve child_tiers based on hive_name
    if hive_name is not None:
        child_tiers = resolve_child_tiers_for_hive(hive_name, config)
    else:
        # When hive_name is None, use scope-level config.child_tiers
        # If config.child_tiers is None (not configured), default to {}
        child_tiers = config.child_tiers if config and config.child_tiers is not None else {}

    # Check if ticket_type is a child tier (in child_tiers or a friendly name)
    is_child_tier = False
    if child_tiers:
        # Check if it's a tier ID (t1, t2, t3...)
        if ticket_type in child_tiers:
            is_child_tier = True
        else:
            # Check if it's a friendly name (singular/plural)
            for tier_config in child_tiers.values():
                if ticket_type == tier_config.singular or ticket_type == tier_config.plural:
                    is_child_tier = True
                    break

    # If it's a child tier, require parent
    if is_child_tier:
        if "parent" not in data or not data["parent"]:
            raise ValidationError(f"{ticket_type} must have a parent")


def validate_field_types(data: dict[str, Any]) -> None:
    """
    Validate that list fields are lists of strings and parent is string or None.

    Args:
        data: Ticket frontmatter dictionary

    Raises:
        ValidationError: If field types are incorrect
    """
    # Validate optional list fields
    list_fields = ["tags", "up_dependencies", "down_dependencies", "children"]
    for field in list_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], list):
                raise ValidationError(f"Field '{field}' must be list, got {type(data[field])}")

            # Check all items are strings
            for item in data[field]:
                if not isinstance(item, str):
                    raise ValidationError(f"Field '{field}' must contain only strings, found {type(item)}")

    # Validate parent field
    if "parent" in data and data["parent"] is not None:
        if not isinstance(data["parent"], str):
            raise ValidationError(f"Field 'parent' must be string or null, got {type(data['parent'])}")


def validate_ticket_business(data: dict[str, Any]) -> None:
    """
    Validate ticket data against business rules (strict validation).

    Args:
        data: Ticket frontmatter dictionary

    Raises:
        ValidationError: If validation fails

    Validation rules:
    - Required fields: id, type, title
    - type must be one of: bee or config child_tiers (t1, t2, ...)
    - id must match format: b.XXX (3 chars) or t{N}.{3+N*2 chars}
    - tags must be list if present
    - dependencies must be lists if present
    - parent must be string or None
    - children must be list if present
    - child tier tickets must have parent
    """
    # Check required fields
    required_fields = ["id", "type", "title"]
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")

        if not data[field]:
            raise ValidationError(f"Required field '{field}' cannot be empty")

    # Validate ID format
    ticket_id = data["id"]
    if not isinstance(ticket_id, str):
        raise ValidationError(f"Field 'id' must be string, got {type(ticket_id)}")

    if not validate_id_format(ticket_id):
        raise ValidationError(
            f"Invalid ID format: {ticket_id}. Expected format: b.XXX (3 chars) or t{{N}}.{{N+3 chars}} "
            "(using 34-char lowercase-only charset: 1-9, a-z excluding 'l')"
        )

    # Validate title
    if not isinstance(data["title"], str):
        raise ValidationError(f"Field 'title' must be string, got {type(data['title'])}")

    # Validate type against config
    ticket_type = data["type"]
    validate_ticket_type(ticket_type)

    # Validate field types (lists, parent)
    validate_field_types(data)

    # Validate child tier parent requirement
    validate_child_tier_parent(data)


# Legacy alias for backward compatibility
def validate_ticket(data: dict[str, Any]) -> None:
    """Legacy alias for validate_ticket_business(). Use validate_ticket_business() instead."""
    validate_ticket_business(data)


# Legacy alias for backward compatibility
def validate_subtask_parent(data: dict[str, Any]) -> None:
    """Legacy alias for validate_child_tier_parent(). Use validate_child_tier_parent() instead."""
    validate_child_tier_parent(data)


def validate_structure(data: dict[str, Any]) -> None:
    """
    Validate ticket structural requirements only (permissive validation).

    Checks only that required fields exist and are non-empty.
    Does NOT validate business rules like valid types, ID format, or subtask parent requirements.

    Args:
        data: Ticket frontmatter dictionary

    Raises:
        ValidationError: If structural validation fails

    Structural checks:
    - Required fields present: id, type, title
    - Fields are not empty
    - Fields are strings (type checking, not business validation)
    """
    # Check required fields exist
    required_fields = ["id", "type", "title"]
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")

        if not data[field]:
            raise ValidationError(f"Required field '{field}' cannot be empty")

        # Validate field is a string (type checking)
        if not isinstance(data[field], str):
            raise ValidationError(f"Field '{field}' must be string, got {type(data[field])}")


def validate_id_format(ticket_id: str) -> bool:
    """
    Check if ticket ID matches required format with length validation.

    Args:
        ticket_id: The ticket ID to validate

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_id_format("b.amx")
        True
        >>> validate_id_format("t1.amx12")
        True
        >>> validate_id_format("t2.amx1249")
        True
        >>> validate_id_format("b.amx9")  # wrong length
        False
    """
    # Use the validator from id_utils for full validation including length
    from .id_utils import is_valid_ticket_id

    return is_valid_ticket_id(ticket_id)
