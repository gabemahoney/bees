"""Query parser and validator for MCP query system.

Parses and validates YAML query structures for the multi-stage pipeline system.
"""

import re
from dataclasses import dataclass

__all__ = [
    "NON_REPORTABLE_FIELDS",
    "QUERY_YAML_EXAMPLE",
    "REPORT_QUERY_YAML_EXAMPLE",
    "ParsedQuery",
    "QueryParser",
    "QueryValidationError",
    "PRIORITY_TERMS_HELP",
    "VALID_REPORT_FIELDS",
    "is_priority_term",
    "parse_priority_term",
]

VALID_REPORT_FIELDS: frozenset[str] = frozenset({
    "ticket_type",
    "ticket_status",
    "title",
    "tags",
    "parent",
    "children",
    "up_dependencies",
    "down_dependencies",
    "created_at",
    "schema_version",
    "guid",
    "hive",
    "priority",
})

# Ticket fields that "report" rejects: query results omit them, so callers use show_ticket.
NON_REPORTABLE_FIELDS: frozenset[str] = frozenset({"body", "reference_materials"})

# Single-line YAML flow-style queries shown in CLI help and the sting reference.
# They work typed into a shell inside single quotes, with no newline escapes.
QUERY_YAML_EXAMPLE = "{stages: [[type=bee, status=pupa], [children]]}"
REPORT_QUERY_YAML_EXAMPLE = "{stages: [[type=bee, status=pupa]], report: [title, ticket_status]}"

# Help for the priority search terms, shared by the CLI help, the sting reference and the
# MCP tool descriptions so they can't drift. Plain lines with no indent; callers indent them.
# Deliberately holds no runnable "bees ..." example line.
PRIORITY_TERMS_HELP = (
    "priority=N | priority!=N | priority<N | priority<=N | priority>N | priority>=N\n"
    "    compare priority with the integer N (negatives allowed, e.g. priority<=0, priority>-2)\n"
    "priority=none\n"
    '    tickets with no priority (lowercase "none", "=" only)\n'
    "A ticket with no priority never matches a numeric term, including priority!=N;\n"
    "use priority=none to find those tickets."
)


# Priority terms: ``priority`` + operator + value. Longest operators first so "<=" is never read as "<".
_PRIORITY_TERM_RE = re.compile(r"priority(!=|<=|>=|=|<|>)(.*)", re.DOTALL)
_PRIORITY_INTEGER_RE = re.compile(r"-?[0-9]+")


def is_priority_term(term: str) -> bool:
    """Return True if term is a priority search term (well-formed or not).

    A term is a priority term when it starts with ``priority`` followed by one of
    ``=``, ``!=``, ``<`` or ``>``. Whether the operator and value are valid is decided
    by parse_priority_term, so malformed terms still classify as search terms and
    fail with a precise error.
    """
    return term.startswith(("priority=", "priority!=", "priority<", "priority>"))


def parse_priority_term(term: str) -> tuple[str, int | None]:
    """Parse a priority term into (operator, value).

    Grammar: ``priority`` then one of ``=``, ``!=``, ``<``, ``<=``, ``>``, ``>=`` then an
    integer literal (optional leading ``-``, ASCII digits only, no ``+`` or whitespace),
    or the lowercase literal ``none`` which is accepted only with ``=``.

    Args:
        term: Priority term string, e.g. "priority<=0" or "priority=none"

    Returns:
        (operator, value). For ``priority=none`` the result is ("=", None), meaning
        "unset"; for numeric terms value is an int.

    Raises:
        QueryValidationError: If the term is malformed
    """
    match = _PRIORITY_TERM_RE.fullmatch(term)
    if match is None:
        raise QueryValidationError(
            f"Invalid priority term '{term}'. Expected priority<op><integer> with op one of "
            f"=, !=, <, <=, >, >=, or priority=none"
        )
    operator, raw = match.group(1), match.group(2)
    if not raw:
        raise QueryValidationError(f"Invalid priority term '{term}': missing value")
    if raw == "none":
        if operator != "=":
            raise QueryValidationError(
                f"Invalid priority term '{term}': 'none' is only valid with '=' (use priority=none)"
            )
        return ("=", None)
    if _PRIORITY_INTEGER_RE.fullmatch(raw) is None:
        raise QueryValidationError(
            f"Invalid priority term '{term}': value must be an integer (negatives allowed) "
            f"or 'none' with '='"
        )
    return (operator, int(raw))


