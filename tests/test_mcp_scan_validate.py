"""
Unit tests for MCP server scan and validation logic.

Tests ticket discovery (scan_for_hive), path validation (validate_hive_path),
and repository root detection (get_repo_root_from_path). CRUD operation tests
are in test_mcp_server.py.
"""

import pytest
from pathlib import Path
from src.mcp_server import (
    get_repo_root_from_path,
    validate_hive_path,
    scan_for_hive
)
from src.repo_context import repo_root_context
from src.config import load_bees_config, save_bees_config, BeesConfig, HiveConfig
from datetime import datetime
import json
import logging


class TestGetRepoRoot:
    """Tests for get_repo_root_from_path() helper function."""

    def test_get_repo_root_success(self, tmp_path, monkeypatch):
        """Test get_repo_root_from_path finds .git directory in current or parent directories."""
        # Create a fake repo structure
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        subdir = repo_root / "some" / "nested" / "dir"
        subdir.mkdir(parents=True)

        # Should find repo root by walking up from subdir
        result = get_repo_root_from_path(subdir)
        assert result == repo_root

    def test_get_repo_root_at_root(self, tmp_path, monkeypatch):
        """Test get_repo_root_from_path when .git is in current directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        result = get_repo_root_from_path(repo_root)
        assert result == repo_root

    def test_get_repo_root_not_in_repo(self, tmp_path, monkeypatch):
        """Test get_repo_root_from_path raises ValueError when not in a git repo."""
        # Create directory without .git
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()

        with pytest.raises(ValueError, match="Not in a git repository"):
            get_repo_root_from_path(non_repo)


class TestValidateHivePath:
    """Tests for validate_hive_path() function."""

    def test_validate_hive_path_valid_absolute_path(self, tmp_path):
        """Test validation succeeds for valid absolute path within repo."""
        # Create repo structure
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        hive_dir = repo_root / "tickets" / "backend"
        hive_dir.mkdir(parents=True)

        # Should succeed and return normalized path
        with repo_root_context(repo_root):
            result = validate_hive_path(str(hive_dir))
        assert result == hive_dir.resolve()

    def test_validate_hive_path_with_trailing_slash(self, tmp_path):
        """Test validation normalizes trailing slashes."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        hive_dir = repo_root / "tickets"
        hive_dir.mkdir()

        # Test with trailing slash
        with repo_root_context(repo_root):
            result = validate_hive_path(str(hive_dir) + "/")
        assert result == hive_dir.resolve()
        # Verify no trailing slash in result
        assert not str(result).endswith("/")

    def test_validate_hive_path_relative_path_fails(self, tmp_path):
        """Test validation rejects relative paths."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Try to use relative path
        with repo_root_context(repo_root):
            with pytest.raises(ValueError, match="must be absolute.*relative path"):
                validate_hive_path("tickets/backend")

    def test_validate_hive_path_nonexistent_parent_fails(self, tmp_path):
        """Test validation creates parent directory if it doesn't exist."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Parent directory doesn't exist
        nonexistent_parent = repo_root / "does_not_exist" / "child"

        # New behavior: validate_hive_path creates parent directories
        with repo_root_context(repo_root):
            result = validate_hive_path(str(nonexistent_parent))

        # Should succeed and create the parent directory
        assert result == nonexistent_parent.resolve()
        assert nonexistent_parent.parent.exists()

    def test_validate_hive_path_outside_repo_fails(self, tmp_path):
        """Test validation rejects paths outside repository root."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Create directory outside repo
        outside = tmp_path / "outside"
        outside.mkdir()

        with repo_root_context(repo_root):
            with pytest.raises(ValueError, match="must be within repository root"):
                validate_hive_path(str(outside))

    def test_validate_hive_path_at_repo_root(self, tmp_path):
        """Test validation allows path at repo root itself."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Using repo root as hive path should be valid
        with repo_root_context(repo_root):
            result = validate_hive_path(str(repo_root))
        assert result == repo_root.resolve()

    def test_validate_hive_path_deeply_nested(self, tmp_path):
        """Test validation works for deeply nested paths."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Create deeply nested structure
        deep_path = repo_root / "level1" / "level2" / "level3" / "level4"
        deep_path.mkdir(parents=True)

        with repo_root_context(repo_root):
            result = validate_hive_path(str(deep_path))
        assert result == deep_path.resolve()


class TestScanForHiveConfigAutoUpdate:
    """Tests for scan_for_hive() config auto-update behavior."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    def test_scan_for_hive_updates_config_with_stale_path(self, temp_repo, monkeypatch):
        """Test that scan_for_hive updates config.json when hive is found at new location."""
        # Create initial config with stale path
        old_path = temp_repo / "old_location"
        new_path = temp_repo / "new_location"
        new_path.mkdir(parents=True)

        config = BeesConfig(hives={
            "test_hive": HiveConfig(
                display_name="Test Hive",
                path=str(old_path),
                created_at=datetime.now().isoformat()
            )
        })
        save_bees_config(config)

        # Create .hive marker at new location
        hive_marker = new_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Scan for hive - should find it and update config
        result = scan_for_hive("test_hive")

        assert result == new_path

        # Verify config was updated with new path
        updated_config = load_bees_config()
        assert updated_config.hives["test_hive"].path == str(new_path)

    def test_scan_for_hive_handles_missing_config(self, temp_repo, monkeypatch):
        """Test that scan_for_hive handles case where hive not in config yet."""
        # Create hive without config entry
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "unregistered_hive",
            "display_name": "Unregistered Hive"
        }))

        # Scan should find hive but log warning (not update config)
        result = scan_for_hive("unregistered_hive")

        assert result == hive_path
        # Config should remain empty or unchanged (no crash)

    def test_scan_for_hive_updates_only_target_hive(self, temp_repo, monkeypatch):
        """Test that scan_for_hive only updates the target hive in config with multiple hives."""
        # Create config with multiple hives
        hive1_path = temp_repo / "hive1"
        hive2_old = temp_repo / "hive2_old"
        hive2_new = temp_repo / "hive2_new"
        hive2_new.mkdir(parents=True)

        config = BeesConfig(hives={
            "hive1": HiveConfig(display_name="Hive 1", path=str(hive1_path), created_at=datetime.now().isoformat()),
            "hive2": HiveConfig(display_name="Hive 2", path=str(hive2_old), created_at=datetime.now().isoformat())
        })
        save_bees_config(config)

        # Create .hive marker for hive2 at new location
        hive_marker = hive2_new / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "hive2",
            "display_name": "Hive 2"
        }))

        # Scan for hive2
        result = scan_for_hive("hive2")

        assert result == hive2_new

        # Verify only hive2 was updated
        updated_config = load_bees_config()
        assert updated_config.hives["hive1"].path == str(hive1_path)  # Unchanged
        assert updated_config.hives["hive2"].path == str(hive2_new)   # Updated


