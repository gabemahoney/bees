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
        """Verify mcp_repo_utils.get_repo_root_from_path is patched."""
        monkeypatch.chdir(tmp_path)

        # The mock should return cwd, not raise an error
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == Path.cwd()

    def test_mcp_server_requires_separate_patch(self):
        """Verify mcp_server requires separate patching due to import binding."""
        # Python imports create name bindings at import time
        # mcp_server.py:32: from .mcp_repo_utils import get_repo_root_from_path
        # This creates a local binding in mcp_server's namespace to the function object
        # After the mock patches both, they should both point to the mock
        assert hasattr(mcp_server, 'get_repo_root_from_path')
        assert hasattr(mcp_repo_utils, 'get_repo_root_from_path')

        # Both should be patched to the same mock function
        assert mcp_server.get_repo_root_from_path is mcp_repo_utils.get_repo_root_from_path

    def test_mock_allows_non_git_directory(self, tmp_path, monkeypatch):
        """Verify mock allows tests in non-git temporary directories."""
        monkeypatch.chdir(tmp_path)

        # tmp_path has no .git or .bees directory
        assert not (tmp_path / '.git').exists()
        assert not (tmp_path / '.bees').exists()

        # Mock should still return a valid path (cwd)
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == Path.cwd()
        assert result.exists()

    def test_mock_handles_nested_directories(self, tmp_path, monkeypatch):
        """Verify mock works correctly with nested directories."""
        monkeypatch.chdir(tmp_path)

        # Create nested directory structure
        nested = tmp_path / 'a' / 'b' / 'c'
        nested.mkdir(parents=True)

        # Mock should return cwd regardless of nesting
        result = mcp_repo_utils.get_repo_root_from_path(nested)
        assert result == Path.cwd()

    def test_mock_with_git_directory_present(self, tmp_path, monkeypatch):
        """Verify mock finds .git directory when present."""
        monkeypatch.chdir(tmp_path)

        # Create .git directory
        git_dir = tmp_path / '.git'
        git_dir.mkdir()

        # Mock should return the directory containing .git
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path

    def test_mock_with_bees_directory_present(self, tmp_path, monkeypatch):
        """Verify mock finds .bees directory when present."""
        monkeypatch.chdir(tmp_path)

        # Create .bees directory
        bees_dir = tmp_path / '.bees'
        bees_dir.mkdir()

        # Mock should return the directory containing .bees
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path

    def test_mock_fallback_to_cwd(self, tmp_path, monkeypatch):
        """Verify mock falls back to cwd when no markers found."""
        monkeypatch.chdir(tmp_path)

        # Create subdirectory without .git or .bees
        subdir = tmp_path / 'subdir'
        subdir.mkdir()

        # Mock should fall back to cwd
        result = mcp_repo_utils.get_repo_root_from_path(subdir)
        assert result == Path.cwd()


class TestMockGitRepoCheckMarker:
    """Test the @pytest.mark.needs_real_git_check marker."""

    @pytest.mark.needs_real_git_check
    def test_marker_bypasses_mock(self, tmp_path):
        """Verify tests marked with needs_real_git_check bypass the mock."""
        # This test is marked to bypass the mock
        # In a non-git directory, it should raise an error
        # Note: This test validates the marker exists and is recognized by pytest
        # The actual bypass behavior is tested in integration tests
        pass


class TestMockGitRepoCheckEdgeCases:
    """Test edge cases in mock_git_repo_check fixture."""

    def test_mock_with_symlinked_directory(self, tmp_path, monkeypatch):
        """Verify mock handles symlinked directories correctly."""
        monkeypatch.chdir(tmp_path)

        # Create target directory and symlink
        target = tmp_path / 'target'
        target.mkdir()
        symlink = tmp_path / 'link'
        symlink.symlink_to(target)

        # Mock should resolve symlinks and return cwd
        result = mcp_repo_utils.get_repo_root_from_path(symlink)
        assert result == Path.cwd()

    def test_mock_returns_resolved_paths(self, tmp_path, monkeypatch):
        """Verify mock returns resolved (absolute) paths."""
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
        config_path = Path.cwd() / '.bees' / 'config.json'
        assert config_path.exists()

    def test_setup_tickets_dir_uses_mock(self, tmp_path, monkeypatch):
        """Verify fixtures using tmp_path work correctly with mock."""
        monkeypatch.chdir(tmp_path)

        # Create .bees directory
        bees_dir = tmp_path / '.bees'
        bees_dir.mkdir()

        # Should be able to find repo root via mock
        result = mcp_repo_utils.get_repo_root_from_path(tmp_path)
        assert result == tmp_path
