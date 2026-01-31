"""Search stage executor for query pipeline system.

This module implements search-based filtering of tickets using exact match
and regex patterns. All search terms in a stage are combined with AND logic.
"""

import re
from typing import Dict, List, Set, Any


class SearchExecutor:
    """Executes search stage filtering on in-memory ticket data.

    Supports filtering by:
    - type= (exact match on issue_type)
    - id= (exact match on ticket ID)
    - title~ (regex match on title)
    - label~ (regex match on any label)

    All filters in a stage are ANDed together - tickets must match ALL terms.
    """

    def filter_by_type(self, tickets: Dict[str, Dict[str, Any]], type_value: str) -> Set[str]:
        """Filter tickets by exact match on issue_type field.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            type_value: Type to match (e.g., 'epic', 'task', 'subtask')

        Returns:
            Set of ticket IDs where issue_type matches type_value
        """
        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            if ticket_data.get('issue_type') == type_value:
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_id(self, tickets: Dict[str, Dict[str, Any]], id_value: str) -> Set[str]:
        """Filter tickets by exact match on ticket ID.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            id_value: Ticket ID to match

        Returns:
            Set containing single ticket ID if exact match found, empty set otherwise
        """
        if id_value in tickets:
            return {id_value}
        return set()

    def filter_by_title_regex(self, tickets: Dict[str, Dict[str, Any]], regex_pattern: str) -> Set[str]:
        """Filter tickets by regex match on title field.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            regex_pattern: Regex pattern to match against title

        Returns:
            Set of ticket IDs where title matches regex pattern

        Raises:
            re.error: If regex pattern is invalid
        """
        try:
            pattern = re.compile(regex_pattern, re.IGNORECASE)
        except re.error as e:
            raise re.error(f"Invalid regex pattern '{regex_pattern}': {e}")

        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            title = ticket_data.get('title', '')
            if pattern.search(title):
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_label_regex(self, tickets: Dict[str, Dict[str, Any]], regex_pattern: str) -> Set[str]:
        """Filter tickets by regex match on any label.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            regex_pattern: Regex pattern to match against labels

        Returns:
            Set of ticket IDs where ANY label matches regex pattern

        Raises:
            re.error: If regex pattern is invalid
        """
        try:
            pattern = re.compile(regex_pattern, re.IGNORECASE)
        except re.error as e:
            raise re.error(f"Invalid regex pattern '{regex_pattern}': {e}")

        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            labels = ticket_data.get('labels', [])
            if not labels:
                continue

            # Check if ANY label matches the pattern
            for label in labels:
                if pattern.search(label):
                    matching_ids.add(ticket_id)
                    break  # Found a match, no need to check other labels

        return matching_ids

    def execute(self, tickets: Dict[str, Dict[str, Any]], search_terms: List[str]) -> Set[str]:
        """Execute search stage with AND logic across all search terms.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            search_terms: List of search term strings (e.g., ['type=epic', 'label~beta'])

        Returns:
            Set of ticket IDs that match ALL search terms

        Raises:
            ValueError: If search term format is invalid
            re.error: If regex pattern is invalid
        """
        # Start with all ticket IDs
        result_ids = set(tickets.keys())

        # Apply each filter sequentially (AND logic via intersection)
        for term in search_terms:
            if '=' in term:
                # Exact match terms: type=, id=
                term_name, term_value = term.split('=', 1)

                if term_name == 'type':
                    matching_ids = self.filter_by_type(tickets, term_value)
                elif term_name == 'id':
                    matching_ids = self.filter_by_id(tickets, term_value)
                else:
                    raise ValueError(f"Unknown exact match term: {term_name}")

            elif '~' in term:
                # Regex match terms: title~, label~
                term_name, regex_pattern = term.split('~', 1)

                if term_name == 'title':
                    matching_ids = self.filter_by_title_regex(tickets, regex_pattern)
                elif term_name == 'label':
                    matching_ids = self.filter_by_label_regex(tickets, regex_pattern)
                else:
                    raise ValueError(f"Unknown regex term: {term_name}")
            else:
                raise ValueError(f"Invalid search term format: {term}")

            # Intersect with current results (AND logic)
            result_ids &= matching_ids

            # Short-circuit if no matches remain
            if not result_ids:
                break

        return result_ids
