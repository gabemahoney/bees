"""Unit tests for GraphExecutor class."""

import pytest
import logging
from src.graph_executor import GraphExecutor


@pytest.fixture
def sample_tickets():
    """Sample ticket data with relationships for testing."""
    return {
        'default.bees-ep1': {
            'id': 'default.bees-ep1',
            'issue_type': 'epic',
            'title': 'Build Authentication System',
            'parent': None,
            'children': ['default.bees-tk1', 'default.bees-tk2'],
            'up_dependencies': [],
            'down_dependencies': ['default.bees-ep2'],
        },
        'default.bees-tk1': {
            'id': 'default.bees-tk1',
            'issue_type': 'task',
            'title': 'Implement OAuth Login',
            'parent': 'default.bees-ep1',
            'children': ['default.bees-st1', 'default.bees-st2'],
            'up_dependencies': [],
            'down_dependencies': ['default.bees-tk2'],
        },
        'default.bees-tk2': {
            'id': 'default.bees-tk2',
            'issue_type': 'task',
            'title': 'Build User Profile API',
            'parent': 'default.bees-ep1',
            'children': ['default.bees-st3'],
            'up_dependencies': ['default.bees-tk1'],
            'down_dependencies': [],
        },
        'default.bees-st1': {
            'id': 'default.bees-st1',
            'issue_type': 'subtask',
            'title': 'Write OAuth tests',
            'parent': 'default.bees-tk1',
            'children': [],
            'up_dependencies': [],
            'down_dependencies': [],
        },
        'default.bees-st2': {
            'id': 'default.bees-st2',
            'issue_type': 'subtask',
            'title': 'Document OAuth flow',
            'parent': 'default.bees-tk1',
            'children': [],
            'up_dependencies': ['default.bees-st1'],
            'down_dependencies': [],
        },
        'default.bees-st3': {
            'id': 'default.bees-st3',
            'issue_type': 'subtask',
            'title': 'Write API tests',
            'parent': 'default.bees-tk2',
            'children': [],
            'up_dependencies': [],
            'down_dependencies': [],
        },
        'default.bees-ep2': {
            'id': 'default.bees-ep2',
            'issue_type': 'epic',
            'title': 'Frontend Dashboard',
            'parent': None,
            'children': ['default.bees-tk3'],
            'up_dependencies': ['default.bees-ep1'],
            'down_dependencies': [],
        },
        'default.bees-tk3': {
            'id': 'default.bees-tk3',
            'issue_type': 'task',
            'title': 'Build Dashboard UI',
            'parent': 'default.bees-ep2',
            'children': [],
            'up_dependencies': [],
            'down_dependencies': [],
        },
    }


@pytest.fixture
def executor():
    """Create GraphExecutor instance."""
    return GraphExecutor()


