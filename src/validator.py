"""Validator for ticket schema compliance."""

import re
from typing import Any

__all__ = ["validate_ticket", "validate_id_format", "ValidationError"]


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


# ID format: bees-XXX OR {hive_name}.bees-XXX where XXX is 3 alphanumeric chars (lowercase)
# Hive prefix must start with letter or underscore, contain only lowercase letters, numbers, and underscores
ID_PATTERN = re.compile(r"^([a-z_][a-z0-9_]*\.)?bees-[a-z0-9]{3}$")

VALID_TYPES = {"epic", "task", "subtask"}


def validate_ticket(data: dict[str, Any]) -> None:
    """
    Validate ticket data against schema requirements.

    Args:
        data: Ticket frontmatter dictionary

    Raises:
        ValidationError: If validation fails

    Validation rules:
    - Required fields: id, type, title
    - type must be one of: epic, task, subtask
    - id must match format: bees-XXX (3 alphanumeric chars)
    - labels must be list if present
    - dependencies must be lists if present
    - parent must be string or None
    - children must be list if present
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

    if not ID_PATTERN.match(ticket_id):
        raise ValidationError(
            f"Invalid ID format: {ticket_id}. Expected format: bees-XXX or hive.bees-XXX "
            "(3 lowercase alphanumeric characters)"
        )

    # Validate type enum
    ticket_type = data["type"]
    if not isinstance(ticket_type, str):
        raise ValidationError(f"Field 'type' must be string, got {type(ticket_type)}")

    if ticket_type not in VALID_TYPES:
        raise ValidationError(
            f"Invalid type: {ticket_type}. Must be one of {VALID_TYPES}"
        )

    # Validate title
    if not isinstance(data["title"], str):
        raise ValidationError(f"Field 'title' must be string, got {type(data['title'])}")

    # Validate optional list fields
    list_fields = ["labels", "up_dependencies", "down_dependencies", "children"]
    for field in list_fields:
        if field in data and data[field] is not None:
            if not isinstance(data[field], list):
                raise ValidationError(
                    f"Field '{field}' must be list, got {type(data[field])}"
                )

            # Check all items are strings
            for item in data[field]:
                if not isinstance(item, str):
                    raise ValidationError(
                        f"Field '{field}' must contain only strings, "
                        f"found {type(item)}"
                    )

    # Validate parent field
    if "parent" in data and data["parent"] is not None:
        if not isinstance(data["parent"], str):
            raise ValidationError(
                f"Field 'parent' must be string or null, got {type(data['parent'])}"
            )

    # Subtasks must have parent
    if ticket_type == "subtask":
        if "parent" not in data or not data["parent"]:
            raise ValidationError("Subtask must have a parent")


def validate_id_format(ticket_id: str) -> bool:
    """
    Check if ticket ID matches required format.

    Args:
        ticket_id: The ticket ID to validate

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_id_format("bees-250")
        True
        >>> validate_id_format("bees-abc")
        True
        >>> validate_id_format("bees-INVALID")
        False
        >>> validate_id_format("invalid-250")
        False
    """
    return bool(ID_PATTERN.match(ticket_id))
