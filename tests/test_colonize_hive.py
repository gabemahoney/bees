"""
Unit tests for hive colonization and hive discovery.

PURPOSE:
Tests hive directory creation, config registration, .hive marker file handling,
and hive recovery via filesystem scanning.

SCOPE - Tests that belong here:
- colonize_hive(): Directory creation, config registration, .hive marker
- Directory structure creation (.hive/identity.json)
- Idempotency (re-colonizing existing hive)
- Error handling: invalid paths, permission errors, duplicate names
- Name normalization during colonization
- .hive marker format and persistence
- Integration tests (real filesystem + config)
- Unit tests (mocked config system)

SCOPE - Tests that DON'T belong here:
- scan_for_hive() discovery -> test_mcp_scan_validate.py (uses it for validation)
- Hive path validation -> test_mcp_scan_validate.py
- Config registry operations -> test_config_registration.py
- Hive renaming -> test_mcp_rename_hive.py
- Hive sanitization/linting -> test_sanitize_hive.py
- MCP colonize_hive tool wrapper -> test_mcp_hive_*.py

RELATED FILES:
- test_mcp_scan_validate.py: Hive scanning and path validation
- test_config_registration.py: Hive registry operations
- test_mcp_rename_hive.py: Hive renaming functionality
"""

import json
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from src.mcp_hive_ops import _list_hives, colonize_hive_core as colonize_hive
from src.mcp_hive_utils import scan_for_hive
from src.repo_context import repo_root_context
from tests.test_constants import (
    RESULT_STATUS_SUCCESS,
)


