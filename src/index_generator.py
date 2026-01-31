"""Index generation module for creating markdown index of all tickets."""

from datetime import datetime
from pathlib import Path

from .models import Ticket
from .paths import list_tickets, get_index_path
from .reader import read_ticket

__all__ = ["scan_tickets", "format_index_markdown", "generate_index", "is_index_stale"]


def scan_tickets(
    status_filter: str | None = None,
    type_filter: str | None = None
) -> dict[str, list[Ticket]]:
    """
    Scan tickets/ directory and load all ticket metadata.

    Recursively scans the tickets directory structure (epics/, tasks/, subtasks/)
    and loads all ticket files, grouping them by type. Optionally filters results
    by status and/or type.

    Args:
        status_filter: Optional status to filter by (e.g., 'open', 'completed')
        type_filter: Optional type to filter by (e.g., 'epic', 'task', 'subtask')

    Returns:
        Dictionary with keys 'epic', 'task', 'subtask' containing lists of
        corresponding Ticket objects. Empty lists if no tickets of that type exist
        or if filtered out.

    Examples:
        >>> tickets = scan_tickets()
        >>> len(tickets['epic'])
        5
        >>> tickets = scan_tickets(status_filter='open')
        >>> tickets = scan_tickets(type_filter='epic')
        >>> tickets = scan_tickets(status_filter='completed', type_filter='task')
    """
    # Initialize result dictionary with empty lists for each type
    result: dict[str, list[Ticket]] = {
        "epic": [],
        "task": [],
        "subtask": []
    }

    # Get all ticket files
    all_ticket_paths = list_tickets()

    # Load each ticket and group by type
    for ticket_path in all_ticket_paths:
        try:
            ticket = read_ticket(ticket_path)

            # Apply filters
            if status_filter and ticket.status != status_filter:
                continue
            if type_filter and ticket.type != type_filter:
                continue

            result[ticket.type].append(ticket)
        except Exception as e:
            # Log warning but continue processing other tickets
            import warnings
            warnings.warn(
                f"Failed to load ticket {ticket_path}: {e}. Skipping."
            )
            continue

    return result


def format_index_markdown(tickets: dict[str, list[Ticket]], include_timestamp: bool = True) -> str:
    """
    Generate formatted markdown index from grouped ticket data.

    Creates a structured markdown document with sections for Epics, Tasks, and
    Subtasks. Each ticket shows ID, title, status, and hierarchy information.

    Args:
        tickets: Dictionary with 'epic', 'task', 'subtask' keys containing
                 lists of Ticket objects
        include_timestamp: If True, includes generation timestamp in header

    Returns:
        Formatted markdown string with all tickets organized by type

    Examples:
        >>> tickets = scan_tickets()
        >>> markdown = format_index_markdown(tickets)
        >>> print(markdown)
        # Ticket Index

        ## Epics
        - [bees-250] Authentication System (open)
        ...
    """
    lines = []

    # Add header
    lines.append("# Ticket Index")
    lines.append("")

    # Add timestamp metadata
    if include_timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"*Generated: {timestamp}*")
        lines.append("")

    # Section for each ticket type
    sections = [
        ("Epics", "epic"),
        ("Tasks", "task"),
        ("Subtasks", "subtask")
    ]

    for section_title, ticket_type in sections:
        lines.append(f"## {section_title}")
        lines.append("")

        ticket_list = tickets.get(ticket_type, [])

        if not ticket_list:
            lines.append("*No tickets found*")
            lines.append("")
        else:
            # Sort by ID for consistent ordering
            sorted_tickets = sorted(ticket_list, key=lambda t: t.id)

            for ticket in sorted_tickets:
                # Format: - [ticket-id: title](tickets/{type}s/ticket-id.md) (status)
                status = ticket.status or "unknown"
                line = f"- [{ticket.id}: {ticket.title}](tickets/{ticket.type}s/{ticket.id}.md) ({status})"

                # Add parent info for subtasks
                if ticket.parent:
                    line += f" (parent: {ticket.parent})"

                lines.append(line)

            lines.append("")

    return "\n".join(lines)


def is_index_stale() -> bool:
    """
    Check if index.md is stale (older than ticket files).

    Returns:
        True if index needs regeneration, False if index is up-to-date

    Examples:
        >>> is_index_stale()
        True
    """
    from .paths import TICKETS_DIR

    index_path = get_index_path()

    # If index doesn't exist, it's stale
    if not index_path.exists():
        return True

    # Get index modification time
    index_mtime = index_path.stat().st_mtime

    # Check all ticket files
    all_tickets = list_tickets()

    # If no tickets exist, index is not stale
    if not all_tickets:
        return False

    # Check if any ticket is newer than index
    for ticket_path in all_tickets:
        if ticket_path.stat().st_mtime > index_mtime:
            return True

    return False


def generate_index(
    status_filter: str | None = None,
    type_filter: str | None = None
) -> str:
    """
    Generate complete markdown index for all tickets.

    High-level orchestration function that scans the tickets directory,
    loads all tickets, and formats them into a markdown index. Optionally
    filters results by status and/or type.

    Args:
        status_filter: Optional status to filter by (e.g., 'open', 'completed')
        type_filter: Optional type to filter by (e.g., 'epic', 'task', 'subtask')

    Returns:
        Complete markdown index as a string

    Examples:
        >>> index_md = generate_index()
        >>> print(index_md)
        # Ticket Index
        ## Epics
        ...
        >>> open_tickets = generate_index(status_filter='open')
        >>> epics_only = generate_index(type_filter='epic')
    """
    tickets = scan_tickets(status_filter, type_filter)
    return format_index_markdown(tickets, include_timestamp=True)
