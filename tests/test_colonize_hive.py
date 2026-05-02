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

from src.config import load_global_config
from src.mcp_hive_ops import _list_hives, colonize_hive_core as colonize_hive
from src.mcp_hive_utils import scan_for_hive
from src.repo_context import repo_root_context
from tests.conftest import write_multi_scope_config
from tests.test_constants import (
    RESULT_STATUS_SUCCESS,
    SCOPE_PATTERN_PROJECTS_DEEP,
    SCOPE_PATTERN_PROJECTS_EXACT,
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

    @patch("src.mcp_hive_ops.save_global_config")
    @patch("src.mcp_hive_ops.load_global_config")
    @patch("src.mcp_hive_ops.save_bees_config")
    @patch("src.mcp_hive_ops.load_bees_config")
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


# ============================================================================
# SCOPE PARAMETER TESTS
# ============================================================================


class TestColonizeHiveScope:
    """Integration tests for the scope parameter in colonize_hive_core."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            yield tmp_path

    async def test_scope_creates_new_scope_entry(self, git_repo_tmp_path, mock_global_bees_dir):
        """scope parameter registers hive under the given pattern as config key."""
        hive_path = git_repo_tmp_path / "scoped_hive"
        # Use parent/* so it matches git_repo_tmp_path (one level deep from parent)
        scope = str(git_repo_tmp_path.parent) + "/*"

        result = await colonize_hive("Scoped Hive", str(hive_path), scope=scope)

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = json.loads((mock_global_bees_dir / "config.json").read_text())
        assert scope in config["scopes"]
        assert "scoped_hive" in config["scopes"][scope]["hives"]

    async def test_scope_adds_hive_to_existing_scope(self, git_repo_tmp_path, mock_global_bees_dir):
        """Hive is added to existing scope entry while preserving existing hives."""
        # Use parent/* — matches git_repo_tmp_path so load_bees_config() can find it
        scope = str(git_repo_tmp_path.parent) + "/*"
        existing_path = str(git_repo_tmp_path / "existing")

        write_multi_scope_config(
            mock_global_bees_dir,
            {
                scope: {
                    "hives": {
                        "existing_hive": {
                            "path": existing_path,
                            "display_name": "Existing Hive",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                }
            },
        )

        new_hive_path = git_repo_tmp_path / "new_hive"
        result = await colonize_hive("New Hive", str(new_hive_path), scope=scope)

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = json.loads((mock_global_bees_dir / "config.json").read_text())
        hives = config["scopes"][scope]["hives"]
        assert "existing_hive" in hives
        assert "new_hive" in hives

    @pytest.mark.parametrize(
        "scope",
        [
            pytest.param("/foo/*/bar", id="mid_path_wildcard"),
            pytest.param("/a/*/b/**", id="mid_wildcard_with_terminal"),
            pytest.param("/x/*/y/z", id="mid_path_three_segments"),
        ],
    )
    async def test_scope_invalid_pattern_wildcard_non_terminal(self, git_repo_tmp_path, scope):
        """Mid-path wildcards return invalid_scope_pattern before any filesystem ops."""
        hive_path = git_repo_tmp_path / "bad_hive"
        result = await colonize_hive("Bad Hive", str(hive_path), scope=scope)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_scope_pattern"

    async def test_scope_non_canonical_string_reuses_existing_scope(self, git_repo_tmp_path, mock_global_bees_dir):
        """Non-canonical scope string that canonicalizes to an existing key is treated as re-use, not conflict."""
        # /foo/bar (no trailing slash) canonicalizes to /foo/bar/ — same as the existing key
        # → should succeed and place the hive in the existing /foo/bar/ scope entry
        write_multi_scope_config(
            mock_global_bees_dir,
            {"/foo/bar/": {"hives": {}}},
        )

        hive_path = git_repo_tmp_path / "reuse_hive"
        result = await colonize_hive("Reuse Hive", str(hive_path), scope="/foo/bar")

        assert result["status"] == "success"

    async def test_scope_different_prefix_same_tier_no_conflict(self, git_repo_tmp_path, mock_global_bees_dir):
        """Different bare prefixes at same tier do NOT conflict (fixes false-positive bug)."""
        # /foo/bar/* and /baz/qux/* have the same tier but different prefixes → no conflict
        write_multi_scope_config(
            mock_global_bees_dir,
            {"/foo/bar/*": {"hives": {}}},
        )

        hive_path = git_repo_tmp_path / "no_conflict_hive"
        result = await colonize_hive("No Conflict Hive", str(hive_path), scope="/baz/qux/*")

        # Should succeed (different bare prefix → no scope conflict)
        assert result["status"] == "success"

    async def test_scope_same_hive_name_at_more_specific_scope_is_blocked(self, git_repo_tmp_path, mock_global_bees_dir):
        """Same hive name at a more specific overlapping scope is now blocked.

        A "My Hive" at /projects/** blocks a "My Hive" at /projects/sub/ because
        the scopes overlap and cross-scope conflict prevention catches it.
        """
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                "/projects/**": {
                    "hives": {
                        "my_hive": {
                            "path": str(git_repo_tmp_path / "existing"),
                            "display_name": "My Hive",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                }
            },
        )

        hive_path = git_repo_tmp_path / "dup_hive"
        result = await colonize_hive("My Hive", str(hive_path), scope="/projects/sub/")

        assert result["status"] == "error"
        assert result["error_type"] == "cross_scope_hive_conflict"


# ============================================================================
# CROSS-SCOPE CONFLICT PREVENTION TESTS
# ============================================================================


class TestColonizeHiveCrossScopeConflict:
    """Tests for cross-scope hive name conflict detection during colonization."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            yield tmp_path

    @pytest.mark.parametrize(
        "existing_scope,colonize_scope",
        [
            pytest.param(
                SCOPE_PATTERN_PROJECTS_EXACT,
                SCOPE_PATTERN_PROJECTS_DEEP,
                id="exact_exists_colonize_deep",
            ),
            pytest.param(
                SCOPE_PATTERN_PROJECTS_DEEP,
                SCOPE_PATTERN_PROJECTS_EXACT,
                id="deep_exists_colonize_exact",
            ),
        ],
    )
    async def test_cross_scope_conflict_both_directions(
        self, git_repo_tmp_path, mock_global_bees_dir, existing_scope, colonize_scope
    ):
        """Colonizing a hive name that exists in an overlapping scope returns cross_scope_hive_conflict."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                existing_scope: {
                    "hives": {
                        "bugs": {
                            "path": str(git_repo_tmp_path / "existing_bugs"),
                            "display_name": "Bugs",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                }
            },
        )

        hive_path = git_repo_tmp_path / "new_bugs"
        result = await colonize_hive("Bugs", str(hive_path), scope=colonize_scope)

        assert result["status"] == "error"
        assert result["error_type"] == "cross_scope_hive_conflict"
        assert "bugs" in result["message"]

    async def test_cross_scope_conflict_disjoint_scopes_succeed(
        self, git_repo_tmp_path, mock_global_bees_dir
    ):
        """Same hive name under completely disjoint scopes succeeds (no overlap)."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                "/alpha/**": {
                    "hives": {
                        "bugs": {
                            "path": str(git_repo_tmp_path / "alpha_bugs"),
                            "display_name": "Bugs",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                }
            },
        )

        hive_path = git_repo_tmp_path / "beta_bugs"
        result = await colonize_hive("Bugs", str(hive_path), scope="/beta/**")

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["normalized_name"] == "bugs"

    async def test_cross_scope_conflict_same_scope_regression(
        self, git_repo_tmp_path, mock_global_bees_dir
    ):
        """Same normalized name in the exact same scope returns duplicate_hive_name (not cross_scope)."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                SCOPE_PATTERN_PROJECTS_DEEP: {
                    "hives": {
                        "bugs": {
                            "path": str(git_repo_tmp_path / "existing_bugs"),
                            "display_name": "Bugs",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                }
            },
        )

        hive_path = git_repo_tmp_path / "dup_bugs"
        result = await colonize_hive("Bugs", str(hive_path), scope=SCOPE_PATTERN_PROJECTS_DEEP)

        assert result["status"] == "error"
        assert result["error_type"] == "duplicate_hive_name"


# ============================================================================
# SCOPE SELECTION TESTS (wildcard vs exact-path)
# ============================================================================


class TestColonizeHiveScopeSelection:
    """Tests that colonize_hive registers hives in exact-path scopes, not wildcard parents."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        """Create a temporary directory with git repo structure."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            yield tmp_path

    async def test_wildcard_parent_scope_creates_new_exact_scope(
        self, git_repo_tmp_path, mock_global_bees_dir
    ):
        """Wildcard parent scope exists but no exact scope → hive goes in new exact-path scope, not wildcard."""
        wildcard_pattern = str(git_repo_tmp_path.parent) + "/**"
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                wildcard_pattern: {
                    "hives": {
                        "other_hive": {
                            "path": str(git_repo_tmp_path.parent / "other" / "tickets"),
                            "display_name": "Other Hive",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                }
            },
        )

        hive_path = git_repo_tmp_path / "tickets"
        result = await colonize_hive("Tickets", str(hive_path))

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = load_global_config()
        exact_scope = str(git_repo_tmp_path)
        # Hive must be in the new exact-path scope keyed by str(repo_root) (no trailing slash)
        assert exact_scope in config["scopes"]
        assert "tickets" in config["scopes"][exact_scope]["hives"]
        # Hive must NOT appear in the wildcard scope
        assert "tickets" not in config["scopes"].get(wildcard_pattern, {}).get("hives", {})

    async def test_exact_scope_exists_hive_added_to_it(
        self, git_repo_tmp_path, mock_global_bees_dir
    ):
        """Exact scope already exists for repo_root → new hive is added to that scope."""
        exact_scope = str(git_repo_tmp_path) + "/"
        existing_hive_path = str(git_repo_tmp_path / "existing_tickets")
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                exact_scope: {
                    "hives": {
                        "existing": {
                            "path": existing_hive_path,
                            "display_name": "Existing",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                }
            },
        )

        hive_path = git_repo_tmp_path / "new_tickets"
        result = await colonize_hive("New Tickets", str(hive_path))

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = load_global_config()
        scope_hives = config["scopes"][exact_scope]["hives"]
        # Both old and new hive present in the same exact scope
        assert "existing" in scope_hives
        assert "new_tickets" in scope_hives
        # No extra scope was created
        assert len(config["scopes"]) == 1

    async def test_no_scope_creates_exact_path_scope(
        self, git_repo_tmp_path, mock_global_bees_dir
    ):
        """No pre-existing scopes → colonize_hive creates a new exact-path scope for repo_root."""
        hive_path = git_repo_tmp_path / "tickets"
        result = await colonize_hive("Tickets", str(hive_path))

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = load_global_config()
        # Exactly one scope should exist, keyed by repo_root (exact path, no wildcards)
        assert len(config["scopes"]) == 1
        scope_key = next(iter(config["scopes"]))
        assert "*" not in scope_key
        assert "tickets" in config["scopes"][scope_key]["hives"]

    async def test_wildcard_and_exact_scope_both_exist_uses_exact(
        self, git_repo_tmp_path, mock_global_bees_dir
    ):
        """Both wildcard parent AND exact scope exist → hive is added to exact scope, not wildcard."""
        wildcard_pattern = str(git_repo_tmp_path.parent) + "/**"
        exact_scope = str(git_repo_tmp_path)
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                wildcard_pattern: {
                    "hives": {
                        "parent_hive": {
                            "path": str(git_repo_tmp_path.parent / "parent_tickets"),
                            "display_name": "Parent Hive",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                },
                exact_scope: {
                    "hives": {
                        "existing": {
                            "path": str(git_repo_tmp_path / "existing"),
                            "display_name": "Existing",
                            "created_at": "2026-01-01T00:00:00",
                        }
                    }
                },
            },
        )

        hive_path = git_repo_tmp_path / "new_tickets"
        result = await colonize_hive("New Tickets", str(hive_path))

        assert result["status"] == RESULT_STATUS_SUCCESS
        config = load_global_config()
        # New hive must be in the exact scope
        assert "new_tickets" in config["scopes"][exact_scope]["hives"]
        # Wildcard scope must be untouched
        assert "new_tickets" not in config["scopes"].get(wildcard_pattern, {}).get("hives", {})


class TestColonizeHiveDescription:
    """Tests for the optional description field on hives."""

    @pytest.fixture
    def git_repo_tmp_path(self, tmp_path, monkeypatch):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            yield tmp_path

    async def test_colonize_with_description(self, git_repo_tmp_path):
        """Colonizing a hive with description stores it in config."""
        hive_path = git_repo_tmp_path / "tickets"
        hive_path.mkdir()

        result = await colonize_hive("Tickets", str(hive_path), description="Bug tracking hive")

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["description"] == "Bug tracking hive"

        config = load_global_config()
        scope_key = str(git_repo_tmp_path)
        hive_data = config["scopes"][scope_key]["hives"]["tickets"]
        assert hive_data["description"] == "Bug tracking hive"

    async def test_colonize_without_description(self, git_repo_tmp_path):
        """Colonizing a hive without description omits it from config."""
        hive_path = git_repo_tmp_path / "tickets"
        hive_path.mkdir()

        result = await colonize_hive("Tickets", str(hive_path))

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert "description" not in result

        config = load_global_config()
        scope_key = str(git_repo_tmp_path)
        hive_data = config["scopes"][scope_key]["hives"]["tickets"]
        assert "description" not in hive_data

    async def test_list_hives_includes_description(self, git_repo_tmp_path):
        """list_hives returns description when set."""
        hive_path = git_repo_tmp_path / "tickets"
        hive_path.mkdir()

        await colonize_hive("Tickets", str(hive_path), description="Bug tracking")

        result = await _list_hives(resolved_root=git_repo_tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert len(result["hives"]) == 1
        assert result["hives"][0]["description"] == "Bug tracking"

    async def test_list_hives_omits_description_when_none(self, git_repo_tmp_path):
        """list_hives omits description field when not set."""
        hive_path = git_repo_tmp_path / "tickets"
        hive_path.mkdir()

        await colonize_hive("Tickets", str(hive_path))

        result = await _list_hives(resolved_root=git_repo_tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert len(result["hives"]) == 1
        assert "description" not in result["hives"][0]
