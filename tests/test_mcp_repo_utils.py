"""Tests for MCP repository root detection utilities."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from src.mcp_repo_utils import get_repo_root_from_path, get_client_repo_root, get_repo_root
from fastmcp.exceptions import NotFoundError


# Tests for get_repo_root_from_path()

def test_get_repo_root_from_path_returns_resolved_path(tmp_path):
    """Test get_repo_root_from_path returns resolved absolute path."""
    result = get_repo_root_from_path(tmp_path)
    assert result == tmp_path.resolve()


def test_get_repo_root_from_path_resolves_subdirectory(tmp_path):
    """Test get_repo_root_from_path returns the resolved subdirectory, not a parent."""
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    result = get_repo_root_from_path(sub)
    assert result == sub.resolve()


def test_get_repo_root_from_path_no_error_without_git(tmp_path):
    """Test get_repo_root_from_path does not raise in non-git directory."""
    # Should not raise ValueError — bees does not require git
    result = get_repo_root_from_path(tmp_path)
    assert result == tmp_path.resolve()


def test_get_repo_root_from_path_resolves_symlinks(tmp_path):
    """Test get_repo_root_from_path resolves symlinks."""
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)

    result = get_repo_root_from_path(link)
    assert result == target.resolve()


# Tests for get_client_repo_root()

@pytest.mark.asyncio
async def test_get_client_repo_root_with_valid_roots():
    """Test get_client_repo_root extracts path from context."""
    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = "file:///Users/test/projects/myrepo"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)

    assert result == Path("/Users/test/projects/myrepo")


@pytest.mark.asyncio
async def test_get_client_repo_root_strips_file_prefix():
    """Test get_client_repo_root strips file:// prefix correctly."""
    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = "file:///home/user/code/project"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)

    assert result == Path("/home/user/code/project")
    assert "file://" not in str(result)


@pytest.mark.asyncio
async def test_get_client_repo_root_handles_no_file_prefix():
    """Test get_client_repo_root handles URIs without file:// prefix."""
    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = "/Users/test/projects/myrepo"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)

    assert result == Path("/Users/test/projects/myrepo")


@pytest.mark.asyncio
async def test_get_client_repo_root_returns_none_on_empty_roots():
    """Test get_client_repo_root returns None when roots list is empty."""
    ctx = Mock()

    async def mock_list_roots():
        return []

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_get_client_repo_root_returns_none_on_none_roots():
    """Test get_client_repo_root returns None when list_roots returns None."""
    ctx = Mock()

    async def mock_list_roots():
        return None

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_get_client_repo_root_returns_none_on_exception():
    """Test get_client_repo_root returns None when list_roots raises exception."""
    ctx = Mock()

    async def mock_list_roots():
        raise NotFoundError("Method not found (-32601)")

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_get_client_repo_root_uses_first_root():
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
async def test_get_repo_root_with_valid_context():
    """Test get_repo_root uses context to find repo root."""
    test_repo = Path(__file__).parent.parent

    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = f"file://{test_repo}"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    result = await get_repo_root(ctx)

    assert result == test_repo


@pytest.mark.asyncio
async def test_get_repo_root_returns_none_on_empty_roots():
    """Test get_repo_root returns None when context has empty roots."""
    ctx = Mock()

    async def mock_list_roots():
        return []

    ctx.list_roots = mock_list_roots

    result = await get_repo_root(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_get_repo_root_returns_none_on_none_roots():
    """Test get_repo_root returns None when roots protocol unavailable."""
    ctx = Mock()

    async def mock_list_roots():
        return None

    ctx.list_roots = mock_list_roots

    result = await get_repo_root(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_get_repo_root_falls_back_to_cwd_when_no_context():
    """Test get_repo_root uses cwd when ctx=None (for CLI/tests)."""
    result = await get_repo_root(ctx=None)

    # Should return cwd resolved
    assert result == Path.cwd().resolve()


@pytest.mark.asyncio
async def test_get_repo_root_returns_none_on_context_exception():
    """Test get_repo_root returns None when context raises exception."""
    ctx = Mock()

    async def mock_list_roots():
        raise NotFoundError("Method not found")

    ctx.list_roots = mock_list_roots

    result = await get_repo_root(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_get_repo_root_non_git_context_returns_resolved_path(tmp_path):
    """Test get_repo_root returns resolved path even for non-git directory in context."""
    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = f"file://{tmp_path}"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # Should NOT raise — just returns the resolved path
    result = await get_repo_root(ctx)
    assert result == tmp_path.resolve()


# Integration Tests

@pytest.mark.asyncio
async def test_repo_detection_full_workflow():
    """Test complete workflow: context extraction and path resolution."""
    test_repo = Path(__file__).parent.parent
    test_subdir = test_repo / "src"

    # Create context pointing to subdirectory
    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = f"file://{test_subdir}"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # Should extract from context and return resolved path (no git walk-up)
    result = await get_repo_root(ctx)

    assert result == test_subdir.resolve()


@pytest.mark.asyncio
async def test_logging_output(caplog):
    """Test that appropriate logging occurs during root detection."""
    import logging

    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = "file:///Users/test/repo"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    with caplog.at_level(logging.INFO):
        await get_client_repo_root(ctx)

    # Should log root detection
    assert any("Client provided" in record.message for record in caplog.records)
    assert any("Using first root" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_logging_on_roots_unavailable(caplog):
    """Test logging when roots protocol is unavailable."""
    import logging

    ctx = Mock()

    async def mock_list_roots():
        raise NotFoundError("Method not found")

    ctx.list_roots = mock_list_roots

    with caplog.at_level(logging.INFO):
        result = await get_client_repo_root(ctx)

    assert result is None
    assert any("doesn't support roots protocol" in record.message for record in caplog.records)