@dataclass
class ParsedQuery:
    """Result of parsing and validating a query."""

    stages: list[list[str]]
    report: list[str] | None


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
    - priority=<N>, priority!=<N>, priority<<N>, priority<=<N>, priority><N>, priority>=<N>
      (N an integer, negatives allowed)
    - priority=none (tickets with no priority)

    Graph terms:
    - down_dependencies
    - up_dependencies
    - parent
    - children
    """

    # Valid search term prefixes
    SEARCH_TERMS = {
        "type=",
        "id=",
        "status=",
        "title~",
        "tag~",
        "parent=",
        "guid=",
        "hive=",
        "hive~",
        "priority=",
        "priority!=",
        "priority<",
        "priority<=",
        "priority>",
        "priority>=",
    }

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

    def parse(self, query_input: dict) -> list[list[str]]:
        """Parse query dict into list of stages.

        Args:
            query_input: Dict with a "stages" key containing a list of stages

        Returns:
            List of stages, where each stage is a list of term strings

        Raises:
            QueryValidationError: If query structure is invalid
        """
        if not isinstance(query_input, dict):
            raise QueryValidationError(
                f'Query must be a dict with a "stages" key, e.g. {{"stages": [...]}}, '
                f"got {type(query_input).__name__}"
            )

        if "stages" not in query_input:
            raise QueryValidationError('Query dict must contain a "stages" key')

        stages_data = query_input["stages"]

        if not isinstance(stages_data, list):
            raise QueryValidationError(f'"stages" must be a list, got {type(stages_data).__name__}')

        if len(stages_data) == 0:
            raise QueryValidationError("Query cannot be empty")

        # Parse each stage
        stages = []
        for stage_idx, stage in enumerate(stages_data):
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
        if is_priority_term(term):
            try:
                parse_priority_term(term)
            except QueryValidationError as e:
                raise QueryValidationError(f"Stage {stage_idx}: {e}") from e

        elif term.startswith("type="):
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

    def parse_and_validate(self, query_input: dict) -> ParsedQuery:
        """Parse and validate query in one step.

        Args:
            query_input: Dict with a "stages" key and optional "report" key

        Returns:
            ParsedQuery with validated stages and optional report

        Raises:
            QueryValidationError: If query is invalid
        """
        if not isinstance(query_input, dict):
            raise QueryValidationError(
                f'Query must be a dict with a "stages" key, e.g. {{"stages": [...]}}, '
                f"got {type(query_input).__name__}"
            )

        report = None
        if "report" in query_input:
            report = query_input["report"]
            if not isinstance(report, list):
                raise QueryValidationError(
                    f'"report" must be a list, got {type(report).__name__}'
                )

            for entry_idx, entry in enumerate(report):
                if not isinstance(entry, str):
                    raise QueryValidationError(
                        f'each "report" entry must be a field name (a string), '
                        f"got {type(entry).__name__} at index {entry_idx}"
                    )

            # Silently strip ticket_id
            report = [f for f in report if f != "ticket_id"]

            if len(report) == 0:
                raise QueryValidationError("report list cannot be empty")

            for field in report:
                if field in NON_REPORTABLE_FIELDS:
                    raise QueryValidationError(
                        f'report field "{field}" is not available in query results; use show_ticket to retrieve it'
                    )
                if field not in VALID_REPORT_FIELDS:
                    raise QueryValidationError(
                        f'report field "{field}" is not recognized'
                    )

        validated_stages = self.parse(query_input)
        self.validate(validated_stages)
        return ParsedQuery(stages=validated_stages, report=report)