class TestColonizeHive:
    """Tests for colonize_hive() function (integration tests)."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            yield tmp_path

    async def test_creates_directory_structure(self, git_repo_tmp_path):
        """Test that .hive directory is created during colonization, but NOT /evicted or /eggs."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        await colonize_hive("Test Hive", str(hive_path))

        assert not (hive_path / "eggs").exists(), "eggs/ should NOT be created during colonization"
        assert not (hive_path / "evicted").exists(), "evicted/ should NOT be created during colonization"
        assert (hive_path / ".hive").exists() and (hive_path / ".hive").is_dir()

    async def test_colonize_does_not_create_eggs_directory(self, git_repo_tmp_path):
        """Explicit test: colonize_hive should create only .hive/, NOT evicted/ or eggs/."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path))

        # Verify success
        assert result["status"] == RESULT_STATUS_SUCCESS

        # Verify only .hive/ exists, NOT evicted/ or eggs/
        assert (hive_path / ".hive").exists(), ".hive/ should exist"
        assert not (hive_path / "evicted").exists(), "evicted/ should NOT exist - no longer created on colonization"
        assert not (hive_path / "eggs").exists(), "eggs/ should NOT exist - it's created on-demand by ticket creation"

    async def test_idempotent_directory_creation(self, git_repo_tmp_path):
        """Test that function handles existing directories gracefully (exist_ok=True behavior)."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result1 = await colonize_hive("Test Hive", str(hive_path))
        assert result1["status"] == RESULT_STATUS_SUCCESS

        result2 = await colonize_hive("Test Hive 2", str(hive_path))
        assert result2["status"] == RESULT_STATUS_SUCCESS

        assert (hive_path / ".hive").exists()

    @pytest.mark.parametrize(
        "name, expected_normalized",
        [
            ("Multi Word Name", "multi_word_name"),
            ("UPPERCASE", "uppercase"),
            ("Back End", "back_end"),
        ],
    )
    async def test_name_normalization(self, git_repo_tmp_path, name, expected_normalized):
        """Test that function normalizes hive names correctly."""
        hive_path = git_repo_tmp_path / f"test_hive_{expected_normalized}"
        hive_path.mkdir()

        result = await colonize_hive(name, str(hive_path))

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["normalized_name"] == expected_normalized

    async def test_hive_marker_identity_file(self, git_repo_tmp_path):
        """Test that .hive marker stores correct identity data with all required fields."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        await colonize_hive("Back End", str(hive_path))

        identity_file = hive_path / ".hive" / "identity.json"
        assert identity_file.exists() and identity_file.is_file()

        with open(identity_file) as f:
            identity_data = json.load(f)

        # Verify correct data
        assert identity_data["normalized_name"] == "back_end"
        assert identity_data["display_name"] == "Back End"

        # Verify required fields exist with correct types
        assert isinstance(identity_data["created_at"], str) and identity_data["created_at"]
        assert isinstance(identity_data["version"], str) and identity_data["version"]

    async def test_handles_permission_error_on_marker_file_write(self, git_repo_tmp_path):
        """Test that function returns error dict on .hive identity file write failure."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        original_open = open

        def mock_open_func(file, *args, **kwargs):
            if "identity.json" in str(file):
                raise PermissionError("Permission denied")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", mock_open_func):
            result = await colonize_hive("Test Hive", str(hive_path))

            assert result["status"] == "error"
            assert result["error_type"] == "filesystem_error"
            assert "identity" in result["message"].lower()

    async def test_colonize_with_child_tiers(self, git_repo_tmp_path):
        """Test that colonize_hive accepts and stores child_tiers parameter."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        child_tiers = {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}
        result = await colonize_hive("Test Hive", str(hive_path), child_tiers=child_tiers)

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["child_tiers"] == child_tiers

        # Verify it was stored in config by reading the global config directly
        from src.config import load_global_config

        global_config = load_global_config()
        scope_data = global_config["scopes"].get(str(git_repo_tmp_path))
        assert scope_data is not None
        hive_data = scope_data["hives"].get("test_hive")
        assert hive_data is not None
        assert "child_tiers" in hive_data
        assert hive_data["child_tiers"] == child_tiers

    async def test_colonize_with_empty_child_tiers(self, git_repo_tmp_path):
        """Test that colonize_hive accepts empty child_tiers (bees-only hive)."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path), child_tiers={})

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["child_tiers"] == {}

        # Verify it was stored in config by reading the global config directly
        from src.config import load_global_config

        global_config = load_global_config()
        scope_data = global_config["scopes"].get(str(git_repo_tmp_path))
        assert scope_data is not None
        hive_data = scope_data["hives"].get("test_hive")
        assert hive_data is not None
        assert "child_tiers" in hive_data
        assert hive_data["child_tiers"] == {}

    async def test_colonize_without_child_tiers(self, git_repo_tmp_path):
        """Test that colonize_hive without child_tiers parameter stores None."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path))

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["child_tiers"] is None

        # Verify child_tiers key is NOT in the config (should be omitted when None)
        from src.config import load_global_config

        global_config = load_global_config()
        scope_data = global_config["scopes"].get(str(git_repo_tmp_path))
        assert scope_data is not None
        hive_data = scope_data["hives"].get("test_hive")
        assert hive_data is not None
        assert "child_tiers" not in hive_data  # Should be omitted when None

    async def test_colonize_with_invalid_child_tiers(self, git_repo_tmp_path):
        """Test that colonize_hive rejects invalid child_tiers configuration."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # Invalid: gap in tier keys (t1, t3 without t2)
        child_tiers = {"t1": ["Task", "Tasks"], "t3": ["Subtask", "Subtasks"]}
        result = await colonize_hive("Test Hive", str(hive_path), child_tiers=child_tiers)

        assert result["status"] == "error"
        assert result["error_type"] == "child_tiers_validation_error"
        assert "gap" in result["message"].lower() or "sequential" in result["message"].lower()

    @pytest.mark.parametrize(
        "invalid_key,expected_error_fragment",
        [
            pytest.param("tier1", "pattern", id="wrong_format_tier1"),
            pytest.param("task", "pattern", id="wrong_format_task"),
            pytest.param("t", "pattern", id="missing_number"),
            pytest.param("1", "pattern", id="missing_t_prefix"),
            pytest.param("t0", "start at 't1'", id="starts_at_t0"),
        ],
    )
    async def test_colonize_with_invalid_child_tiers_keys(
        self, git_repo_tmp_path, invalid_key, expected_error_fragment
    ):
        """Test that colonize_hive rejects child_tiers with invalid key formats."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        child_tiers = {invalid_key: ["Task", "Tasks"]}
        result = await colonize_hive("Test Hive", str(hive_path), child_tiers=child_tiers)

        assert result["status"] == "error"
        assert result["error_type"] == "child_tiers_validation_error"
        assert expected_error_fragment.lower() in result["message"].lower()

    async def test_colonize_rejects_child_tiers_exceeding_t9(self, git_repo_tmp_path):
        """Test that child_tiers with tier keys beyond T9 are rejected."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # T10 exceeds maximum supported depth of T9
        child_tiers = {f"t{i}": [f"Level{i}", f"Level{i}s"] for i in range(1, 11)}
        result = await colonize_hive("Test Hive", str(hive_path), child_tiers=child_tiers)

        assert result["status"] == "error"
        assert result["error_type"] == "child_tiers_validation_error"
        assert "t10" in result["message"]
        assert "9" in result["message"]

    async def test_colonize_accepts_t9_child_tiers(self, git_repo_tmp_path):
        """Test that child_tiers up to T9 are accepted (T9 is maximum)."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        child_tiers = {f"t{i}": [f"Level{i}", f"Level{i}s"] for i in range(1, 10)}
        result = await colonize_hive("Test Hive", str(hive_path), child_tiers=child_tiers)

        assert result["status"] == "success"


class TestScanForHive:
    """Tests for scan_for_hive() function."""

    @pytest.fixture(autouse=True)
    def set_repo_context(self, tmp_path, monkeypatch):
        """Override repo_root_context to tmp_path for all tests in this class."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir(exist_ok=True)
        with repo_root_context(tmp_path):
            yield

    async def test_finds_hive_by_marker(self, tmp_path):
        """Test that scan_for_hive finds a moved hive by its .hive marker."""
        hive_path = tmp_path / "tickets"
        hive_path.mkdir()
        await colonize_hive("Back End", str(hive_path))

        found_path = scan_for_hive("back_end")
        assert found_path == hive_path

    def test_returns_none_for_nonexistent_hive(self, tmp_path):
        """Test that scan_for_hive returns None if hive not found."""
        found_path = scan_for_hive("nonexistent")
        assert found_path is None

    async def test_finds_hive_in_subdirectory(self, tmp_path):
        """Test that scan_for_hive finds hives in nested directories."""
        hive_path = tmp_path / "nested" / "dir" / "tickets"
        hive_path.mkdir(parents=True)
        await colonize_hive("Nested Hive", str(hive_path))

        found_path = scan_for_hive("nested_hive")
        assert found_path == hive_path

    @pytest.mark.parametrize(
        "setup_type,search_name,expected_log",
        [
            pytest.param("orphaned", "other_hive", "orphaned", id="orphaned_marker"),
            pytest.param("missing_identity", "test_hive", "without identity.json", id="missing_identity"),
            pytest.param("corrupted", "test_hive", "Could not read identity", id="corrupted_identity"),
        ],
    )
    def test_scan_for_hive_marker_edge_cases(
        self, tmp_path, caplog, setup_type, search_name, expected_log
    ):
        """Test scan_for_hive handles various .hive marker edge cases."""
        import logging

        caplog.set_level(logging.WARNING)
        hive_path = tmp_path / f"{setup_type}_hive"
        hive_marker_path = hive_path / ".hive"
        hive_marker_path.mkdir(parents=True)

        if setup_type == "orphaned":
            with open(hive_marker_path / "identity.json", "w") as f:
                json.dump({"normalized_name": "orphaned_hive", "display_name": "Orphaned Hive",
                          "created_at": "2026-01-01T00:00:00", "version": "0.1"}, f)
        elif setup_type == "corrupted":
            with open(hive_marker_path / "identity.json", "w") as f:
                f.write("{ invalid json }")

        found_path = scan_for_hive(search_name)
        if setup_type != "orphaned":
            assert found_path is None
        assert any(expected_log in record.message.lower() if setup_type == "orphaned"
                   else expected_log in record.message for record in caplog.records)


