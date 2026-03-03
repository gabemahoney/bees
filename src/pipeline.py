"""Pipeline evaluator for query execution system.

This module implements the main pipeline evaluator that loads all tickets into
memory once, then executes stages sequentially against in-memory data.
"""

import logging
from pathlib import Path
from typing import Any

from src.graph_executor import GraphExecutor
from src.search_executor import SearchExecutor

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

    def __init__(self, tickets_dir: str | None = None):
        """Initialize pipeline and load all tickets into memory from configured hives.

        Args:
            tickets_dir: DEPRECATED - kept for backward compatibility, not used

        Raises:
            FileNotFoundError: If hive directories not found
            ValueError: If YAML frontmatter contains invalid syntax
        """
        # DEPRECATED: tickets_dir parameter is kept for backward compatibility
        # but is no longer used. Tickets are now loaded from hives defined in config.

        # In-memory ticket storage: ticket_id -> ticket_data
        self.tickets: dict[str, dict[str, Any]] = {}

        # Initialize executors
        self.search_executor = SearchExecutor()
        self.graph_executor = GraphExecutor()

        # Load all tickets into memory from all hives
        self._load_tickets()

        logger.info(f"Loaded {len(self.tickets)} tickets into memory from all hives")

    def _load_tickets(self) -> None:
        """Load all tickets from markdown files with YAML frontmatter from all configured hives.

        Scans hive directories recursively (hierarchical storage) for **/*.md files and parses
        YAML frontmatter from each. Only processes files with schema_version field.
        Excludes special directories (eggs/, evicted/, .hive/) and index.md files.
        Only includes files matching {ticket_id}/{ticket_id}.md pattern.

        NOTE: This method intentionally bypasses read_ticket() and the mtime cache
        (see engineering best practices Section 8). The bypass is valid here because:
        - The pipeline holds a read-only in-memory dict; it never writes ticket files.
        - Tickets are loaded once at init and never re-read during a pipeline lifetime.
        - No cache interaction occurs: we neither read from nor populate the mtime cache.
        - fast_parse_frontmatter() is ~10x faster than yaml.safe_load on ~39k files.
        Files missing schema_version are skipped (not bees tickets). Parse failures
        (corrupted files) are also silently skipped, matching the schema_version behavior.

        Raises:
            FileNotFoundError: If hive directory not found
        """
        from src.config import load_bees_config
        from src.fast_parser import fast_parse_frontmatter

        # Load hive configuration
        config = load_bees_config()

        if not config or not config.hives:
            # No hives configured - return with empty ticket set
            logger.warning("No hives configured, no tickets will be loaded")
            return

        # Load tickets from each hive
        for hive_name, hive_config in config.hives.items():
            hive_path = Path(hive_config.path)

            if not hive_path.exists():
                logger.warning(f"Hive directory not found: {hive_path} (hive: {hive_name})")
                continue

            logger.debug(f"Loading tickets from hive '{hive_name}' at {hive_path}")

            # Selective traversal: only enters ticket-ID directories
            from src.paths import iter_ticket_files

            for md_file in iter_ticket_files(hive_path):
                # Returns None for non-ticket files (no schema_version) and parse failures
                fm = fast_parse_frontmatter(md_file)
                if fm is None:
                    continue

                ticket_id = fm.get("id")
                if not ticket_id:
                    logger.warning(f"Skipping {md_file}: no ID in frontmatter")
                    continue

                self.tickets[ticket_id] = {
                    "id": ticket_id,
                    "title": fm.get("title"),
                    "issue_type": fm.get("type") or "",  # 'type' field maps to 'issue_type'
                    "status": fm.get("status") or "",
                    "tags": fm.get("tags", []),
                    "parent": fm.get("parent"),
                    "children": fm.get("children", []),
                    "up_dependencies": fm.get("up_dependencies", []),
                    "down_dependencies": fm.get("down_dependencies", []),
                    "hive": hive_name,
                    "guid": fm.get("guid"),
                }

        # Second pass: Build reverse relationships (children from parents, etc)
        self._build_reverse_relationships()

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
            parent_id = ticket_data.get("parent")
            if parent_id and parent_id in self.tickets:
                parent = self.tickets[parent_id]
                if ticket_id not in parent["children"]:
                    parent["children"].append(ticket_id)

            # Build down_dependencies (tickets blocked by this ticket)
            up_deps = ticket_data.get("up_dependencies", [])
            for blocker_id in up_deps:
                if blocker_id in self.tickets:
                    blocker = self.tickets[blocker_id]
                    if ticket_id not in blocker["down_dependencies"]:
                        blocker["down_dependencies"].append(ticket_id)

    def get_stage_type(self, stage: list[str]) -> str:
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

        search_prefixes = {"type=", "id=", "status=", "title~", "tag~", "parent=", "guid=", "hive=", "hive~"}
        graph_terms = {"parent", "children", "up_dependencies", "down_dependencies"}

        has_search = any(any(term.startswith(prefix) for prefix in search_prefixes) for term in stage)
        has_graph = any(term in graph_terms for term in stage)

        if has_search and has_graph:
            raise ValueError(
                f"Stage has mixed search and graph terms: {stage}. Each stage must be purely search or graph."
            )

        if has_search:
            return "search"
        elif has_graph:
            return "graph"
        else:
            raise ValueError(f"Stage has no recognized search or graph terms: {stage}")

    def execute_query(self, stages: list[list[str]]) -> set[str]:
        """Execute multi-stage query pipeline with sequential evaluation.

        Executes stages in order, passing result set from stage N to stage N+1.
        Deduplicates ticket IDs after each stage. Short-circuits if any stage
        returns empty set.

        Args:
            stages: List of stages from QueryParser.parse()

        Returns:
            Set of ticket IDs that passed through all stages

        Raises:
            ValueError: If stage type cannot be determined or is mixed
        """
        # Start with all ticket IDs for first stage
        current_results = set(self.tickets.keys())

        logger.info(f"Starting query execution with {len(stages)} stages")
        logger.info(f"Initial ticket count: {len(current_results)}")

        # Execute each stage sequentially
        for stage_idx, stage in enumerate(stages):
            logger.info(f"Executing stage {stage_idx}: {stage}")

            # Determine stage type and route to appropriate executor
            stage_type = self.get_stage_type(stage)

            if stage_type == "search":
                # Search stage: filter current results
                # Build filtered ticket dict with only current_results tickets
                filtered_tickets = {tid: self.tickets[tid] for tid in current_results if tid in self.tickets}
                current_results = self.search_executor.execute(filtered_tickets, stage)
            else:  # graph
                # Graph stage: traverse relationships from current results
                # Each graph term in stage ANDed together
                for term in stage:
                    current_results = self.graph_executor.traverse(self.tickets, current_results, term)
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

    def execute_batch(self, queries: list[list[list[str]]]) -> list[set[str]]:
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

        logger.info("Batch execution complete")
        return results
