"""Tests for queen repo (elevated_repos) configuration validation.

Covers load_global_config() validation of the elevated_repos key, surfaced through
the _list_hives() MCP operation which returns invalid_config on any violation.
"""

import json
from pathlib import Path

import pytest

from src.mcp_hive_ops import _list_hives
from src.repo_context import repo_root_context
from tests.conftest import write_elevated_repos_config

# ---------------------------------------------------------------------------
# Parametrize cases for invalid elevated_repos structures
# Each value is written directly as the elevated_repos field in config.json.
# The helper write_elevated_repos_config() only accepts well-typed tuples, so
# invalid structures that cannot be expressed as (str, bool|None) tuples are
# written via direct config manipulation.
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

    async def test_write_elevated_repos_config_preserves_scopes(
        self,
        tmp_path: Path,
        mock_global_bees_dir: Path,
        monkeypatch,
    ):
        """write_elevated_repos_config() merges elevated_repos without clobbering scopes."""
        from tests.conftest import write_scoped_config

        monkeypatch.chdir(tmp_path)
        # First write a scoped config so scopes is populated
        write_scoped_config(
            mock_global_bees_dir,
            tmp_path,
            {"hives": {}, "child_tiers": {}},
        )
        config_before = json.loads((mock_global_bees_dir / "config.json").read_text())
        assert "scopes" in config_before

        # Now add elevated_repos — scopes must be preserved
        write_elevated_repos_config(mock_global_bees_dir, [("/some/path", None)])
        config_after = json.loads((mock_global_bees_dir / "config.json").read_text())

        assert "scopes" in config_after
        assert config_after["scopes"] == config_before["scopes"]
        assert "elevated_repos" in config_after
        assert config_after["elevated_repos"] == [{"path": "/some/path"}]
