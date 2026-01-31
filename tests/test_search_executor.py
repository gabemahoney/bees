"""Unit tests for SearchExecutor class."""

import pytest
import re
from src.search_executor import SearchExecutor


@pytest.fixture
def sample_tickets():
    """Sample ticket data for testing."""
    return {
        'bees-ep1': {
            'id': 'bees-ep1',
            'issue_type': 'epic',
            'title': 'Build Authentication System',
            'labels': ['backend', 'security', 'beta'],
        },
        'bees-tk1': {
            'id': 'bees-tk1',
            'issue_type': 'task',
            'title': 'Implement OAuth Login',
            'labels': ['backend', 'api'],
        },
        'bees-tk2': {
            'id': 'bees-tk2',
            'issue_type': 'task',
            'title': 'Build User Profile API',
            'labels': ['backend', 'api', 'beta'],
        },
        'bees-st1': {
            'id': 'bees-st1',
            'issue_type': 'subtask',
            'title': 'Write OAuth tests',
            'labels': ['testing', 'preview'],
        },
        'bees-ep2': {
            'id': 'bees-ep2',
            'issue_type': 'epic',
            'title': 'Frontend Dashboard',
            'labels': ['frontend', 'ui'],
        },
        'bees-nolabels': {
            'id': 'bees-nolabels',
            'issue_type': 'task',
            'title': 'Task without labels',
        },
    }


@pytest.fixture
def executor():
    """Create SearchExecutor instance."""
    return SearchExecutor()


class TestFilterByType:
    """Tests for filter_by_type method."""

    def test_filter_epic(self, executor, sample_tickets):
        result = executor.filter_by_type(sample_tickets, 'epic')
        assert result == {'bees-ep1', 'bees-ep2'}

    def test_filter_task(self, executor, sample_tickets):
        result = executor.filter_by_type(sample_tickets, 'task')
        assert result == {'bees-tk1', 'bees-tk2', 'bees-nolabels'}

    def test_filter_subtask(self, executor, sample_tickets):
        result = executor.filter_by_type(sample_tickets, 'subtask')
        assert result == {'bees-st1'}

    def test_filter_nonexistent_type(self, executor, sample_tickets):
        result = executor.filter_by_type(sample_tickets, 'nonexistent')
        assert result == set()

    def test_filter_empty_tickets(self, executor):
        result = executor.filter_by_type({}, 'epic')
        assert result == set()


class TestFilterById:
    """Tests for filter_by_id method."""

    def test_filter_existing_id(self, executor, sample_tickets):
        result = executor.filter_by_id(sample_tickets, 'bees-tk1')
        assert result == {'bees-tk1'}

    def test_filter_nonexistent_id(self, executor, sample_tickets):
        result = executor.filter_by_id(sample_tickets, 'bees-xxx')
        assert result == set()

    def test_filter_empty_tickets(self, executor):
        result = executor.filter_by_id({}, 'bees-ep1')
        assert result == set()


class TestFilterByTitleRegex:
    """Tests for filter_by_title_regex method."""

    def test_simple_match(self, executor, sample_tickets):
        result = executor.filter_by_title_regex(sample_tickets, 'OAuth')
        assert result == {'bees-tk1', 'bees-st1'}

    def test_case_insensitive(self, executor, sample_tickets):
        result = executor.filter_by_title_regex(sample_tickets, 'oauth')
        assert result == {'bees-tk1', 'bees-st1'}

    def test_regex_pattern(self, executor, sample_tickets):
        result = executor.filter_by_title_regex(sample_tickets, 'Build.*API')
        assert result == {'bees-tk2'}

    def test_multiple_matches(self, executor, sample_tickets):
        result = executor.filter_by_title_regex(sample_tickets, 'Build')
        assert result == {'bees-ep1', 'bees-tk2'}

    def test_no_matches(self, executor, sample_tickets):
        result = executor.filter_by_title_regex(sample_tickets, 'Nonexistent')
        assert result == set()

    def test_invalid_regex(self, executor, sample_tickets):
        with pytest.raises(re.error):
            executor.filter_by_title_regex(sample_tickets, '[invalid(')

    def test_empty_tickets(self, executor):
        result = executor.filter_by_title_regex({}, 'test')
        assert result == set()


class TestFilterByLabelRegex:
    """Tests for filter_by_label_regex method."""

    def test_single_label_match(self, executor, sample_tickets):
        result = executor.filter_by_label_regex(sample_tickets, 'beta')
        assert result == {'bees-ep1', 'bees-tk2'}

    def test_case_insensitive(self, executor, sample_tickets):
        result = executor.filter_by_label_regex(sample_tickets, 'BETA')
        assert result == {'bees-ep1', 'bees-tk2'}

    def test_or_pattern(self, executor, sample_tickets):
        result = executor.filter_by_label_regex(sample_tickets, 'beta|preview')
        assert result == {'bees-ep1', 'bees-tk2', 'bees-st1'}

    def test_multiple_label_match(self, executor, sample_tickets):
        result = executor.filter_by_label_regex(sample_tickets, 'backend')
        assert result == {'bees-ep1', 'bees-tk1', 'bees-tk2'}

    def test_no_matches(self, executor, sample_tickets):
        result = executor.filter_by_label_regex(sample_tickets, 'nonexistent')
        assert result == set()

    def test_ticket_without_labels(self, executor, sample_tickets):
        result = executor.filter_by_label_regex(sample_tickets, 'api')
        # bees-nolabels has no labels field, should not match
        assert result == {'bees-tk1', 'bees-tk2'}

    def test_invalid_regex(self, executor, sample_tickets):
        with pytest.raises(re.error):
            executor.filter_by_label_regex(sample_tickets, '[invalid(')

    def test_empty_tickets(self, executor):
        result = executor.filter_by_label_regex({}, 'test')
        assert result == set()


