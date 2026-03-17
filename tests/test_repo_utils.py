"""
Unit tests for transport-agnostic repository root detection.

PURPOSE:
Tests filesystem utilities that resolve a path to its canonical absolute form.
No git traversal, no .git scanning, no MCP context involved.

SCOPE - Tests that belong here:
- get_repo_root_from_path(): Returns start_path.resolve() directly

SCOPE - Tests that DON'T belong here:
- MCP client/context tests -> test_mcp_adapter.py
- Path validation -> test_mcp_hive_utils.py
- Hive scanning -> test_mcp_hive_utils.py
- Config repo_root usage -> test_config.py
- Repo context management -> test_repo_context.py

RELATED FILES:
- test_mcp_adapter.py: MCP context and roots protocol tests
- test_mcp_hive_utils.py: Hive path validation
"""

from pathlib import Path

import pytest

from src.repo_utils import get_repo_root_from_path


class TestGetRepoRootFromPath:
    """Tests for get_repo_root_from_path() — always returns start_path.resolve()."""

    def test_returns_resolved_path(self, tmp_path):
        """Returns the resolved form of the given path."""
        result = get_repo_root_from_path(tmp_path)
        assert result == tmp_path.resolve()

    def test_returns_subdirectory_not_parent(self, tmp_path):
        """Returns the given subdirectory itself, not any parent."""
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        result = get_repo_root_from_path(sub)
        assert result == sub.resolve()
        assert result != tmp_path.resolve()

    def test_regression_inside_git_repo_returns_self_not_git_root(self, tmp_path):
        """Regression for b.ij5: a path inside a git repo returns itself, not the git root."""
        # Simulate a parent "git repo" with a .git dir
        git_root = tmp_path / "repo"
        (git_root / ".git").mkdir(parents=True)
        inner = git_root / "subdir"
        inner.mkdir()

        result = get_repo_root_from_path(inner)

        # Must return the inner path, NOT the git root
        assert result == inner.resolve()
        assert result != git_root.resolve()

    def test_nonexistent_path_resolves(self, tmp_path):
        """Works with a path that does not yet exist on disk."""
        phantom = tmp_path / "does" / "not" / "exist"
        result = get_repo_root_from_path(phantom)
        assert result == phantom.resolve()
