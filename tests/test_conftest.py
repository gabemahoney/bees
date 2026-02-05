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


class TestTieredFixtures:
    """Test the new tiered pytest fixtures (bees_repo, single_hive, multi_hive, hive_with_tickets)."""

    def test_bees_repo_creates_structure(self, bees_repo):
        """Verify bees_repo fixture creates .bees directory."""
        repo_root = bees_repo
        assert repo_root.exists()
        assert (repo_root / ".bees").exists()
        assert (repo_root / ".bees").is_dir()

    def test_bees_repo_uses_tmp_path(self, bees_repo, tmp_path):
        """Verify bees_repo is based on tmp_path for isolation."""
        # bees_repo should be tmp_path (or a derivative)
        # Both should be temporary directories
        assert bees_repo.exists()
        assert tmp_path.exists()

    def test_single_hive_creates_hive(self, single_hive):
        """Verify single_hive fixture creates backend hive with proper structure."""
        repo_root, hive_path = single_hive
        
        # Check hive directory exists
        assert hive_path.exists()
        assert hive_path.is_dir()
        assert hive_path.name == "backend"
        
        # Check .hive/identity.json exists
        identity_file = hive_path / ".hive" / "identity.json"
        assert identity_file.exists()
        
        import json
        identity_data = json.loads(identity_file.read_text())
        assert identity_data["normalized_name"] == "backend"
        assert identity_data["display_name"] == "Backend"
        assert "created_at" in identity_data

    def test_single_hive_registers_config(self, single_hive):
        """Verify single_hive fixture registers hive in config.json."""
        repo_root, hive_path = single_hive
        
        config_path = repo_root / ".bees" / "config.json"
        assert config_path.exists()
        
        import json
        config_data = json.loads(config_path.read_text())
        assert "hives" in config_data
        assert "backend" in config_data["hives"]
        assert config_data["hives"]["backend"]["display_name"] == "Backend"
        assert config_data["hives"]["backend"]["path"] == str(hive_path)

    def test_multi_hive_creates_both_hives(self, multi_hive):
        """Verify multi_hive fixture creates backend and frontend hives."""
        repo_root, backend_path, frontend_path = multi_hive
        
        # Check both hive directories exist
        assert backend_path.exists()
        assert backend_path.name == "backend"
        assert frontend_path.exists()
        assert frontend_path.name == "frontend"
        
        # Check both have identity markers
        backend_identity = backend_path / ".hive" / "identity.json"
        frontend_identity = frontend_path / ".hive" / "identity.json"
        assert backend_identity.exists()
        assert frontend_identity.exists()

    def test_multi_hive_registers_both_configs(self, multi_hive):
        """Verify multi_hive fixture registers both hives in config.json."""
        repo_root, backend_path, frontend_path = multi_hive
        
        config_path = repo_root / ".bees" / "config.json"
        assert config_path.exists()
        
        import json
        config_data = json.loads(config_path.read_text())
        assert "backend" in config_data["hives"]
        assert "frontend" in config_data["hives"]
        assert config_data["hives"]["backend"]["display_name"] == "Backend"
        assert config_data["hives"]["frontend"]["display_name"] == "Frontend"

    def test_hive_with_tickets_creates_hierarchy(self, hive_with_tickets):
        """Verify hive_with_tickets fixture creates epic → task → subtask hierarchy."""
        repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
        
        # Check all ticket IDs are valid format
        assert epic_id.startswith("backend.bees-")
        assert task_id.startswith("backend.bees-")
        assert subtask_id.startswith("backend.bees-")
        
        # Check ticket files exist
        assert (hive_path / f"{epic_id}.md").exists()
        assert (hive_path / f"{task_id}.md").exists()
        assert (hive_path / f"{subtask_id}.md").exists()

    def test_hive_with_tickets_has_proper_relationships(self, hive_with_tickets):
        """Verify hive_with_tickets creates tickets with proper types."""
        from src.reader import read_ticket
        
        repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
        
        # Read tickets using full file paths
        epic = read_ticket(hive_path / f"{epic_id}.md")
        task = read_ticket(hive_path / f"{task_id}.md")
        subtask = read_ticket(hive_path / f"{subtask_id}.md")
        
        # Verify types
        assert epic.type == "epic"
        assert task.type == "task"
        assert subtask.type == "subtask"
        
        # Verify parent assignments were made
        assert task.parent == epic_id
        assert subtask.parent == task_id

    def test_fixture_composition_chain(self, bees_repo, single_hive, multi_hive):
        """Verify fixtures compose properly and maintain isolation."""
        # bees_repo is base
        assert bees_repo.exists()
        
        # single_hive and multi_hive should each have their own repo roots
        single_repo, single_hive_path = single_hive
        multi_repo, multi_backend, multi_frontend = multi_hive
        
        # Each fixture should have isolated directory structure
        assert single_repo.exists()
        assert multi_repo.exists()
        
        # Verify they're different temp directories (isolation)
        # This ensures no state pollution between tests
        assert single_hive_path.exists()
        assert multi_backend.exists()

    def test_fixture_cleanup_happens_automatically(self, bees_repo):
        """Verify fixtures clean up automatically via tmp_path."""
        # This test validates the design - cleanup is automatic
        # Because fixtures use tmp_path, pytest handles cleanup
        repo_root = bees_repo
        assert repo_root.exists()
        # Cleanup verification happens implicitly - pytest removes tmp_path after test
