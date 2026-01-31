"""Graph stage executor for query pipeline system.

This module implements graph-based traversal of ticket relationships using
in-memory data structures. Supports parent, children, and dependency traversal.
"""

import logging
from typing import Dict, Set, Any

logger = logging.getLogger(__name__)


class GraphExecutor:
    """Executes graph stage traversal on in-memory ticket data.

    Supports traversing relationships:
    - parent: Get parent ticket of each input ticket
    - children: Get all children of each input ticket
    - up_dependencies: Get tickets that each input ticket depends on (blockers)
    - down_dependencies: Get tickets that depend on each input ticket (blocked)

    All operations work on in-memory data with no disk I/O.
    """

    def traverse(
        self,
        tickets: Dict[str, Dict[str, Any]],
        input_ticket_ids: Set[str],
        graph_term: str
    ) -> Set[str]:
        """Traverse ticket relationships based on graph term.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            input_ticket_ids: Set of ticket IDs to start traversal from
            graph_term: Relationship type to traverse (parent|children|up_dependencies|down_dependencies)

        Returns:
            Set of related ticket IDs found through traversal

        Raises:
            ValueError: If graph_term is not one of the supported relationship types
        """
        # Validate graph term
        valid_terms = {'parent', 'children', 'up_dependencies', 'down_dependencies'}
        if graph_term not in valid_terms:
            logger.warning(f"Invalid graph term '{graph_term}', returning empty set")
            return set()

        related_ids = set()

        # Traverse relationships for each input ticket
        for ticket_id in input_ticket_ids:
            # Skip None or empty ticket IDs
            if not ticket_id:
                logger.warning("Encountered None or empty ticket ID in input set, skipping")
                continue

            # Skip if ticket doesn't exist in data
            if ticket_id not in tickets:
                logger.warning(f"Ticket {ticket_id} not found in ticket data, skipping")
                continue

            ticket_data = tickets[ticket_id]

            if graph_term == 'parent':
                # Get parent ticket (single value)
                parent_id = ticket_data.get('parent')
                if parent_id:
                    related_ids.add(parent_id)

            elif graph_term == 'children':
                # Get all children tickets (list)
                children = ticket_data.get('children', [])
                if children:
                    related_ids.update(children)

            elif graph_term == 'up_dependencies':
                # Get tickets this ticket depends on (blockers)
                up_deps = ticket_data.get('up_dependencies', [])
                if up_deps:
                    related_ids.update(up_deps)

            elif graph_term == 'down_dependencies':
                # Get tickets that depend on this ticket
                down_deps = ticket_data.get('down_dependencies', [])
                if down_deps:
                    related_ids.update(down_deps)

        return related_ids
