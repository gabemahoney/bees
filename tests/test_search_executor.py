"""
Unit tests for search query execution.

PURPOSE:
Tests the SearchExecutor that filters tickets based on search terms
(type=, id=, title~, tag~, status=, etc.).

SCOPE - Tests that belong here:
- SearchExecutor: Search term evaluation
- Search term types: exact match (type=, id=), regex (title~, tag~)
- Field filtering: type, id, title, description, tags, status
- Regex pattern matching
- AND logic (all terms must match)
- Empty search results
- Invalid search terms

SCOPE - Tests that DON'T belong here:
- Query parsing -> test_query_parser.py
- Pipeline orchestration -> test_pipeline.py
- Graph traversal -> test_graph_executor.py
- Query storage -> test_query_tools.py

RELATED FILES:
- test_pipeline.py: Uses SearchExecutor for search stages
- test_query_parser.py: Parses search terms
- test_graph_executor.py: Complementary graph traversal
"""

import re

import pytest

from src.search_executor import SearchExecutor
from tests.test_constants import (
    TICKET_ID_EP1,
    TICKET_ID_EP2,
    TICKET_ID_ST1,
    TICKET_ID_TK1,
    TICKET_ID_TK2,
    TICKET_ID_XXX,
)


@pytest.fixture
def sample_tickets():
    """Sample ticket data for testing."""
    return {
        TICKET_ID_EP1: {
            "id": TICKET_ID_EP1,
            "issue_type": "bee",
            "title": "Build Authentication System",
            "status": "open",
            "tags": ["backend", "security", "beta"],
            "guid": "ep1aaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "hive": "backend",
        },
        TICKET_ID_TK1: {
            "id": TICKET_ID_TK1,
            "issue_type": "t1",
            "title": "Implement OAuth Login",
            "status": "in_progress",
            "tags": ["backend", "api"],
            "parent": TICKET_ID_EP1,
            "guid": "tk11bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "hive": "backend",
        },
        TICKET_ID_TK2: {
            "id": TICKET_ID_TK2,
            "issue_type": "t1",
            "title": "Build User Profile API",
            "status": "open",
            "tags": ["backend", "api", "beta"],
            "parent": TICKET_ID_EP1,
            "guid": "tk22cccccccccccccccccccccccccccc",
            "hive": "backend",
        },
        TICKET_ID_ST1: {
            "id": TICKET_ID_ST1,
            "issue_type": "t2",
            "title": "Write OAuth tests",
            "status": "completed",
            "tags": ["testing", "preview"],
            "parent": TICKET_ID_TK1,
            "guid": "st111ddddddddddddddddddddddddddd",
            "hive": "backend",
        },
        TICKET_ID_EP2: {
            "id": TICKET_ID_EP2,
            "issue_type": "bee",
            "title": "Frontend Dashboard",
            "status": "open",
            "tags": ["frontend", "ui"],
            "guid": "ep2eeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            "hive": "frontend",
        },
        "b.nol": {
            "id": "b.nol",
            "issue_type": "t1",
            "title": "Task without tags",
            "parent": TICKET_ID_EP2,
            "hive": "frontend",
        },
    }


@pytest.fixture
def executor():
    """Create SearchExecutor instance."""
    return SearchExecutor()


class TestFilterByType:
    """Tests for filter_by_type method."""

    @pytest.mark.parametrize(
        "type_value,expected",
        [
            pytest.param("bee", {TICKET_ID_EP1, TICKET_ID_EP2}, id="bee"),
            pytest.param("t1", {TICKET_ID_TK1, TICKET_ID_TK2, "b.nol"}, id="t1"),
            pytest.param("t2", {TICKET_ID_ST1}, id="t2"),
            pytest.param("nonexistent", set(), id="nonexistent"),
        ],
    )
    def test_filter_by_type(self, executor, sample_tickets, type_value, expected):
        """Test filtering by ticket type."""
        assert executor.filter_by_type(sample_tickets, type_value) == expected

    def test_filter_empty_tickets(self, executor):
        result = executor.filter_by_type({}, "bee")
        assert result == set()


