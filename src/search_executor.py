"""Search stage executor for query pipeline system.

This module implements search-based filtering of tickets using exact match
and regex patterns. All search terms in a stage are combined with AND logic.
"""

import re
from typing import Any


class SearchExecutor:
    """Executes search stage filtering on in-memory ticket data.

    Supports filtering by:
    - type= (exact match on issue_type)
    - id= (exact match on ticket ID)
    - status= (exact match on status field)
    - title~ (regex match on title)
    - tag~ (regex match on any tag)
    - parent= (exact match on parent field)
    - guid= (exact match on guid field)
    - hive= (exact match on hive field)
    - hive~ (regex match on hive field)

    All filters in a stage are ANDed together - tickets must match ALL terms.
    """

    def filter_by_type(self, tickets: dict[str, dict[str, Any]], type_value: str) -> set[str]:
        """Filter tickets by exact match on issue_type field.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            type_value: Type to match (e.g., 'bee', 't1', 't2')

        Returns:
            Set of ticket IDs where issue_type matches type_value
        """
        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            if ticket_data.get("issue_type") == type_value:
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_status(self, tickets: dict[str, dict[str, Any]], status_value: str) -> set[str]:
        """Filter tickets by exact match on status field.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            status_value: Status to match (e.g., 'open', 'in_progress', 'completed')

        Returns:
            Set of ticket IDs where status matches status_value
        """
        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            if ticket_data.get("status") == status_value:
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_id(self, tickets: dict[str, dict[str, Any]], id_value: str) -> set[str]:
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

    def filter_by_parent(self, tickets: dict[str, dict[str, Any]], parent_value: str) -> set[str]:
        """Filter tickets by exact match on parent field.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            parent_value: Parent ticket ID to match

        Returns:
            Set of ticket IDs where parent matches parent_value
        """
        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            if ticket_data.get("parent") == parent_value:
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_guid(self, tickets: dict[str, dict[str, Any]], guid_value: str) -> set[str]:
        """Filter tickets by exact match on guid field.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            guid_value: GUID string to match

        Returns:
            Set of ticket IDs where guid matches guid_value
        """
        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            if ticket_data.get("guid") == guid_value:
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_hive(self, tickets: dict[str, dict[str, Any]], hive_value: str) -> set[str]:
        """Filter tickets by exact match on hive field.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            hive_value: Hive name to match

        Returns:
            Set of ticket IDs where hive matches hive_value
        """
        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            if ticket_data.get("hive") == hive_value:
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_hive_regex(self, tickets: dict[str, dict[str, Any]], regex_pattern: str) -> set[str]:
        """Filter tickets by regex match on hive field.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            regex_pattern: Regex pattern to match against hive name

        Returns:
            Set of ticket IDs where hive matches regex pattern

        Raises:
            re.error: If regex pattern is invalid
        """
        try:
            pattern = re.compile(regex_pattern, re.IGNORECASE)
        except re.error as e:
            raise re.error(f"Invalid regex pattern '{regex_pattern}': {e}") from e

        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            hive = ticket_data.get("hive", "")
            if pattern.search(hive):
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_title_regex(self, tickets: dict[str, dict[str, Any]], regex_pattern: str) -> set[str]:
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
            raise re.error(f"Invalid regex pattern '{regex_pattern}': {e}") from e

        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            title = ticket_data.get("title", "")
            if pattern.search(title):
                matching_ids.add(ticket_id)
        return matching_ids

    def filter_by_tag_regex(self, tickets: dict[str, dict[str, Any]], regex_pattern: str) -> set[str]:
        """Filter tickets by regex match on any tag.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            regex_pattern: Regex pattern to match against tags

        Returns:
            Set of ticket IDs where ANY tag matches regex pattern

        Raises:
            re.error: If regex pattern is invalid
        """
        try:
            pattern = re.compile(regex_pattern, re.IGNORECASE)
        except re.error as e:
            raise re.error(f"Invalid regex pattern '{regex_pattern}': {e}") from e

        matching_ids = set()
        for ticket_id, ticket_data in tickets.items():
            tags = ticket_data.get("tags", [])
            if not tags:
                continue

            # Check if ANY tag matches the pattern
            for tag in tags:
                if pattern.search(tag):
                    matching_ids.add(ticket_id)
                    break  # Found a match, no need to check other tags

        return matching_ids

    def execute(self, tickets: dict[str, dict[str, Any]], search_terms: list[str]) -> set[str]:
        """Execute search stage with AND logic across all search terms.

        Args:
            tickets: Dict mapping ticket_id -> ticket data
            search_terms: List of search term strings (e.g., ['type=bee', 'tag~beta'])

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
            if "=" in term:
                # Exact match terms: type=, id=, parent=
                term_name, term_value = term.split("=", 1)

                if term_name == "type":
                    matching_ids = self.filter_by_type(tickets, term_value)
                elif term_name == "id":
                    matching_ids = self.filter_by_id(tickets, term_value)
                elif term_name == "status":
                    matching_ids = self.filter_by_status(tickets, term_value)
                elif term_name == "parent":
                    matching_ids = self.filter_by_parent(tickets, term_value)
                elif term_name == "guid":
                    matching_ids = self.filter_by_guid(tickets, term_value)
                elif term_name == "hive":
                    matching_ids = self.filter_by_hive(tickets, term_value)
                else:
                    raise ValueError(f"Unknown exact match term: {term_name}")

            elif "~" in term:
                # Regex match terms: title~, tag~
                term_name, regex_pattern = term.split("~", 1)

                if term_name == "title":
                    matching_ids = self.filter_by_title_regex(tickets, regex_pattern)
                elif term_name == "tag":
                    matching_ids = self.filter_by_tag_regex(tickets, regex_pattern)
                elif term_name == "hive":
                    matching_ids = self.filter_by_hive_regex(tickets, regex_pattern)
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