class TestScanForHiveSecurity:
    """Tests for scan_for_hive() depth limit security feature."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    def test_scan_for_hive_respects_depth_limit(self, temp_repo):
        """Test that scan_for_hive skips .hive markers beyond MAX_SCAN_DEPTH."""
        # Create deeply nested hive (depth > 10)
        deep_path = temp_repo
        for i in range(12):  # Create 12 levels deep
            deep_path = deep_path / f"level{i}"
            deep_path.mkdir()

        hive_marker = deep_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "deep_hive",
            "display_name": "Deep Hive"
        }))

        # Scan should not find hive beyond depth limit
        result = scan_for_hive("deep_hive")
        assert result is None

    def test_scan_for_hive_finds_hive_within_depth_limit(self, temp_repo):
        """Test that scan_for_hive finds .hive markers within MAX_SCAN_DEPTH."""
        # Create hive at depth 5 (well within limit)
        hive_path = temp_repo
        for i in range(5):
            hive_path = hive_path / f"level{i}"
            hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "shallow_hive",
            "display_name": "Shallow Hive"
        }))

        # Scan should find hive within depth limit
        result = scan_for_hive("shallow_hive")
        assert result == hive_path

    def test_scan_for_hive_depth_limit_boundary(self, temp_repo):
        """Test scan_for_hive at exact MAX_SCAN_DEPTH boundary (depth 10)."""
        # Create hive at exactly depth 10 for the .hive marker
        # This means 9 levels of directories, then .hive at depth 10
        hive_path = temp_repo
        for i in range(9):
            hive_path = hive_path / f"level{i}"
            hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "boundary_hive",
            "display_name": "Boundary Hive"
        }))

        # Scan should find hive with .hive at depth 10 (inclusive)
        result = scan_for_hive("boundary_hive")
        assert result == hive_path


class TestScanForHiveConfigOptimization:
    """Tests for scan_for_hive() config parameter optimization."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    def test_scan_for_hive_accepts_config_parameter(self, temp_repo):
        """Test that scan_for_hive accepts optional config BeesConfig parameter."""
        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with config parameter
        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })
        result = scan_for_hive("test_hive", config=config)

        assert result == hive_path

    def test_scan_for_hive_empty_config_parameter(self, temp_repo):
        """Test that scan_for_hive handles BeesConfig with empty hives."""
        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with empty config
        result = scan_for_hive("test_hive", config=BeesConfig(hives={}))
        assert result == hive_path


