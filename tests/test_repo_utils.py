"""
Unit tests for transport-agnostic repository root detection.

PURPOSE:
Tests filesystem utilities for detecting repository boundaries by scanning
the directory tree for .git markers. No MCP context or roots protocol involved.

SCOPE - Tests that belong here:
- get_repo_root_from_path(): Find repo root by scanning for .git
- .git directory detection
- Error handling: outside repo, missing .git, nested paths

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

# Tests for get_repo_root_from_path()


@pytest.mark.needs_real_git_check
class TestGetRepoRootFromPath:
    """Tests for get_repo_root_from_path()."""

    def test_finds_git_repo(self):
        """Test get_repo_root_from_path finds .git directory."""
        test_repo = Path(__file__).parent.parent
        result = get_repo_root_from_path(test_repo / "tests")
        assert result == test_repo
        assert (result / ".git").exists()

    def test_from_repo_root(self):
        """Test get_repo_root_from_path works when starting from repo root."""
        test_repo = Path(__file__).parent.parent
        assert get_repo_root_from_path(test_repo) == test_repo

    def test_raises_on_non_git(self):
        """Test get_repo_root_from_path returns resolved path when outside git repo."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_repo_root_from_path(Path(tmpdir))
            assert result == Path(tmpdir).resolve()

    def test_walks_up_tree(self):
        """Test get_repo_root_from_path walks up multiple levels."""
        test_repo = Path(__file__).parent.parent
        deep_path = test_repo / "tests" / "subfolder" / "nested"
        assert get_repo_root_from_path(deep_path) == test_repo
