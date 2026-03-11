"""Tests for queen repo (elevated_repos) configuration validation.

Covers:
- load_global_config() validation of elevated_repos, surfaced through _list_hives()
- check_queen_elevation() pure function
- check_queen_write_access() pure function
"""

import json
from pathlib import Path

import pytest

from src.config import check_queen_elevation, check_queen_write_access
from src.mcp_hive_ops import _list_hives
from src.repo_context import repo_root_context
from tests.conftest import write_elevated_repos_config

# ---------------------------------------------------------------------------
# Parametrize cases for invalid elevated_repos structures
# ---------------------------------------------------------------------------
_INVALID_ELEVATED_REPOS_VALUES = [
    pytest.param([{"write": True}], id="missing_path_key"),
    pytest.param([{"path": 123}], id="path_not_a_string"),
    pytest.param([{"path": "/some/path", "write": "yes"}], id="write_not_bool"),
    pytest.param("oops", id="not_a_list"),
]


class TestElevatedReposConfigValidation:
    """Config validation for elevated_repos surfaced via list_hives."""

    @pytest.mark.parametrize("elevated_repos_value", _INVALID_ELEVATED_REPOS_VALUES)
    async def test_invalid_elevated_repos_returns_invalid_config(
        self,
        elevated_repos_value,
        tmp_path: Path,
        mock_global_bees_dir: Path,
        monkeypatch,
    ):
        """Invalid elevated_repos structures cause list_hives to return invalid_config."""
        monkeypatch.chdir(tmp_path)
        config = {
            "scopes": {},
            "schema_version": "2.0",
            "elevated_repos": elevated_repos_value,
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(config))

        with repo_root_context(tmp_path):
            result = await _list_hives(resolved_root=tmp_path)

        assert result["status"] == "error"
        assert result["error_type"] == "invalid_config"

    async def test_nonexistent_elevated_repos_path_no_error(
        self,
        tmp_path: Path,
        mock_global_bees_dir: Path,
        monkeypatch,
    ):
        """Non-existent path in elevated_repos is silently accepted (no error)."""
        monkeypatch.chdir(tmp_path)
        write_elevated_repos_config(
            mock_global_bees_dir,
            [("/nonexistent/path/that/does/not/exist", True)],
        )

        with repo_root_context(tmp_path):
            result = await _list_hives(resolved_root=tmp_path)

        assert result["status"] == "success"


class TestCheckQueenElevation:
    """Unit tests for check_queen_elevation() in src/config.py."""

    def test_no_elevated_repos_key(self, tmp_path: Path):
        """Returns (False, False) when elevated_repos absent from config."""
        is_queen, has_write = check_queen_elevation(tmp_path, {})
        assert (is_queen, has_write) == (False, False)

    def test_repo_not_in_list(self, tmp_path: Path):
        """Returns (False, False) when resolved_root not in elevated_repos."""
        other = tmp_path / "other"
        other.mkdir()
        config = {"elevated_repos": [{"path": str(other)}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (False, False)

    def test_matching_entry_no_write_key(self, tmp_path: Path):
        """Returns (True, False) when matching entry has no write key."""
        config = {"elevated_repos": [{"path": str(tmp_path)}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (True, False)

    def test_matching_entry_write_true(self, tmp_path: Path):
        """Returns (True, True) when matching entry has write: true."""
        config = {"elevated_repos": [{"path": str(tmp_path), "write": True}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (True, True)

    def test_matching_entry_write_false(self, tmp_path: Path):
        """Returns (True, False) when matching entry has write: false."""
        config = {"elevated_repos": [{"path": str(tmp_path), "write": False}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (True, False)

    def test_nonexistent_path_skipped(self, tmp_path: Path):
        """Entries whose path doesn't exist on disk are skipped — no match, no error."""
        config = {"elevated_repos": [{"path": "/nonexistent/path/xyz"}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (False, False)

    def test_nonexistent_path_skipped_even_if_listed_before_real_match(self, tmp_path: Path):
        """Nonexistent entries before a real match are skipped; real match still found."""
        config = {
            "elevated_repos": [
                {"path": "/nonexistent/path/xyz"},
                {"path": str(tmp_path), "write": True},
            ]
        }
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (True, True)


class TestCheckQueenWriteAccess:
    """Unit tests for check_queen_write_access() in src/config.py."""

    def test_non_queen_repo_returns_none(self, tmp_path: Path):
        """Non-queen repo always has write access — returns None."""
        result = check_queen_write_access(tmp_path, {})
        assert result is None

    def test_queen_with_write_true_returns_none(self, tmp_path: Path):
        """Queen repo with write=True has write access — returns None."""
        config = {"elevated_repos": [{"path": str(tmp_path), "write": True}]}
        result = check_queen_write_access(tmp_path, config)
        assert result is None

    def test_queen_without_write_returns_permission_denied(self, tmp_path: Path):
        """Queen repo without write access returns permission_denied error dict."""
        config = {"elevated_repos": [{"path": str(tmp_path)}]}
        result = check_queen_write_access(tmp_path, config)
        assert result is not None
        assert result["error_type"] == "permission_denied"

    def test_queen_with_write_false_returns_permission_denied(self, tmp_path: Path):
        """Queen repo with write=False returns permission_denied error dict."""
        config = {"elevated_repos": [{"path": str(tmp_path), "write": False}]}
        result = check_queen_write_access(tmp_path, config)
        assert result is not None
        assert result["error_type"] == "permission_denied"