class TestColonizeHiveOrchestrationUnit:
    """Unit tests for colonize_hive() orchestration logic with mocked config system."""

    @patch("src.mcp_hive_ops.save_global_config")
    @patch("src.mcp_hive_ops.load_global_config")
    @patch("src.mcp_hive_ops.save_bees_config")
    @patch("src.mcp_hive_ops.load_bees_config")
    @patch("src.mcp_hive_ops.validate_unique_hive_name")
    @patch("src.mcp_hive_ops.validate_hive_path")
    @patch("src.mcp_server.get_repo_root")
    @patch("src.mcp_hive_ops.normalize_hive_name")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    async def test_calls_normalize_name(
        self,
        mock_file_open,
        mock_mkdir,
        mock_normalize,
        mock_get_repo,
        mock_validate_path,
        mock_validate_unique,
        mock_load_config,
        mock_save_config,
        mock_load_global,
        mock_save_global,
    ):
        """Test that colonize_hive calls normalize_hive_name from config system."""
        mock_normalize.return_value = "back_end"
        mock_get_repo.return_value = Path("/repo")
        mock_validate_path.return_value = Path("/repo/tickets")
        mock_load_config.return_value = None
        mock_load_global.return_value = {"scopes": {}, "schema_version": "2.0"}

        await colonize_hive("Back End", "/repo/tickets")

        mock_normalize.assert_called_once_with("Back End")

    @patch("src.mcp_hive_ops.normalize_hive_name")
    async def test_returns_error_on_empty_normalized_name(self, mock_normalize):
        """Test that colonize_hive returns error when name normalizes to empty string."""
        mock_normalize.return_value = ""

        result = await colonize_hive("!!!", "/some/path")

        assert result["status"] == "error"
        assert result["error_type"] == "validation_error"
        assert "empty string" in result["message"]

    @patch("src.mcp_hive_ops.get_repo_root_from_path")
    @patch("src.mcp_hive_ops.normalize_hive_name")
    @patch("src.mcp_hive_ops.validate_hive_path")
    async def test_validates_hive_path_and_returns_error_on_invalid(
        self, mock_validate_path, mock_normalize, mock_get_repo_from_path
    ):
        """Test that colonize_hive calls validate_hive_path and returns error on invalid path."""
        mock_normalize.return_value = "backend"
        mock_get_repo_from_path.return_value = Path("/repo")
        mock_validate_path.side_effect = ValueError("Path must be absolute")

        result = await colonize_hive("Backend", "relative/path")

        mock_validate_path.assert_called_once_with("relative/path")
        assert result["status"] == "error"
        assert result["error_type"] == "path_validation_error"
        assert "must be absolute" in result["message"]

    @patch("src.mcp_hive_ops.validate_unique_hive_name")
    @patch("src.mcp_hive_ops.validate_hive_path")
    @patch("src.mcp_hive_ops.get_repo_root_from_path")
    @patch("src.mcp_hive_ops.normalize_hive_name")
    async def test_validates_unique_name_and_returns_error_on_duplicate(
        self, mock_normalize, mock_get_repo_from_path, mock_validate_path, mock_validate_unique
    ):
        """Test that colonize_hive validates unique name and returns error on duplicate."""
        mock_normalize.return_value = "backend"
        mock_get_repo_from_path.return_value = Path("/repo")
        mock_validate_path.return_value = Path("/repo/tickets")
        mock_validate_unique.side_effect = ValueError("Hive 'backend' already exists")

        result = await colonize_hive("Backend", "/repo/tickets")

        mock_validate_unique.assert_called_once_with("backend")
        assert result["status"] == "error"
        assert result["error_type"] == "duplicate_name_error"
        assert "already exists" in result["message"]

    @patch("src.mcp_hive_ops.save_global_config")
    @patch("src.mcp_hive_ops.load_global_config")
    @patch("src.mcp_hive_ops.save_bees_config")
    @patch("src.mcp_hive_ops.load_bees_config")
    @patch("src.mcp_hive_ops.validate_unique_hive_name")
    @patch("src.mcp_hive_ops.validate_hive_path")
    @patch("src.mcp_hive_ops.get_repo_root_from_path")
    @patch("src.mcp_hive_ops.normalize_hive_name")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    async def test_success_return_structure(
        self,
        mock_file_open,
        mock_mkdir,
        mock_normalize,
        mock_get_repo_from_path,
        mock_validate_path,
        mock_validate_unique,
        mock_load_config,
        mock_save_config,
        mock_load_global,
        mock_save_global,
    ):
        """Test that successful colonization returns correct structure."""
        mock_normalize.return_value = "backend"
        mock_get_repo_from_path.return_value = Path("/repo")
        mock_validate_path.return_value = Path("/repo/tickets")
        mock_load_config.return_value = None
        mock_load_global.return_value = {"scopes": {}, "schema_version": "2.0"}

        result = await colonize_hive("Backend", "/repo/tickets")

        assert result["status"] == "success"
        assert "message" in result
        assert result["normalized_name"] == "backend"
        assert result["display_name"] == "Backend"
        assert result["path"] == "/repo/tickets"

    @patch("src.mcp_hive_ops.normalize_hive_name")
    async def test_error_return_structure(self, mock_normalize):
        """Test that errors return consistent structure with validation_details."""
        mock_normalize.return_value = ""

        result = await colonize_hive("", "/some/path")

        assert result["status"] == "error"
        assert "message" in result
        assert "error_type" in result
        assert "validation_details" in result
        assert isinstance(result["validation_details"], dict)


