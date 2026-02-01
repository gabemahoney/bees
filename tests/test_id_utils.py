"""Unit tests for ID generation utilities with hive support."""

import pytest
from src.id_utils import (
    normalize_hive_name,
    generate_ticket_id,
    is_valid_ticket_id,
    generate_unique_ticket_id,
    extract_existing_ids_from_all_hives,
)


class TestNormalizeHiveName:
    """Tests for normalize_hive_name() function."""

    def test_lowercase_conversion(self):
        """Should convert to lowercase."""
        assert normalize_hive_name("BackEnd") == "backend"
        assert normalize_hive_name("FRONTEND") == "frontend"
        assert normalize_hive_name("MixedCase") == "mixedcase"

    def test_space_to_underscore(self):
        """Should convert spaces to underscores."""
        assert normalize_hive_name("My Hive") == "my_hive"
        assert normalize_hive_name("Back End") == "back_end"
        assert normalize_hive_name("Multi Word Name") == "multi_word_name"

    def test_hyphen_to_underscore(self):
        """Should convert hyphens to underscores."""
        assert normalize_hive_name("front-end") == "front_end"
        assert normalize_hive_name("my-hive-name") == "my_hive_name"

    def test_special_chars_removed(self):
        """Should remove special characters."""
        assert normalize_hive_name("my@hive") == "myhive"
        assert normalize_hive_name("test#123") == "test123"
        assert normalize_hive_name("hive!name$") == "hivename"

    def test_leading_number_gets_underscore(self):
        """Should add underscore if starts with number."""
        assert normalize_hive_name("2backend") == "_2backend"
        assert normalize_hive_name("123test") == "_123test"

    def test_already_normalized(self):
        """Should handle already normalized names."""
        assert normalize_hive_name("backend") == "backend"
        assert normalize_hive_name("my_hive") == "my_hive"

    def test_complex_normalization(self):
        """Should handle complex cases."""
        assert normalize_hive_name("My-Hive@2024!") == "my_hive2024"
        assert normalize_hive_name("Back End (v2)") == "back_end_v2"

    def test_empty_string(self):
        """Should return empty string for empty input."""
        assert normalize_hive_name("") == ""

    def test_unicode_characters(self):
        """Should handle unicode characters."""
        # Unicode letters should be removed (not in [a-z0-9_])
        assert normalize_hive_name("café") == "caf"
        assert normalize_hive_name("München") == "mnchen"
        assert normalize_hive_name("日本") == ""
        # Unicode with regular chars
        assert normalize_hive_name("test_café") == "test_caf"

    def test_mixed_special_chars_with_hyphens(self):
        """Should handle mixed special characters and hyphens."""
        assert normalize_hive_name("test-@name!") == "test_name"
        assert normalize_hive_name("my-#hive$2024") == "my_hive2024"
        assert normalize_hive_name("front-end!@#") == "front_end"
        # Multiple consecutive hyphens and special chars
        assert normalize_hive_name("test--@@name") == "test__name"

    def test_only_special_characters(self):
        """Should return empty string for only special characters."""
        assert normalize_hive_name("@#$%") == ""
        assert normalize_hive_name("!!!") == ""
        assert normalize_hive_name("***&&&") == ""
        assert normalize_hive_name("&&&") == ""

    def test_whitespace_only_strings(self):
        """Should convert whitespace-only strings to underscores."""
        # Single space becomes single underscore
        assert normalize_hive_name(" ") == "_"
        # Multiple spaces become multiple underscores
        assert normalize_hive_name("   ") == "___"
        # Tab character becomes underscore (via space conversion)
        # Note: tabs are not converted to spaces first, they're removed as special chars
        assert normalize_hive_name("\t") == ""
        # Newline is removed as special char
        assert normalize_hive_name("\n") == ""
        # Mixed whitespace - spaces become underscores, tabs/newlines removed
        assert normalize_hive_name(" \t \n ") == "___"

    def test_mixed_special_chars_and_whitespace(self):
        """Should handle mixed special characters and whitespace."""
        # Spaces become underscores, special chars removed
        assert normalize_hive_name("  @#$  ") == "____"
        # Tab and special chars - tab is removed, spaces from edges remain
        assert normalize_hive_name("\t!!!\n") == ""
        # Mix of everything
        assert normalize_hive_name(" @ # $ ") == "____"
        assert normalize_hive_name("  !!!  ") == "____"

    def test_multiple_consecutive_spaces(self):
        """Should convert multiple spaces to multiple underscores."""
        assert normalize_hive_name("test  name") == "test__name"
        assert normalize_hive_name("a   b") == "a___b"

    def test_leading_and_trailing_spaces(self):
        """Should convert leading/trailing spaces to underscores."""
        assert normalize_hive_name(" test") == "_test"
        assert normalize_hive_name("test ") == "test_"
        assert normalize_hive_name(" test ") == "_test_"

    def test_mixed_hyphens_and_spaces(self):
        """Should convert both hyphens and spaces to underscores."""
        assert normalize_hive_name("my hive-name") == "my_hive_name"
        assert normalize_hive_name("back-end team") == "back_end_team"


