"""Unit tests for graph traversal query execution."""

import logging

import pytest

from src.graph_executor import GraphExecutor
from tests.test_constants import (
    TICKET_ID_EP1,
    TICKET_ID_EP2,
    TICKET_ID_INDEPENDENT,
    TICKET_ID_ISOLATED,
    TICKET_ID_LEAF,
    TICKET_ID_LONELY,
    TICKET_ID_ORPHAN,
    TICKET_ID_ROOT,
    TICKET_ID_ST1,
    TICKET_ID_ST2,
    TICKET_ID_ST3,
    TICKET_ID_TERMINAL,
    TICKET_ID_TK1,
    TICKET_ID_TK2,
    TICKET_ID_TK3,
    TICKET_ID_XXX,
)


@pytest.fixture
def sample_tickets():
    """Sample ticket data with relationships for testing."""
    return {
        TICKET_ID_EP1: {
            "id": TICKET_ID_EP1, "issue_type": "bee", "title": "Build Auth",
            "parent": None, "children": [TICKET_ID_TK1, TICKET_ID_TK2],
            "up_dependencies": [], "down_dependencies": [TICKET_ID_EP2],
        },
        TICKET_ID_TK1: {
            "id": TICKET_ID_TK1, "issue_type": "t1", "title": "Implement OAuth",
            "parent": TICKET_ID_EP1, "children": [TICKET_ID_ST1, TICKET_ID_ST2],
            "up_dependencies": [], "down_dependencies": [TICKET_ID_TK2],
        },
        TICKET_ID_TK2: {
            "id": TICKET_ID_TK2, "issue_type": "t1", "title": "Build Profile API",
            "parent": TICKET_ID_EP1, "children": [TICKET_ID_ST3],
            "up_dependencies": [TICKET_ID_TK1], "down_dependencies": [],
        },
        TICKET_ID_ST1: {
            "id": TICKET_ID_ST1, "issue_type": "t2", "title": "Write OAuth tests",
            "parent": TICKET_ID_TK1, "children": [], "up_dependencies": [], "down_dependencies": [],
        },
        TICKET_ID_ST2: {
            "id": TICKET_ID_ST2, "issue_type": "t2", "title": "Document OAuth flow",
            "parent": TICKET_ID_TK1, "children": [], "up_dependencies": [TICKET_ID_ST1], "down_dependencies": [],
        },
        TICKET_ID_ST3: {
            "id": TICKET_ID_ST3, "issue_type": "t2", "title": "Write API tests",
            "parent": TICKET_ID_TK2, "children": [], "up_dependencies": [], "down_dependencies": [],
        },
        TICKET_ID_EP2: {
            "id": TICKET_ID_EP2, "issue_type": "bee", "title": "Frontend Dashboard",
            "parent": None, "children": [TICKET_ID_TK3],
            "up_dependencies": [TICKET_ID_EP1], "down_dependencies": [],
        },
        TICKET_ID_TK3: {
            "id": TICKET_ID_TK3, "issue_type": "t1", "title": "Build Dashboard UI",
            "parent": TICKET_ID_EP2, "children": [], "up_dependencies": [], "down_dependencies": [],
        },
    }


@pytest.fixture
def executor():
    """Create GraphExecutor instance."""
    return GraphExecutor()


class TestTraverseParent:
    """Tests for parent relationship traversal."""

    def test_single_ticket_with_parent(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_TK1}, "parent") == {TICKET_ID_EP1}

    def test_multiple_tickets_different_parents(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_ST1, TICKET_ID_ST3}, "parent") == {TICKET_ID_TK1, TICKET_ID_TK2}

    def test_ticket_without_parent(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_EP1}, "parent") == set()

    @pytest.mark.parametrize("term", ["parent", "children", "up_dependencies", "down_dependencies"])
    def test_empty_input_set(self, executor, sample_tickets, term):
        assert executor.traverse(sample_tickets, set(), term) == set()

    @pytest.mark.parametrize("term", ["parent", "children", "up_dependencies", "down_dependencies"])
    def test_empty_tickets_dict(self, executor, term):
        assert executor.traverse({}, {TICKET_ID_TK1}, term) == set()


class TestTraverseChildren:
    """Tests for children relationship traversal."""

    def test_single_ticket_with_children(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_EP1}, "children") == {TICKET_ID_TK1, TICKET_ID_TK2}

    def test_multiple_tickets_with_children(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_TK1, TICKET_ID_TK2}, "children") == {TICKET_ID_ST1, TICKET_ID_ST2, TICKET_ID_ST3}

    def test_ticket_without_children(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_ST1}, "children") == set()