class TestColonizeHiveChildTiers:
    """Integration tests for colonize_hive() with child_tiers parameter."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            yield tmp_path

    @pytest.mark.parametrize(
        "child_tiers,expected_in_result",
        [
            pytest.param(
                {"t1": ["Epic", "Epics"]},
                {"t1": ["Epic", "Epics"]},
                id="single_tier",
            ),
            pytest.param(
                {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
                {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
                id="two_tiers",
            ),
            pytest.param(
                {"t1": ["Phase", "Phases"], "t2": ["Step", "Steps"], "t3": ["Action", "Actions"]},
                {"t1": ["Phase", "Phases"], "t2": ["Step", "Steps"], "t3": ["Action", "Actions"]},
                id="three_tiers",
            ),
        ],
    )
    async def test_colonize_stores_child_tiers(self, git_repo_tmp_path, child_tiers, expected_in_result):
        """Test that colonize_hive stores child_tiers when provided."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path), child_tiers=child_tiers)

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["child_tiers"] == expected_in_result

    async def test_colonize_without_child_tiers_returns_none(self, git_repo_tmp_path):
        """Test that colonize_hive without child_tiers returns None in result."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path))

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["child_tiers"] is None

    async def test_colonize_with_empty_child_tiers_stores_bees_only(self, git_repo_tmp_path):
        """Test that colonize_hive with {} stores empty dict (bees-only mode)."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path), child_tiers={})

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["child_tiers"] == {}

    async def test_colonize_child_tiers_persisted_in_config(self, git_repo_tmp_path):
        """Test that child_tiers provided to colonize_hive are persisted in config."""
        from src.config import load_bees_config
        from src.repo_context import repo_root_context

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        child_tiers = {"t1": ["Epic", "Epics"]}
        result = await colonize_hive("Test Hive", str(hive_path), child_tiers=child_tiers)
        assert result["status"] == RESULT_STATUS_SUCCESS

        with repo_root_context(git_repo_tmp_path):
            config = load_bees_config()
            assert config is not None
            hive_config = config.hives["test_hive"]
            assert hive_config.child_tiers is not None
            assert "t1" in hive_config.child_tiers
            assert hive_config.child_tiers["t1"].singular == "Epic"
            assert hive_config.child_tiers["t1"].plural == "Epics"

    async def test_colonize_none_child_tiers_not_persisted(self, git_repo_tmp_path):
        """Test that colonize_hive without child_tiers leaves HiveConfig.child_tiers as None."""
        from src.config import load_bees_config
        from src.repo_context import repo_root_context

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path))
        assert result["status"] == RESULT_STATUS_SUCCESS

        with repo_root_context(git_repo_tmp_path):
            config = load_bees_config()
            assert config is not None
            hive_config = config.hives["test_hive"]
            assert hive_config.child_tiers is None

    async def test_colonize_empty_child_tiers_persisted_as_empty(self, git_repo_tmp_path):
        """Test that colonize_hive with {} persists empty dict, not None."""
        from src.config import load_bees_config
        from src.repo_context import repo_root_context

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path), child_tiers={})
        assert result["status"] == RESULT_STATUS_SUCCESS

        with repo_root_context(git_repo_tmp_path):
            config = load_bees_config()
            assert config is not None
            hive_config = config.hives["test_hive"]
            assert hive_config.child_tiers is not None
            assert hive_config.child_tiers == {}

    async def test_colonize_child_tiers_resolution_after_colonize(self, git_repo_tmp_path):
        """Test resolve_child_tiers_for_hive works correctly after colonizing with child_tiers."""
        from src.config import resolve_child_tiers_for_hive
        from src.repo_context import repo_root_context

        # First colonize a hive with scope-level tiers (no hive-level override)
        hive1_path = git_repo_tmp_path / "hive1"
        hive1_path.mkdir()
        result1 = await colonize_hive("Hive One", str(hive1_path))
        assert result1["status"] == RESULT_STATUS_SUCCESS

        # Then colonize a second hive WITH hive-level child_tiers
        hive2_path = git_repo_tmp_path / "hive2"
        hive2_path.mkdir()
        result2 = await colonize_hive(
            "Hive Two", str(hive2_path), child_tiers={"t1": ["Epic", "Epics"]}
        )
        assert result2["status"] == RESULT_STATUS_SUCCESS

        with repo_root_context(git_repo_tmp_path):
            # Hive 1: no hive-level tiers → falls through to scope (which is also empty/default)
            resolved1 = resolve_child_tiers_for_hive("hive_one")
            # Should return scope-level or default (empty = bees-only)
            assert isinstance(resolved1, dict)

            # Hive 2: has hive-level Epic tiers → returns those
            resolved2 = resolve_child_tiers_for_hive("hive_two")
            assert "t1" in resolved2
            assert resolved2["t1"].singular == "Epic"
            assert resolved2["t1"].plural == "Epics"

    async def test_colonize_invalid_child_tiers_returns_error(self, git_repo_tmp_path):
        """Test that colonize_hive returns error for invalid child_tiers (gap in tier keys)."""
        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        # t1 is missing, gap between t0 and t2
        result = await colonize_hive(
            "Test Hive", str(hive_path), child_tiers={"t2": ["Subtask", "Subtasks"]}
        )

        assert result["status"] == "error"
        assert result["error_type"] == "child_tiers_validation_error"