class TestGenerateTicketIdWithHive:
    """Tests for generate_ticket_id() with hive_name parameter."""

    def test_generate_id_with_hive(self):
        """Should generate hive-prefixed ID."""
        ticket_id = generate_ticket_id(hive_name="backend")
        assert ticket_id.startswith("backend.bees-")
        assert is_valid_ticket_id(ticket_id)

    def test_generate_id_normalizes_hive_name(self):
        """Should normalize hive name in generated ID."""
        ticket_id = generate_ticket_id(hive_name="BackEnd")
        assert ticket_id.startswith("backend.bees-")

        ticket_id = generate_ticket_id(hive_name="My Hive")
        assert ticket_id.startswith("my_hive.bees-")

    def test_generate_multiple_ids_are_different(self):
        """Should generate different IDs on each call."""
        ids = {generate_ticket_id(hive_name="backend") for _ in range(100)}
        # With 3 character alphanumeric IDs (36^3 = 46656 possibilities),
        # 100 random IDs should be unique
        assert len(ids) >= 95  # Allow for rare collisions

    def test_whitespace_only_hive_name(self):
        """Should normalize whitespace-only hive name to underscores."""
        # Whitespace normalizes to underscores, not empty string
        ticket_id = generate_ticket_id(hive_name="   ")
        assert ticket_id.startswith("___.bees-")
        assert is_valid_ticket_id(ticket_id)

    def test_mixed_special_chars_and_whitespace_hive_names(self):
        """Should handle mixed special chars and whitespace in hive names."""
        # Spaces preserved as underscores, special chars removed
        ticket_id = generate_ticket_id(hive_name="  @#$  ")
        assert ticket_id.startswith("____.bees-")
        assert is_valid_ticket_id(ticket_id)


class TestIsValidTicketIdWithHive:
    """Tests for is_valid_ticket_id() with hive-prefixed IDs."""

    def test_valid_hive_prefixed_ids(self):
        """Should accept hive-prefixed IDs."""
        assert is_valid_ticket_id("backend.bees-abc")
        assert is_valid_ticket_id("my_hive.bees-123")
        assert is_valid_ticket_id("front_end.bees-x9z")

    def test_hive_with_numbers(self):
        """Should accept hive names with numbers."""
        assert is_valid_ticket_id("hive_v2.bees-abc")
        assert is_valid_ticket_id("test123.bees-xyz")

    def test_hive_starting_with_underscore(self):
        """Should accept hive names starting with underscore."""
        assert is_valid_ticket_id("_private.bees-abc")
        assert is_valid_ticket_id("_test.bees-123")

    def test_invalid_hive_uppercase(self):
        """Should reject uppercase in hive name."""
        assert not is_valid_ticket_id("BackEnd.bees-abc")
        assert not is_valid_ticket_id("HIVE.bees-123")

    def test_invalid_hive_with_hyphen(self):
        """Should reject hyphens in hive name."""
        assert not is_valid_ticket_id("back-end.bees-abc")
        assert not is_valid_ticket_id("my-hive.bees-123")

    def test_invalid_hive_starting_with_number(self):
        """Should reject hive names starting with number."""
        assert not is_valid_ticket_id("2backend.bees-abc")
        assert not is_valid_ticket_id("123test.bees-xyz")

    def test_invalid_no_dot_separator(self):
        """Should reject missing dot separator."""
        assert not is_valid_ticket_id("backendbees-abc")

    def test_invalid_multiple_dots(self):
        """Should reject multiple dots."""
        assert not is_valid_ticket_id("back.end.bees-abc")

    def test_invalid_empty_hive(self):
        """Should reject empty hive name."""
        assert not is_valid_ticket_id(".bees-abc")


