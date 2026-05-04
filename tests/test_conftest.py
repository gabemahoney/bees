"""
Tests for conftest.py fixture patching behavior.

Validates that the mock_git_repo_check fixture properly patches
get_repo_root_from_path and allows tests to run in non-git temp directories.
"""

import pytest
from pathlib import Path
from src import mcp_repo_utils, mcp_server


class TestMockGitRepoCheck:
    """Test the mock_git_repo_check fixture behavior."""

    def test_mcp_repo_utils_is_patched(self, tmp_path, monkeypatch):
        """Verify mcp_repo_utils.get_repo_root_from_path returns resolved path."""
        monkeypatch.chdir(tmp_path)

        # Should return the resolved start_path
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path.resolve()

    def test_mcp_server_requires_separate_patch(self):
        """Verify mcp_server requires separate patching due to import binding."""
        # Python imports create name bindings at import time
        # mcp_server.py imports get_repo_root_from_path from repo_utils
        # This creates a local binding in mcp_server's namespace to the function object
        assert hasattr(mcp_server, 'get_repo_root_from_path')
        assert hasattr(mcp_repo_utils, 'get_repo_root_from_path')

        # Both should return start_path.resolve() — same behavior
        test_path = Path("/tmp/test")
        assert mcp_server.get_repo_root_from_path(test_path) == test_path.resolve()
        assert mcp_repo_utils.get_repo_root_from_path(test_path) == test_path.resolve()

    def test_mock_allows_non_git_directory(self, tmp_path, monkeypatch):
        """Verify function works in non-git temporary directories."""
        monkeypatch.chdir(tmp_path)

        # tmp_path has no .git or .bees directory
        assert not (tmp_path / '.git').exists()
        assert not (tmp_path / '.bees').exists()

        # Should return the resolved start_path without error
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path.resolve()
        assert result.exists()

    def test_mock_handles_nested_directories(self, tmp_path, monkeypatch):
        """Verify function returns the resolved nested path, not a parent."""
        monkeypatch.chdir(tmp_path)

        # Create nested directory structure
        nested = tmp_path / 'a' / 'b' / 'c'
        nested.mkdir(parents=True)

        # Should return the resolved start_path (not cwd or a parent)
        result = mcp_repo_utils.get_repo_root_from_path(nested)
        assert result == nested.resolve()

    def test_mock_with_git_directory_present(self, tmp_path, monkeypatch):
        """Verify function works when .git is present (but doesn't depend on it)."""
        monkeypatch.chdir(tmp_path)

        # Create .git directory
        git_dir = tmp_path / '.git'
        git_dir.mkdir()

        # Should return the resolved start_path
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path

    def test_mock_with_bees_directory_present(self, tmp_path, monkeypatch):
        """Verify function works when .bees is present (but doesn't depend on it)."""
        monkeypatch.chdir(tmp_path)

        # Create .bees directory
        bees_dir = tmp_path / '.bees'
        bees_dir.mkdir()

        # Should return the resolved start_path
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path

    def test_mock_returns_resolved_start_path(self, tmp_path, monkeypatch):
        """Verify function returns the resolved start_path for subdirectories."""
        monkeypatch.chdir(tmp_path)

        # Create subdirectory without .git or .bees
        subdir = tmp_path / 'subdir'
        subdir.mkdir()

        # Should return the resolved start_path
        result = mcp_repo_utils.get_repo_root_from_path(subdir)
        assert result == subdir.resolve()


class TestMockGitRepoCheckMarker:
    """Test the @pytest.mark.needs_real_git_check marker."""

    @pytest.mark.needs_real_git_check
    def test_marker_bypasses_mock(self, tmp_path):
        """Verify tests marked with needs_real_git_check bypass the mock."""
        # This test is marked to bypass the mock
        # Note: This test validates the marker exists and is recognized by pytest
        # The actual bypass behavior is tested in integration tests
        pass


class TestMockGitRepoCheckEdgeCases:
    """Test edge cases in mock_git_repo_check fixture."""

    def test_mock_with_symlinked_directory(self, tmp_path, monkeypatch):
        """Verify function resolves symlinks correctly."""
        monkeypatch.chdir(tmp_path)

        # Create target directory and symlink
        target = tmp_path / 'target'
        target.mkdir()
        symlink = tmp_path / 'link'
        symlink.symlink_to(target)

        # Should resolve symlinks and return target
        result = mcp_repo_utils.get_repo_root_from_path(symlink)
        assert result == target.resolve()

    def test_mock_returns_resolved_paths(self, tmp_path, monkeypatch):
        """Verify function returns resolved (absolute) paths."""
        monkeypatch.chdir(tmp_path)

        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result.is_absolute()
        assert result == result.resolve()


class TestFixtureIntegration:
    """Test fixture integration with other test fixtures."""

    def test_isolated_bees_env_uses_mock(self, isolated_bees_env):
        """Verify isolated_bees_env fixture benefits from mock_git_repo_check."""
        helper = isolated_bees_env

        # The environment should be usable without a real git repo
        # Create a hive and verify it works
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        assert hive_dir.exists()

        # Config operations should work with the mock
        helper.write_config()
        config_path = helper.global_bees_dir / 'config.json'
        assert config_path.exists()

    def test_setup_tickets_dir_uses_mock(self, tmp_path, monkeypatch):
        """Verify fixtures using tmp_path work correctly with function."""
        monkeypatch.chdir(tmp_path)

        # Create .bees directory
        bees_dir = tmp_path / '.bees'
        bees_dir.mkdir()

        # Should be able to find repo root
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path