class TestColonizeHiveEggResolver:
    """Integration tests for colonize_hive() with egg_resolver parameter."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            yield tmp_path

    async def test_colonize_with_egg_resolver_persists_to_hive_config(self, git_repo_tmp_path):
        """Test that egg_resolver passed to colonize_hive is stored in HiveConfig."""
        from src.config import load_bees_config
        from src.repo_context import repo_root_context

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        resolver_path = "/repo/resolve_eggs.sh"
        result = await colonize_hive("Test Hive", str(hive_path), egg_resolver=resolver_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

        with repo_root_context(git_repo_tmp_path):
            config = load_bees_config()
            assert config is not None
            hive_config = config.hives["test_hive"]
            assert hive_config.egg_resolver == resolver_path

    async def test_colonize_without_egg_resolver_leaves_hive_config_none(self, git_repo_tmp_path):
        """Test that colonize_hive without egg_resolver leaves HiveConfig.egg_resolver as None."""
        from src.config import load_bees_config
        from src.repo_context import repo_root_context

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path))
        assert result["status"] == RESULT_STATUS_SUCCESS

        with repo_root_context(git_repo_tmp_path):
            config = load_bees_config()
            assert config is not None
            hive_config = config.hives["test_hive"]
            assert hive_config.egg_resolver is None

    @pytest.mark.parametrize(
        "egg_resolver,expected",
        [
            pytest.param("/repo/resolve.sh", "/repo/resolve.sh", id="with_resolver"),
            pytest.param(None, None, id="without_resolver"),
        ],
    )
    async def test_colonize_egg_resolver_saved_to_config(
        self, git_repo_tmp_path, egg_resolver, expected
    ):
        """Test that egg_resolver is correctly saved to config (or omitted when None)."""
        from src.config import load_global_config

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path), egg_resolver=egg_resolver)
        assert result["status"] == RESULT_STATUS_SUCCESS

        global_config = load_global_config()
        scope_data = global_config["scopes"].get(str(git_repo_tmp_path))
        assert scope_data is not None
        hive_data = scope_data["hives"].get("test_hive")
        assert hive_data is not None

        if expected is None:
            assert "egg_resolver" not in hive_data
        else:
            assert hive_data["egg_resolver"] == expected

    async def test_colonize_with_egg_resolver_timeout_persists_to_hive_config(self, git_repo_tmp_path):
        """Test that egg_resolver_timeout passed to colonize_hive is stored in HiveConfig."""
        from src.config import load_bees_config
        from src.repo_context import repo_root_context

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive(
            "Test Hive", str(hive_path), egg_resolver="/repo/resolve.sh", egg_resolver_timeout=5.0
        )
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["egg_resolver_timeout"] == 5.0

        with repo_root_context(git_repo_tmp_path):
            config = load_bees_config()
            assert config is not None
            hive_config = config.hives["test_hive"]
            assert hive_config.egg_resolver_timeout == 5.0

    async def test_colonize_without_egg_resolver_timeout_leaves_hive_config_none(self, git_repo_tmp_path):
        """Test that colonize_hive without egg_resolver_timeout leaves HiveConfig.egg_resolver_timeout as None."""
        from src.config import load_bees_config
        from src.repo_context import repo_root_context

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()

        result = await colonize_hive("Test Hive", str(hive_path))
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert "egg_resolver_timeout" not in result

        with repo_root_context(git_repo_tmp_path):
            config = load_bees_config()
            assert config is not None
            hive_config = config.hives["test_hive"]
            assert hive_config.egg_resolver_timeout is None


class TestColonizeHiveRepoRootContext:
    """Regression tests for b.W1f: colonize_hive_core must read repo_root from the
    ContextVar when repo_root param is None, not from get_repo_root_from_path().

    In a non-git directory, get_repo_root_from_path() falls back to Path.cwd()
    (the real project root), which is a different scope than what was set in the
    ContextVar. The fix makes colonize_hive_core try get_repo_root() first.

    These tests FAIL without the fix and PASS with it.
    """

    @pytest.mark.no_repo_context
    async def test_colonize_uses_context_var_repo_root_in_non_git_dir(self, tmp_path):
        """colonize_hive_core without repo_root arg must use the ContextVar, not path detection.

        Without the fix: get_repo_root_from_path(hive_path) returns Path.cwd() for a
        non-git tmp_path, registering the hive under the wrong scope. _list_hives then
        finds no hives under the ContextVar's tmp_path scope.

        With the fix: get_repo_root() reads the ContextVar (tmp_path), the hive is
        registered under that scope, and _list_hives returns it.
        """
        hive_path = tmp_path / "tickets"
        hive_path.mkdir()

        # Set the ContextVar to tmp_path (a non-git directory — no .git present).
        # colonize_hive_core must honour this rather than falling back to path detection.
        with repo_root_context(tmp_path):
            result = await colonize_hive("Test Hive", str(hive_path))

            assert result["status"] == RESULT_STATUS_SUCCESS, (
                f"colonize_hive_core failed: {result.get('message')}"
            )

            # _list_hives reads the same ContextVar; the hive must appear here.
            list_result = await _list_hives()

        assert list_result["status"] == RESULT_STATUS_SUCCESS
        hive_names = [h["normalized_name"] for h in list_result["hives"]]
        assert "test_hive" in hive_names, (
            "Hive was not registered under the ContextVar repo_root. "
            "colonize_hive_core likely called get_repo_root_from_path() instead of get_repo_root()."
        )
