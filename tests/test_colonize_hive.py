"""
Unit tests for colonize_hive() and scan_for_hive() functions.

Tests directory creation, error handling, idempotency of hive colonization,
and .hive marker functionality for hive recovery.
"""

import pytest
import json
from pathlib import Path
from src.mcp_server import colonize_hive, scan_for_hive


class TestColonizeHive:
    """Tests for colonize_hive() function."""

    def test_creates_eggs_directory(self, tmp_path):
        """Test that /eggs directory is created during colonization."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        eggs_path = hive_path / "eggs"
        assert eggs_path.exists()
        assert eggs_path.is_dir()

    def test_creates_evicted_directory(self, tmp_path):
        """Test that /evicted directory is created during colonization."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        evicted_path = hive_path / "evicted"
        assert evicted_path.exists()
        assert evicted_path.is_dir()

    def test_creates_both_subdirectories(self, tmp_path):
        """Test that both /eggs and /evicted directories are created."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        eggs_path = hive_path / "eggs"
        evicted_path = hive_path / "evicted"

        assert eggs_path.exists()
        assert evicted_path.exists()

    def test_idempotent_directory_creation(self, tmp_path):
        """Test that function handles existing directories gracefully (exist_ok=True behavior)."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        # First call - creates directories
        result1 = colonize_hive("Test Hive", str(hive_path))
        assert result1["status"] == "success"

        # Second call - directories already exist, should not raise error
        result2 = colonize_hive("Test Hive", str(hive_path))
        assert result2["status"] == "success"

        # Verify directories still exist
        assert (hive_path / "eggs").exists()
        assert (hive_path / "evicted").exists()

    def test_creates_parent_directories(self, tmp_path):
        """Test that function creates parent directories if they don't exist (parents=True)."""
        # Path with non-existent parent
        hive_path = tmp_path / "nested" / "parent" / "test_hive"

        # Parent doesn't exist yet
        assert not hive_path.exists()

        result = colonize_hive("Test Hive", str(hive_path))

        # Should create all parents plus subdirectories
        assert hive_path.exists()
        assert (hive_path / "eggs").exists()
        assert (hive_path / "evicted").exists()

    def test_returns_normalized_name(self, tmp_path):
        """Test that function returns normalized hive name."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Back End", str(hive_path))

        assert result["status"] == "success"
        assert result["hive_name"] == "back_end"

    def test_returns_hive_path(self, tmp_path):
        """Test that function returns hive path in response."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        assert result["status"] == "success"
        assert result["hive_path"] == str(hive_path)

    def test_response_structure(self, tmp_path):
        """Test that function returns correct response structure."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        # Verify response has all expected keys
        assert "status" in result
        assert "hive_name" in result
        assert "hive_path" in result
        assert result["status"] == "success"

    def test_handles_spaces_in_hive_name(self, tmp_path):
        """Test that function handles hive names with spaces correctly."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Multi Word Name", str(hive_path))

        assert result["status"] == "success"
        assert result["hive_name"] == "multi_word_name"
        assert (hive_path / "eggs").exists()
        assert (hive_path / "evicted").exists()

    def test_handles_uppercase_in_hive_name(self, tmp_path):
        """Test that function handles uppercase in hive names correctly."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("UPPERCASE", str(hive_path))

        assert result["status"] == "success"
        assert result["hive_name"] == "uppercase"

    def test_creates_hive_marker(self, tmp_path):
        """Test that .hive marker directory is created during colonization."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        hive_marker_path = hive_path / ".hive"
        assert hive_marker_path.exists()
        assert hive_marker_path.is_dir()

    def test_hive_marker_contains_identity_file(self, tmp_path):
        """Test that .hive marker contains identity.json file."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        assert identity_file.exists()
        assert identity_file.is_file()

    def test_hive_marker_has_correct_data(self, tmp_path):
        """Test that .hive marker stores correct identity data."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Back End", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        with open(identity_file, 'r') as f:
            identity_data = json.load(f)

        assert identity_data["normalized_name"] == "back_end"
        assert identity_data["display_name"] == "Back End"

    def test_hive_marker_data_structure(self, tmp_path):
        """Test that .hive marker has required fields."""
        hive_path = tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        with open(identity_file, 'r') as f:
            identity_data = json.load(f)

        assert "normalized_name" in identity_data
        assert "display_name" in identity_data


class TestScanForHive:
    """Tests for scan_for_hive() function."""

    def test_finds_hive_by_marker(self, tmp_path, monkeypatch):
        """Test that scan_for_hive finds a moved hive by its .hive marker."""
        # Set up a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Create a hive with .hive marker
        hive_path = tmp_path / "tickets"
        hive_path.mkdir()
        colonize_hive("Back End", str(hive_path))

        # Scan for the hive
        found_path = scan_for_hive("back_end")

        assert found_path == hive_path

    def test_returns_none_for_nonexistent_hive(self, tmp_path, monkeypatch):
        """Test that scan_for_hive returns None if hive not found."""
        # Set up a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Scan for non-existent hive
        found_path = scan_for_hive("nonexistent")

        assert found_path is None

    def test_finds_hive_in_subdirectory(self, tmp_path, monkeypatch):
        """Test that scan_for_hive finds hives in nested directories."""
        # Set up a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Create a hive in a nested directory
        hive_path = tmp_path / "nested" / "dir" / "tickets"
        hive_path.mkdir(parents=True)
        colonize_hive("Nested Hive", str(hive_path))

        # Scan for the hive
        found_path = scan_for_hive("nested_hive")

        assert found_path == hive_path

    def test_warns_on_orphaned_markers(self, tmp_path, monkeypatch, caplog):
        """Test that scan_for_hive logs warnings for orphaned .hive markers."""
        import logging
        caplog.set_level(logging.WARNING)

        # Set up a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Create a hive with .hive marker (but don't register in config)
        hive_path = tmp_path / "orphaned_hive"
        hive_path.mkdir()
        colonize_hive("Orphaned Hive", str(hive_path))

        # Scan for a different hive
        found_path = scan_for_hive("other_hive")

        # Should log warning about orphaned marker
        assert any("orphaned" in record.message.lower() for record in caplog.records)

    def test_handles_missing_identity_file(self, tmp_path, monkeypatch, caplog):
        """Test that scan_for_hive handles .hive markers without identity.json."""
        import logging
        caplog.set_level(logging.WARNING)

        # Set up a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Create a .hive marker without identity.json
        hive_path = tmp_path / "broken_hive"
        hive_marker_path = hive_path / ".hive"
        hive_marker_path.mkdir(parents=True)

        # Scan should handle missing identity.json gracefully
        found_path = scan_for_hive("test_hive")

        assert found_path is None
        assert any("without identity.json" in record.message for record in caplog.records)

    def test_handles_corrupted_identity_file(self, tmp_path, monkeypatch, caplog):
        """Test that scan_for_hive handles corrupted identity.json files."""
        import logging
        caplog.set_level(logging.WARNING)

        # Set up a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Create a .hive marker with corrupted identity.json
        hive_path = tmp_path / "corrupted_hive"
        hive_marker_path = hive_path / ".hive"
        hive_marker_path.mkdir(parents=True)

        identity_file = hive_marker_path / "identity.json"
        with open(identity_file, 'w') as f:
            f.write("{ invalid json }")

        # Scan should handle corrupted JSON gracefully
        found_path = scan_for_hive("test_hive")

        assert found_path is None
        assert any("Could not read identity" in record.message for record in caplog.records)
