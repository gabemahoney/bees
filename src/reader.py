"""Ticket reader module for loading and parsing ticket files."""

from datetime import datetime
from pathlib import Path
from typing import Any

from . import cache
from .models import Ticket
from .parser import ParseError, parse_frontmatter
from .types import TicketType
from .validator import ValidationError, validate_structure

__all__ = ["get_ticket_type", "read_ticket"]


def read_ticket(ticket_id: str, file_path: Path | str | None = None) -> Ticket:
    """
    Read and parse a ticket file, returning a Ticket object.

    Uses a module-level cache keyed on ticket_id. A stat() check on the file
    determines freshness: cache hit on mtime match, re-read on mismatch,
    read+cache on miss.

    When file_path is provided, it is used directly.

    When file_path is omitted, the cached path is used if available (with a
    freshness check). If the cached path is stale (FileNotFoundError) or there
    is no cache entry, all configured hives are searched for the ticket file.

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx", "t1.X4F2")
        file_path: Optional path to the ticket markdown file. If omitted,
            the cached path or hive discovery is used.

    Returns:
        Ticket object with type specified in frontmatter

    Raises:
        FileNotFoundError: If file doesn't exist or cannot be found in any hive
        ParseError: If file has invalid format or YAML
        ValidationError: If ticket data doesn't match schema

    Examples:
        >>> ticket = read_ticket("b.Amx", "backend/b.Amx.md")
        >>> ticket.id
        'b.Amx'
        >>> ticket.type
        'bee'
        >>> ticket = read_ticket("b.Amx")  # ID-only lookup via cache or discovery
        >>> ticket.type
        'bee'
    """
    if file_path is not None:
        # Path-based lookup: use provided path directly
        file_path = Path(file_path)
        return _read_from_path(ticket_id, file_path)

    # ID-only lookup: check cache for stored path first
    cached = cache.get(ticket_id)
    if cached is not None:
        cached_mtime, cached_path, cached_ticket = cached
        try:
            file_mtime = cached_path.stat().st_mtime
        except FileNotFoundError:
            # Stale cached path — evict and fall through to discovery
            cache.evict(ticket_id)
        else:
            if cached_mtime == file_mtime:
                return cached_ticket
            # mtime mismatch — re-read from cached path (pass known mtime to avoid redundant stat)
            return _read_from_path(ticket_id, cached_path, _known_mtime=file_mtime)

    # Cache miss or stale: discover via hive config
    from .config import load_bees_config
    from .paths import compute_ticket_path

    config = load_bees_config()
    if config and config.hives:
        for hive_config in config.hives.values():
            hive_path = Path(hive_config.path)
            candidate = compute_ticket_path(ticket_id, hive_path)
            if candidate.exists():
                return _read_from_path(ticket_id, candidate)

    raise FileNotFoundError(f"Ticket '{ticket_id}' not found in any configured hive")


def _read_from_path(ticket_id: str, file_path: Path, *, _known_mtime: float | None = None) -> Ticket:
    """Read and cache a ticket from an explicit file path.

    Args:
        _known_mtime: If provided, skip the stat() call and cache freshness check.
            Used when the caller has already verified the file exists and the cache
            is stale (e.g., ID-only lookup with mtime mismatch).
    """
    if _known_mtime is not None:
        file_mtime = _known_mtime
    else:
        # Stat the file to get mtime; evict on FileNotFoundError, propagate other OSError
        try:
            file_mtime = file_path.stat().st_mtime
        except FileNotFoundError:
            cache.evict(ticket_id)
            raise
        except OSError:
            raise

        # Check cache freshness
        cached = cache.get(ticket_id)
        if cached is not None:
            cached_mtime, cached_path, cached_ticket = cached
            if cached_mtime == file_mtime:
                return cached_ticket
            # mtime mismatch — fall through to re-read

    # Parse file
    frontmatter, body = parse_frontmatter(file_path)

    # Check for schema_version field to confirm this is a Bees ticket
    if "schema_version" not in frontmatter:
        raise ValidationError("Markdown file is not a valid Bees ticket: missing 'schema_version' field in frontmatter")

    # Validate structural requirements only (permissive - allows invalid types)
    validate_structure(frontmatter)

    # Capture raw frontmatter keys before any mutations (used by linter for disallowed field detection)
    raw_keys = frozenset(frontmatter.keys())

    # Add description from body
    frontmatter["description"] = body

    # Convert date strings to datetime if present
    for date_field in ["created_at"]:
        if date_field in frontmatter and frontmatter[date_field]:
            if isinstance(frontmatter[date_field], str):
                try:
                    frontmatter[date_field] = datetime.fromisoformat(frontmatter[date_field])
                except (ValueError, TypeError) as e:
                    # Log warning but keep as string if parsing fails
                    import warnings

                    warnings.warn(
                        f"Could not parse {date_field} as ISO datetime: {e}. "
                        f"Keeping as string: {frontmatter[date_field]}",
                        stacklevel=2,
                    )

    # Return Ticket object - type validation happens in __post_init__
    ticket = Ticket(**_filter_ticket_fields(frontmatter))
    ticket._raw_keys = raw_keys

    cache.put(ticket_id, file_mtime, file_path, ticket)

    return ticket


def get_ticket_type(ticket_id: str) -> TicketType | None:
    """Return the type of a ticket given its ID.

    Delegates to read_ticket() which handles cache lookup and hive discovery.

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx", "t1.X4F2")

    Returns:
        The ticket type ('bee', 't1', 't2', etc.) if found, None otherwise.
    """
    if not ticket_id:
        return None

    try:
        ticket = read_ticket(ticket_id)
        return ticket.type
    except (FileNotFoundError, ParseError, ValidationError):
        return None


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
        "tags",
        "up_dependencies",
        "down_dependencies",
        "parent",
        "children",
        "egg",
        "created_at",
        "status",
        "schema_version",
        "guid",
    }

    return {k: v for k, v in data.items() if k in known_fields}
