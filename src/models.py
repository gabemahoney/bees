"""Data models for ticket types."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .types import TicketType

__all__ = ["Ticket", "TicketType"]


@dataclass
class Ticket:
    """Base ticket model with common fields.

    Validation Architecture:
    ------------------------
    This model performs STRUCTURAL validation only (ensuring fields have correct types).
    Business rule validation (valid ticket types, tier hierarchies, relationship constraints)
    is handled by the linter (src/linter.py).

    Why this split?
    - Allows linter to load corrupt tickets to analyze and fix them
    - Separates concerns: data structure vs business logic
    - Prevents validation from blocking ticket instantiation

    Structural Validation (IN MODEL):
    - Field types are correct (str, list, datetime, etc.)
    - Required fields are present

    Business Validation (IN LINTER):
    - Ticket type is valid ('bee' or configured tier types like 't1', 't2')
    - Parent/child relationships follow tier hierarchy rules
    - Dependencies are bidirectional and valid
    - No circular dependencies exist

    Example:
        # This succeeds (structural validation passes):
        ticket = Ticket(id="b.Amx", type="invalid_type", title="Test")

        # Linter then detects and reports business rule violations:
        # "Invalid ticket type: 'invalid_type'"
    """

    id: str
    type: TicketType
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    up_dependencies: list[str] = field(default_factory=list)
    down_dependencies: list[str] = field(default_factory=list)
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    egg: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    created_at: datetime | None = None
    status: str | None = None
    schema_version: str | None = None
    guid: str | None = None

    def __post_init__(self):
        """Permissive post-init - allows any type value and parent configuration.

        Business rule validation (valid types, parent requirements) is handled by the linter.
        Ticket model accepts corrupt data to allow linter to load and fix it.
        """
        # No validation - accept any type value and any parent configuration
        pass