class TestExecute:
    """Tests for execute method with AND logic."""

    def test_single_type_filter(self, executor, sample_tickets):
        result = executor.execute(sample_tickets, ['type=epic'])
        assert result == {'bees-ep1', 'bees-ep2'}

    def test_single_id_filter(self, executor, sample_tickets):
        result = executor.execute(sample_tickets, ['id=bees-tk1'])
        assert result == {'bees-tk1'}

    def test_single_title_filter(self, executor, sample_tickets):
        result = executor.execute(sample_tickets, ['title~OAuth'])
        assert result == {'bees-tk1', 'bees-st1'}

    def test_single_label_filter(self, executor, sample_tickets):
        result = executor.execute(sample_tickets, ['label~beta'])
        assert result == {'bees-ep1', 'bees-tk2'}

    def test_and_logic_two_filters(self, executor, sample_tickets):
        # Type=task AND label~beta
        result = executor.execute(sample_tickets, ['type=task', 'label~beta'])
        assert result == {'bees-tk2'}

    def test_and_logic_three_filters(self, executor, sample_tickets):
        # Type=task AND label~backend AND title~API
        result = executor.execute(sample_tickets, ['type=task', 'label~backend', 'title~API'])
        # Only bees-tk2 has all three: task type, backend label, and "API" in title
        assert result == {'bees-tk2'}

    def test_and_logic_no_common_matches(self, executor, sample_tickets):
        # Type=epic AND label~testing (no epics have testing label)
        result = executor.execute(sample_tickets, ['type=epic', 'label~testing'])
        assert result == set()

    def test_short_circuit_empty_result(self, executor, sample_tickets):
        # First filter returns empty, should short-circuit
        result = executor.execute(sample_tickets, ['type=nonexistent', 'label~beta'])
        assert result == set()

    def test_empty_search_terms(self, executor, sample_tickets):
        # No filters = all tickets
        result = executor.execute(sample_tickets, [])
        assert result == set(sample_tickets.keys())

    def test_invalid_term_format(self, executor, sample_tickets):
        with pytest.raises(ValueError, match="Invalid search term format"):
            executor.execute(sample_tickets, ['invalid_term'])

    def test_unknown_exact_match_term(self, executor, sample_tickets):
        with pytest.raises(ValueError, match="Unknown exact match term"):
            executor.execute(sample_tickets, ['unknown=value'])

    def test_unknown_regex_term(self, executor, sample_tickets):
        with pytest.raises(ValueError, match="Unknown regex term"):
            executor.execute(sample_tickets, ['unknown~pattern'])

    def test_invalid_regex_in_execute(self, executor, sample_tickets):
        with pytest.raises(re.error):
            executor.execute(sample_tickets, ['title~[invalid('])

    def test_complex_and_logic(self, executor, sample_tickets):
        # Epic with backend label
        result = executor.execute(sample_tickets, ['type=epic', 'label~backend'])
        assert result == {'bees-ep1'}

    def test_empty_tickets(self, executor):
        result = executor.execute({}, ['type=epic'])
        assert result == set()


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_ticket_missing_issue_type(self, executor):
        tickets = {
            'bees-bad': {
                'id': 'bees-bad',
                'title': 'Missing type',
            }
        }
        result = executor.filter_by_type(tickets, 'epic')
        assert result == set()

    def test_ticket_missing_title(self, executor):
        tickets = {
            'bees-bad': {
                'id': 'bees-bad',
                'issue_type': 'task',
            }
        }
        result = executor.filter_by_title_regex(tickets, 'test')
        assert result == set()

    def test_ticket_with_empty_labels_list(self, executor):
        tickets = {
            'bees-empty': {
                'id': 'bees-empty',
                'issue_type': 'task',
                'labels': [],
            }
        }
        result = executor.filter_by_label_regex(tickets, 'test')
        assert result == set()

    def test_regex_special_characters(self, executor, sample_tickets):
        # Test regex with special chars
        result = executor.filter_by_title_regex(sample_tickets, r'Build\s+User')
        assert result == {'bees-tk2'}

    def test_negation_regex(self, executor, sample_tickets):
        # Negation: NOT containing "OAuth"
        result = executor.filter_by_title_regex(sample_tickets, r'^(?!.*OAuth).*')
        # Should match everything except tickets with OAuth in title
        assert 'bees-tk1' not in result
        assert 'bees-st1' not in result
        assert 'bees-ep1' in result