class TestFilterById:
    """Tests for filter_by_id method."""

    @pytest.mark.parametrize(
        "id_value,expected",
        [
            pytest.param(TICKET_ID_TK1, {TICKET_ID_TK1}, id="existing"),
            pytest.param(TICKET_ID_XXX, set(), id="nonexistent"),
        ],
    )
    def test_filter_by_id(self, executor, sample_tickets, id_value, expected):
        assert executor.filter_by_id(sample_tickets, id_value) == expected


class TestFilterByParent:
    """Tests for filter_by_parent method."""

    @pytest.mark.parametrize(
        "parent_value,expected",
        [
            pytest.param(TICKET_ID_EP1, {TICKET_ID_TK1, TICKET_ID_TK2}, id="multiple_children"),
            pytest.param(TICKET_ID_TK1, {TICKET_ID_ST1}, id="single_child"),
            pytest.param(TICKET_ID_EP2, {"b.nol"}, id="different_parent"),
            pytest.param(TICKET_ID_XXX, set(), id="nonexistent"),
            pytest.param(None, {TICKET_ID_EP1, TICKET_ID_EP2}, id="no_parent"),
        ],
    )
    def test_filter_by_parent(self, executor, sample_tickets, parent_value, expected):
        """Should filter by parent field."""
        assert executor.filter_by_parent(sample_tickets, parent_value) == expected


class TestFilterByStatus:
    """Tests for filter_by_status method."""

    @pytest.mark.parametrize(
        "status_value,expected",
        [
            pytest.param("open", {TICKET_ID_EP1, TICKET_ID_TK2, TICKET_ID_EP2}, id="open"),
            pytest.param("in_progress", {TICKET_ID_TK1}, id="in_progress"),
            pytest.param("completed", {TICKET_ID_ST1}, id="completed"),
            pytest.param("nonexistent", set(), id="nonexistent"),
        ],
    )
    def test_filter_by_status(self, executor, sample_tickets, status_value, expected):
        """Test filtering by ticket status."""
        assert executor.filter_by_status(sample_tickets, status_value) == expected

    def test_filter_missing_status(self, executor):
        """Tickets without status field should not match."""
        tickets = {"b.nos": {"id": "b.nos", "issue_type": "t1"}}
        assert executor.filter_by_status(tickets, "open") == set()


class TestFilterByGuid:
    """Tests for filter_by_guid method."""

    @pytest.mark.parametrize(
        "guid_value,expected",
        [
            pytest.param("ep1aaaaaaaaaaaaaaaaaaaaaaaaaaaaa", {TICKET_ID_EP1}, id="exact_match"),
            pytest.param("tk11bbbbbbbbbbbbbbbbbbbbbbbbbbbb", {TICKET_ID_TK1}, id="t1_match"),
            pytest.param("nonexistent_guid_value", set(), id="nonexistent"),
        ],
    )
    def test_filter_by_guid(self, executor, sample_tickets, guid_value, expected):
        """Test filtering by exact guid match."""
        assert executor.filter_by_guid(sample_tickets, guid_value) == expected

    def test_filter_missing_guid(self, executor):
        """Tickets without guid field should not match."""
        tickets = {"b.nog": {"id": "b.nog", "issue_type": "bee"}}
        assert executor.filter_by_guid(tickets, "some_guid_value_here") == set()


class TestFilterByHive:
    """Tests for filter_by_hive method."""

    @pytest.mark.parametrize(
        "hive_value,expected",
        [
            pytest.param("backend", {TICKET_ID_EP1, TICKET_ID_TK1, TICKET_ID_TK2, TICKET_ID_ST1}, id="backend"),
            pytest.param("frontend", {TICKET_ID_EP2, "b.nol"}, id="frontend"),
            pytest.param("nonexistent", set(), id="nonexistent"),
        ],
    )
    def test_filter_by_hive(self, executor, sample_tickets, hive_value, expected):
        assert executor.filter_by_hive(sample_tickets, hive_value) == expected

    def test_filter_missing_hive(self, executor):
        """Tickets without hive field should not match."""
        tickets = {"b.noh": {"id": "b.noh", "issue_type": "bee"}}
        assert executor.filter_by_hive(tickets, "backend") == set()