class TestScanForHiveBugFixes:
    """Tests for scan_for_hive() bug fixes: config type handling, None safety, and early return."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    def test_scan_for_hive_config_none_handling(self, temp_repo):
        """Test that scan_for_hive handles config=None without AttributeError."""
        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with config=None - should not raise AttributeError
        result = scan_for_hive("test_hive", config=None)
        assert result == hive_path

    def test_scan_for_hive_early_return_behavior(self, temp_repo):
        """Test that scan_for_hive returns immediately upon finding target hive."""
        # Create multiple hives
        hive1_path = temp_repo / "hive1"
        hive1_path.mkdir()
        hive1_marker = hive1_path / ".hive"
        hive1_marker.mkdir()
        (hive1_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "target_hive",
            "display_name": "Target Hive"
        }))

        hive2_path = temp_repo / "hive2"
        hive2_path.mkdir()
        hive2_marker = hive2_path / ".hive"
        hive2_marker.mkdir()
        (hive2_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "other_hive",
            "display_name": "Other Hive"
        }))

        # Scan for target_hive - should find it and return immediately
        result = scan_for_hive("target_hive")
        assert result == hive1_path


class TestScanForHiveFileVsDirectory:
    """Tests for scan_for_hive() handling of .hive as file vs directory."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    def test_scan_for_hive_skips_file_marker(self, temp_repo):
        """Test that scan_for_hive() skips .hive when it's a file instead of directory."""
        # Create a .hive FILE (not directory) - this is the edge case
        hive_file = temp_repo / ".hive"
        hive_file.write_text("This is a file, not a directory")

        # Also create a valid hive directory elsewhere to confirm scan still works
        valid_hive_path = temp_repo / "valid_hive"
        valid_hive_path.mkdir()

        valid_marker = valid_hive_path / ".hive"
        valid_marker.mkdir()
        identity_file = valid_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Scan should skip the .hive file and find the valid directory
        result = scan_for_hive("test_hive")

        # Should find the valid hive, not fail on the file
        assert result == valid_hive_path

    def test_scan_for_hive_returns_none_when_only_file_marker(self, temp_repo):
        """Test that scan_for_hive() returns None when .hive is only a file, not directory."""
        # Create only a .hive FILE (no valid directory marker)
        hive_file = temp_repo / ".hive"
        hive_file.write_text("This is a file, not a directory")

        # Scan should return None (no valid hive found)
        result = scan_for_hive("test_hive")

        assert result is None


class TestScanForHiveExceptionHandling:
    """Tests for scan_for_hive() exception handling with specific exception types."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    def test_scan_for_hive_handles_ioerror_on_config_update(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive re-raises IOError when config.json cannot be written."""
        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise IOError
        def mock_save_ioerror(cfg, repo_root=None):
            raise IOError("Permission denied")

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_ioerror)

        # Should log error and re-raise
        with pytest.raises(IOError, match="Permission denied"):
            scan_for_hive("test_hive")
        assert any("Failed to update config.json" in record.message for record in caplog.records)

    def test_scan_for_hive_does_not_catch_programming_errors(self, temp_repo, monkeypatch):
        """Test that scan_for_hive does NOT catch programming errors like NameError."""
        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock load_bees_config to raise NameError (programming error)
        def mock_load_name_error(repo_root=None):
            raise NameError("undefined_variable is not defined")

        monkeypatch.setattr("src.mcp_hive_utils.load_bees_config", mock_load_name_error)

        # Should propagate NameError, not catch it
        with pytest.raises(NameError, match="undefined_variable is not defined"):
            scan_for_hive("test_hive")


