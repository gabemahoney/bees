"""
Unit tests for colonize_hive() and scan_for_hive() functions.

Tests directory creation, error handling, idempotency of hive colonization,
and .hive marker functionality for hive recovery.

Includes both unit tests (mocking config system) and integration tests (real filesystem).
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from src.mcp_server import colonize_hive, scan_for_hive


class TestColonizeHive:
    """Tests for colonize_hive() function (integration tests)."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        # Create .git directory to make it a git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        # Change to tmp_path so get_repo_root() works
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_creates_eggs_directory(self, git_repo_tmp_path):
        """Test that /eggs directory is created during colonization."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        eggs_path = hive_path / "eggs"
        assert eggs_path.exists()
        assert eggs_path.is_dir()

    def test_creates_evicted_directory(self, git_repo_tmp_path):
        """Test that /evicted directory is created during colonization."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        evicted_path = hive_path / "evicted"
        assert evicted_path.exists()
        assert evicted_path.is_dir()

    def test_creates_both_subdirectories(self, git_repo_tmp_path):
        """Test that both /eggs and /evicted directories are created."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        eggs_path = hive_path / "eggs"
        evicted_path = hive_path / "evicted"

        assert eggs_path.exists()
        assert evicted_path.exists()

    def test_idempotent_directory_creation(self, git_repo_tmp_path):
        """Test that function handles existing directories gracefully (exist_ok=True behavior)."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # First call - creates directories
        result1 = colonize_hive("Test Hive", str(hive_path))
        assert result1["status"] == "success"

        # Second call - directories already exist, should return error for duplicate name
        result2 = colonize_hive("Test Hive 2", str(hive_path))
        assert result2["status"] == "success"

        # Verify directories still exist
        assert (hive_path / "eggs").exists()
        assert (hive_path / "evicted").exists()

    def test_creates_parent_directories(self, git_repo_tmp_path):
        """Test that function creates parent directories for /eggs and /evicted if hive path exists."""
        # Create hive path but not subdirectories
        hive_path = git_repo_tmp_path / "nested" / "parent" / "test_hive"
        hive_path.mkdir(parents=True)

        # Hive path exists but subdirectories don't
        assert hive_path.exists()
        assert not (hive_path / "eggs").exists()

        result = colonize_hive("Test Hive", str(hive_path))

        # Should create subdirectories
        assert (hive_path / "eggs").exists()
        assert (hive_path / "evicted").exists()

    def test_returns_normalized_name(self, git_repo_tmp_path):
        """Test that function returns normalized hive name."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Back End", str(hive_path))

        assert result["status"] == "success"
        assert result["normalized_name"] == "back_end"

    def test_returns_hive_path(self, git_repo_tmp_path):
        """Test that function returns hive path in response."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        assert result["status"] == "success"
        assert result["path"] == str(hive_path)

    def test_response_structure(self, git_repo_tmp_path):
        """Test that function returns correct response structure."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        # Verify response has all expected keys
        assert "status" in result
        assert "normalized_name" in result
        assert "path" in result
        assert result["status"] == "success"

    def test_handles_spaces_in_hive_name(self, git_repo_tmp_path):
        """Test that function handles hive names with spaces correctly."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Multi Word Name", str(hive_path))

        assert result["status"] == "success"
        assert result["normalized_name"] == "multi_word_name"
        assert (hive_path / "eggs").exists()
        assert (hive_path / "evicted").exists()

    def test_handles_uppercase_in_hive_name(self, git_repo_tmp_path):
        """Test that function handles uppercase in hive names correctly."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("UPPERCASE", str(hive_path))

        assert result["status"] == "success"
        assert result["normalized_name"] == "uppercase"

    def test_creates_hive_marker(self, git_repo_tmp_path):
        """Test that .hive marker directory is created during colonization."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        hive_marker_path = hive_path / ".hive"
        assert hive_marker_path.exists()
        assert hive_marker_path.is_dir()

    def test_hive_marker_contains_identity_file(self, git_repo_tmp_path):
        """Test that .hive marker contains identity.json file."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        assert identity_file.exists()
        assert identity_file.is_file()

    def test_hive_marker_has_correct_data(self, git_repo_tmp_path):
        """Test that .hive marker stores correct identity data."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Back End", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        with open(identity_file, 'r') as f:
            identity_data = json.load(f)

        assert identity_data["normalized_name"] == "back_end"
        assert identity_data["display_name"] == "Back End"

    def test_hive_marker_data_structure(self, git_repo_tmp_path):
        """Test that .hive marker has required fields."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        with open(identity_file, 'r') as f:
            identity_data = json.load(f)

        assert "normalized_name" in identity_data
        assert "display_name" in identity_data
        assert "created_at" in identity_data
        assert "version" in identity_data

    def test_hive_marker_has_timestamp(self, git_repo_tmp_path):
        """Test that .hive marker includes creation timestamp."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        with open(identity_file, 'r') as f:
            identity_data = json.load(f)

        # Verify timestamp exists and is non-empty
        assert "created_at" in identity_data
        assert identity_data["created_at"]
        assert isinstance(identity_data["created_at"], str)

    def test_hive_marker_has_version(self, git_repo_tmp_path):
        """Test that .hive marker includes version field."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = colonize_hive("Test Hive", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        with open(identity_file, 'r') as f:
            identity_data = json.load(f)

        # Verify version exists and is in expected format
        assert "version" in identity_data
        assert identity_data["version"]
        assert isinstance(identity_data["version"], str)

    def test_handles_permission_error_on_eggs_creation(self, git_repo_tmp_path):
        """Test that function returns error dict on /eggs creation failure."""
        from unittest.mock import patch

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Mock Path.mkdir to raise PermissionError on /eggs creation
        original_mkdir = Path.mkdir
        def mock_mkdir(self, *args, **kwargs):
            if self.name == "eggs":
                raise PermissionError("Permission denied")
            return original_mkdir(self, *args, **kwargs)

        with patch.object(Path, 'mkdir', mock_mkdir):
            result = colonize_hive("Test Hive", str(hive_path))

            # Verify error response structure
            assert result["status"] == "error"
            assert result["error_type"] == "filesystem_error"
            assert "eggs" in result["message"].lower()

    def test_handles_os_error_on_evicted_creation(self, git_repo_tmp_path):
        """Test that function returns error dict on /evicted creation failure."""
        from unittest.mock import patch

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Mock Path.mkdir to raise OSError on /evicted creation
        original_mkdir = Path.mkdir
        def mock_mkdir(self, *args, **kwargs):
            if self.name == "evicted":
                raise OSError("Disk full")
            return original_mkdir(self, *args, **kwargs)

        with patch.object(Path, 'mkdir', mock_mkdir):
            result = colonize_hive("Test Hive", str(hive_path))

            # Verify error response structure
            assert result["status"] == "error"
            assert result["error_type"] == "filesystem_error"

    def test_handles_permission_error_on_marker_file_write(self, git_repo_tmp_path):
        """Test that function returns error dict on .hive identity file write failure."""
        from unittest.mock import patch

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Mock open to raise PermissionError on identity.json write
        original_open = open
        def mock_open_func(file, *args, **kwargs):
            if "identity.json" in str(file):
                raise PermissionError("Permission denied")
            return original_open(file, *args, **kwargs)

        with patch('builtins.open', mock_open_func):
            result = colonize_hive("Test Hive", str(hive_path))

            # Verify error response structure
            assert result["status"] == "error"
            assert result["error_type"] == "filesystem_error"
            assert "identity" in result["message"].lower()

    def test_linter_stub_placeholder_exists(self, git_repo_tmp_path):
        """Test that colonize_hive includes linter stub placeholder without breaking functionality."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Call colonize_hive and verify it succeeds with linter stub in place
        result = colonize_hive("Test Hive", str(hive_path))

        # Verify colonize_hive completes successfully (linter stub is non-breaking)
        assert result["status"] == "success"
        assert result["normalized_name"] == "test_hive"

        # Verify all expected directories were created despite linter stub
        assert (hive_path / "eggs").exists()
        assert (hive_path / "evicted").exists()
        assert (hive_path / ".hive").exists()

    def test_linter_stub_code_exists_in_source(self):
        """Test that linter stub TODO comment exists in colonize_hive source code."""
        import inspect
        from src.mcp_server import colonize_hive

        # Get source code of colonize_hive function
        source = inspect.getsource(colonize_hive)

        # Verify linter stub TODO comment is present
        assert "TODO: Linter integration stub" in source or "TODO" in source and "linter" in source.lower()
        assert "conflicting tickets" in source.lower() or "linter" in source.lower()


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

        # Create a .hive marker manually (without going through colonize_hive)
        # This creates an orphaned marker not in config
        hive_path = tmp_path / "orphaned_hive"
        hive_marker_path = hive_path / ".hive"
        hive_marker_path.mkdir(parents=True)

        identity_file = hive_marker_path / "identity.json"
        import json
        with open(identity_file, 'w') as f:
            json.dump({
                "normalized_name": "orphaned_hive",
                "display_name": "Orphaned Hive",
                "created_at": "2026-01-01T00:00:00",
                "version": "1.0.0"
            }, f)

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


