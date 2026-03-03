"""Query parser and validator for MCP query system.

Parses and validates YAML query structures for the multi-stage pipeline system.
"""

import re

import yaml

__all__ = ["QueryParser", "QueryValidationError"]


class QueryValidationError(Exception):
    """Raised when query validation fails."""

    pass


class QueryParser:
    """Parse and validate YAML query structures.

    A query is a list of stages evaluated sequentially as a pipeline.
    Each stage is a list of terms that are ANDed together.
    Stages can be either Search stages or Graph stages, but not mixed.

    Search terms:
    - type=<value>
    - id=<value>
    - status=<value>
    - title~<regex>
    - tag~<regex>
    - parent=<value>
    - guid=<value>
    - hive=<value>
    - hive~<regex>

    Graph terms:
    - down_dependencies
    - up_dependencies
    - parent
    - children
    """

    # Valid search term prefixes
    SEARCH_TERMS = {"type=", "id=", "status=", "title~", "tag~", "parent=", "guid=", "hive=", "hive~"}

    # Valid graph term names
    GRAPH_TERMS = {"down_dependencies", "up_dependencies", "parent", "children"}

    def __init__(self):
        """Initialize QueryParser."""
        pass

    def _is_valid_tier_type(self, ticket_type: str) -> bool:
        """Check if ticket type matches valid tier format.

        Valid formats:
        - "bee": Base tier
        - "t<N>": Dynamic tier types (t1, t2, t3, t10, etc.)

        Args:
            ticket_type: Type string to validate

        Returns:
            True if ticket_type matches a valid tier format
        """
        if ticket_type == "bee":
            return True
        # Match t<number> pattern (t1, t2, t3, t10, t100, etc.)
        if ticket_type.startswith("t") and len(ticket_type) >= 2:
            try:
                int(ticket_type[1:])
                return True
            except ValueError:
                return False
        return False

    def parse(self, query_yaml: str | list) -> list[list[str]]:
        """Parse YAML query into list of stages.

        Args:
            query_yaml: YAML string or already parsed list structure

        Returns:
            List of stages, where each stage is a list of term strings

        Raises:
            QueryValidationError: If query structure is invalid
        """
        # Parse YAML if string
        if isinstance(query_yaml, str):
            try:
                query_data = yaml.safe_load(query_yaml)
            except yaml.YAMLError as e:
                raise QueryValidationError(f"Invalid YAML: {e}") from e
        else:
            query_data = query_yaml

        # Validate basic structure
        if not isinstance(query_data, list):
            raise QueryValidationError(f"Query must be a list, got {type(query_data).__name__}")

        if len(query_data) == 0:
            raise QueryValidationError("Query cannot be empty")

        # Parse each stage
        stages = []
        for stage_idx, stage in enumerate(query_data):
            if not isinstance(stage, list):
                raise QueryValidationError(f"Stage {stage_idx} must be a list, got {type(stage).__name__}")

            if len(stage) == 0:
                raise QueryValidationError(f"Stage {stage_idx} cannot be empty")

            # Extract terms as strings
            terms = []
            for term_idx, term in enumerate(stage):
                if not isinstance(term, str):
                    raise QueryValidationError(
                        f"Stage {stage_idx}, term {term_idx} must be a string, got {type(term).__name__}"
                    )
                terms.append(term)

            stages.append(terms)

        return stages

    def validate(self, stages: list[list[str]]) -> None:
        """Validate query structure and semantics.

        Args:
            stages: List of stages from parse()

        Raises:
            QueryValidationError: If query is invalid
        """
        for stage_idx, stage in enumerate(stages):
            self._validate_stage(stage, stage_idx)

    def _validate_stage(self, stage: list[str], stage_idx: int) -> None:
        """Validate a single stage.

        Args:
            stage: List of term strings
            stage_idx: Stage index for error messages

        Raises:
            QueryValidationError: If stage is invalid
        """
        stage_types = set()

        for term in stage:
            # Determine term type and validate
            if self._is_search_term(term):
                stage_types.add("search")
                self._validate_search_term(term, stage_idx)
            elif self._is_graph_term(term):
                stage_types.add("graph")
                self._validate_graph_term(term, stage_idx)
            else:
                raise QueryValidationError(
                    f"Stage {stage_idx}: Unknown term '{term}'. "
                    f"Valid search terms: {', '.join(self.SEARCH_TERMS)}. "
                    f"Valid graph terms: {', '.join(self.GRAPH_TERMS)}"
                )

        # Enforce stage purity - no mixing search and graph terms
        if len(stage_types) > 1:
            raise QueryValidationError(
                f"Stage {stage_idx}: Cannot mix search and graph terms in same stage. "
                f"Found both: {', '.join(stage_types)}"
            )

    def _is_search_term(self, term: str) -> bool:
        """Check if term is a search term."""
        return any(term.startswith(prefix) for prefix in self.SEARCH_TERMS)

    def _is_graph_term(self, term: str) -> bool:
        """Check if term is a graph term."""
        return term in self.GRAPH_TERMS

    def _validate_search_term(self, term: str, stage_idx: int) -> None:
        """Validate a search term.

        Args:
            term: Search term string
            stage_idx: Stage index for error messages

        Raises:
            QueryValidationError: If term is invalid
        """
        if term.startswith("type="):
            value = term[5:]  # Skip 'type='
            if not value:
                raise QueryValidationError(f"Stage {stage_idx}: type= term missing value")
            if not self._is_valid_tier_type(value):
                raise QueryValidationError(
                    f"Stage {stage_idx}: Invalid type '{value}'. Valid formats: 'bee' or 't<N>' (t1, t2, t3, etc.)"
                )

        elif term.startswith("id="):
            value = term[3:]  # Skip 'id='
            if not value:
                raise QueryValidationError(f"Stage {stage_idx}: id= term missing value")

        elif term.startswith("status="):
            value = term[7:]  # Skip 'status='
            if not value:
                raise QueryValidationError(f"Stage {stage_idx}: status= term missing value")
            # ID format validation could be added here

        elif term.startswith("parent="):
            value = term[7:]  # Skip 'parent='
            if not value:
                raise QueryValidationError(f"Stage {stage_idx}: parent= term missing value")

        elif term.startswith("guid="):
            value = term[5:]  # Skip 'guid='
            if not value:
                raise QueryValidationError(f"Stage {stage_idx}: guid= term missing value")

        elif term.startswith("hive="):
            value = term[5:]  # Skip 'hive='
            if not value:
                raise QueryValidationError(f"Stage {stage_idx}: hive= term missing value")

        elif term.startswith("hive~"):
            pattern = term[5:]  # Skip 'hive~'
            if not pattern:
                raise QueryValidationError(f"Stage {stage_idx}: hive~ term missing regex pattern")
            self._validate_regex_pattern(pattern, "hive~", stage_idx)

        elif term.startswith("title~") or term.startswith("tag~"):
            prefix_len = 6 if term.startswith("title~") else 4  # title~ is 6, tag~ is 4
            pattern = term[prefix_len:]
            if not pattern:
                raise QueryValidationError(f"Stage {stage_idx}: {term[:prefix_len]} term missing regex pattern")
            # Validate regex pattern
            self._validate_regex_pattern(pattern, term[:prefix_len], stage_idx)

    def _validate_regex_pattern(self, pattern: str, term_type: str, stage_idx: int) -> None:
        """Validate regex pattern can be compiled.

        Args:
            pattern: Regex pattern string
            term_type: Term type for error messages (e.g., 'title~', 'tag~')
            stage_idx: Stage index for error messages

        Raises:
            QueryValidationError: If regex is invalid
        """
        try:
            re.compile(pattern)
        except re.error as e:
            raise QueryValidationError(f"Stage {stage_idx}: Invalid regex pattern in {term_type} term: {e}") from e

    def _validate_graph_term(self, term: str, stage_idx: int) -> None:
        """Validate a graph term.

        Args:
            term: Graph term string
            stage_idx: Stage index for error messages

        Raises:
            QueryValidationError: If term is invalid
        """
        # Graph terms should be exact matches (no parameters)
        if term not in self.GRAPH_TERMS:
            raise QueryValidationError(
                f"Stage {stage_idx}: Invalid graph term '{term}'. Valid graph terms: {', '.join(self.GRAPH_TERMS)}"
            )

    def parse_and_validate(self, query_yaml: str | list) -> list[list[str]]:
        """Parse and validate query in one step.

        Args:
            query_yaml: YAML string or already parsed list structure

        Returns:
            List of validated stages

        Raises:
            QueryValidationError: If query is invalid
        """
        stages = self.parse(query_yaml)
        self.validate(stages)
        return stages