class TestFilterByHiveRegex:
    """Tests for filter_by_hive_regex method."""

    @pytest.mark.parametrize(
        "pattern,expected",
        [
            pytest.param("backend", {TICKET_ID_EP1, TICKET_ID_TK1, TICKET_ID_TK2, TICKET_ID_ST1}, id="exact"),
            pytest.param("back.*", {TICKET_ID_EP1, TICKET_ID_TK1, TICKET_ID_TK2, TICKET_ID_ST1}, id="wildcard"),
            pytest.param("backend|frontend", {TICKET_ID_EP1, TICKET_ID_TK1, TICKET_ID_TK2, TICKET_ID_ST1, TICKET_ID_EP2, "b.nol"}, id="alternation"),
            pytest.param("nonexistent", set(), id="no_match"),
        ],
    )
    def test_filter_by_hive_regex(self, executor, sample_tickets, pattern, expected):
        assert executor.filter_by_hive_regex(sample_tickets, pattern) == expected

    def test_invalid_regex(self, executor, sample_tickets):
        with pytest.raises(re.error):
            executor.filter_by_hive_regex(sample_tickets, "[invalid(")


class TestFilterByTitleRegex:
    """Tests for filter_by_title_regex method."""

    @pytest.mark.parametrize(
        "pattern,expected",
        [
            pytest.param("OAuth", {TICKET_ID_TK1, TICKET_ID_ST1}, id="simple"),
            pytest.param("oauth", {TICKET_ID_TK1, TICKET_ID_ST1}, id="case_insensitive"),
            pytest.param("Build.*API", {TICKET_ID_TK2}, id="regex"),
            pytest.param("Build", {TICKET_ID_EP1, TICKET_ID_TK2}, id="multiple"),
            pytest.param("Nonexistent", set(), id="no_match"),
        ],
    )
    def test_filter_by_title(self, executor, sample_tickets, pattern, expected):
        assert executor.filter_by_title_regex(sample_tickets, pattern) == expected

    def test_invalid_regex(self, executor, sample_tickets):
        with pytest.raises(re.error):
            executor.filter_by_title_regex(sample_tickets, "[invalid(")


class TestFilterByTagRegex:
    """Tests for filter_by_tag_regex method."""

    @pytest.mark.parametrize(
        "pattern,expected",
        [
            pytest.param("beta", {TICKET_ID_EP1, TICKET_ID_TK2}, id="single"),
            pytest.param("BETA", {TICKET_ID_EP1, TICKET_ID_TK2}, id="case_insensitive"),
            pytest.param("beta|preview", {TICKET_ID_EP1, TICKET_ID_TK2, TICKET_ID_ST1}, id="or_pattern"),
            pytest.param("backend", {TICKET_ID_EP1, TICKET_ID_TK1, TICKET_ID_TK2}, id="multiple"),
            pytest.param("nonexistent", set(), id="no_match"),
            pytest.param("api", {TICKET_ID_TK1, TICKET_ID_TK2}, id="skip_no_tags"),
        ],
    )
    def test_filter_by_tag(self, executor, sample_tickets, pattern, expected):
        assert executor.filter_by_tag_regex(sample_tickets, pattern) == expected

    def test_invalid_regex(self, executor, sample_tickets):
        with pytest.raises(re.error):
            executor.filter_by_tag_regex(sample_tickets, "[invalid(")


