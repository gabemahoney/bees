"""Ticket reader module for loading and parsing ticket files."""

from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Epic, Task, Subtask, Ticket
from .parser import parse_frontmatter
from .validator import validate_ticket

__all__ = ["read_ticket"]


def read_ticket(file_path: Path | str) -> Ticket:
    """
    Read and parse a ticket file, returning appropriate ticket object.

    Args:
        file_path: Path to the ticket markdown file

    Returns:
        Epic, Task, or Subtask object based on ticket type

    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If file has invalid format or YAML
        ValidationError: If ticket data doesn't match schema

    Examples:
        >>> ticket = read_ticket("tickets/epics/bees-250.md")
        >>> ticket.id
        'bees-250'
        >>> isinstance(ticket, Epic)
        True
    """
    # Parse file
    frontmatter, body = parse_frontmatter(file_path)

    # Validate against schema
    validate_ticket(frontmatter)

    # Add description from body
    frontmatter["description"] = body

    # Convert date strings to datetime if present
    for date_field in ["created_at", "updated_at"]:
        if date_field in frontmatter and frontmatter[date_field]:
            if isinstance(frontmatter[date_field], str):
                try:
                    frontmatter[date_field] = datetime.fromisoformat(
                        frontmatter[date_field]
                    )
                except (ValueError, TypeError) as e:
                    # Log warning but keep as string if parsing fails
                    import warnings
                    warnings.warn(
                        f"Could not parse {date_field} as ISO datetime: {e}. "
                        f"Keeping as string: {frontmatter[date_field]}"
                    )

    # Instantiate appropriate ticket type
    ticket_type = frontmatter["type"]

    if ticket_type == "epic":
        return Epic(**_filter_ticket_fields(frontmatter))
    elif ticket_type == "task":
        return Task(**_filter_ticket_fields(frontmatter))
    elif ticket_type == "subtask":
        return Subtask(**_filter_ticket_fields(frontmatter))
    else:
        # Should never reach here due to validation, but satisfy type checker
        raise ValueError(f"Invalid ticket type: {ticket_type}")


def _filter_ticket_fields(data: dict[str, Any]) -> dict[str, Any]:
    """
    Filter frontmatter to only include fields defined in Ticket model.

    Args:
        data: Full frontmatter dictionary

    Returns:
        Filtered dictionary with only known ticket fields
    """
    known_fields = {
        "id",
        "type",
        "title",
        "description",
        "labels",
        "up_dependencies",
        "down_dependencies",
        "parent",
        "children",
        "created_at",
        "updated_at",
        "created_by",
        "owner",
        "priority",
        "status",
    }

    return {k: v for k, v in data.items() if k in known_fields}
