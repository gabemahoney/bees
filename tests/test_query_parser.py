"""
Unit tests for query parsing and validation.

PURPOSE:
Tests the query parser that converts dict query structures into validated
internal representations, enforcing query syntax rules.

SCOPE - Tests that belong here:
- QueryParser: Parsing dict query structures
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

from src.query_parser import VALID_REPORT_FIELDS, ParsedQuery, QueryParser, QueryValidationError
from tests.test_constants import TICKET_ID_TEST_BEE


class TestQueryParserBasics:
    """Tests for basic query parsing."""

    @pytest.mark.parametrize(
        "stages,expected_len,expected_stages",
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
    def test_parse_valid_queries(self, stages, expected_len, expected_stages):
        """Should parse valid dict queries."""
        parser = QueryParser()
        result = parser.parse({"stages": stages})
        assert len(result) == expected_len
        assert result == expected_stages

    def test_parse_dict_with_extra_keys(self):
        """Should parse dict and ignore unrecognised keys (report etc.)."""
        parser = QueryParser()
        result = parser.parse({"stages": [["type=t1"]], "report": ["title"]})
        assert result == [["type=t1"]]

    @pytest.mark.parametrize(
        "invalid_query,expected_error",
        [
            pytest.param({"stages": []}, "cannot be empty", id="empty_stages"),
            pytest.param({"stages": "not-a-list"}, '"stages" must be a list', id="stages_not_list"),
            pytest.param({"stages": ["not-a-list"]}, "Stage 0 must be a list", id="non_list_stage"),
            pytest.param({"stages": [[]]}, "Stage 0 cannot be empty", id="empty_stage"),
            pytest.param({"stages": [[123]]}, "must be a string", id="non_string_term"),
            # Bare-list rejection (new format requirement)
            pytest.param([["type=bee"]], "Query must be a dict", id="bare_list_rejected"),
            pytest.param("not-a-dict", "Query must be a dict", id="string_rejected"),
            # Missing stages key
            pytest.param({}, '"stages" key', id="missing_stages_key"),
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
        stages = parser.parse({"stages": query})
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
        stages = parser.parse({"stages": query})
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
        stages = parser.parse({"stages": query})
        parser.validate(stages)

    def test_invalid_graph_term_raises_error(self):
        """Should reject invalid graph term names."""
        parser = QueryParser()
        query = [["invalid_term"]]
        stages = parser.parse({"stages": query})
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
        stages = parser.parse({"stages": query})
        parser.validate(stages)

    def test_mixed_stage_raises_error(self):
        """Should reject stage mixing search and graph terms."""
        parser = QueryParser()
        query = [["type=bee", "children"]]
        stages = parser.parse({"stages": query})
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
        result = parser.parse_and_validate({"stages": query})
        assert isinstance(result, ParsedQuery)
        assert len(result.stages) == expected_len


class TestParseAndValidate:
    """Tests for combined parse_and_validate method."""

    def test_parse_and_validate_valid_query(self):
        """Should parse and validate in one step."""
        parser = QueryParser()
        result = parser.parse_and_validate({"stages": [["type=bee", "tag~beta"]]})
        assert isinstance(result, ParsedQuery)
        assert len(result.stages) == 1

    def test_parse_and_validate_invalid_query(self):
        """Should raise error on invalid query."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError):
            parser.parse_and_validate({"stages": [["type=invalid"]]})

    def test_parse_and_validate_with_report(self):
        """Should preserve report field in ParsedQuery result."""
        parser = QueryParser()
        result = parser.parse_and_validate({"stages": [["type=t1"]], "report": ["title", "ticket_status"]})
        assert isinstance(result, ParsedQuery)
        assert result.stages == [["type=t1"]]
        assert result.report == ["title", "ticket_status"]

    def test_parse_and_validate_bare_list_rejected(self):
        """Should raise error when bare list passed instead of dict."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match="Query must be a dict"):
            parser.parse_and_validate([["type=t1"]])

    def test_parse_and_validate_missing_stages_key_rejected(self):
        """Should raise error when dict is missing the stages key."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match='"stages" key'):
            parser.parse_and_validate({})


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
        result = parser.parse_and_validate({"stages": query})
        assert result.stages[0] == expected_term


