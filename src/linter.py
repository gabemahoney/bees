"""Linter module for ticket validation.

This module provides the main linter infrastructure for validating tickets,
including scanning tickets from the filesystem and running validation checks.
"""

from pathlib import Path
from typing import Generator, Dict, Any, List, Set
import logging

from src.reader import read_ticket
from src.models import Ticket
from src.linter_report import LinterReport, ValidationError
from src.id_utils import is_valid_ticket_id
from src.corruption_state import mark_corrupt, mark_clean

logger = logging.getLogger(__name__)


class TicketScanner:
    """Scanner to load and iterate over all tickets from the filesystem.

    Uses the ticket reader module to load tickets from markdown files
    in the tickets directory structure (epics/, tasks/, subtasks/).
    """

    def __init__(self, tickets_dir: str = "tickets"):
        """Initialize ticket scanner.

        Args:
            tickets_dir: Path to tickets directory (default: 'tickets')
        """
        self.tickets_dir = Path(tickets_dir)

    def scan_all(self) -> Generator[Ticket, None, None]:
        """Scan and yield all tickets from the filesystem.

        Yields:
            Ticket objects (Epic, Task, or Subtask) from all subdirectories

        Raises:
            FileNotFoundError: If tickets directory doesn't exist
        """
        if not self.tickets_dir.exists():
            raise FileNotFoundError(
                f"Tickets directory not found: {self.tickets_dir}"
            )

        # Scan subdirectories for ticket files
        subdirs = ['epics', 'tasks', 'subtasks']

        for subdir in subdirs:
            subdir_path = self.tickets_dir / subdir
            if not subdir_path.exists():
                logger.warning(f"Subdirectory not found: {subdir_path}")
                continue

            # Load all markdown files in subdirectory
            for md_file in sorted(subdir_path.glob('*.md')):
                try:
                    ticket = read_ticket(md_file)
                    yield ticket
                except Exception as e:
                    logger.error(f"Error loading ticket {md_file}: {e}")
                    continue


