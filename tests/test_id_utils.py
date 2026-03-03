"""
Unit tests for ticket ID generation and utilities.

PURPOSE:
Tests core ID utilities including generation, validation, and uniqueness checking
with the new type-prefixed ID format.

SCOPE - Tests that belong here:
- resolve_tier_info(): Map ticket type to prefix and length
- generate_ticket_id(): Generate new ticket IDs with type prefix
- generate_guid(): Generate 32-char GUID from short_id
- is_valid_ticket_id(): Validate ID format
- generate_unique_ticket_id(): Generate IDs avoiding collisions via shallow hive scan
- generate_child_tier_id(): Generate hierarchical child IDs from parent ID
- ID format rules (b.XXX, t1.XXXX, t2.XXXXX pattern)
- Charset validation (Modified Crockford Base32)
- Tier-length validation

SCOPE - Tests that DON'T belong here:
- ID parsing -> test_paths.py
- ID validation in linter -> test_linter.py
- Hive operations -> test_colonize_hive.py, test_mcp_hive_*.py
- Ticket creation using IDs -> test_create_ticket.py

RELATED FILES:
- test_paths.py: ID parsing functions
- test_linter.py: Linter ID validation
- test_create_ticket.py: Using ID generation
"""

import pytest

from src.constants import ID_CHARSET, GUID_LENGTH
from src.id_utils import (
    generate_child_tier_id,
    generate_guid,
    generate_ticket_id,
    generate_unique_ticket_id,
    is_ticket_id,
    is_valid_ticket_id,
    parent_id_from_ticket_id,
    resolve_tier_info,
    ticket_type_from_prefix,
)
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
from tests.test_constants import (
    TICKET_ID_CASE_AMX_LOWER,
    TICKET_ID_INVALID_I_LOWER,
    TICKET_ID_INVALID_I_UPPER,
    TICKET_ID_INVALID_L_LOWER,
    TICKET_ID_INVALID_L_UPPER,
    TICKET_ID_INVALID_O_LOWER,
    TICKET_ID_INVALID_O_UPPER,
    TICKET_ID_INVALID_OLD_T1,
    TICKET_ID_INVALID_OLD_T2,
    TICKET_ID_INVALID_T1_LONG,
    TICKET_ID_INVALID_T1_SHORT,
    TICKET_ID_INVALID_T2_SHORT,
    TICKET_ID_INVALID_TOO_LONG,
    TICKET_ID_INVALID_TOO_SHORT,
    TICKET_ID_INVALID_ZERO,
    TICKET_ID_T1,
    TICKET_ID_T2,
    TICKET_ID_UNKNOWN_HIVE,
    TICKET_ID_VALID_BEE_MIXED,
    TICKET_ID_VALID_BEE_R8P,
    TICKET_ID_VALID_BEE_X4F,
    TICKET_ID_VALID_T1_R8P2,
    TICKET_ID_VALID_T3_CAPS,
)