class TestScanForHiveErrorPropagation:
    """Tests for scan_for_hive() error propagation when config updates fail."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    def test_scan_for_hive_raises_ioerror_on_config_save_failure(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive re-raises IOError when save_bees_config fails."""
        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise IOError
        def mock_save_ioerror(cfg, repo_root=None):
            raise IOError("Permission denied")

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_ioerror)

        # Should log error and re-raise exception
        with pytest.raises(IOError, match="Permission denied"):
            scan_for_hive("test_hive")

        # Verify error was logged before re-raising
        assert any("Failed to update config.json" in record.message for record in caplog.records)

    def test_scan_for_hive_raises_json_decode_error_on_config_failure(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive re-raises JSONDecodeError when config update fails."""
        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise JSONDecodeError
        def mock_save_json_error(cfg, repo_root=None):
            raise json.JSONDecodeError("Malformed JSON", "", 0)

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_json_error)

        # Should log error and re-raise exception
        with pytest.raises(json.JSONDecodeError, match="Malformed JSON"):
            scan_for_hive("test_hive")

        # Verify error was logged
        assert any("Failed to update config.json" in record.message for record in caplog.records)

    def test_scan_for_hive_logs_before_raising(self, temp_repo, monkeypatch, caplog):
        """Test that scan_for_hive logs error message before re-raising exception."""
        caplog.set_level(logging.ERROR)

        # Create config and hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(temp_repo / "old"), created_at=datetime.now().isoformat())
        })
        save_bees_config(config)

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Mock save_bees_config to raise IOError
        def mock_save_ioerror(cfg, repo_root=None):
            raise IOError("Test error")

        monkeypatch.setattr("src.mcp_hive_utils.save_bees_config", mock_save_ioerror)

        # Should log error and re-raise
        try:
            scan_for_hive("test_hive")
        except IOError:
            pass  # Expected

        # Verify error was logged with specific format
        error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_logs) > 0
        assert any("Failed to update config.json" in log.message and "test_hive" in log.message
                   for log in error_logs)


class TestScanForHiveConfigHandling:
    """Tests for scan_for_hive() config parameter handling after simplification."""

    @pytest.fixture
    def temp_repo(self, tmp_path, monkeypatch):
        """Create temporary repository with config directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        config_dir = repo_root / ".bees"
        config_dir.mkdir()

        monkeypatch.chdir(repo_root)
        return repo_root

    def test_scan_for_hive_with_config_none_loads_from_disk(self, temp_repo):
        """Test scan_for_hive with config=None loads config from disk."""
        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Save config to disk
        config = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })
        save_bees_config(config)

        # Call with config=None - should load from disk
        result = scan_for_hive("test_hive", config=None)
        assert result == hive_path

    def test_scan_for_hive_with_empty_hives_dict(self, temp_repo):
        """Test scan_for_hive with config having empty hives dict."""
        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()

        # Create .hive marker
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        identity_file = hive_marker / "identity.json"
        identity_file.write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Call with empty config
        config = BeesConfig(hives={})
        result = scan_for_hive("test_hive", config=config)

        # Should find hive even though not in config's registered hives
        assert result == hive_path

    def test_scan_for_hive_with_populated_hives(self, temp_repo):
        """Test scan_for_hive with config having populated hives."""
        # Create two hives
        hive1_path = temp_repo / "hive1"
        hive1_path.mkdir()
        hive1_marker = hive1_path / ".hive"
        hive1_marker.mkdir()
        (hive1_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "registered_hive",
            "display_name": "Registered Hive"
        }))

        hive2_path = temp_repo / "hive2"
        hive2_path.mkdir()
        hive2_marker = hive2_path / ".hive"
        hive2_marker.mkdir()
        (hive2_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "unregistered_hive",
            "display_name": "Unregistered Hive"
        }))

        # Create config with only hive1 registered
        config = BeesConfig(hives={
            "registered_hive": HiveConfig(
                display_name="Registered Hive",
                path=str(hive1_path),
                created_at=datetime.now().isoformat()
            )
        })

        # Scan for registered hive
        result1 = scan_for_hive("registered_hive", config=config)
        assert result1 == hive1_path

        # Scan for unregistered hive - should still be found
        result2 = scan_for_hive("unregistered_hive", config=config)
        assert result2 == hive2_path

    def test_scan_for_hive_registered_hives_set_populated_correctly(self, temp_repo):
        """Test that registered_hives set is correctly populated in each config case."""
        # Create hive
        hive_path = temp_repo / "hive"
        hive_path.mkdir()
        hive_marker = hive_path / ".hive"
        hive_marker.mkdir()
        (hive_marker / "identity.json").write_text(json.dumps({
            "normalized_name": "test_hive",
            "display_name": "Test Hive"
        }))

        # Test 1: config=None with config on disk
        config_disk = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })
        save_bees_config(config_disk)
        result1 = scan_for_hive("test_hive", config=None)
        assert result1 == hive_path

        # Test 2: config with empty hives
        config_empty = BeesConfig(hives={})
        result2 = scan_for_hive("test_hive", config=config_empty)
        assert result2 == hive_path

        # Test 3: config with populated hives
        config_populated = BeesConfig(hives={
            "test_hive": HiveConfig(display_name="Test Hive", path=str(hive_path), created_at=datetime.now().isoformat())
        })
        result3 = scan_for_hive("test_hive", config=config_populated)
        assert result3 == hive_path
