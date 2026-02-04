"""Tests for MCP repository root detection utilities."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from src.mcp_repo_utils import get_repo_root_from_path, get_client_repo_root, get_repo_root


# Tests for get_repo_root_from_path()

@pytest.mark.needs_real_git_check
def test_get_repo_root_from_path_finds_git_repo():
    """Test get_repo_root_from_path finds .git directory."""
    # Use the actual test repo's path
    test_repo = Path(__file__).parent.parent
    test_subdir = test_repo / "tests"

    result = get_repo_root_from_path(test_subdir)

    assert result == test_repo
    assert (result / ".git").exists()


@pytest.mark.needs_real_git_check
def test_get_repo_root_from_path_from_repo_root():
    """Test get_repo_root_from_path works when starting from repo root."""
    test_repo = Path(__file__).parent.parent

    result = get_repo_root_from_path(test_repo)

    assert result == test_repo
    assert (result / ".git").exists()


@pytest.mark.needs_real_git_check
def test_get_repo_root_from_path_raises_on_non_git():
    """Test get_repo_root_from_path raises ValueError outside git repo."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        with pytest.raises(ValueError, match="Not in a git repository"):
            get_repo_root_from_path(temp_path)


@pytest.mark.needs_real_git_check
def test_get_repo_root_from_path_walks_up_tree():
    """Test get_repo_root_from_path walks up multiple levels."""
    test_repo = Path(__file__).parent.parent
    # Go down multiple levels
    deep_path = test_repo / "tests" / "subfolder" / "nested"

    # Even though deep_path doesn't exist, resolve() normalizes it
    result = get_repo_root_from_path(deep_path)

    assert result == test_repo


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
        raise Exception("Method not found (-32601)")

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
@pytest.mark.needs_real_git_check
async def test_get_repo_root_falls_back_to_cwd_when_no_context():
    """Test get_repo_root uses cwd when ctx=None (for CLI/tests)."""
    result = await get_repo_root(ctx=None)

    # Should return the test repo since we're running from it
    test_repo = Path(__file__).parent.parent
    assert result == test_repo
    assert (result / ".git").exists()


@pytest.mark.asyncio
async def test_get_repo_root_returns_none_on_context_exception():
    """Test get_repo_root returns None when context raises exception."""
    ctx = Mock()

    async def mock_list_roots():
        raise Exception("Method not found")

    ctx.list_roots = mock_list_roots

    result = await get_repo_root(ctx)

    assert result is None


@pytest.mark.asyncio
@pytest.mark.needs_real_git_check
async def test_get_repo_root_with_invalid_git_path_in_context():
    """Test get_repo_root raises ValueError when context points to non-git directory."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = Mock()
        mock_root = Mock()
        mock_root.uri = f"file://{tmpdir}"

        async def mock_list_roots():
            return [mock_root]

        ctx.list_roots = mock_list_roots

        # Should raise because tmpdir is not a git repo
        with pytest.raises(ValueError, match="Not in a git repository"):
            await get_repo_root(ctx)


# Integration Tests

@pytest.mark.asyncio
async def test_repo_detection_full_workflow():
    """Test complete workflow: context extraction, path walking, repo detection."""
    test_repo = Path(__file__).parent.parent
    test_subdir = test_repo / "src"

    # Create context pointing to subdirectory
    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = f"file://{test_subdir}"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # Should extract from context, then walk up to find .git
    result = await get_repo_root(ctx)

    assert result == test_repo
    assert (result / ".git").exists()


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
        raise Exception("Method not found")

    ctx.list_roots = mock_list_roots

    with caplog.at_level(logging.INFO):
        result = await get_client_repo_root(ctx)

    assert result is None
    assert any("doesn't support roots protocol" in record.message for record in caplog.records)
