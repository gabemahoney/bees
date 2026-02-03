"""Pipeline evaluator for query execution system.

This module implements the main pipeline evaluator that loads all tickets into
memory once, then executes stages sequentially against in-memory data.
"""

import json
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Set, Any

from src.search_executor import SearchExecutor
from src.graph_executor import GraphExecutor

logger = logging.getLogger(__name__)


class PipelineEvaluator:
    """Main pipeline evaluator for multi-stage query execution.

    Loads all tickets into memory once from tickets/ directory (markdown files with
    YAML frontmatter), then executes query stages sequentially with result passing
    between stages.

    Features:
    - Single disk load per pipeline instance
    - Sequential stage execution with result passing
    - Deduplication after each stage
    - Short-circuit on empty results
    - Stage type detection and routing to appropriate executor
    - Batch query execution support
    """

    def __init__(self, tickets_dir: str = "tickets"):
        """Initialize pipeline and load all tickets into memory.

        Args:
            tickets_dir: Path to tickets directory containing markdown files with YAML frontmatter

        Raises:
            FileNotFoundError: If tickets directory not found
            ValueError: If YAML frontmatter contains invalid syntax
        """
        self.tickets_dir = Path(tickets_dir)

        # In-memory ticket storage: ticket_id -> ticket_data
        self.tickets: Dict[str, Dict[str, Any]] = {}

        # Initialize executors
        self.search_executor = SearchExecutor()
        self.graph_executor = GraphExecutor()

        # Load all tickets into memory
        self._load_tickets()

        logger.info(f"Loaded {len(self.tickets)} tickets into memory")

    def _load_tickets(self) -> None:
        """Load all tickets from markdown files with YAML frontmatter into memory.

        Scans hive root directory (flat storage) for *.md files and parses YAML
        frontmatter from each. Only processes files with bees_version field.
        Skips subdirectories (/eggs, /evicted). Stores tickets as dict[ticket_id -> ticket_data].

        Raises:
            FileNotFoundError: If hive directory not found
            ValueError: If YAML frontmatter contains invalid syntax
        """
        if not self.tickets_dir.exists():
            raise FileNotFoundError(
                f"Tickets directory not found: {self.tickets_dir}. "
                f"Ensure tickets directory exists at hive root."
            )

        # Scan only hive root for markdown files (flat storage)
        for md_file in self.tickets_dir.glob('*.md'):
            # Skip files in subdirectories (e.g., /eggs, /evicted)
            if md_file.parent != self.tickets_dir:
                continue

            try:
                with open(md_file, 'r') as f:
                    content = f.read()

                # Parse YAML frontmatter
                if not content.startswith('---'):
                    logger.warning(f"Skipping {md_file}: no YAML frontmatter")
                    continue

                # Extract frontmatter between --- delimiters
                parts = content.split('---', 2)
                if len(parts) < 3:
                    logger.warning(f"Skipping {md_file}: malformed YAML frontmatter")
                    continue

                frontmatter_str = parts[1]
                ticket = yaml.safe_load(frontmatter_str)

                if not isinstance(ticket, dict):
                    logger.warning(f"Skipping {md_file}: frontmatter is not a dict")
                    continue

                # Filter by bees_version field - skip files without it
                if 'bees_version' not in ticket:
                    logger.debug(f"Skipping {md_file}: no bees_version field")
                    continue

                # Extract ticket ID and store ticket data
                ticket_id = ticket.get('id')
                if not ticket_id:
                    logger.warning(f"Skipping {md_file}: no ID in frontmatter")
                    continue

                # Normalize ticket data structure for executors
                normalized = self._normalize_ticket(ticket)
                self.tickets[ticket_id] = normalized

            except yaml.YAMLError as e:
                raise ValueError(
                    f"Invalid YAML in {md_file}: {e}"
                )
            except Exception as e:
                logger.warning(f"Error loading {md_file}: {e}")
                continue

        # Second pass: Build reverse relationships (children from parents, etc)
        self._build_reverse_relationships()

    def _normalize_ticket(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize ticket data structure for executor consumption.

        Converts YAML frontmatter format to executor-friendly format:
        - Extracts relationship fields (parent, children, up_dependencies, down_dependencies)
        - Maps 'type' field to 'issue_type'
        - Handles 'labels' field

        Args:
            ticket: Raw ticket dict from YAML frontmatter

        Returns:
            Normalized ticket dict with fields expected by executors
        """
        # Convert 'type' field to 'issue_type' for backward compatibility
        issue_type = ticket.get('type', ticket.get('issue_type', ''))

        normalized = {
            'id': ticket.get('id'),
            'title': ticket.get('title', ''),
            'issue_type': issue_type,
            'status': ticket.get('status', ''),
            'labels': ticket.get('labels', []),
            'parent': ticket.get('parent'),
            'children': ticket.get('children', []),
            'up_dependencies': ticket.get('up_dependencies', []),
            'down_dependencies': ticket.get('down_dependencies', []),
        }

        return normalized

    def _build_reverse_relationships(self) -> None:
        """Build reverse relationships after all tickets are loaded.

        This creates bidirectional relationships:
        - If ticket A has parent B, add A to B's children list
        - If ticket A is blocked_by B, add A to B's down_dependencies list

        This second pass is needed because markdown files store relationships from
        one direction only (child -> parent, blocked -> blocker).
        """
        for ticket_id, ticket_data in self.tickets.items():
            # Build children list on parent tickets
            parent_id = ticket_data.get('parent')
            if parent_id and parent_id in self.tickets:
                parent = self.tickets[parent_id]
                if ticket_id not in parent['children']:
                    parent['children'].append(ticket_id)

            # Build down_dependencies (tickets blocked by this ticket)
            up_deps = ticket_data.get('up_dependencies', [])
            for blocker_id in up_deps:
                if blocker_id in self.tickets:
                    blocker = self.tickets[blocker_id]
                    if ticket_id not in blocker['down_dependencies']:
                        blocker['down_dependencies'].append(ticket_id)

    def get_stage_type(self, stage: List[str]) -> str:
        """Determine if stage contains search or graph terms.

        Args:
            stage: List of term strings from query

        Returns:
            'search' if stage has search terms, 'graph' if graph terms

        Raises:
            ValueError: If stage is empty or has mixed term types
        """
        if not stage:
            raise ValueError("Cannot determine type of empty stage")

        search_prefixes = {'type=', 'id=', 'title~', 'label~', 'parent='}
        graph_terms = {'parent', 'children', 'up_dependencies', 'down_dependencies'}

        has_search = any(
            any(term.startswith(prefix) for prefix in search_prefixes)
            for term in stage
        )
        has_graph = any(term in graph_terms for term in stage)

        if has_search and has_graph:
            raise ValueError(
                f"Stage has mixed search and graph terms: {stage}. "
                f"Each stage must be purely search or graph."
            )

        if has_search:
            return 'search'
        elif has_graph:
            return 'graph'
        else:
            raise ValueError(f"Stage has no recognized search or graph terms: {stage}")

    def execute_query(self, stages: List[List[str]], hive_names: list[str] | None = None) -> Set[str]:
        """Execute multi-stage query pipeline with sequential evaluation.

        Executes stages in order, passing result set from stage N to stage N+1.
        Deduplicates ticket IDs after each stage. Short-circuits if any stage
        returns empty set.

        Args:
            stages: List of stages from QueryParser.parse()
            hive_names: Optional list of hive names to filter results by (default: None = all hives)

        Returns:
            Set of ticket IDs that passed through all stages

        Raises:
            ValueError: If stage type cannot be determined or is mixed
        """
        # Start with all ticket IDs for first stage
        current_results = set(self.tickets.keys())

        # Apply hive filter if specified
        if hive_names is not None:
            # Filter tickets to only those from specified hives
            # Empty list means "no hives" = empty result set
            filtered_results = set()
            for ticket_id in current_results:
                # Extract hive prefix from ticket ID (format: hive_name.bees-abc1)
                if '.' in ticket_id:
                    hive_prefix = ticket_id.split('.', 1)[0]
                    if hive_prefix in hive_names:
                        filtered_results.add(ticket_id)
                # Skip tickets without hive prefix (legacy format)
            current_results = filtered_results
            logger.info(f"Applied hive filter: {hive_names}, filtered to {len(current_results)} tickets")

        logger.info(f"Starting query execution with {len(stages)} stages")
        logger.info(f"Initial ticket count: {len(current_results)}")

        # Execute each stage sequentially
        for stage_idx, stage in enumerate(stages):
            logger.info(f"Executing stage {stage_idx}: {stage}")

            # Determine stage type and route to appropriate executor
            stage_type = self.get_stage_type(stage)

            if stage_type == 'search':
                # Search stage: filter current results
                # Build filtered ticket dict with only current_results tickets
                filtered_tickets = {tid: self.tickets[tid] for tid in current_results if tid in self.tickets}
                current_results = self.search_executor.execute(
                    filtered_tickets,
                    stage
                )
            else:  # graph
                # Graph stage: traverse relationships from current results
                # Each graph term in stage ANDed together
                for term in stage:
                    current_results = self.graph_executor.traverse(
                        self.tickets,
                        current_results,
                        term
                    )
                    # Short-circuit within stage if empty
                    if not current_results:
                        break

            # Deduplicate (set operations already deduplicate, but explicit for clarity)
            current_results = set(current_results)

            logger.info(f"Stage {stage_idx} result count: {len(current_results)}")

            # Short-circuit if stage returned no results
            if not current_results:
                logger.info("Query short-circuited due to empty result set")
                break

        logger.info(f"Query execution complete. Final result count: {len(current_results)}")
        return current_results

    def execute_batch(self, queries: List[List[List[str]]]) -> List[Set[str]]:
        """Execute multiple queries in batch using same in-memory ticket data.

        Reuses cached ticket data for efficient multi-query execution without
        re-loading from disk.

        Args:
            queries: List of queries, where each query is a list of stages

        Returns:
            List of result sets, one per query
        """
        logger.info(f"Starting batch execution of {len(queries)} queries")

        results = []
        for query_idx, query_stages in enumerate(queries):
            logger.info(f"Executing batch query {query_idx}")
            result = self.execute_query(query_stages)
            results.append(result)

        logger.info(f"Batch execution complete")
        return results