class TestReportFieldValidation:
    """Tests for report field validation in parse_and_validate."""

    @pytest.mark.parametrize(
        "field",
        [pytest.param(f, id=f) for f in sorted(VALID_REPORT_FIELDS)],
    )
    def test_valid_report_field_accepted(self, field):
        """Should accept each valid report field individually."""
        parser = QueryParser()
        result = parser.parse_and_validate({"stages": [["type=t1"]], "report": [field]})
        assert isinstance(result, ParsedQuery)
        assert field in result.report

    def test_multiple_valid_fields_accepted(self):
        """Should accept a list of multiple valid report fields."""
        parser = QueryParser()
        result = parser.parse_and_validate(
            {"stages": [["type=t1"]], "report": ["title", "ticket_status", "tags"]}
        )
        assert result.report == ["title", "ticket_status", "tags"]

    def test_ticket_id_silently_stripped(self):
        """ticket_id should be removed from report without raising an error."""
        parser = QueryParser()
        result = parser.parse_and_validate(
            {"stages": [["type=t1"]], "report": ["title", "ticket_id"]}
        )
        assert "ticket_id" not in result.report
        assert "title" in result.report

    def test_report_only_ticket_id_raises_after_strip(self):
        """report: [ticket_id] should error after strip leaves an empty list."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match="cannot be empty"):
            parser.parse_and_validate({"stages": [["type=t1"]], "report": ["ticket_id"]})

    def test_empty_report_list_raises(self):
        """report: [] should raise a validation error."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match="cannot be empty"):
            parser.parse_and_validate({"stages": [["type=t1"]], "report": []})

    @pytest.mark.parametrize(
        "field",
        [pytest.param("body", id="body"), pytest.param("egg", id="egg")],
    )
    def test_body_and_egg_rejected_with_show_ticket_hint(self, field):
        """body and egg should be rejected with a message mentioning show_ticket."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match="show_ticket"):
            parser.parse_and_validate({"stages": [["type=t1"]], "report": [field]})

    def test_hive_rejected(self):
        """hive should be rejected as not available in query results."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match="hive"):
            parser.parse_and_validate({"stages": [["type=t1"]], "report": ["hive"]})

    def test_unrecognized_field_error_names_the_field(self):
        """An unrecognized field name should appear in the error message."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match="banana"):
            parser.parse_and_validate({"stages": [["type=t1"]], "report": ["banana"]})

    def test_mix_of_valid_and_invalid_catches_first_invalid(self):
        """First invalid field in a mixed list should be caught."""
        parser = QueryParser()
        with pytest.raises(QueryValidationError, match="hive"):
            parser.parse_and_validate(
                {"stages": [["type=t1"]], "report": ["title", "hive", "tags"]}
            )


class TestErrorMessages:
    """Tests for clear error messages."""

    def test_stage_mixing_error_message(self):
        """Should provide clear error for mixing stage types."""
        parser = QueryParser()
        stages = parser.parse({"stages": [["type=bee", "children"]]})
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)
        assert "Cannot mix search and graph terms" in str(exc_info.value)
        assert "Stage 0" in str(exc_info.value)

    def test_invalid_type_error_message(self):
        """Should provide clear error for invalid type."""
        parser = QueryParser()
        stages = parser.parse({"stages": [["type=invalid"]]})
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)
        error_msg = str(exc_info.value)
        assert "Invalid type" in error_msg
        for t in ["bee", "t1", "t2", "t3"]:
            assert t in error_msg

    def test_unknown_term_error_includes_parent(self):
        """Should include parent= in valid search terms and show unknown term."""
        parser = QueryParser()
        stages = parser.parse({"stages": [["unknown_term"]]})
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)
        error_msg = str(exc_info.value)
        assert "Unknown term" in error_msg
        assert "unknown_term" in error_msg
        assert "parent=" in error_msg
        assert "status=" in error_msg
        assert "guid=" in error_msg
        assert "hive=" in error_msg