class TestExecute:
    """Tests for execute method with AND logic."""

    @pytest.mark.parametrize(
        "terms,expected",
        [
            pytest.param(["type=bee"], {TICKET_ID_EP1, TICKET_ID_EP2}, id="single_type"),
            pytest.param([f"id={TICKET_ID_TK1}"], {TICKET_ID_TK1}, id="single_id"),
            pytest.param(["title~OAuth"], {TICKET_ID_TK1, TICKET_ID_ST1}, id="single_title"),
            pytest.param(["tag~beta"], {TICKET_ID_EP1, TICKET_ID_TK2}, id="single_tag"),
            pytest.param(["status=open"], {TICKET_ID_EP1, TICKET_ID_TK2, TICKET_ID_EP2}, id="single_status"),
            pytest.param([f"parent={TICKET_ID_EP1}"], {TICKET_ID_TK1, TICKET_ID_TK2}, id="single_parent"),
            pytest.param(["type=bee", "status=open"], {TICKET_ID_EP1, TICKET_ID_EP2}, id="type_and_status"),
            pytest.param(["type=t1", "tag~beta"], {TICKET_ID_TK2}, id="and_two"),
            pytest.param(["type=t1", f"parent={TICKET_ID_EP1}"], {TICKET_ID_TK1, TICKET_ID_TK2}, id="parent_with_type"),
            pytest.param(["type=t1", f"parent={TICKET_ID_EP1}", "tag~beta"], {TICKET_ID_TK2}, id="parent_multi"),
            pytest.param(["type=t1", "tag~backend", "title~API"], {TICKET_ID_TK2}, id="and_three"),
            pytest.param(["type=bee", "tag~testing"], set(), id="and_no_common"),
            pytest.param(["type=nonexistent", "tag~beta"], set(), id="short_circuit"),
            pytest.param([f"parent={TICKET_ID_XXX}", "tag~beta"], set(), id="parent_short_circuit"),
            pytest.param(["type=bee", "tag~backend"], {TICKET_ID_EP1}, id="complex_and"),
            pytest.param(["guid=ep1aaaaaaaaaaaaaaaaaaaaaaaaaaaaa"], {TICKET_ID_EP1}, id="single_guid"),
            pytest.param(["guid=nonexistent_guid_val"], set(), id="guid_no_match"),
            pytest.param(["guid=ep1aaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "type=bee"], {TICKET_ID_EP1}, id="guid_and_type"),
            pytest.param(["guid=ep1aaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "type=t1"], set(), id="guid_type_mismatch"),
            pytest.param(["hive=backend"], {TICKET_ID_EP1, TICKET_ID_TK1, TICKET_ID_TK2, TICKET_ID_ST1}, id="single_hive"),
            pytest.param(["hive=backend", "type=bee"], {TICKET_ID_EP1}, id="hive_and_type"),
            pytest.param(["hive~back.*"], {TICKET_ID_EP1, TICKET_ID_TK1, TICKET_ID_TK2, TICKET_ID_ST1}, id="hive_regex"),
            pytest.param(["hive~backend|frontend", "type=bee"], {TICKET_ID_EP1, TICKET_ID_EP2}, id="hive_regex_and_type"),
        ],
    )
    def test_execute_search(self, executor, sample_tickets, terms, expected):
        """Test execute with various search term combinations."""
        assert executor.execute(sample_tickets, terms) == expected

    def test_empty_search_terms(self, executor, sample_tickets):
        """No filters = all tickets."""
        assert executor.execute(sample_tickets, []) == set(sample_tickets.keys())

    @pytest.mark.parametrize(
        "terms,match",
        [
            pytest.param(["invalid_term"], "Invalid search term format", id="invalid_format"),
            pytest.param(["unknown=value"], "Unknown exact match term", id="unknown_exact"),
            pytest.param(["unknown~pattern"], "Unknown regex term", id="unknown_regex"),
        ],
    )
    def test_invalid_terms_raise_error(self, executor, sample_tickets, terms, match):
        with pytest.raises(ValueError, match=match):
            executor.execute(sample_tickets, terms)

    def test_invalid_regex_in_execute(self, executor, sample_tickets):
        with pytest.raises(re.error):
            executor.execute(sample_tickets, ["title~[invalid("])


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.parametrize(
        "tickets,method,args,expected",
        [
            pytest.param(
                {"b.bad": {"id": "b.bad", "title": "Missing type"}},
                "filter_by_type", ("bee",), set(), id="missing_type",
            ),
            pytest.param(
                {"b.bad": {"id": "b.bad", "issue_type": "t1"}},
                "filter_by_title_regex", ("test",), set(), id="missing_title",
            ),
            pytest.param(
                {"b.emp": {"id": "b.emp", "issue_type": "t1", "tags": []}},
                "filter_by_tag_regex", ("test",), set(), id="empty_tags",
            ),
        ],
    )
    def test_missing_fields(self, executor, tickets, method, args, expected):
        """Test graceful handling of tickets with missing fields."""
        assert getattr(executor, method)(tickets, *args) == expected

    def test_regex_special_characters(self, executor, sample_tickets):
        result = executor.filter_by_title_regex(sample_tickets, r"Build\s+User")
        assert result == {TICKET_ID_TK2}

    def test_negation_regex(self, executor, sample_tickets):
        result = executor.filter_by_title_regex(sample_tickets, r"^(?!.*OAuth).*")
        assert TICKET_ID_TK1 not in result
        assert TICKET_ID_EP1 in result
