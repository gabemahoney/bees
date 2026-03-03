"""
Unit tests for query parsing and validation.

PURPOSE:
Tests the query parser that converts YAML query pipelines into validated
internal representations, enforcing query syntax rules.

SCOPE - Tests that belong here:
- QueryParser: Parsing YAML query pipelines
- Query syntax validation (stage structure, term format)
- Stage type detection (search vs graph)
- Term parsing (type=, id=, title~, tag~, parent, children, etc.)
- QueryValidationError: Query validation error handling
- Stage purity enforcement (no mixing search and graph in one stage)
- Multi-stage pipeline parsing

SCOPE - Tests that DON'T belong here:
- Query execution -> test_pipeline.py, test_search_executor.py, test_graph_executor.py
- Query storage -> test_query_tools.py
- Named queries -> test_query_tools.py
- MCP query tools -> test_query_tools.py (MCP layer)

RELATED FILES:
- test_pipeline.py: Pipeline execution
- test_query_tools.py: Query storage and MCP tools
- test_search_executor.py: Search term execution
- test_graph_executor.py: Graph traversal execution
"""

import pytest

from src.query_parser import QueryParser, QueryValidationError
from tests.test_constants import TICKET_ID_TEST_BEE


class TestQueryParserBasics:
    """Tests for basic query parsing."""

    @pytest.mark.parametrize(
        "query,expected_len,expected_stages",
        [
            pytest.param([["type=bee"]], 1, [["type=bee"]], id="simple_single_stage"),
            pytest.param(
                [["type=bee", "tag~beta"], ["children"], ["tag~open"]],
                3,
                [["type=bee", "tag~beta"], ["children"], ["tag~open"]],
                id="multi_stage",
            ),
        ],
    )
    def test_parse_valid_queries(self, query, expected_len, expected_stages):
        """Should parse valid queries."""
        parser = QueryParser()
        stages = parser.parse(query)
        assert len(stages) == expected_len
        assert stages == expected_stages

    def test_parse_yaml_string(self):
        """Should parse YAML string input."""
        parser = QueryParser()
        yaml_query = """
        - ['type=t1']
        - ['parent']
        """
        stages = parser.parse(yaml_query)
        assert len(stages) == 2
        assert stages[0] == ["type=t1"]
        assert stages[1] == ["parent"]

    @pytest.mark.parametrize(
        "invalid_query,expected_error",
        [
            pytest.param([], "cannot be empty", id="empty_query"),
            pytest.param("not-a-list", "must be a list", id="non_list_query"),
            pytest.param(["not-a-list"], "Stage 0 must be a list", id="non_list_stage"),
            pytest.param([[]], "Stage 0 cannot be empty", id="empty_stage"),
            pytest.param([[123]], "must be a string", id="non_string_term"),
            pytest.param("[invalid: yaml: syntax", "Invalid YAML", id="invalid_yaml"),
        ],
    )
    def test_parse_errors(self, invalid_query, expected_error):
        """Should raise errors for invalid queries."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match=expected_error):
            parser.parse(invalid_query)


class TestSearchTermValidation:
    """Tests for search term validation."""

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param([["type=bee"]], id="type_bee"),
            pytest.param([["type=t1"]], id="type_t1"),
            pytest.param([["type=t2"]], id="type_t2"),
            pytest.param([[f"id={TICKET_ID_TEST_BEE}"]], id="valid_id"),
            pytest.param([["title~test"]], id="title_simple"),
            pytest.param([["title~^(?!.*preview).*"]], id="title_negative_lookahead"),
            pytest.param([["tag~open"]], id="tag_simple"),
            pytest.param([["tag~beta|preview"]], id="tag_alternation"),
            pytest.param([["status=open"]], id="status_open"),
            pytest.param([["status=completed"]], id="status_completed"),
            pytest.param([["status=in_progress"]], id="status_in_progress"),
            pytest.param([["parent=b.abc"]], id="parent_bugs"),
            pytest.param([["parent=b.b123"]], id="parent_backend"),
            pytest.param([["type=t1", "tag~open", "tag~p0"]], id="multiple_search_terms"),
            pytest.param([["type=t1", "parent=b.abc"]], id="parent_in_search_stage"),
            pytest.param([["guid=ep1AAAAAAAAAAAAAAAAAAA"]], id="guid_match"),
            pytest.param([["hive=backend"]], id="hive_exact"),
            pytest.param([["hive~back.*"]], id="hive_regex"),
            pytest.param([["hive=backend", "type=bee"]], id="hive_with_type"),
        ],
    )
    def test_valid_search_terms(self, query):
        """Should accept valid search terms."""
        parser = QueryParser()
        stages = parser.parse(query)
        parser.validate(stages)

    @pytest.mark.parametrize(
        "query,expected_error",
        [
            pytest.param([["type=invalid"]], "Invalid type", id="invalid_type_value"),
            pytest.param([["type="]], "type= term missing value", id="empty_type_value"),
            pytest.param([["id="]], "id= term missing value", id="empty_id_value"),
            pytest.param([["title~"]], "title~ term missing regex pattern", id="empty_title_regex"),
            pytest.param([["title~[unclosed"]], "Invalid regex pattern", id="invalid_title_regex"),
            pytest.param([["tag~"]], "tag~ term missing regex pattern", id="empty_tag_regex"),
            pytest.param([["tag~(?P<invalid"]], "Invalid regex pattern", id="invalid_tag_regex"),
            pytest.param([["status="]], "status= term missing value", id="empty_status_value"),
            pytest.param([["parent="]], "parent= term missing value", id="empty_parent_value"),
            pytest.param([["guid="]], "guid= term missing value", id="empty_guid_value"),
            pytest.param([["hive="]], "hive= term missing value", id="empty_hive_value"),
            pytest.param([["hive~"]], "hive~ term missing regex pattern", id="empty_hive_regex"),
            pytest.param([["hive~[unclosed"]], "Invalid regex pattern", id="invalid_hive_regex"),
            pytest.param(
                [["parent=b.be1", "children"]], "Cannot mix search and graph terms", id="parent_mixed_with_graph"
            ),
        ],
    )
    def test_invalid_search_terms(self, query, expected_error):
        """Should reject invalid search terms."""
        parser = QueryParser()
        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match=expected_error):
            parser.validate(stages)


class TestGraphTermValidation:
    """Tests for graph term validation."""

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param([["down_dependencies"]], id="down_dependencies"),
            pytest.param([["up_dependencies"]], id="up_dependencies"),
            pytest.param([["parent"]], id="parent"),
            pytest.param([["children"]], id="children"),
        ],
    )
    def test_valid_graph_terms(self, query):
        """Should accept valid graph terms."""
        parser = QueryParser()
        stages = parser.parse(query)
        parser.validate(stages)

    def test_invalid_graph_term_raises_error(self):
        """Should reject invalid graph term names."""
        parser = QueryParser()
        query = [["invalid_term"]]
        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="Unknown term"):
            parser.validate(stages)


class TestStagePurityEnforcement:
    """Tests for stage purity (no mixing search and graph terms)."""

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param([["type=bee", "tag~beta", "title~test"]], id="pure_search"),
            pytest.param([["children"]], id="pure_graph"),
            pytest.param(
                [["type=bee", "tag~beta"], ["children"], ["tag~open"]], id="multiple_stages_different_types"
            ),
        ],
    )
    def test_valid_stage_purity(self, query):
        """Should accept pure search or pure graph stages."""
        parser = QueryParser()
        stages = parser.parse(query)
        parser.validate(stages)

    def test_mixed_stage_raises_error(self):
        """Should reject stage mixing search and graph terms."""
        parser = QueryParser()
        query = [["type=bee", "children"]]
        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="Cannot mix search and graph terms"):
            parser.validate(stages)


class TestPRDExampleQueries:
    """Tests for example queries from PRD."""

    @pytest.mark.parametrize(
        "query,expected_len",
        [
            pytest.param(
                [["type=bee", "tag~(?i)(beta|preview)"], ["children"], ["tag~(?i)(open|in progress)"]],
                3, id="open_beta_work_items",
            ),
            pytest.param(
                [["tag~^(?!.*beta).*"]],
                1, id="non_beta_items",
            ),
            pytest.param(
                [["type=t1", "tag~^(?!.*preview).*", "tag~(?i)(open|in progress)"]],
                1, id="open_non_preview_tasks",
            ),
        ],
    )
    def test_prd_queries(self, query, expected_len):
        """Should validate PRD example queries."""
        parser = QueryParser()
        stages = parser.parse_and_validate(query)
        assert len(stages) == expected_len


class TestParseAndValidate:
    """Tests for combined parse_and_validate method."""

    def test_parse_and_validate_valid_query(self):
        """Should parse and validate in one step."""
        parser = QueryParser()
        stages = parser.parse_and_validate([["type=bee", "tag~beta"]])
        assert len(stages) == 1

    def test_parse_and_validate_invalid_query(self):
        """Should raise error on invalid query."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError):
            parser.parse_and_validate([["type=invalid"]])

    def test_parse_and_validate_yaml_string(self):
        """Should parse and validate YAML string."""
        parser = QueryParser()
        stages = parser.parse_and_validate("- ['type=t1', 'tag~open']\n- ['parent']")
        assert len(stages) == 2