class TestGenerateUniqueTicketIdWithHive:
    """Tests for generate_unique_ticket_id() with hive_name parameter."""

    def test_generate_unique_with_hive(self):
        """Should generate unique ID with hive prefix."""
        existing = {"backend.bees-abc", "backend.bees-123"}
        ticket_id = generate_unique_ticket_id(existing, hive_name="backend")
        assert ticket_id not in existing
        assert ticket_id.startswith("backend.bees-")
        assert is_valid_ticket_id(ticket_id)

    def test_collision_detection_with_hive(self):
        """Should detect collisions in hive-prefixed IDs."""
        # Create a set with many IDs to increase collision chance
        existing = {f"backend.bees-{i:03x}" for i in range(100)}

        # Generate new ID that doesn't collide
        ticket_id = generate_unique_ticket_id(existing, hive_name="backend")
        assert ticket_id not in existing

    def test_hive_namespacing(self):
        """IDs with different hive prefixes should not collide."""
        existing = {"backend.bees-abc"}

        # Same base ID but different hive should not count as collision
        ticket_id = generate_unique_ticket_id(existing, hive_name="frontend")
        # Could be frontend.bees-abc since backend.bees-abc doesn't conflict

    def test_max_attempts_exceeded(self):
        """Should raise error if max attempts exceeded."""
        # Create a mock that always returns the same ID to force collision
        from unittest.mock import patch

        existing = {"backend.bees-abc"}

        # Patch generate_ticket_id to always return an ID that's already in existing
        with patch('src.id_utils.generate_ticket_id', return_value="backend.bees-abc"):
            with pytest.raises(RuntimeError, match="Failed to generate unique ticket ID"):
                generate_unique_ticket_id(existing, hive_name="backend", max_attempts=10)


class TestExtractExistingIdsFromAllHives:
    """Tests for extract_existing_ids_from_all_hives() function."""

    def test_extract_ids_from_multiple_hives(self, tmp_path, monkeypatch):
        """Should extract IDs from all configured hives."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive directories with tickets
        backend_dir = tmp_path / "backend"
        frontend_dir = tmp_path / "frontend"

        backend_epics = backend_dir / "epics"
        frontend_tasks = frontend_dir / "tasks"
        backend_epics.mkdir(parents=True)
        frontend_tasks.mkdir(parents=True)

        # Create ticket files
        (backend_epics / "backend.bees-abc.md").touch()
        (backend_epics / "backend.bees-xyz.md").touch()
        (frontend_tasks / "frontend.bees-123.md").touch()

        # Configure hives
        config = BeesConfig(
            hives={
                "backend": HiveConfig(path=str(backend_dir), display_name="Backend"),
                "frontend": HiveConfig(path=str(frontend_dir), display_name="Frontend"),
            }
        )
        save_bees_config(config)

        # Extract all IDs
        ids = extract_existing_ids_from_all_hives()
        assert len(ids) == 3
        assert "backend.bees-abc" in ids
        assert "backend.bees-xyz" in ids
        assert "frontend.bees-123" in ids

    def test_extract_ids_returns_empty_when_no_hives(self, tmp_path, monkeypatch):
        """Should return empty set when no hives configured."""
        monkeypatch.chdir(tmp_path)

        # No hives configured
        ids = extract_existing_ids_from_all_hives()
        assert ids == set()

    def test_extract_ids_skips_invalid_ids(self, tmp_path, monkeypatch):
        """Should skip files with invalid ticket IDs."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create hive directory
        backend_dir = tmp_path / "backend"
        backend_epics = backend_dir / "epics"
        backend_epics.mkdir(parents=True)

        # Create valid and invalid ticket files
        (backend_epics / "backend.bees-abc.md").touch()
        (backend_epics / "invalid-id.md").touch()
        (backend_epics / "README.md").touch()

        # Configure hives
        config = BeesConfig(
            hives={"backend": HiveConfig(path=str(backend_dir), display_name="Backend")}
        )
        save_bees_config(config)

        # Extract IDs - should only get valid one
        ids = extract_existing_ids_from_all_hives()
        assert len(ids) == 1
        assert "backend.bees-abc" in ids

    def test_extract_ids_handles_nonexistent_hive_path(self, tmp_path, monkeypatch):
        """Should skip hives with nonexistent paths."""
        from src.config import BeesConfig, HiveConfig, save_bees_config

        monkeypatch.chdir(tmp_path)

        # Create one valid hive, one with nonexistent path
        backend_dir = tmp_path / "backend"
        backend_epics = backend_dir / "epics"
        backend_epics.mkdir(parents=True)
        (backend_epics / "backend.bees-abc.md").touch()

        # Configure hives - frontend path doesn't exist
        config = BeesConfig(
            hives={
                "backend": HiveConfig(path=str(backend_dir), display_name="Backend"),
                "frontend": HiveConfig(path=str(tmp_path / "nonexistent"), display_name="Frontend"),
            }
        )
        save_bees_config(config)

        # Extract IDs - should only get backend ticket
        ids = extract_existing_ids_from_all_hives()
        assert len(ids) == 1
        assert "backend.bees-abc" in ids
