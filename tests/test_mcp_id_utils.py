"""Unit tests for mcp_id_utils module."""

import pytest
from src.mcp_id_utils import parse_ticket_id, parse_hive_from_ticket_id


class TestParseTicketId:
    """Tests for parse_ticket_id() function."""

    def test_new_format_with_hive_prefix(self):
        """Should parse new format IDs with hive prefix."""
        assert parse_ticket_id('backend.bees-abc1') == ('backend', 'bees-abc1')
        assert parse_ticket_id('frontend.bees-xyz9') == ('frontend', 'bees-xyz9')
        assert parse_ticket_id('my_hive.bees-123') == ('my_hive', 'bees-123')

    def test_legacy_format_without_hive_prefix(self):
        """Should parse legacy format IDs without hive prefix."""
        assert parse_ticket_id('bees-abc1') == ('', 'bees-abc1')
        assert parse_ticket_id('bees-xyz9') == ('', 'bees-xyz9')

    def test_multiple_dots_splits_on_first(self):
        """Should split on first dot only."""
        assert parse_ticket_id('multi.dot.bees-xyz9') == ('multi', 'dot.bees-xyz9')
        assert parse_ticket_id('my.hive.name.bees-abc') == ('my', 'hive.name.bees-abc')

    def test_none_ticket_id_raises_error(self):
        """Should raise ValueError for None ticket_id."""
        with pytest.raises(ValueError, match="ticket_id cannot be None"):
            parse_ticket_id(None)

    def test_empty_string_raises_error(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            parse_ticket_id('')

    def test_whitespace_only_raises_error(self):
        """Should raise ValueError for whitespace-only string."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            parse_ticket_id('   ')
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            parse_ticket_id('\t')
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            parse_ticket_id('\n')

    def test_complex_hive_names(self):
        """Should handle complex but valid hive names."""
        assert parse_ticket_id('back_end.bees-abc') == ('back_end', 'bees-abc')
        assert parse_ticket_id('test_123.bees-xyz') == ('test_123', 'bees-xyz')
        assert parse_ticket_id('_private.bees-abc') == ('_private', 'bees-abc')


class TestParseHiveFromTicketId:
    """Tests for parse_hive_from_ticket_id() function."""

    def test_extract_hive_from_prefixed_id(self):
        """Should extract hive name from prefixed IDs."""
        assert parse_hive_from_ticket_id('backend.bees-abc1') == 'backend'
        assert parse_hive_from_ticket_id('frontend.bees-xyz9') == 'frontend'
        assert parse_hive_from_ticket_id('my_hive.bees-123') == 'my_hive'

    def test_unprefixed_id_returns_none(self):
        """Should return None for unprefixed/malformed IDs."""
        assert parse_hive_from_ticket_id('bees-abc1') is None
        assert parse_hive_from_ticket_id('bees-xyz9') is None

    def test_multiple_dots_returns_first_part(self):
        """Should return first part before first dot."""
        assert parse_hive_from_ticket_id('multi.dot.bees-xyz9') == 'multi'
        assert parse_hive_from_ticket_id('my.hive.name.bees-abc') == 'my'

    def test_complex_hive_names(self):
        """Should handle complex but valid hive names."""
        assert parse_hive_from_ticket_id('back_end.bees-abc') == 'back_end'
        assert parse_hive_from_ticket_id('test_123.bees-xyz') == 'test_123'
        assert parse_hive_from_ticket_id('_private.bees-abc') == '_private'

    def test_empty_hive_prefix(self):
        """Should handle edge case of empty hive prefix."""
        assert parse_hive_from_ticket_id('.bees-abc') == ''

    def test_no_error_handling(self):
        """Should not raise errors for any input (returns None for invalid)."""
        # These don't raise errors, just return None or extract prefix
        assert parse_hive_from_ticket_id('invalid-id') is None
        assert parse_hive_from_ticket_id('') is None
        assert parse_hive_from_ticket_id('just-a-dot.') == 'just-a-dot'


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_parse_ticket_id_with_dot_only(self):
        """Should handle ticket ID with just a dot."""
        assert parse_ticket_id('.') == ('', '')
        assert parse_ticket_id('.bees-abc') == ('', 'bees-abc')

    def test_parse_hive_with_trailing_dot(self):
        """Should handle ticket ID with trailing dot."""
        assert parse_hive_from_ticket_id('backend.') == 'backend'

    def test_consistency_between_functions(self):
        """parse_ticket_id and parse_hive_from_ticket_id should be consistent."""
        test_ids = [
            'backend.bees-abc1',
            'frontend.bees-xyz9',
            'bees-abc1',
            'multi.dot.bees-xyz9',
        ]

        for ticket_id in test_ids:
            hive_name, _ = parse_ticket_id(ticket_id)
            extracted_hive = parse_hive_from_ticket_id(ticket_id)

            # If hive_name is empty, extracted_hive should be None
            if hive_name == '':
                assert extracted_hive is None or extracted_hive == ''
            else:
                assert hive_name == extracted_hive

    def test_parse_ticket_id_preserves_base_id(self):
        """Should preserve everything after first dot as base_id."""
        _, base_id = parse_ticket_id('backend.bees-abc.extra.dots')
        assert base_id == 'bees-abc.extra.dots'

        _, base_id = parse_ticket_id('hive.complex.base.id')
        assert base_id == 'complex.base.id'
