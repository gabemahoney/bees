"""Index generation module for creating markdown index of all tickets."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import Ticket
from .paths import list_tickets
from .reader import read_ticket

__all__ = ["scan_tickets", "format_index_markdown", "generate_index", "is_index_stale"]


@dataclass
class _TicketNode:
    """A ticket and its resolved children in the hierarchy tree."""

    ticket: Ticket
    children: list[_TicketNode] = field(default_factory=list)


def _natural_sort_key(text: str) -> list[int | str]:
    """Return a sort key that orders digit runs numerically.

    Splits *text* on digit boundaries so that ``"Test 2"`` sorts before
    ``"Test 11"`` instead of using pure lexicographic order.
    """
    parts: list[int | str] = []
    for part in re.split(r"(\d+)", text.lower()):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part)
    return parts


def _topo_sort_nodes(nodes: list[_TicketNode]) -> list[_TicketNode]:
    """Topologically sort nodes using Kahn's algorithm.

    Sorts by ``up_dependencies`` so that a node appears after the nodes it
    depends on.  Ties within the same topological level are broken by
    ``_natural_sort_key`` on the ticket title.  If cycles exist the
    remaining nodes are appended in natural-title order.
    """
    if len(nodes) <= 1:
        return list(nodes)

    node_map: dict[str, _TicketNode] = {n.ticket.id: n for n in nodes}
    ids_in_group: set[str] = set(node_map)

    # Compute in-degree counting only deps within this group
    in_degree: dict[str, int] = {tid: 0 for tid in ids_in_group}
    for node in nodes:
        for dep_id in node.ticket.up_dependencies:
            if dep_id in ids_in_group:
                in_degree[node.ticket.id] += 1

    # Seed queue with zero-in-degree nodes, sorted by natural title
    queue: deque[_TicketNode] = deque(
        sorted(
            (node_map[tid] for tid, deg in in_degree.items() if deg == 0),
            key=lambda n: _natural_sort_key(n.ticket.title),
        )
    )

    result: list[_TicketNode] = []
    while queue:
        # Process one level at a time for stable tie-breaking
        level_size = len(queue)
        next_ready: list[_TicketNode] = []
        for _ in range(level_size):
            node = queue.popleft()
            result.append(node)
            # Decrease in-degree for nodes that depend on this one
            for other in nodes:
                if node.ticket.id in other.ticket.up_dependencies and other.ticket.id in ids_in_group:
                    in_degree[other.ticket.id] -= 1
                    if in_degree[other.ticket.id] == 0:
                        next_ready.append(other)
        # Sort newly ready nodes by natural title before adding to queue
        next_ready.sort(key=lambda n: _natural_sort_key(n.ticket.title))
        queue.extend(next_ready)

    # Handle cycles: append remaining nodes sorted by natural title
    if len(result) < len(nodes):
        remaining = [n for n in nodes if n not in result]
        remaining.sort(key=lambda n: _natural_sort_key(n.ticket.title))
        result.extend(remaining)

    return result


def _get_tier_display_names(hive_name: str | None = None) -> dict[str, str]:
    """
    Load tier display names from config.

    Reads child_tiers from config and returns a mapping of tier IDs
    to plural friendly names. Falls back to tier ID when friendly names are None.

    Args:
        hive_name: Optional hive name. When provided, resolves child_tiers for that hive
                   using the fallback chain (hive → scope → global → bees-only).
                   When omitted, uses scope-level child_tiers (legacy behavior).

    Returns:
        Dictionary mapping tier IDs to display names, e.g.:
        - {"t1": "Tasks", "t2": "Subtasks"} when friendly names defined
        - {"t1": "t1", "t2": "t2"} when friendly names are None
        - {} if no config or child_tiers not defined

    Examples:
        >>> names = _get_tier_display_names()
        >>> names.get("t1", "t1")
        'Tasks'
        >>> names = _get_tier_display_names(hive_name="backend")
        >>> names.get("t1", "t1")
        'Epic'
    """
    from .config import load_bees_config, resolve_child_tiers_for_hive

    config = load_bees_config()

    if not config:
        return {}

    # Resolve child_tiers based on hive_name parameter
    if hive_name:
        # Per-hive resolution using fallback chain
        child_tiers = resolve_child_tiers_for_hive(hive_name, config)
    else:
        # Legacy behavior: use scope-level child_tiers
        child_tiers = config.child_tiers

    # Return empty dict if no child_tiers
    if not child_tiers:
        return {}

    # Build mapping: tier_id -> display name (plural friendly name or tier_id fallback)
    result = {}
    for tier_id, tier_config in child_tiers.items():
        # Use plural friendly name if available, otherwise fall back to tier ID
        display_name = tier_config.plural if tier_config.plural else tier_id
        result[tier_id] = display_name

    return result


def scan_tickets(
    hive_name: str | None = None,
) -> dict[str, list[Ticket]]:
    """
    Scan tickets/ directory and load all ticket metadata.

    Scans hive root directories (flat storage) and loads all ticket files,
    grouping them by type from YAML frontmatter. Optionally filters by hive.

    Args:
        hive_name: Optional hive name to filter by (e.g., 'backend'). When provided,
                   only returns tickets belonging to that hive. When omitted, returns
                   tickets from all hives.

    Returns:
        Dictionary with ticket type keys (e.g., 'bee', 't1', 't2') containing lists of
        corresponding Ticket objects. Empty lists if no tickets of that type exist.

    Examples:
        >>> tickets = scan_tickets()
        >>> len(tickets['bee'])
        5
        >>> tickets = scan_tickets(hive_name='backend')
    """
    # Initialize result dictionary dynamically from config
    # Build keys as: "bee" + tier IDs from child_tiers (t1, t2, t3...)
    from .config import load_bees_config, resolve_child_tiers_for_hive

    config = load_bees_config()

    # Start with "bee" key
    result: dict[str, list[Ticket]] = {"bee": []}

    # Add tier keys from config (resolve per-hive if hive_name provided)
    if config:
        # Resolve child_tiers based on hive_name parameter
        if hive_name:
            # Per-hive resolution using fallback chain
            child_tiers = resolve_child_tiers_for_hive(hive_name, config)
        else:
            # Legacy behavior: use scope-level child_tiers
            child_tiers = config.child_tiers

        if child_tiers:
            # Sort tier keys to maintain order (t1, t2, t3...)
            tier_keys = sorted(child_tiers.keys(), key=lambda x: int(x[1:]))
            for tier_id in tier_keys:
                result[tier_id] = []

    # Get all ticket files
    all_ticket_paths = list_tickets()

    # Config is required for hive resolution; list_tickets() already returns []
    # when config is None, but guard explicitly so ticket_hive derivation is always safe.
    if not config:
        return result

    # Load each ticket and group by type
    for ticket_path in all_ticket_paths:
        try:
            ticket_id = ticket_path.stem
            ticket = read_ticket(ticket_id, file_path=ticket_path)

            # Apply hive filter - check if ticket file is in the specified hive
            if hive_name:
                # With new ID format, hive is NOT part of ticket ID
                # Instead, check if ticket_path is within the hive directory
                if hive_name in config.hives:
                    hive_path = Path(config.hives[hive_name].path)
                    # Check if ticket file is in this hive's directory
                    try:
                        ticket_path.relative_to(hive_path)
                    except ValueError:
                        # ticket_path is not under hive_path, skip it
                        continue
                else:
                    # Hive not in config, skip all tickets
                    continue

            # Group ticket by type, skipping if type not in result dict
            if ticket.type in result:
                result[ticket.type].append(ticket)
        except Exception as e:
            # Log warning but continue processing other tickets
            import warnings

            warnings.warn(f"Failed to load ticket {ticket_path}: {e}. Skipping.", stacklevel=2)
            continue

    return result


def _build_ticket_tree(
    tickets: dict[str, list[Ticket]],
) -> tuple[list[_TicketNode], list[_TicketNode]]:
    """Build a hierarchy tree from flat ticket groups.

    Collects all tickets into a flat lookup keyed by ticket ID, walks bee-level
    tickets as roots, and recursively resolves children via each ticket's
    ``children`` list.  Tickets not reachable from any bee root are collected
    into a separate unparented list.

    Args:
        tickets: Dictionary with ticket type keys containing lists of Ticket
                 objects (as returned by ``scan_tickets()``).

    Returns:
        A ``(roots, unparented)`` tuple where *roots* are bee-level
        ``_TicketNode`` trees and *unparented* contains nodes not reachable
        from any root.
    """
    # Flat lookup keyed by ticket ID
    lookup: dict[str, Ticket] = {}
    for ticket_list in tickets.values():
        for ticket in ticket_list:
            lookup[ticket.id] = ticket

    # Build node wrappers
    nodes: dict[str, _TicketNode] = {
        tid: _TicketNode(ticket=t) for tid, t in lookup.items()
    }

    # Resolve tree from bee roots
    visited: set[str] = set()

    def _resolve(node: _TicketNode) -> None:
        visited.add(node.ticket.id)
        for child_id in node.ticket.children:
            if child_id in nodes and child_id not in visited:
                child_node = nodes[child_id]
                node.children.append(child_node)
                _resolve(child_node)

    roots: list[_TicketNode] = []
    for bee in tickets.get("bee", []):
        root = nodes[bee.id]
        roots.append(root)
        _resolve(root)

    roots = sorted(roots, key=lambda n: _natural_sort_key(n.ticket.title))

    # Collect unparented: not reached from any root
    unparented: list[_TicketNode] = [
        nodes[tid] for tid in sorted(nodes) if tid not in visited
    ]

    return roots, unparented


def _compute_ticket_link(ticket: Ticket, hive_name: str | None) -> str:
    """Compute the relative link path for a ticket.

    Uses ``get_ticket_path()`` relative to the hive root when *hive_name* is
    provided and config is available.  Falls back to ``{id}/{id}.md``.
    """
    if hive_name:
        try:
            from .config import load_bees_config
            from .paths import get_ticket_path

            config = load_bees_config()
            if config and hive_name in config.hives:
                ticket_path = get_ticket_path(ticket.id, ticket.type, hive_name)
                hive_path = Path(config.hives[hive_name].path)
                return str(ticket_path.relative_to(hive_path))
        except Exception:
            pass
    return f"{ticket.id}/{ticket.id}.md"


def _get_empty_state_message(
    ticket_type: str, tier_display_names: dict[str, str]
) -> str:
    """Return an italicised empty-state message for a parent's missing children.

    Determines the next child tier based on the ticket's type and returns
    a message like ``*No epics*`` using the tier's plural display name.
    """
    if not tier_display_names:
        return "*No child tickets*"

    sorted_tiers = sorted(tier_display_names.keys(), key=lambda x: int(x[1:]))

    if ticket_type == "bee":
        if sorted_tiers:
            return f"*No {tier_display_names[sorted_tiers[0]].lower()}*"
        return "*No child tickets*"

    # For tier types, find the next tier in sequence
    if ticket_type in sorted_tiers:
        idx = sorted_tiers.index(ticket_type)
        if idx + 1 < len(sorted_tiers):
            return f"*No {tier_display_names[sorted_tiers[idx + 1]].lower()}*"

    return "*No child tickets*"


def _render_node(
    node: _TicketNode,
    hive_name: str | None,
    tier_display_names: dict[str, str],
    mermaid_enabled: bool = True,
) -> list[str]:
    """Render a single ticket node as markdown lines.

    Nodes with children render as ``<details>/<summary>`` blocks with a
    markdown link inside the expanded body.  Leaf nodes render as plain
    markdown links inside a ``<div>``.
    """
    ticket = node.ticket
    link = _compute_ticket_link(ticket, hive_name)
    status = ticket.status or "unknown"
    html_id = ticket.id.replace(".", "-")

    if not node.children:
        return [
            f'<div id="{html_id}" style="margin-left:1em">',
            "",
            f"[{ticket.title}]({link}) [{ticket.id}] `{status}`",
            "",
            "</div>",
        ]

    lines: list[str] = []

    lines.append(
        f'<details><summary id="{html_id}">'
        f"{ticket.title} [{ticket.id}] <code>{status}</code>"
        f"</summary>"
    )
    lines.append("")

    if mermaid_enabled:
        try:
            child_graph = _generate_mermaid_graph(
                [c.ticket for c in node.children]
            )
            if child_graph:
                lines.append(child_graph)
                lines.append("")
        except Exception:
            pass

    lines.append(f"&ensp;&ensp;&ensp;&ensp;[{ticket.title}]({link}) [{ticket.id}]")
    lines.append("")

    lines.append('<div style="padding-left: 1.5em">')
    lines.append("")

    for child in sorted(node.children, key=lambda n: _natural_sort_key(n.ticket.title)):
        lines.extend(
            _render_node(child, hive_name, tier_display_names, mermaid_enabled)
        )

    lines.append("")
    lines.append("</div>")
    lines.append("</details>")

    return lines


_MERMAID_UNSAFE_CHARS = str.maketrans({
    '"': "'", '`': None, '<': None, '>': None,
    '[': None, ']': None, '{': None, '}': None,
    '(': None, ')': None, '|': None, ';': None, '#': None,
})


def _sanitize_mermaid_label(text: str) -> str:
    """Strip or replace characters that break Mermaid node label syntax."""
    return text.translate(_MERMAID_UNSAFE_CHARS)


def _generate_mermaid_graph(tickets: list[Ticket]) -> str:
    """Generate a Mermaid dependency graph for the given tickets.

    Builds a ``graph TD`` diagram showing all tickets as nodes, with
    ``up_dependencies`` edges between them.  Returns an empty string when
    no tickets are provided.

    Args:
        tickets: Flat list of Ticket objects to include in the graph.

    Returns:
        A fenced ``mermaid`` code block string, or ``""`` if fewer than two
        local tickets or no dependency edges exist.
    """
    ticket_map: dict[str, Ticket] = {t.id: t for t in tickets}

    if len(ticket_map) <= 1:
        return ""

    # Collect edges and determine which nodes participate
    edges: list[tuple[str, str]] = []
    orphan_dep_ids: set[str] = set()
    for t in tickets:
        for dep_id in t.up_dependencies:
            edges.append((dep_id, t.id))
            if dep_id not in ticket_map:
                orphan_dep_ids.add(dep_id)

    if not edges:
        return ""

    def _mermaid_node_id(ticket_id: str) -> str:
        return ticket_id.replace(".", "_")

    # Compute uniform node width from the widest label (~8px per char)
    max_label_len = max(
        (len(f"{t.id}: {_sanitize_mermaid_label(t.title)}") for t in ticket_map.values()),
        default=0,
    )
    node_min_width = max(150, max_label_len * 8)

    lines: list[str] = [
        "```mermaid",
        "graph TD",
        f"  classDef larva fill:#e8e8e8,stroke:#999,color:#333,min-width:{node_min_width}px",
        f"  classDef pupa fill:#d4e8ff,stroke:#5599cc,color:#003366,min-width:{node_min_width}px",
        f"  classDef worker fill:#fff3cd,stroke:#cc9900,color:#664400,min-width:{node_min_width}px",
        f"  classDef finished fill:#d4edda,stroke:#28a745,color:#1a5c2a,min-width:{node_min_width}px",
        f"  classDef failed fill:#f8d7da,stroke:#dc3545,color:#721c24,min-width:{node_min_width}px",
        "",
    ]

    # Emit all ticket node declarations
    for tid in sorted(ticket_map):
        t = ticket_map[tid]
        nid = _mermaid_node_id(tid)
        status = t.status or "larva"
        lines.append(f'  {nid}["{t.id}: {_sanitize_mermaid_label(t.title)}"]:::{status}')

    # Emit orphan dep nodes (stadium shape, no class)
    for dep_id in sorted(orphan_dep_ids):
        nid = _mermaid_node_id(dep_id)
        lines.append(f'  {nid}(["{_sanitize_mermaid_label(dep_id)}"])')

    # Emit edges
    for dep_id, tid in edges:
        lines.append(f"  {_mermaid_node_id(dep_id)} --> {_mermaid_node_id(tid)}")


    lines.append("```")
    return "\n".join(lines)


def format_index_markdown(
    tickets: dict[str, list[Ticket]], include_timestamp: bool = True, hive_name: str | None = None
) -> str:
    """
    Generate formatted markdown index from grouped ticket data.

    Output structure: ``# Ticket Index`` header → optional timestamp →
    optional Mermaid dependency graph of bee-level tickets → collapsible
    ``<details>/<summary>`` tree for each bee root → optional unparented
    section.

    The Mermaid graph is emitted only when bee-level dependency edges exist.

    When the total ticket count is zero the output contains only the
    header and optional timestamp — no graph or ``<details>`` blocks.

    Args:
        tickets: Dictionary with ticket type keys (e.g., 'bee', 't1', 't2') containing
                 lists of Ticket objects
        include_timestamp: If True, includes generation timestamp in header
        hive_name: Optional hive name for computing correct relative paths to ticket files

    Returns:
        Formatted markdown string with all tickets organized hierarchically
    """
    lines: list[str] = []

    # Header
    lines.append("# Ticket Index")
    lines.append("")

    if include_timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"*Generated: {timestamp}*")
        lines.append("")

    # Zero tickets → header and timestamp only
    total = sum(len(tl) for tl in tickets.values())
    if total == 0:
        return "\n".join(lines)

    # Check global mermaid_charts setting
    from .config import get_mermaid_charts_enabled

    mermaid_enabled = get_mermaid_charts_enabled()

    # Bee-level dependency graph (omitted when no bee-to-bee edges)
    if mermaid_enabled:
        try:
            bee_graph = _generate_mermaid_graph(tickets.get("bee", []))
            if bee_graph:
                lines.append(bee_graph)
                lines.append("")
        except Exception:
            lines.append("*Dependency graph could not be generated*")
            lines.append("")

    # Build hierarchy tree
    roots, unparented = _build_ticket_tree(tickets)

    # Tier display names for empty-state messages
    tier_display_names = _get_tier_display_names(hive_name)

    # Render bee roots
    for root in roots:
        lines.extend(_render_node(root, hive_name, tier_display_names, mermaid_enabled))
        lines.append("")

    # Render unparented section
    if unparented:
        lines.append("<details><summary>Unparented Tickets</summary>")
        lines.append("")
        for node in unparented:
            lines.extend(_render_node(node, hive_name, tier_display_names, mermaid_enabled))
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def is_index_stale(hive_name: str | None = None) -> bool:
    """
    Check if index.md files are stale (older than ticket files).

    Scans hive directories recursively (hierarchical storage) to check if any
    ticket file is newer than the index. Excludes special directories and only
    checks files matching {ticket_id}/{ticket_id}.md pattern.

    If hive_name is provided, checks only that hive's index.
    If hive_name is None, checks all hive indexes.

    Args:
        hive_name: Optional hive name to check. If None, checks all hives.

    Returns:
        True if any index needs regeneration, False if all indexes are up-to-date

    Examples:
        >>> is_index_stale()
        True
        >>> is_index_stale("backend")
        False
    """
    from .config import load_bees_config

    config = load_bees_config()

    if not config or not config.hives:
        # No hives configured - nothing to check
        return False

    # Determine which hives to check
    if hive_name:
        if hive_name not in config.hives:
            return True  # Hive doesn't exist, treat as stale
        hives_to_check = [(hive_name, config.hives[hive_name])]
    else:
        hives_to_check = list(config.hives.items())

    # Check each hive's index
    for _hive_key, hive_config in hives_to_check:
        hive_path = Path(hive_config.path)

        if not hive_path.exists():
            continue

        index_path = hive_path / "index.md"

        # If index doesn't exist, it's stale
        if not index_path.exists():
            return True

        # Get index modification time
        index_mtime = index_path.stat().st_mtime

        # Check ticket files using selective traversal (only enters ticket-ID directories)
        from .paths import iter_ticket_files

        for ticket_path in iter_ticket_files(hive_path):
            # Check if ticket file is newer than index
            if ticket_path.stat().st_mtime > index_mtime:
                return True

    return False


def generate_index(
    hive_name: str | None = None,
) -> str:
    """
    Generate complete markdown index for all tickets and write to disk.

    High-level orchestration function that scans the tickets directory,
    loads all tickets, formats them into a markdown index, and writes to
    the appropriate location. Can generate per-hive indexes or indexes
    for all hives.

    When hive_name is provided, generates and writes index only for that hive
    to {hive_path}/index.md.

    When hive_name is omitted, iterates all registered hives and generates
    separate index.md files for each hive at their respective hive roots.

    Args:
        hive_name: Optional hive name to generate index for specific hive only.
                   If provided, generates index only for that hive.
                   If omitted, generates indexes for all hives.

    Returns:
        Complete markdown index as a string (for single hive or last hive processed)

    Examples:
        >>> index_md = generate_index()
        >>> print(index_md)
        # Ticket Index

        <details><summary id="b-Amx">...</summary>
        ...
        </details>
        >>> backend_index = generate_index(hive_name='backend')
    """
    from .config import load_bees_config

    config = load_bees_config()

    if hive_name:
        # Generate index for specific hive
        tickets = scan_tickets(hive_name)
        markdown = format_index_markdown(tickets, include_timestamp=True, hive_name=hive_name)

        # Write to hive root directory
        if config and hive_name in config.hives:
            hive_path = Path(config.hives[hive_name].path)
            index_path = hive_path / "index.md"
            index_path.write_text(markdown)
        else:
            # Hive not in config - write to {cwd}/{hive_name}/index.md
            hive_path = Path.cwd() / hive_name
            index_path = hive_path / "index.md"
            # Create directory if needed
            hive_path.mkdir(parents=True, exist_ok=True)
            index_path.write_text(markdown)

        return markdown
    else:
        # Generate indexes for all hives
        if not config or not config.hives:
            # No hives configured - just return markdown without writing
            # (backward compatibility for tests and legacy usage)
            tickets = scan_tickets(None)
            markdown = format_index_markdown(tickets, include_timestamp=True)
            return markdown

        # Iterate all hives and generate separate indexes
        last_markdown = ""
        for hive_name_key in config.hives:
            tickets = scan_tickets(hive_name_key)
            markdown = format_index_markdown(tickets, include_timestamp=True, hive_name=hive_name_key)

            # Write to hive root directory
            hive_path = Path(config.hives[hive_name_key].path)

            # Skip if hive path doesn't exist (e.g., config from different environment)
            if not hive_path.exists():
                continue

            index_path = hive_path / "index.md"
            index_path.write_text(markdown)

            last_markdown = markdown

        # If no hives were actually written (all paths invalid), return markdown for all tickets
        if not last_markdown:
            tickets = scan_tickets(None)
            last_markdown = format_index_markdown(tickets, include_timestamp=True)

        return last_markdown