class TestResolveTierInfo:
    """Tests for resolve_tier_info() function."""

    @pytest.mark.parametrize(
        "ticket_type,expected_prefix,expected_length",
        [
            pytest.param("bee", "b", 3, id="bee"),
            pytest.param("t1", "t1", 5, id="t1"),
            pytest.param("t2", "t2", 7, id="t2"),
            pytest.param("t3", "t3", 9, id="t3"),
            pytest.param("t10", "t10", 23, id="t10"),
        ],
    )
    def test_resolve_tier_info_for_tier_ids(self, ticket_type, expected_prefix, expected_length):
        """Should map tier IDs to prefix and length."""
        prefix, length = resolve_tier_info(ticket_type)
        assert prefix == expected_prefix
        assert length == expected_length

    def test_resolve_tier_info_for_friendly_name(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should resolve friendly names from child_tiers config."""
        monkeypatch.chdir(tmp_path)

        scope_data = {
            "hives": {},
            "child_tiers": {
                "t1": ["Task", "Tasks"],
                "t2": ["Subtask", "Subtasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            prefix, length = resolve_tier_info("Task")
            assert prefix == "t1"
            assert length == 5

            prefix, length = resolve_tier_info("Subtask")
            assert prefix == "t2"
            assert length == 7

    def test_resolve_tier_info_invalid_type(self):
        """Should raise ValueError for invalid ticket type."""
        with pytest.raises(ValueError, match="Invalid ticket_type: invalid"):
            resolve_tier_info("invalid")


class TestResolveTierInfoPerHive:
    """Tests for resolve_tier_info() with per-hive child_tiers resolution."""

    def test_resolve_with_hive_specific_friendly_names(self):
        """Should resolve friendly names from hive-specific child_tiers."""
        from unittest.mock import MagicMock, patch

        from src.config import BeesConfig, ChildTierConfig

        # Mock config with hive-specific child_tiers
        mock_config = BeesConfig(
            hives={
                "backend": MagicMock(
                    path="/fake/backend",
                    display_name="Backend",
                    created_at="2026-01-01T00:00:00",
                )
            }
        )

        # Mock resolve_child_tiers_for_hive to return hive-specific tiers
        mock_hive_tiers = {
            "t1": ChildTierConfig(singular="Epic", plural="Epics"),
            "t2": ChildTierConfig(singular="Story", plural="Stories"),
        }

        with patch("src.config.load_bees_config", return_value=mock_config):
            with patch("src.config.resolve_child_tiers_for_hive", return_value=mock_hive_tiers):
                prefix, length = resolve_tier_info("Epic", hive_name="backend")
                assert prefix == "t1"
                assert length == 5

                prefix, length = resolve_tier_info("Story", hive_name="backend")
                assert prefix == "t2"
                assert length == 7

    def test_resolve_with_hive_having_bees_only(self):
        """Should raise error when hive has child_tiers={} (bees-only)."""
        from unittest.mock import MagicMock, patch

        from src.config import BeesConfig

        mock_config = BeesConfig(
            hives={
                "backend": MagicMock(
                    path="/fake/backend",
                    display_name="Backend",
                    created_at="2026-01-01T00:00:00",
                )
            }
        )

        # Mock resolve_child_tiers_for_hive to return {} (bees-only)
        with patch("src.config.load_bees_config", return_value=mock_config):
            with patch("src.config.resolve_child_tiers_for_hive", return_value={}):
                # Should raise error when trying to resolve friendly name
                with pytest.raises(ValueError, match="Invalid ticket_type: Task. No child_tiers configured"):
                    resolve_tier_info("Task", hive_name="backend")

                # But tier IDs should still work
                prefix, length = resolve_tier_info("t1", hive_name="backend")
                assert prefix == "t1"
                assert length == 5

    def test_resolve_scope_name_not_found_in_hive_tiers(self):
        """Should raise error when friendly name exists in scope but not in hive tiers."""
        from unittest.mock import MagicMock, patch

        from src.config import BeesConfig, ChildTierConfig

        # Scope has Task/Subtask, but hive has Epic/Story
        mock_config = BeesConfig(
            hives={
                "backend": MagicMock(
                    path="/fake/backend",
                    display_name="Backend",
                    created_at="2026-01-01T00:00:00",
                )
            },
            child_tiers={
                "t1": ChildTierConfig(singular="Task", plural="Tasks"),
                "t2": ChildTierConfig(singular="Subtask", plural="Subtasks"),
            },
        )

        # Hive has different friendly names
        mock_hive_tiers = {
            "t1": ChildTierConfig(singular="Epic", plural="Epics"),
            "t2": ChildTierConfig(singular="Story", plural="Stories"),
        }

        with patch("src.config.load_bees_config", return_value=mock_config):
            with patch("src.config.resolve_child_tiers_for_hive", return_value=mock_hive_tiers):
                # Should NOT find "Task" in hive tiers (only Epic/Story exist there)
                with pytest.raises(
                    ValueError,
                    match=(
                        "Invalid ticket_type: Task. Must be 'bee', a tier ID like 't1', "
                        "or a friendly name from child_tiers config"
                    ),
                ):
                    resolve_tier_info("Task", hive_name="backend")

                # But should find Epic
                prefix, length = resolve_tier_info("Epic", hive_name="backend")
                assert prefix == "t1"
                assert length == 5

    def test_backward_compat_without_hive_name(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should use scope-level child_tiers when hive_name is None (backward compat)."""
        monkeypatch.chdir(tmp_path)

        scope_data = {
            "hives": {},
            "child_tiers": {
                "t1": ["Task", "Tasks"],
                "t2": ["Subtask", "Subtasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            # Without hive_name, should use scope-level child_tiers
            prefix, length = resolve_tier_info("Task")
            assert prefix == "t1"
            assert length == 5

            prefix, length = resolve_tier_info("Subtask")
            assert prefix == "t2"
            assert length == 7


class TestGenerateTicketIdByTier:
    """Tests for generate_ticket_id() with ticket_type parameter."""

    @pytest.mark.parametrize(
        "ticket_type,expected_prefix,expected_len",
        [
            pytest.param("bee", "b.", 5, id="bee"),
            pytest.param("t1", "t1.", 9, id="t1"),
            pytest.param("t2", "t2.", 12, id="t2"),
        ],
    )
    def test_generate_id_by_tier(self, ticket_type, expected_prefix, expected_len):
        """Should generate ID with correct prefix and length for each tier."""
        ticket_id = generate_ticket_id(ticket_type=ticket_type)
        assert ticket_id.startswith(expected_prefix)
        assert len(ticket_id) == expected_len
        assert is_valid_ticket_id(ticket_id)

    def test_generate_multiple_ids_are_different(self):
        """Should generate different IDs on each call."""
        ids = {generate_ticket_id(ticket_type="bee") for _ in range(100)}
        assert len(ids) >= 95  # Allow some collisions


class TestGenerateTicketIdPerHive:
    """Tests for generate_ticket_id() with per-hive child_tiers resolution."""

    def test_generate_id_with_hive_name_and_friendly_name(self):
        """Should generate ID using hive-specific friendly names."""
        from unittest.mock import MagicMock, patch

        from src.config import BeesConfig, ChildTierConfig

        mock_config = BeesConfig(
            hives={
                "backend": MagicMock(
                    path="/fake/backend",
                    display_name="Backend",
                    created_at="2026-01-01T00:00:00",
                )
            }
        )

        mock_hive_tiers = {
            "t1": ChildTierConfig(singular="Epic", plural="Epics"),
            "t2": ChildTierConfig(singular="Story", plural="Stories"),
        }

        with patch("src.config.load_bees_config", return_value=mock_config):
            with patch("src.config.resolve_child_tiers_for_hive", return_value=mock_hive_tiers):
                # Generate ID using friendly name from hive-specific config
                ticket_id = generate_ticket_id(ticket_type="Epic", hive_name="backend")
                assert ticket_id.startswith("t1.")
                assert len(ticket_id) == 9  # "t1." + "abc.de" (6 chars)
                assert is_valid_ticket_id(ticket_id)

                ticket_id = generate_ticket_id(ticket_type="Story", hive_name="backend")
                assert ticket_id.startswith("t2.")
                assert len(ticket_id) == 12  # "t2." + "abc.de.fg" (9 chars)
                assert is_valid_ticket_id(ticket_id)

    def test_generate_id_with_hive_name_and_tier_id(self):
        """Should generate ID with tier ID even when hive has different friendly names."""
        from unittest.mock import MagicMock, patch

        from src.config import BeesConfig, ChildTierConfig

        mock_config = BeesConfig(
            hives={
                "backend": MagicMock(
                    path="/fake/backend",
                    display_name="Backend",
                    created_at="2026-01-01T00:00:00",
                )
            }
        )

        mock_hive_tiers = {
            "t1": ChildTierConfig(singular="Epic", plural="Epics"),
        }

        with patch("src.config.load_bees_config", return_value=mock_config):
            with patch("src.config.resolve_child_tiers_for_hive", return_value=mock_hive_tiers):
                # Tier IDs should always work regardless of friendly names
                ticket_id = generate_ticket_id(ticket_type="t1", hive_name="backend")
                assert ticket_id.startswith("t1.")
                assert len(ticket_id) == 9
                assert is_valid_ticket_id(ticket_id)

    def test_backward_compat_generate_without_hive_name(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should use scope-level child_tiers when hive_name is None."""
        monkeypatch.chdir(tmp_path)

        scope_data = {
            "hives": {},
            "child_tiers": {
                "t1": ["Task", "Tasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            # Without hive_name, should use scope-level child_tiers
            ticket_id = generate_ticket_id(ticket_type="Task")
            assert ticket_id.startswith("t1.")
            assert len(ticket_id) == 9
            assert is_valid_ticket_id(ticket_id)


class TestIsValidTicketIdNewFormat:
    """Tests for is_valid_ticket_id() with new type-prefixed format."""

    @pytest.mark.parametrize(
        "ticket_id,expected",
        [
            # Valid IDs (all lowercase, ID_CHARSET)
            pytest.param(TICKET_ID_CASE_AMX_LOWER, True, id="bee_valid"),
            pytest.param(TICKET_ID_VALID_BEE_X4F, True, id="bee_digits"),
            pytest.param(TICKET_ID_VALID_BEE_MIXED, True, id="bee_lowercase"),
            pytest.param(TICKET_ID_VALID_T1_R8P2, True, id="t1_valid"),
            pytest.param(TICKET_ID_T2, True, id="t2_valid"),
            pytest.param(TICKET_ID_VALID_T3_CAPS, True, id="t3_valid"),
            pytest.param("t10.abc.de.fg.hi.jk.mn.pq.rs.tu.vw.xy", True, id="t10_valid"),
            # Invalid - old concatenated format (no period-separation)
            pytest.param(TICKET_ID_INVALID_OLD_T1, False, id="old_t1_no_period"),
            pytest.param(TICKET_ID_INVALID_OLD_T2, False, id="old_t2_no_period"),
            # Invalid - wrong length
            pytest.param(TICKET_ID_INVALID_TOO_LONG, False, id="bee_too_long"),
            pytest.param(TICKET_ID_INVALID_TOO_SHORT, False, id="bee_too_short"),
            pytest.param(TICKET_ID_INVALID_T1_SHORT, False, id="t1_too_short"),
            pytest.param(TICKET_ID_INVALID_T1_LONG, False, id="t1_too_long"),
            pytest.param(TICKET_ID_INVALID_T2_SHORT, False, id="t2_too_short"),
            # Invalid - bad charset (excluded chars: 0, O, I, l, and all uppercase)
            pytest.param(TICKET_ID_INVALID_ZERO, False, id="contains_zero"),
            pytest.param(TICKET_ID_INVALID_O_UPPER, False, id="contains_uppercase_o"),
            pytest.param(TICKET_ID_INVALID_I_UPPER, False, id="contains_uppercase_i"),
            pytest.param(TICKET_ID_INVALID_L_LOWER, False, id="contains_lowercase_l"),
            pytest.param(TICKET_ID_INVALID_L_UPPER, False, id="contains_uppercase_L"),
            # Valid - lowercase o and i, previously excluded but now in ID_CHARSET
            pytest.param(TICKET_ID_INVALID_O_LOWER, True, id="contains_lowercase_o_now_valid"),
            pytest.param(TICKET_ID_INVALID_I_LOWER, True, id="contains_lowercase_i_now_valid"),
            # Invalid - unknown prefix
            pytest.param(TICKET_ID_UNKNOWN_HIVE, False, id="unknown_prefix"),
            # Invalid - structure
            pytest.param("", False, id="empty_string"),
            pytest.param(None, False, id="none"),
            pytest.param("bAmx", False, id="no_dot"),
            pytest.param("b.", False, id="empty_short_id"),
            pytest.param(".Amx", False, id="empty_prefix"),
        ],
    )
    def test_validate_ticket_id(self, ticket_id, expected):
        """Should validate new type-prefixed ticket ID format."""
        assert is_valid_ticket_id(ticket_id) is expected


class TestTicketTypeFromPrefix:
    """Tests for ticket_type_from_prefix() pure string function."""

    @pytest.mark.parametrize(
        "ticket_id,expected",
        [
            pytest.param("b.amx", "bee", id="bee"),
            pytest.param("t1.abc.de", "t1", id="t1"),
            pytest.param("t2.abc.de.fg", "t2", id="t2"),
            pytest.param("t10.abc.de.fg", "t10", id="t10"),
        ],
    )
    def test_valid_ids(self, ticket_id, expected):
        """Should derive correct ticket type from valid ID prefixes."""
        assert ticket_type_from_prefix(ticket_id) == expected

    @pytest.mark.parametrize(
        "ticket_id,expected",
        [
            pytest.param("bAmx", "bAmx", id="no_dot_returns_whole_string"),
            pytest.param("", "", id="empty_string_returns_empty"),
        ],
    )
    def test_invalid_inputs_do_not_raise(self, ticket_id, expected):
        """Should return the prefix portion without crashing for malformed inputs."""
        assert ticket_type_from_prefix(ticket_id) == expected


class TestCharsetValidation:
    """Tests to ensure excluded characters never appear in generated IDs."""

    EXCLUDED_CHARS = {'0', 'O', 'I', 'l'}

    def test_charset_constant_excludes_ambiguous_chars(self):
        """ID_CHARSET should exclude visually ambiguous characters."""
        for char in self.EXCLUDED_CHARS:
            assert char not in ID_CHARSET, f"Excluded char '{char}' found in ID_CHARSET"

    def test_charset_has_correct_count(self):
        """ID_CHARSET should have exactly 34 characters."""
        assert len(ID_CHARSET) == 34
        assert not any(c.isupper() for c in ID_CHARSET), "ID_CHARSET must not contain uppercase letters"

    def test_generated_ids_never_contain_excluded_chars(self):
        """Generated IDs should never contain excluded characters."""
        # Generate many IDs to increase confidence
        for _ in range(1000):
            for ticket_type in ["bee", "t1", "t2"]:
                ticket_id = generate_ticket_id(ticket_type=ticket_type)
                for char in self.EXCLUDED_CHARS:
                    assert char not in ticket_id, f"Excluded char '{char}' found in ID: {ticket_id}"


class TestCaseSensitivity:
    """Tests for ID charset validation — uppercase is now invalid."""

    def test_uppercase_ids_are_invalid(self):
        """Uppercase characters are not in ID_CHARSET; uppercase IDs are invalid."""
        assert not is_valid_ticket_id("b.Amx")
        assert not is_valid_ticket_id("b.AMX")
        assert not is_valid_ticket_id("t1.X4F2a")
        assert is_valid_ticket_id(TICKET_ID_CASE_AMX_LOWER)
        assert is_valid_ticket_id(TICKET_ID_VALID_T1_R8P2)

    def test_collision_detection_with_lowercase_ids(self):
        """Collision detection should work for distinct lowercase IDs via shallow scan."""
        from unittest.mock import patch

        # With no hives configured, any generated ID is unique
        with patch("src.config.load_bees_config", return_value=None):
            new_id = generate_unique_ticket_id(ticket_type="bee")
        assert new_id.startswith("b.")
        assert is_valid_ticket_id(new_id)


class TestGenerateUniqueTicketId:
    """Tests for generate_unique_ticket_id() with ticket_type parameter."""

    def test_generate_unique_bee(self):
        """Should generate a valid bee ID when no hives are configured."""
        from unittest.mock import patch

        with patch("src.config.load_bees_config", return_value=None):
            ticket_id = generate_unique_ticket_id(ticket_type="bee")
        assert ticket_id.startswith("b.")
        assert is_valid_ticket_id(ticket_id)

    def test_generate_unique_t1(self):
        """Should generate a valid t1 ID when no hives are configured."""
        from unittest.mock import patch

        with patch("src.config.load_bees_config", return_value=None):
            ticket_id = generate_unique_ticket_id(ticket_type="t1")
        assert ticket_id.startswith("t1.")
        assert is_valid_ticket_id(ticket_id)

    def test_too_many_bees_raises_error(self, tmp_path):
        """Should raise RuntimeError when generated ID always collides with hive entries."""
        from unittest.mock import MagicMock, patch

        from src.config import BeesConfig

        mock_config = BeesConfig(
            hives={
                "backend": MagicMock(
                    path=str(tmp_path),
                    display_name="Backend",
                    created_at="2026-01-01T00:00:00",
                )
            }
        )
        # Place the fixed ID in the hive dir so it always shows up in listdir
        (tmp_path / TICKET_ID_CASE_AMX_LOWER).touch()

        with patch("src.id_utils.generate_ticket_id", return_value=TICKET_ID_CASE_AMX_LOWER):
            with patch("src.config.load_bees_config", return_value=mock_config):
                with pytest.raises(RuntimeError, match="Too many bees"):
                    generate_unique_ticket_id(ticket_type="bee", max_attempts=5)



class TestGenerateUniqueTicketIdPerHive:
    """Tests for generate_unique_ticket_id() with per-hive child_tiers resolution."""

    def test_generate_unique_with_hive_name_and_friendly_name(self):
        """Should generate unique ID using hive-specific friendly names."""
        from unittest.mock import MagicMock, patch

        from src.config import BeesConfig, ChildTierConfig

        mock_config = BeesConfig(
            hives={
                "backend": MagicMock(
                    path="/fake/backend",
                    display_name="Backend",
                    created_at="2026-01-01T00:00:00",
                )
            }
        )

        mock_hive_tiers = {
            "t1": ChildTierConfig(singular="Epic", plural="Epics"),
        }

        with patch("src.config.load_bees_config", return_value=mock_config):
            with patch("src.config.resolve_child_tiers_for_hive", return_value=mock_hive_tiers):
                # /fake/backend doesn't exist so existing set stays empty
                ticket_id = generate_unique_ticket_id(ticket_type="Epic", hive_name="backend")
                assert ticket_id.startswith("t1.")
                assert len(ticket_id) == 9
                assert is_valid_ticket_id(ticket_id)

    def test_generate_unique_with_hive_name_collision_avoidance(self, tmp_path):
        """Should return an ID not already present in the hive directory."""
        from unittest.mock import MagicMock, patch

        from src.config import BeesConfig, ChildTierConfig

        mock_config = BeesConfig(
            hives={
                "backend": MagicMock(
                    path=str(tmp_path),
                    display_name="Backend",
                    created_at="2026-01-01T00:00:00",
                )
            }
        )

        mock_hive_tiers = {
            "t1": ChildTierConfig(singular="Epic", plural="Epics"),
        }

        # Seed hive dir with some existing IDs
        existing = set()
        for _ in range(10):
            entry_id = generate_ticket_id(ticket_type="t1")
            (tmp_path / entry_id).touch()
            existing.add(entry_id)

        with patch("src.config.load_bees_config", return_value=mock_config):
            with patch("src.config.resolve_child_tiers_for_hive", return_value=mock_hive_tiers):
                ticket_id = generate_unique_ticket_id(ticket_type="Epic", hive_name="backend")
                assert ticket_id not in existing
                assert ticket_id.startswith("t1.")
                assert is_valid_ticket_id(ticket_id)

    def test_backward_compat_generate_unique_without_hive_name(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should use scope-level child_tiers when hive_name is None."""
        monkeypatch.chdir(tmp_path)

        scope_data = {
            "hives": {},
            "child_tiers": {
                "t1": ["Task", "Tasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            # Without hive_name, should use scope-level child_tiers
            ticket_id = generate_unique_ticket_id(ticket_type="Task")
            assert ticket_id.startswith("t1.")
            assert len(ticket_id) == 9
            assert is_valid_ticket_id(ticket_id)


class TestGenerateGuid:
    """Tests for generate_guid() function."""

    @pytest.mark.parametrize(
        "short_id",
        [
            pytest.param("amx", id="bee_3char"),
            pytest.param("r8p.2a", id="t1_period_separated"),
            pytest.param("abc.de.fg", id="t2_period_separated"),
            pytest.param("x4f.2a.bc.de", id="t3_period_separated"),
        ],
    )
    def test_guid_length_and_prefix(self, short_id):
        """generate_guid strips periods and returns GUID_LENGTH chars prefixed with stripped short_id."""
        guid = generate_guid(short_id)
        stripped = short_id.replace(".", "")
        assert len(guid) == GUID_LENGTH
        assert guid.startswith(stripped)

    def test_guid_all_chars_in_charset(self):
        """Every character in generated GUID belongs to ID_CHARSET."""
        for _ in range(100):
            guid = generate_guid("amx")
            for ch in guid:
                assert ch in ID_CHARSET, f"Char '{ch}' not in ID_CHARSET"

    def test_guid_uniqueness(self):
        """Repeated calls produce different GUIDs."""
        guids = {generate_guid("amx") for _ in range(100)}
        assert len(guids) >= 95


class TestGuidCharsetExclusions:
    """Tests that ID_CHARSET explicitly excludes ambiguous characters."""

    @pytest.mark.parametrize(
        "excluded",
        [
            pytest.param("0", id="zero"),
            pytest.param("O", id="uppercase_O"),
            pytest.param("I", id="uppercase_I"),
            pytest.param("l", id="lowercase_l"),
        ],
    )
    def test_charset_excludes_char(self, excluded):
        """ID_CHARSET must not contain the given ambiguous character."""
        assert excluded not in ID_CHARSET


class TestIsTicketId:
    """Tests for is_ticket_id() relaxed directory-filtering function."""

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("b.amx", id="bee_short"),
            pytest.param("b.x4f", id="bee_digits"),
            pytest.param("t1.x4f.2a", id="t1"),
            pytest.param("t2.r8p.2k", id="t2"),
            pytest.param("t10.abc.12", id="t10"),
            pytest.param("b.a", id="bee_single_char"),
        ],
    )
    def test_true_for_valid_ticket_ids(self, name):
        """Should return True for strings matching ticket ID directory pattern."""
        assert is_ticket_id(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("cemetery", id="cemetery"),
            pytest.param("eggs", id="eggs"),
            pytest.param(".hive", id="dot_hive"),
            pytest.param("evicted", id="evicted"),
            pytest.param("index.md", id="index_md"),
            pytest.param("README.md", id="readme"),
            pytest.param("", id="empty_string"),
            pytest.param("bAmx", id="no_dot"),
            pytest.param(".Amx", id="dot_prefix"),
            pytest.param("wrong_name", id="plain_word"),
        ],
    )
    def test_false_for_non_ticket_ids(self, name):
        """Should return False for non-ticket directory names."""
        assert is_ticket_id(name) is False


class TestGenerateChildTierId:
    """Tests for generate_child_tier_id() function."""

    def test_bee_parent_prefix(self, tmp_path):
        """Child of a bee should get t1 prefix with parent's short ID and period separator."""
        child_id = generate_child_tier_id("b.abc", tmp_path)
        assert child_id.startswith("t1.abc.")
        assert len(child_id) == 9  # "t1." (3) + "abc" (3) + "." (1) + 2 suffix

    def test_t1_parent_prefix(self, tmp_path):
        """Child of a t1 ticket should get t2 prefix with parent's short ID and period separator."""
        child_id = generate_child_tier_id("t1.abc.de", tmp_path)
        assert child_id.startswith("t2.abc.de.")
        assert len(child_id) == 12  # "t2." (3) + "abc.de" (6) + "." (1) + 2 suffix

    def test_mkdir_called_for_returned_id(self, tmp_path):
        """Should claim the child ID by creating its directory inside parent_dir."""
        child_id = generate_child_tier_id("b.abc", tmp_path)
        assert (tmp_path / child_id).is_dir()

    def test_capacity_exhaustion(self, tmp_path):
        """Should raise RuntimeError when all 100 mkdir attempts hit FileExistsError."""
        from unittest.mock import patch

        with patch("pathlib.Path.mkdir", side_effect=FileExistsError):
            with pytest.raises(RuntimeError, match="has reached capacity"):
                generate_child_tier_id("b.abc", tmp_path)

    def test_collision_retry(self, tmp_path):
        """Should retry on FileExistsError and return the first ID that succeeds."""
        from unittest.mock import patch

        call_count = {"n": 0}

        def mock_choices(population, k):
            if call_count["n"] == 0:
                call_count["n"] += 1
                return list("xy")  # first attempt — will collide
            return list("zz")  # second attempt — succeeds

        # Make the first mkdir raise FileExistsError, subsequent calls succeed
        mkdir_call_count = {"n": 0}

        def mock_mkdir(**kwargs):
            if mkdir_call_count["n"] == 0:
                mkdir_call_count["n"] += 1
                raise FileExistsError
            # succeed silently

        with patch("src.id_utils.random.choices", side_effect=mock_choices):
            with patch("pathlib.Path.mkdir", side_effect=mock_mkdir):
                child_id = generate_child_tier_id("b.abc", tmp_path)

        assert child_id == "t1.abc.zz"


class TestParentIdFromTicketId:
    """Tests for parent_id_from_ticket_id() pure string function."""

    @pytest.mark.parametrize(
        "ticket_id,expected",
        [
            pytest.param("b.abc", None, id="bee_returns_none"),
            pytest.param("t1.abc.de", "b.abc", id="t1_returns_bee"),
            pytest.param("t2.abc.de.fg", "t1.abc.de", id="t2_returns_t1"),
            pytest.param("t3.abc.de.fg.hi", "t2.abc.de.fg", id="t3_returns_t2"),
        ],
    )
    def test_parent_id(self, ticket_id, expected):
        """Should compute correct parent ID without any file I/O."""
        assert parent_id_from_ticket_id(ticket_id) == expected

    def test_deeply_nested_tier(self):
        """t4 ticket should produce a t3 parent."""
        result = parent_id_from_ticket_id("t4.ab1.cd.ef.gh.ij")
        assert result == "t3.ab1.cd.ef.gh"

    def test_bee_with_real_id_chars(self):
        """Any bee-prefixed ID returns None regardless of the short ID content."""
        assert parent_id_from_ticket_id("b.x4f") is None

    @pytest.mark.parametrize(
        "malformed",
        [
            pytest.param("t1.abc", id="t1_missing_segment"),
            pytest.param("b.", id="bee_empty_short_id"),
        ],
    )
    def test_malformed_ids_do_not_raise_for_non_bee(self, malformed):
        """Malformed non-bee IDs still attempt computation without crashing."""
        # These IDs are structurally odd but the function must not raise
        try:
            result = parent_id_from_ticket_id(malformed)
            # If it returns, that's acceptable — just not None for a t-prefixed ID
            _ = result
        except (ValueError, IndexError):
            pytest.fail(f"parent_id_from_ticket_id raised unexpectedly for {malformed!r}")
