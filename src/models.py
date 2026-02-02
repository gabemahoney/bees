"""Data models for ticket types."""

from dataclasses import dataclass, field
from datetime import datetime

from .types import TicketType

__all__ = ["Ticket", "Epic", "Task", "Subtask", "TicketType"]


@dataclass
class Ticket:
    """Base ticket model with common fields."""

    id: str
    type: TicketType
    title: str
    description: str = ""
    labels: list[str] = field(default_factory=list)
    up_dependencies: list[str] = field(default_factory=list)
    down_dependencies: list[str] = field(default_factory=list)
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    owner: str | None = None
    priority: int | None = None
    status: str | None = None
    bees_version: str | None = None


@dataclass
class Epic(Ticket):
    """Epic ticket model."""

    def __post_init__(self):
        """Ensure type is always 'epic'."""
        object.__setattr__(self, "type", "epic")


@dataclass
class Task(Ticket):
    """Task ticket model."""

    def __post_init__(self):
        """Ensure type is always 'task'."""
        object.__setattr__(self, "type", "task")


@dataclass
class Subtask(Ticket):
    """Subtask ticket model."""

    def __post_init__(self):
        """Ensure type is always 'subtask' and parent is required."""
        object.__setattr__(self, "type", "subtask")
        if not self.parent:
            raise ValueError("Subtask must have a parent")
