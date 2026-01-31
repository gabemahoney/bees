"""Index generation module for creating markdown index of all tickets."""

from pathlib import Path

from .models import Ticket
from .paths import list_tickets
from .reader import read_ticket

__all__ = ["scan_tickets", "format_index_markdown", "generate_index"]


def scan_tickets() -> dict[str, list[Ticket]]:
    """
    Scan tickets/ directory and load all ticket metadata.

    Recursively scans the tickets directory structure (epics/, tasks/, subtasks/)
    and loads all ticket files, grouping them by type.

    Returns:
        Dictionary with keys 'epic', 'task', 'subtask' containing lists of
        corresponding Ticket objects. Empty lists if no tickets of that type exist.

    Examples:
        >>> tickets = scan_tickets()
        >>> len(tickets['epic'])
        5
        >>> tickets['task'][0].title
        'Implement authentication'
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
            result[ticket.type].append(ticket)
        except Exception as e:
            # Log warning but continue processing other tickets
            import warnings
            warnings.warn(
                f"Failed to load ticket {ticket_path}: {e}. Skipping."
            )
            continue

    return result


def format_index_markdown(tickets: dict[str, list[Ticket]]) -> str:
    """
    Generate formatted markdown index from grouped ticket data.

    Creates a structured markdown document with sections for Epics, Tasks, and
    Subtasks. Each ticket shows ID, title, status, and hierarchy information.

    Args:
        tickets: Dictionary with 'epic', 'task', 'subtask' keys containing
                 lists of Ticket objects

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
                # Format: - [ID] Title (status)
                status = ticket.status or "unknown"
                line = f"- [{ticket.id}] {ticket.title} ({status})"

                # Add parent info for subtasks
                if ticket.parent:
                    line += f" (parent: {ticket.parent})"

                lines.append(line)

            lines.append("")

    return "\n".join(lines)


def generate_index() -> str:
    """
    Generate complete markdown index for all tickets.

    High-level orchestration function that scans the tickets directory,
    loads all tickets, and formats them into a markdown index.

    This is the main public API for index generation.

    Returns:
        Complete markdown index as a string

    Examples:
        >>> index_md = generate_index()
        >>> print(index_md)
        # Ticket Index
        ## Epics
        ...
    """
    tickets = scan_tickets()
    return format_index_markdown(tickets)
