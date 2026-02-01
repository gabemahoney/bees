"""
Unit tests for colonize_hive() function.

Tests directory creation, error handling, and idempotency of hive colonization.
"""

import pytest
from pathlib import Path
from src.mcp_server import colonize_hive


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