class TestTraverseDependencies:
    """Tests for dependency traversal."""

    def test_up_dependencies(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_TK2}, "up_dependencies") == {TICKET_ID_TK1}

    def test_multiple_up_dependencies(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_TK2, TICKET_ID_EP2}, "up_dependencies") == {TICKET_ID_TK1, TICKET_ID_EP1}

    def test_no_up_dependencies(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_EP1}, "up_dependencies") == set()

    def test_down_dependencies(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_TK1}, "down_dependencies") == {TICKET_ID_TK2}

    def test_no_down_dependencies(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_TK2}, "down_dependencies") == set()


class TestInvalidGraphTerms:
    """Tests for invalid graph term handling."""

    @pytest.mark.parametrize("term", ["invalid_term", "", "childs"])
    def test_invalid_graph_term(self, executor, sample_tickets, caplog, term):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {TICKET_ID_EP1}, term)
        assert result == set()
        assert f"Invalid graph term '{term}'" in caplog.text


class TestMissingTickets:
    """Tests for handling missing tickets in input set."""

    def test_nonexistent_ticket_id(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {TICKET_ID_XXX}, "parent")
        assert result == set()

    def test_mixed_existing_and_nonexistent(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {TICKET_ID_TK1, TICKET_ID_XXX}, "parent")
        assert result == {TICKET_ID_EP1}


class TestMissingRelationshipFields:
    """Tests for handling missing relationship fields in ticket data."""

    @pytest.mark.parametrize(
        "ticket_id,term",
        [
            pytest.param(TICKET_ID_ORPHAN, "parent", id="missing_parent"),
            pytest.param(TICKET_ID_LONELY, "children", id="missing_children"),
            pytest.param(TICKET_ID_INDEPENDENT, "up_dependencies", id="missing_up_deps"),
            pytest.param(TICKET_ID_ISOLATED, "down_dependencies", id="missing_down_deps"),
        ],
    )
    def test_missing_field_returns_empty(self, executor, ticket_id, term):
        tickets = {ticket_id: {"id": ticket_id, "issue_type": "t1", "title": "Test"}}
        assert executor.traverse(tickets, {ticket_id}, term) == set()

    @pytest.mark.parametrize(
        "ticket_id,term,field",
        [
            pytest.param(TICKET_ID_LEAF, "children", "children", id="empty_children"),
            pytest.param(TICKET_ID_ROOT, "up_dependencies", "up_dependencies", id="empty_up_deps"),
            pytest.param(TICKET_ID_TERMINAL, "down_dependencies", "down_dependencies", id="empty_down_deps"),
        ],
    )
    def test_empty_list_returns_empty(self, executor, ticket_id, term, field):
        tickets = {ticket_id: {"id": ticket_id, "issue_type": "t1", "title": "Test", field: []}}
        assert executor.traverse(tickets, {ticket_id}, term) == set()


class TestNoneAndEmptyInputs:
    """Tests for None and empty values in input set."""

    def test_none_in_input_set(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {None, TICKET_ID_TK1}, "parent")
        assert result == {TICKET_ID_EP1}

    def test_only_none_in_input_set(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {None}, "parent")
        assert result == set()


class TestComplexTraversals:
    """Tests for complex multi-hop traversal scenarios."""

    def test_parent_chain(self, executor, sample_tickets):
        result1 = executor.traverse(sample_tickets, {TICKET_ID_ST1}, "parent")
        assert result1 == {TICKET_ID_TK1}
        result2 = executor.traverse(sample_tickets, result1, "parent")
        assert result2 == {TICKET_ID_EP1}

    def test_children_expansion(self, executor, sample_tickets):
        result1 = executor.traverse(sample_tickets, {TICKET_ID_EP1}, "children")
        assert result1 == {TICKET_ID_TK1, TICKET_ID_TK2}
        result2 = executor.traverse(sample_tickets, result1, "children")
        assert result2 == {TICKET_ID_ST1, TICKET_ID_ST2, TICKET_ID_ST3}

    def test_all_graph_terms_on_same_ticket(self, executor, sample_tickets):
        assert executor.traverse(sample_tickets, {TICKET_ID_TK1}, "parent") == {TICKET_ID_EP1}
        assert executor.traverse(sample_tickets, {TICKET_ID_TK1}, "children") == {TICKET_ID_ST1, TICKET_ID_ST2}
        assert executor.traverse(sample_tickets, {TICKET_ID_TK1}, "up_dependencies") == set()
        assert executor.traverse(sample_tickets, {TICKET_ID_TK1}, "down_dependencies") == {TICKET_ID_TK2}

    def test_ticket_with_all_empty_relationships(self, executor):
        tickets = {
            TICKET_ID_ISOLATED: {"id": TICKET_ID_ISOLATED, "parent": None, "children": [], "up_dependencies": [], "down_dependencies": []},
        }
        for term in ["parent", "children", "up_dependencies", "down_dependencies"]:
            assert executor.traverse(tickets, {TICKET_ID_ISOLATED}, term) == set()