class TestRegexPatterns:
    """Tests for specific regex patterns."""

    @pytest.mark.parametrize(
        "query,expected_term",
        [
            pytest.param([["tag~(?i)beta"]], ["tag~(?i)beta"], id="case_insensitive"),
            pytest.param([["tag~^(?!.*closed).*"]], ["tag~^(?!.*closed).*"], id="negative_lookahead"),
            pytest.param([["tag~beta|alpha|preview"]], ["tag~beta|alpha|preview"], id="alternation"),
            pytest.param([["tag~p[0-4]"]], ["tag~p[0-4]"], id="character_class"),
            pytest.param([["title~(?i)^(task|bee):"]], ["title~(?i)^(task|bee):"], id="complex_title"),
        ],
    )
    def test_regex_patterns(self, query, expected_term):
        """Should accept various regex patterns."""
        parser = QueryParser()
        stages = parser.parse_and_validate(query)
        assert stages[0] == expected_term


class TestErrorMessages:
    """Tests for clear error messages."""

    def test_stage_mixing_error_message(self):
        """Should provide clear error for mixing stage types."""
        parser = QueryParser()
        stages = parser.parse([["type=bee", "children"]])
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)
        assert "Cannot mix search and graph terms" in str(exc_info.value)
        assert "Stage 0" in str(exc_info.value)

    def test_invalid_type_error_message(self):
        """Should provide clear error for invalid type."""
        parser = QueryParser()
        stages = parser.parse([["type=invalid"]])
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)
        error_msg = str(exc_info.value)
        assert "Invalid type" in error_msg
        for t in ["bee", "t1", "t2", "t3"]:
            assert t in error_msg

    def test_unknown_term_error_includes_parent(self):
        """Should include parent= in valid search terms and show unknown term."""
        parser = QueryParser()
        stages = parser.parse([["unknown_term"]])
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)
        error_msg = str(exc_info.value)
        assert "Unknown term" in error_msg
        assert "unknown_term" in error_msg
        assert "parent=" in error_msg
        assert "status=" in error_msg
        assert "guid=" in error_msg
        assert "hive=" in error_msg
