"""Ticket read cache module.

Provides a module-level singleton cache for read_ticket() results.
Key: ticket_id → Value: (mtime, Path, Ticket)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Ticket

__all__ = ["contains", "get", "put", "evict", "clear"]

# Module-private backing store: ticket_id -> (mtime, Path, Ticket)
_cache: dict[str, tuple[float, Path, Ticket]] = {}


def contains(ticket_id: str) -> bool:
    """Return True if ticket_id is present in the cache, regardless of mtime."""
    return ticket_id in _cache


def get(ticket_id: str) -> tuple[float, Path, Ticket] | None:
    """Return (mtime, Path, Ticket) for the given ticket_id, or None if not cached."""
    return _cache.get(ticket_id)


def put(ticket_id: str, mtime: float, path: Path, ticket: Ticket) -> None:
    """Store (mtime, Path, Ticket) under the given ticket_id."""
    _cache[ticket_id] = (mtime, path, ticket)


def evict(ticket_id: str) -> None:
    """Remove entry for the given ticket_id if present."""
    _cache.pop(ticket_id, None)


def clear() -> None:
    """Remove all entries from the cache."""
    _cache.clear()