class Linter:
    """Main linter class for orchestrating ticket validation.

    Coordinates ticket scanning, validation checks, and error reporting.
    Validation rules are implemented as methods that can be extended by
    other tasks.
    """

    def __init__(self, tickets_dir: str = "tickets"):
        """Initialize linter.

        Args:
            tickets_dir: Path to tickets directory (default: 'tickets')
        """
        self.tickets_dir = tickets_dir
        self.scanner = TicketScanner(tickets_dir)

    def run(self) -> LinterReport:
        """Run linter validation on all tickets.

        Scans all tickets, runs validation checks, and collects errors
        into a structured report. Automatically updates corruption state
        based on validation results.

        Returns:
            LinterReport containing all validation errors found
        """
        report = LinterReport()

        logger.info("Starting linter scan")

        # Load all tickets into a list for multiple passes
        tickets = list(self.scanner.scan_all())
        ticket_count = len(tickets)

        # Run per-ticket validation checks
        for ticket in tickets:
            self.validate_ticket(ticket, report)

        # Run cross-ticket validation checks
        self.validate_id_uniqueness(tickets, report)
        self.validate_parent_children_bidirectional(tickets, report)
        self.validate_dependencies_bidirectional(tickets, report)

        # Run cycle detection
        cycle_errors = self.detect_cycles(tickets)
        for error in cycle_errors:
            report.errors.append(error)

        logger.info(f"Linter scan complete. Scanned {ticket_count} tickets, "
                   f"found {len(report.errors)} validation errors")

        # Update corruption state based on validation results
        if report.errors:
            mark_corrupt(report)
            logger.warning("Database marked as corrupt")
        else:
            mark_clean()
            logger.info("Database marked as clean")

        return report

    def validate_ticket(self, ticket: Ticket, report: LinterReport) -> None:
        """Run validation checks on a single ticket.

        This is a stub method that will be extended by other tasks to
        add specific validation rules (ID format, uniqueness, bidirectional
        relationships, cycles, etc.).

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        # ID format validation
        self.validate_id_format(ticket, report)

        # Placeholder for additional validation checks to be implemented by other tasks
        pass

    def validate_id_format(self, ticket: Ticket, report: LinterReport) -> None:
        """Validate that ticket ID matches the required format.

        Checks if ticket ID matches the bees-[a-z0-9]{3} pattern.

        Args:
            ticket: Ticket to validate
            report: LinterReport to collect errors into
        """
        if not is_valid_ticket_id(ticket.id):
            report.add_error(
                ticket_id=ticket.id,
                error_type="id_format",
                message=f"Ticket ID '{ticket.id}' does not match required format: bees-[a-z0-9]{{3}}",
                severity="error"
            )

    def validate_id_uniqueness(self, tickets: List[Ticket], report: LinterReport) -> None:
        """Validate that all ticket IDs are unique.

        Scans all tickets and detects duplicate IDs across all ticket types.

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect errors into
        """
        seen_ids = {}

        for ticket in tickets:
            ticket_id = ticket.id
            if ticket_id in seen_ids:
                # Duplicate found
                report.add_error(
                    ticket_id=ticket_id,
                    error_type="duplicate_id",
                    message=f"Duplicate ticket ID '{ticket_id}' found (also in {seen_ids[ticket_id]})",
                    severity="error"
                )
            else:
                seen_ids[ticket_id] = ticket.type

    def validate_parent_children_bidirectional(
        self, tickets: List[Ticket], report: LinterReport
    ) -> None:
        """Validate bidirectional consistency of parent/children relationships.

        For each ticket with a parent field, verifies the parent ticket lists
        this ticket in its children field. For each ticket with children,
        verifies each child lists this ticket as its parent.

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect errors into
        """
        # Create a lookup map for quick ticket access by ID
        ticket_map = {ticket.id: ticket for ticket in tickets}

        for ticket in tickets:
            # Check if ticket has a parent
            if ticket.parent:
                parent_id = ticket.parent
                parent_ticket = ticket_map.get(parent_id)

                if not parent_ticket:
                    # Parent ticket doesn't exist (handled by other validators)
                    continue

                # Verify parent lists this ticket in its children
                if ticket.id not in parent_ticket.children:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="orphaned_child",
                        message=f"Ticket '{ticket.id}' lists '{parent_id}' as parent, "
                                f"but '{parent_id}' does not list '{ticket.id}' in its children",
                        severity="error"
                    )

            # Check all children have this ticket as their parent
            for child_id in ticket.children:
                child_ticket = ticket_map.get(child_id)

                if not child_ticket:
                    # Child ticket doesn't exist (handled by other validators)
                    continue

                # Verify child lists this ticket as parent
                if child_ticket.parent != ticket.id:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="orphaned_parent",
                        message=f"Ticket '{ticket.id}' lists '{child_id}' as child, "
                                f"but '{child_id}' does not list '{ticket.id}' as its parent",
                        severity="error"
                    )

    def validate_dependencies_bidirectional(
        self, tickets: List[Ticket], report: LinterReport
    ) -> None:
        """Validate bidirectional consistency of dependency relationships.

        For each ticket with up_dependencies, verifies each upstream ticket
        lists this ticket in its down_dependencies. For each ticket with
        down_dependencies, verifies each downstream ticket lists this ticket
        in its up_dependencies.

        Args:
            tickets: List of all tickets to check
            report: LinterReport to collect errors into
        """
        # Create a lookup map for quick ticket access by ID
        ticket_map = {ticket.id: ticket for ticket in tickets}

        for ticket in tickets:
            # Check up_dependencies (this ticket depends on upstream tickets)
            for upstream_id in ticket.up_dependencies:
                upstream_ticket = ticket_map.get(upstream_id)

                if not upstream_ticket:
                    # Upstream ticket doesn't exist (handled by other validators)
                    continue

                # Verify upstream ticket lists this ticket in down_dependencies
                if ticket.id not in upstream_ticket.down_dependencies:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="orphaned_dependency",
                        message=f"Ticket '{ticket.id}' lists '{upstream_id}' in up_dependencies, "
                                f"but '{upstream_id}' does not list '{ticket.id}' in its down_dependencies",
                        severity="error"
                    )

            # Check down_dependencies (downstream tickets depend on this ticket)
            for downstream_id in ticket.down_dependencies:
                downstream_ticket = ticket_map.get(downstream_id)

                if not downstream_ticket:
                    # Downstream ticket doesn't exist (handled by other validators)
                    continue

                # Verify downstream ticket lists this ticket in up_dependencies
                if ticket.id not in downstream_ticket.up_dependencies:
                    report.add_error(
                        ticket_id=ticket.id,
                        error_type="missing_backlink",
                        message=f"Ticket '{ticket.id}' lists '{downstream_id}' in down_dependencies, "
                                f"but '{downstream_id}' does not list '{ticket.id}' in its up_dependencies",
                        severity="error"
                    )

    def detect_cycles(self, tickets: List[Ticket]) -> List[ValidationError]:
        """Detect cycles in both blocking and hierarchical dependency relationships.

        Uses depth-first search (DFS) with path tracking to detect cycles in:
        1. Blocking dependencies (up_dependencies/down_dependencies)
        2. Hierarchical relationships (parent/children)

        Args:
            tickets: List of all tickets to check for cycles

        Returns:
            List of ValidationError objects for each cycle found, with cycle paths
        """
        errors = []
        ticket_map = {ticket.id: ticket for ticket in tickets}

        # Track visited nodes globally to avoid redundant cycle detection
        visited_blocking = set()
        visited_hierarchical = set()

        # Detect cycles in blocking dependencies
        for ticket in tickets:
            if ticket.id not in visited_blocking:
                cycle_path = self._detect_cycle_dfs(
                    ticket_id=ticket.id,
                    ticket_map=ticket_map,
                    visited=visited_blocking,
                    path=[],
                    path_set=set(),
                    get_neighbors=lambda t: t.up_dependencies,
                    relationship_type="blocking dependency"
                )
                if cycle_path:
                    cycle_str = " -> ".join(cycle_path)
                    errors.append(ValidationError(
                        ticket_id=cycle_path[0],
                        error_type="dependency_cycle",
                        message=f"Cycle detected in blocking dependencies: {cycle_str}",
                        severity="error"
                    ))

        # Detect cycles in hierarchical relationships (parent/children)
        for ticket in tickets:
            if ticket.id not in visited_hierarchical:
                cycle_path = self._detect_cycle_dfs(
                    ticket_id=ticket.id,
                    ticket_map=ticket_map,
                    visited=visited_hierarchical,
                    path=[],
                    path_set=set(),
                    get_neighbors=lambda t: [t.parent] if t.parent else [],
                    relationship_type="parent/child"
                )
                if cycle_path:
                    cycle_str = " -> ".join(cycle_path)
                    errors.append(ValidationError(
                        ticket_id=cycle_path[0],
                        error_type="hierarchy_cycle",
                        message=f"Cycle detected in parent/child hierarchy: {cycle_str}",
                        severity="error"
                    ))

        return errors

    def _detect_cycle_dfs(
        self,
        ticket_id: str,
        ticket_map: Dict[str, Ticket],
        visited: Set[str],
        path: List[str],
        path_set: Set[str],
        get_neighbors,
        relationship_type: str
    ) -> List[str] | None:
        """DFS helper to detect cycles in a specific relationship type.

        Args:
            ticket_id: Current ticket ID being explored
            ticket_map: Map of ticket IDs to Ticket objects
            visited: Set of globally visited nodes (to avoid redundant work)
            path: Current path from root to current node
            path_set: Set representation of path for O(1) cycle detection
            get_neighbors: Function to extract neighbor IDs from a ticket
            relationship_type: Type of relationship being checked (for error messages)

        Returns:
            List of ticket IDs representing the cycle path if cycle found, None otherwise
        """
        # Check if we've found a cycle
        if ticket_id in path_set:
            # Extract the cycle portion of the path
            cycle_start_idx = path.index(ticket_id)
            cycle = path[cycle_start_idx:] + [ticket_id]
            return cycle

        # Check if ticket exists
        ticket = ticket_map.get(ticket_id)
        if not ticket:
            # Missing ticket (handled by other validators)
            return None

        # Mark as visited globally
        visited.add(ticket_id)

        # Add to current path
        path.append(ticket_id)
        path_set.add(ticket_id)

        # Explore neighbors
        neighbors = get_neighbors(ticket)
        for neighbor_id in neighbors:
            if neighbor_id not in visited or neighbor_id in path_set:
                # Visit unvisited nodes or nodes in current path (potential cycle)
                cycle = self._detect_cycle_dfs(
                    ticket_id=neighbor_id,
                    ticket_map=ticket_map,
                    visited=visited,
                    path=path[:],
                    path_set=path_set.copy(),
                    get_neighbors=get_neighbors,
                    relationship_type=relationship_type
                )
                if cycle:
                    return cycle

        # Remove from current path when backtracking
        path_set.discard(ticket_id)

        return None
