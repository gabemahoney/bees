"""
Unit tests for MCP adapter repo root resolution.

PURPOSE:
Tests MCP-specific utilities for extracting repository root from MCP client
context via the roots protocol.

SCOPE - Tests that belong here:
- get_client_repo_root(): Extract repo from MCP context/roots protocol
- get_repo_root(): Unified repo detection with MCP context
- URI extraction and normalization
- Empty/None/exception failure modes
- Multi-root selection (uses first)
- Logging output during root detection

SCOPE - Tests that DON'T belong here:
- Filesystem path detection -> test_repo_utils.py
- Path validation -> test_mcp_hive_utils.py
- Hive scanning -> test_mcp_hive_utils.py
- Config repo_root usage -> test_config.py

RELATED FILES:
- test_repo_utils.py: Transport-agnostic filesystem path detection
- test_mcp_hive_utils.py: Hive path validation
"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastmcp.exceptions import NotFoundError

from src.mcp_roots import get_client_repo_root, get_repo_root


def _make_mock_ctx(uri=None, empty=False, none_roots=False, raises=False):
    """Helper to create mock MCP context."""
    ctx = Mock()

    async def mock_list_roots():
        if raises:
            raise NotFoundError("Method not found (-32601)")
        if none_roots:
            return None
        if empty:
            return []
        mock_root = Mock()
        mock_root.uri = uri
        return [mock_root]

    ctx.list_roots = mock_list_roots
    return ctx


@pytest.mark.asyncio
class TestGetClientRepoRoot:
    """Tests for get_client_repo_root()."""

    @pytest.mark.parametrize(
        "uri,expected_path",
        [
            pytest.param("file:///Users/test/projects/myrepo", Path("/Users/test/projects/myrepo"), id="with_file_prefix"),
            pytest.param("file:///home/user/code/project", Path("/home/user/code/project"), id="strips_file_prefix"),
            pytest.param("/Users/test/projects/myrepo", Path("/Users/test/projects/myrepo"), id="no_file_prefix"),
        ],
    )
    async def test_extracts_path_from_context(self, uri, expected_path):
        """Test get_client_repo_root extracts and normalizes path from context."""
        ctx = _make_mock_ctx(uri=uri)
        result = await get_client_repo_root(ctx)
        assert result == expected_path

    @pytest.mark.parametrize(
        "ctx_kwargs",
        [
            pytest.param({"empty": True}, id="empty_roots"),
            pytest.param({"none_roots": True}, id="none_roots"),
            pytest.param({"raises": True}, id="exception"),
        ],
    )
    async def test_returns_none_on_failure(self, ctx_kwargs):
        """Test get_client_repo_root returns None on various failure modes."""
        ctx = _make_mock_ctx(**ctx_kwargs)
        assert await get_client_repo_root(ctx) is None

    async def test_uses_first_root(self):
        """Test get_client_repo_root uses first root when multiple provided."""
        ctx = Mock()
        mock_root1 = Mock()
        mock_root1.uri = "file:///Users/test/repo1"
        mock_root2 = Mock()
        mock_root2.uri = "file:///Users/test/repo2"

        async def mock_list_roots():
            return [mock_root1, mock_root2]

        ctx.list_roots = mock_list_roots
        result = await get_client_repo_root(ctx)
        assert result == Path("/Users/test/repo1")


# Tests for get_repo_root()


@pytest.mark.asyncio
class TestGetRepoRoot:
    """Tests for get_repo_root()."""

    async def test_with_valid_context(self):
        """Test get_repo_root uses context to find repo root."""
        test_repo = Path(__file__).parent.parent
        ctx = _make_mock_ctx(uri=f"file://{test_repo}")
        assert await get_repo_root(ctx) == test_repo

    @pytest.mark.parametrize(
        "ctx_kwargs",
        [
            pytest.param({"empty": True}, id="empty_roots"),
            pytest.param({"none_roots": True}, id="none_roots"),
            pytest.param({"raises": True}, id="exception"),
        ],
    )
    async def test_returns_none_on_failure(self, ctx_kwargs):
        """Test get_repo_root returns None on various failure modes."""
        ctx = _make_mock_ctx(**ctx_kwargs)
        assert await get_repo_root(ctx) is None

    @pytest.mark.needs_real_git_check
    async def test_falls_back_to_cwd_when_no_context(self):
        """Test get_repo_root uses cwd when ctx=None (for CLI/tests)."""
        result = await get_repo_root(ctx=None)
        test_repo = Path(__file__).parent.parent
        assert result == test_repo
        assert (result / ".git").exists()

    @pytest.mark.needs_real_git_check
    async def test_invalid_git_path_in_context(self):
        """Test get_repo_root returns resolved path when context points to non-git directory."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = _make_mock_ctx(uri=f"file://{tmpdir}")
            result = await get_repo_root(ctx)
            assert result == Path(tmpdir).resolve()


# Integration Tests


@pytest.mark.asyncio
async def test_repo_detection_full_workflow():
    """Test complete workflow: context extraction, path walking, repo detection."""
    test_repo = Path(__file__).parent.parent
    ctx = _make_mock_ctx(uri=f"file://{test_repo / 'src'}")
    result = await get_repo_root(ctx)
    assert result == test_repo
    assert (result / ".git").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,ctx_factory,expected_log",
    [
        pytest.param(
            "success",
            lambda: _make_mock_ctx(uri="file:///Users/test/repo"),
            "Client provided",
            id="logs_on_success",
        ),
        pytest.param(
            "unavailable",
            lambda: _make_mock_ctx(raises=True),
            "doesn't support roots protocol",
            id="logs_on_unavailable",
        ),
    ],
)
async def test_logging_output(caplog, scenario, ctx_factory, expected_log):
    """Test that appropriate logging occurs during root detection."""
    import logging

    with caplog.at_level(logging.INFO):
        await get_client_repo_root(ctx_factory())

    assert any(expected_log in record.message for record in caplog.records)