class TestTraverseParent:
    """Tests for parent relationship traversal."""

    def test_single_ticket_with_parent(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-tk1'}, 'parent')
        assert result == {'default.bees-ep1'}

    def test_multiple_tickets_with_parents(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-tk1', 'default.bees-tk2'}, 'parent')
        # Both tasks have same parent
        assert result == {'default.bees-ep1'}

    def test_multiple_tickets_different_parents(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-st1', 'default.bees-st3'}, 'parent')
        assert result == {'default.bees-tk1', 'default.bees-tk2'}

    def test_ticket_without_parent(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-ep1'}, 'parent')
        assert result == set()

    def test_empty_input_set(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, set(), 'parent')
        assert result == set()


class TestTraverseChildren:
    """Tests for children relationship traversal."""

    def test_single_ticket_with_children(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-ep1'}, 'children')
        assert result == {'default.bees-tk1', 'default.bees-tk2'}

    def test_multiple_tickets_with_children(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-tk1', 'default.bees-tk2'}, 'children')
        assert result == {'default.bees-st1', 'default.bees-st2', 'default.bees-st3'}

    def test_ticket_without_children(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-st1'}, 'children')
        assert result == set()

    def test_mixed_tickets_some_with_children(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-st1', 'default.bees-tk1'}, 'children')
        # st1 has no children, tk1 has two children
        assert result == {'default.bees-st1', 'default.bees-st2'}

    def test_empty_input_set(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, set(), 'children')
        assert result == set()


class TestTraverseUpDependencies:
    """Tests for up_dependencies (blockers) traversal."""

    def test_single_ticket_with_up_dependencies(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-tk2'}, 'up_dependencies')
        assert result == {'default.bees-tk1'}

    def test_multiple_tickets_with_up_dependencies(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-tk2', 'default.bees-ep2'}, 'up_dependencies')
        assert result == {'default.bees-tk1', 'default.bees-ep1'}

    def test_ticket_without_up_dependencies(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-ep1'}, 'up_dependencies')
        assert result == set()

    def test_subtask_with_up_dependency(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-st2'}, 'up_dependencies')
        assert result == {'default.bees-st1'}

    def test_empty_input_set(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, set(), 'up_dependencies')
        assert result == set()


class TestTraverseDownDependencies:
    """Tests for down_dependencies (blocked by this) traversal."""

    def test_single_ticket_with_down_dependencies(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-tk1'}, 'down_dependencies')
        assert result == {'default.bees-tk2'}

    def test_multiple_tickets_with_down_dependencies(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-ep1', 'default.bees-st1'}, 'down_dependencies')
        # ep1 blocks ep2, st1 blocks nothing (st2 depends on st1)
        assert result == {'default.bees-ep2'}

    def test_ticket_without_down_dependencies(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, {'default.bees-tk2'}, 'down_dependencies')
        assert result == set()

    def test_empty_input_set(self, executor, sample_tickets):
        result = executor.traverse(sample_tickets, set(), 'down_dependencies')
        assert result == set()


class TestInvalidGraphTerms:
    """Tests for invalid graph term handling."""

    def test_invalid_graph_term(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {'default.bees-ep1'}, 'invalid_term')
        assert result == set()
        assert "Invalid graph term 'invalid_term'" in caplog.text

    def test_empty_graph_term(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {'default.bees-ep1'}, '')
        assert result == set()
        assert "Invalid graph term ''" in caplog.text

    def test_misspelled_graph_term(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {'default.bees-ep1'}, 'childs')
        assert result == set()
        assert "Invalid graph term 'childs'" in caplog.text


class TestMissingTickets:
    """Tests for handling missing tickets in input set."""

    def test_nonexistent_ticket_id(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {'default.bees-xxx'}, 'parent')
        assert result == set()
        assert "Ticket default.bees-xxx not found" in caplog.text

    def test_mixed_existing_and_nonexistent(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {'default.bees-tk1', 'default.bees-xxx'}, 'parent')
        # Should return parent of tk1, skip nonexistent
        assert result == {'default.bees-ep1'}
        assert "Ticket default.bees-xxx not found" in caplog.text

    def test_all_nonexistent_tickets(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {'default.bees-xxx', 'default.bees-yyy'}, 'parent')
        assert result == set()
        assert "default.bees-xxx" in caplog.text
        assert "default.bees-yyy" in caplog.text


class TestMissingRelationshipFields:
    """Tests for handling missing relationship fields in ticket data."""

    def test_ticket_missing_parent_field(self, executor):
        tickets = {
            'default.bees-orphan': {
                'id': 'default.bees-orphan',
                'issue_type': 'task',
                'title': 'Orphaned task',
            }
        }
        result = executor.traverse(tickets, {'default.bees-orphan'}, 'parent')
        assert result == set()

    def test_ticket_missing_children_field(self, executor):
        tickets = {
            'default.bees-lonely': {
                'id': 'default.bees-lonely',
                'issue_type': 'epic',
                'title': 'Epic with no children field',
            }
        }
        result = executor.traverse(tickets, {'default.bees-lonely'}, 'children')
        assert result == set()

    def test_ticket_missing_up_dependencies_field(self, executor):
        tickets = {
            'default.bees-independent': {
                'id': 'default.bees-independent',
                'issue_type': 'task',
                'title': 'Independent task',
            }
        }
        result = executor.traverse(tickets, {'default.bees-independent'}, 'up_dependencies')
        assert result == set()

    def test_ticket_missing_down_dependencies_field(self, executor):
        tickets = {
            'default.bees-isolated': {
                'id': 'default.bees-isolated',
                'issue_type': 'task',
                'title': 'Isolated task',
            }
        }
        result = executor.traverse(tickets, {'default.bees-isolated'}, 'down_dependencies')
        assert result == set()


class TestEmptyRelationshipLists:
    """Tests for handling empty relationship lists."""

    def test_empty_children_list(self, executor):
        tickets = {
            'default.bees-leaf': {
                'id': 'default.bees-leaf',
                'issue_type': 'task',
                'title': 'Leaf task',
                'children': [],
            }
        }
        result = executor.traverse(tickets, {'default.bees-leaf'}, 'children')
        assert result == set()

    def test_empty_up_dependencies_list(self, executor):
        tickets = {
            'default.bees-root': {
                'id': 'default.bees-root',
                'issue_type': 'epic',
                'title': 'Root epic',
                'up_dependencies': [],
            }
        }
        result = executor.traverse(tickets, {'default.bees-root'}, 'up_dependencies')
        assert result == set()

    def test_empty_down_dependencies_list(self, executor):
        tickets = {
            'default.bees-terminal': {
                'id': 'default.bees-terminal',
                'issue_type': 'task',
                'title': 'Terminal task',
                'down_dependencies': [],
            }
        }
        result = executor.traverse(tickets, {'default.bees-terminal'}, 'down_dependencies')
        assert result == set()


class TestNoneAndEmptyInputs:
    """Tests for None and empty values in input set."""

    def test_none_in_input_set(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {None, 'default.bees-tk1'}, 'parent')
        # Should skip None, return parent of tk1
        assert result == {'default.bees-ep1'}
        assert "None or empty ticket ID" in caplog.text

    def test_empty_string_in_input_set(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {'', 'default.bees-tk1'}, 'parent')
        assert result == {'default.bees-ep1'}
        assert "None or empty ticket ID" in caplog.text

    def test_only_none_in_input_set(self, executor, sample_tickets, caplog):
        with caplog.at_level(logging.WARNING):
            result = executor.traverse(sample_tickets, {None}, 'parent')
        assert result == set()
        assert "None or empty ticket ID" in caplog.text


class TestEmptyTicketsDict:
    """Tests for empty tickets dictionary."""

    def test_empty_tickets_parent(self, executor):
        result = executor.traverse({}, {'default.bees-tk1'}, 'parent')
        assert result == set()

    def test_empty_tickets_children(self, executor):
        result = executor.traverse({}, {'default.bees-ep1'}, 'children')
        assert result == set()

    def test_empty_tickets_up_dependencies(self, executor):
        result = executor.traverse({}, {'default.bees-tk1'}, 'up_dependencies')
        assert result == set()

    def test_empty_tickets_down_dependencies(self, executor):
        result = executor.traverse({}, {'default.bees-tk1'}, 'down_dependencies')
        assert result == set()


class TestComplexTraversals:
    """Tests for complex multi-hop traversal scenarios."""

    def test_parent_chain(self, executor, sample_tickets):
        # Get parent of subtask, then parent of that task
        result1 = executor.traverse(sample_tickets, {'default.bees-st1'}, 'parent')
        assert result1 == {'default.bees-tk1'}
        result2 = executor.traverse(sample_tickets, result1, 'parent')
        assert result2 == {'default.bees-ep1'}

    def test_children_expansion(self, executor, sample_tickets):
        # Get children of epic, then children of those tasks
        result1 = executor.traverse(sample_tickets, {'default.bees-ep1'}, 'children')
        assert result1 == {'default.bees-tk1', 'default.bees-tk2'}
        result2 = executor.traverse(sample_tickets, result1, 'children')
        assert result2 == {'default.bees-st1', 'default.bees-st2', 'default.bees-st3'}

    def test_dependency_chain(self, executor, sample_tickets):
        # Get what blocks tk2, then what blocks that
        result1 = executor.traverse(sample_tickets, {'default.bees-tk2'}, 'up_dependencies')
        assert result1 == {'default.bees-tk1'}
        result2 = executor.traverse(sample_tickets, result1, 'up_dependencies')
        # tk1 has no blockers
        assert result2 == set()

    def test_reverse_dependency_chain(self, executor, sample_tickets):
        # Get what st1 blocks, then what that blocks
        result1 = executor.traverse(sample_tickets, {'default.bees-st1'}, 'down_dependencies')
        # st1 doesn't block anything (st2 depends on st1, but it's not in down_dependencies)
        assert result1 == set()


class TestCoverageEdgeCases:
    """Additional tests for 100% code coverage."""

    def test_all_graph_terms_on_same_ticket(self, executor, sample_tickets):
        # Test all four graph terms on tk1
        parent = executor.traverse(sample_tickets, {'default.bees-tk1'}, 'parent')
        children = executor.traverse(sample_tickets, {'default.bees-tk1'}, 'children')
        up_deps = executor.traverse(sample_tickets, {'default.bees-tk1'}, 'up_dependencies')
        down_deps = executor.traverse(sample_tickets, {'default.bees-tk1'}, 'down_dependencies')

        assert parent == {'default.bees-ep1'}
        assert children == {'default.bees-st1', 'default.bees-st2'}
        assert up_deps == set()
        assert down_deps == {'default.bees-tk2'}

    def test_ticket_with_all_empty_relationships(self, executor):
        tickets = {
            'default.bees-isolated': {
                'id': 'default.bees-isolated',
                'parent': None,
                'children': [],
                'up_dependencies': [],
                'down_dependencies': [],
            }
        }
        assert executor.traverse(tickets, {'default.bees-isolated'}, 'parent') == set()
        assert executor.traverse(tickets, {'default.bees-isolated'}, 'children') == set()
        assert executor.traverse(tickets, {'default.bees-isolated'}, 'up_dependencies') == set()
        assert executor.traverse(tickets, {'default.bees-isolated'}, 'down_dependencies') == set()

    def test_multiple_tickets_all_with_same_relationships(self, executor):
        tickets = {
            'default.bees-tk1': {
                'id': 'default.bees-tk1',
                'parent': 'default.bees-ep1',
                'children': ['default.bees-st1'],
            },
            'default.bees-tk2': {
                'id': 'default.bees-tk2',
                'parent': 'default.bees-ep1',
                'children': ['default.bees-st1'],
            },
        }
        # Both tasks have same parent
        result = executor.traverse(tickets, {'default.bees-tk1', 'default.bees-tk2'}, 'parent')
        assert result == {'default.bees-ep1'}

        # Both tasks have same child (overlapping)
        result = executor.traverse(tickets, {'default.bees-tk1', 'default.bees-tk2'}, 'children')
        assert result == {'default.bees-st1'}
