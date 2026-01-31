"""Query storage module for managing named queries.

This module provides persistence for named queries that can be registered
and executed by LLM via MCP tools.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from .query_parser import QueryParser, QueryValidationError

logger = logging.getLogger(__name__)

__all__ = ["QueryStorage", "save_query", "load_query", "list_queries", "validate_query"]


class QueryStorage:
    """Storage manager for named queries."""

    def __init__(self, queries_file: str = ".bees/queries.yaml"):
        """Initialize query storage.

        Args:
            queries_file: Path to queries YAML file
        """
        self.queries_file = Path(queries_file)
        self.parser = QueryParser()

        # Ensure .bees directory exists
        self.queries_file.parent.mkdir(parents=True, exist_ok=True)

        # Create queries file if it doesn't exist
        if not self.queries_file.exists():
            self._initialize_queries_file()

    def _initialize_queries_file(self) -> None:
        """Create empty queries file with header comment."""
        with open(self.queries_file, 'w') as f:
            f.write("# Named Queries for Bees Query System\n")
            f.write("# Each query is a list of stages for the pipeline evaluator\n")
            f.write("---\n")
            yaml.dump({}, f, default_flow_style=False)
        logger.info(f"Initialized queries file: {self.queries_file}")

    def save_query(self, name: str, query_yaml: str | list, validate: bool = True) -> None:
        """Save a named query to storage.

        Args:
            name: Name for the query
            query_yaml: YAML string or list structure representing the query
            validate: Whether to validate query structure (set False for parameterized queries)

        Raises:
            QueryValidationError: If query structure is invalid and validate=True
            IOError: If file cannot be written
        """
        # Validate query structure if requested
        if validate:
            stages = self.parser.parse_and_validate(query_yaml)
        else:
            # Just parse without validation (for parameterized queries)
            stages = self.parser.parse(query_yaml)

        # Load existing queries
        queries = self._load_all_queries()

        # Add or update query
        queries[name] = stages

        # Write back to file
        try:
            with open(self.queries_file, 'w') as f:
                f.write("# Named Queries for Bees Query System\n")
                f.write("# Each query is a list of stages for the pipeline evaluator\n")
                f.write("---\n")
                yaml.dump(queries, f, default_flow_style=False, sort_keys=True)
            logger.info(f"Saved query '{name}' to {self.queries_file}")
        except IOError as e:
            logger.error(f"Failed to write queries file: {e}")
            raise IOError(f"Failed to save query: {e}")

    def load_query(self, name: str) -> list:
        """Load a named query from storage.

        Args:
            name: Name of the query to load

        Returns:
            List of stages for the query

        Raises:
            KeyError: If query name not found
            IOError: If file cannot be read
        """
        queries = self._load_all_queries()

        if name not in queries:
            raise KeyError(f"Query not found: {name}")

        return queries[name]

    def list_queries(self) -> List[str]:
        """List all available query names.

        Returns:
            List of query names
        """
        queries = self._load_all_queries()
        return sorted(queries.keys())

    def _load_all_queries(self) -> Dict[str, Any]:
        """Load all queries from storage file.

        Returns:
            Dictionary mapping query names to query stages

        Raises:
            IOError: If file cannot be read
            yaml.YAMLError: If file contains invalid YAML
        """
        if not self.queries_file.exists():
            return {}

        try:
            with open(self.queries_file, 'r') as f:
                # Skip header comments
                content = f.read()
                # Split on first --- separator
                if '---' in content:
                    _, yaml_content = content.split('---', 1)
                else:
                    yaml_content = content

                queries = yaml.safe_load(yaml_content)
                return queries if queries else {}
        except IOError as e:
            logger.error(f"Failed to read queries file: {e}")
            raise IOError(f"Failed to load queries: {e}")
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in queries file: {e}")
            raise yaml.YAMLError(f"Invalid YAML in queries file: {e}")


# Module-level convenience functions using default storage instance
_default_storage: Optional[QueryStorage] = None


def _get_default_storage() -> QueryStorage:
    """Get or create default storage instance."""
    global _default_storage
    if _default_storage is None:
        _default_storage = QueryStorage()
    return _default_storage


def save_query(name: str, query_yaml: str | list, validate: bool = True) -> None:
    """Save a named query to default storage.

    Args:
        name: Name for the query
        query_yaml: YAML string or list structure representing the query
        validate: Whether to validate query structure (set False for parameterized queries)

    Raises:
        QueryValidationError: If query structure is invalid and validate=True
        IOError: If file cannot be written
    """
    storage = _get_default_storage()
    storage.save_query(name, query_yaml, validate)


def load_query(name: str) -> list:
    """Load a named query from default storage.

    Args:
        name: Name of the query to load

    Returns:
        List of stages for the query

    Raises:
        KeyError: If query name not found
        IOError: If file cannot be read
    """
    storage = _get_default_storage()
    return storage.load_query(name)


def list_queries() -> List[str]:
    """List all available query names from default storage.

    Returns:
        List of query names
    """
    storage = _get_default_storage()
    return storage.list_queries()


def validate_query(query_yaml: str | list) -> list:
    """Validate query structure.

    Args:
        query_yaml: YAML string or list structure representing the query

    Returns:
        List of validated stages

    Raises:
        QueryValidationError: If query structure is invalid
    """
    parser = QueryParser()
    return parser.parse_and_validate(query_yaml)