class TestColonizeHiveOrchestrationUnit:
    """Unit tests for colonize_hive() orchestration logic with mocked config system."""

    @patch('src.mcp_server.init_bees_config_if_needed')
    @patch('src.mcp_server.save_bees_config')
    @patch('src.mcp_server.validate_unique_hive_name')
    @patch('src.mcp_server.validate_hive_path')
    @patch('src.mcp_server.get_repo_root')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', new_callable=mock_open)
    def test_calls_normalize_name(
        self,
        mock_file_open,
        mock_mkdir,
        mock_normalize,
        mock_get_repo,
        mock_validate_path,
        mock_validate_unique,
        mock_save_config,
        mock_init_config
    ):
        """Test that colonize_hive calls normalize_hive_name from config system."""
        mock_normalize.return_value = 'back_end'
        mock_get_repo.return_value = Path('/repo')
        mock_validate_path.return_value = Path('/repo/tickets')
        mock_config = MagicMock()
        mock_config.hives = {}
        mock_init_config.return_value = mock_config

        colonize_hive('Back End', '/repo/tickets')

        mock_normalize.assert_called_once_with('Back End')

    @patch('src.mcp_server.normalize_hive_name')
    def test_returns_error_on_empty_normalized_name(self, mock_normalize):
        """Test that colonize_hive returns error when name normalizes to empty string."""
        mock_normalize.return_value = ''

        result = colonize_hive('!!!', '/some/path')

        assert result['status'] == 'error'
        assert result['error_type'] == 'validation_error'
        assert 'empty string' in result['message']

    @patch('src.mcp_server.get_repo_root')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('src.mcp_server.validate_hive_path')
    def test_calls_validate_hive_path(
        self,
        mock_validate_path,
        mock_normalize,
        mock_get_repo
    ):
        """Test that colonize_hive calls validate_hive_path from config system."""
        mock_normalize.return_value = 'backend'
        mock_get_repo.return_value = Path('/repo')
        mock_validate_path.side_effect = ValueError("Path error")

        result = colonize_hive('Backend', 'relative/path')

        mock_validate_path.assert_called_once_with('relative/path', Path('/repo'))

    @patch('src.mcp_server.get_repo_root')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('src.mcp_server.validate_hive_path')
    def test_returns_error_on_invalid_path(
        self,
        mock_validate_path,
        mock_normalize,
        mock_get_repo
    ):
        """Test that colonize_hive returns error on invalid path validation."""
        mock_normalize.return_value = 'backend'
        mock_get_repo.return_value = Path('/repo')
        mock_validate_path.side_effect = ValueError("Path must be absolute")

        result = colonize_hive('Backend', 'relative/path')

        assert result['status'] == 'error'
        assert result['error_type'] == 'path_validation_error'
        assert 'must be absolute' in result['message']

    @patch('src.mcp_server.validate_unique_hive_name')
    @patch('src.mcp_server.validate_hive_path')
    @patch('src.mcp_server.get_repo_root')
    @patch('src.mcp_server.normalize_hive_name')
    def test_calls_validate_unique_hive_name(
        self,
        mock_normalize,
        mock_get_repo,
        mock_validate_path,
        mock_validate_unique
    ):
        """Test that colonize_hive calls validate_unique_hive_name from config system."""
        mock_normalize.return_value = 'backend'
        mock_get_repo.return_value = Path('/repo')
        mock_validate_path.return_value = Path('/repo/tickets')
        mock_validate_unique.side_effect = ValueError("Name exists")

        result = colonize_hive('Backend', '/repo/tickets')

        mock_validate_unique.assert_called_once_with('backend')

    @patch('src.mcp_server.validate_unique_hive_name')
    @patch('src.mcp_server.validate_hive_path')
    @patch('src.mcp_server.get_repo_root')
    @patch('src.mcp_server.normalize_hive_name')
    def test_returns_error_on_duplicate_name(
        self,
        mock_normalize,
        mock_get_repo,
        mock_validate_path,
        mock_validate_unique
    ):
        """Test that colonize_hive returns error on duplicate normalized name."""
        mock_normalize.return_value = 'backend'
        mock_get_repo.return_value = Path('/repo')
        mock_validate_path.return_value = Path('/repo/tickets')
        mock_validate_unique.side_effect = ValueError("Hive 'backend' already exists")

        result = colonize_hive('Backend', '/repo/tickets')

        assert result['status'] == 'error'
        assert result['error_type'] == 'duplicate_name_error'
        assert 'already exists' in result['message']

    @patch('src.mcp_server.write_hive_config_dict')
    @patch('src.mcp_server.register_hive_dict')
    @patch('src.mcp_server.validate_unique_hive_name')
    @patch('src.mcp_server.validate_hive_path')
    @patch('src.mcp_server.get_repo_root')
    @patch('src.mcp_server.normalize_hive_name')
    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', new_callable=mock_open)
    def test_success_return_structure(
        self,
        mock_file_open,
        mock_mkdir,
        mock_normalize,
        mock_get_repo,
        mock_validate_path,
        mock_validate_unique,
        mock_register_hive,
        mock_write_config
    ):
        """Test that successful colonization returns correct structure."""
        mock_normalize.return_value = 'backend'
        mock_get_repo.return_value = Path('/repo')
        mock_validate_path.return_value = Path('/repo/tickets')
        # Mock register_hive_dict to return a config dict
        mock_register_hive.return_value = {
            'hives': {'backend': {'path': '/repo/tickets', 'display_name': 'Backend'}},
            'allow_cross_hive_dependencies': False,
            'schema_version': '1.0'
        }

        result = colonize_hive('Backend', '/repo/tickets')

        assert result['status'] == 'success'
        assert 'message' in result
        assert result['normalized_name'] == 'backend'
        assert result['display_name'] == 'Backend'
        assert result['path'] == '/repo/tickets'

    @patch('src.mcp_server.normalize_hive_name')
    def test_error_return_structure(self, mock_normalize):
        """Test that errors return consistent structure with validation_details."""
        mock_normalize.return_value = ''

        result = colonize_hive('', '/some/path')

        assert result['status'] == 'error'
        assert 'message' in result
        assert 'error_type' in result
        assert 'validation_details' in result
        assert isinstance(result['validation_details'], dict)
