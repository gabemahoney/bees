"""Tests for MCP roots protocol integration."""
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from src.mcp_repo_utils import get_client_repo_root, get_repo_root
from src.config import get_config_path, load_bees_config


@pytest.mark.asyncio
async def test_get_client_repo_root_with_valid_context():
    """Test extracting repo root from context with roots."""
    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = "file:///Users/test/projects/finance-tracker"

    # Mock the async list_roots method
    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)
    assert result == Path("/Users/test/projects/finance-tracker")


@pytest.mark.asyncio
async def test_get_client_repo_root_returns_none_on_empty_roots():
    """Test returns None when client provides empty roots."""
    ctx = Mock()

    # Mock the async list_roots method returning empty list
    async def mock_list_roots():
        return []

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)
    assert result is None


@pytest.mark.asyncio
async def test_get_client_repo_root_returns_none_on_none_roots():
    """Test returns None when client's list_roots returns None."""
    ctx = Mock()

    # Mock the async list_roots method returning None
    async def mock_list_roots():
        return None

    ctx.list_roots = mock_list_roots

    result = await get_client_repo_root(ctx)
    assert result is None


@pytest.mark.asyncio
async def test_get_repo_root_with_context():
    """Test get_repo_root uses context to find .git directory."""
    ctx = Mock()
    mock_root = Mock()
    # Use actual test repo path
    test_repo = Path(__file__).parent.parent
    mock_root.uri = f"file://{test_repo}"

    # Mock the async list_roots method
    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    result = await get_repo_root(ctx)
    assert result == test_repo
    assert (result / ".git").exists()


@pytest.mark.asyncio
async def test_get_config_path_with_repo_root():
    """Test get_config_path uses explicit repo_root."""
    test_repo = Path(__file__).parent.parent
    config_path = get_config_path(repo_root=test_repo)

    assert config_path == test_repo / ".bees" / "config.json"
    assert "test_mcp_roots.py" not in str(config_path)


@pytest.mark.asyncio
async def test_load_bees_config_with_repo_root():
    """Test load_bees_config uses explicit repo_root."""
    test_repo = Path(__file__).parent.parent

    # This should work with the test repo's actual config
    config = load_bees_config(repo_root=test_repo)

    # Config might be None if no .bees/config.json exists yet, which is fine
    # The important thing is it doesn't raise an error about wrong directory
    assert config is None or hasattr(config, 'hives')


@pytest.mark.needs_real_git_check
def test_get_config_path_raises_without_git_repo():
    """Test get_config_path raises ValueError when not in git repo and no repo_root provided."""
    import tempfile
    import os

    # Create a temporary directory that's not in a git repo
    with tempfile.TemporaryDirectory() as tmpdir:
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Should raise ValueError since tmpdir is not in a git repo and no repo_root provided
            with pytest.raises(ValueError, match="repo_root is required"):
                get_config_path()
        finally:
            os.chdir(old_cwd)


# Phase 2 Tests - Critical MCP Tools

@pytest.mark.asyncio
async def test_list_hives_uses_context():
    """Test that list_hives uses client context to find hives."""
    from src.mcp_server import _list_hives

    ctx = Mock()
    mock_root = Mock()
    # Point to actual test repo
    test_repo = Path(__file__).parent.parent
    mock_root.uri = f"file://{test_repo}"

    # Mock the async list_roots method
    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # This should not raise and should use the context
    result = await _list_hives(ctx=ctx)
    assert "status" in result
    # May have hives or not, but should succeed
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_create_ticket_uses_context():
    """Test that create_ticket uses client context."""
    from src.mcp_server import _create_ticket

    ctx = Mock()
    mock_root = Mock()
    test_repo = Path(__file__).parent.parent
    mock_root.uri = f"file://{test_repo}"

    # Mock the async list_roots method
    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # Should use context to find hive config
    # This will fail if hive doesn't exist, but that's expected
    with pytest.raises(ValueError, match="not found in config"):
        await _create_ticket(
            ticket_type="task",
            title="Test",
            hive_name="nonexistent_hive_for_test",
            ctx=ctx
        )


@pytest.mark.asyncio
async def test_colonize_hive_uses_context():
    """Test that colonize_hive uses client context to find repo root."""
    from src.mcp_server import colonize_hive_core

    ctx = Mock()
    mock_root = Mock()
    test_repo = Path(__file__).parent.parent
    mock_root.uri = f"file://{test_repo}"

    # Mock the async list_roots method
    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # Create a hive in the test repo
    hive_path = test_repo / "test_context_hive"
    hive_path.mkdir(exist_ok=True)

    try:
        result = await colonize_hive_core(
            name="Test Context Hive",
            path=str(hive_path),
            ctx=ctx
        )

        # Should succeed using context
        assert result["status"] == "success"
        assert result["normalized_name"] == "test_context_hive"

        # Clean up created hive
        import shutil
        if hive_path.exists():
            shutil.rmtree(hive_path)

        # Remove from config
        from src.config import load_bees_config, save_bees_config
        config = load_bees_config(test_repo)
        if config and "test_context_hive" in config.hives:
            del config.hives["test_context_hive"]
            save_bees_config(config, test_repo)
    finally:
        # Cleanup
        import shutil
        if hive_path.exists():
            shutil.rmtree(hive_path)


# Phase 4 Tests - get_repo_root() Error Behavior

@pytest.mark.asyncio
@pytest.mark.needs_real_git_check
async def test_get_repo_root_uses_cwd_when_no_context():
    """Test get_repo_root falls back to cwd when ctx=None (for CLI/tests)."""
    # get_repo_root() is allowed to fall back to Path.cwd() when ctx=None
    # This is intentional for CLI and test usage, unlike get_config_path()
    # which was changed to require explicit repo_root
    result = await get_repo_root(ctx=None)
    # Should return the current working directory's git repo root
    # (which will be the bees repo since tests run from there)
    assert result is not None
    assert result == Path(__file__).parent.parent


@pytest.mark.asyncio
async def test_get_repo_root_returns_none_on_empty_roots():
    """Test get_repo_root returns None when context has empty roots."""
    ctx = Mock()

    # Mock list_roots to return empty list (client supports roots but none configured)
    async def mock_list_roots():
        return []

    ctx.list_roots = mock_list_roots

    # Should return None when roots are empty
    result = await get_repo_root(ctx=ctx)
    assert result is None


@pytest.mark.asyncio
async def test_get_repo_root_returns_none_on_none_roots():
    """Test get_repo_root returns None when context returns None roots."""
    ctx = Mock()

    # Mock list_roots to return None (client doesn't support roots protocol)
    async def mock_list_roots():
        return None

    ctx.list_roots = mock_list_roots

    # Should return None when roots protocol unavailable
    result = await get_repo_root(ctx=ctx)
    assert result is None


# Phase 5 Tests - MCP Functions Work With Context

@pytest.mark.asyncio
async def test_create_ticket_works_with_context():
    """Test _create_ticket works with MCP context."""
    from src.mcp_server import _create_ticket

    test_repo = Path(__file__).parent.parent

    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = f"file://{test_repo}"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # Should work with context
    # Will fail because hive doesn't exist, but that validates context was used
    with pytest.raises(ValueError, match="not found in config"):
        await _create_ticket(
            ticket_type="task",
            title="Test Task",
            hive_name="nonexistent_test_hive",
            ctx=ctx
        )


@pytest.mark.asyncio
async def test_show_ticket_works_with_context():
    """Test _show_ticket works with MCP context."""
    from src.mcp_server import _show_ticket

    test_repo = Path(__file__).parent.parent

    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = f"file://{test_repo}"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # Should work with context
    # Will fail with ticket error, which validates context was used
    with pytest.raises(ValueError, match="(Ticket file not found|Ticket does not exist|Hive.*not found)"):
        await _show_ticket(
            ticket_id="bugs.bees-xxx",
            ctx=ctx
        )


@pytest.mark.asyncio
async def test_execute_freeform_query_works_with_context():
    """Test _execute_freeform_query works with MCP context."""
    from src.mcp_server import _execute_freeform_query

    test_repo = Path(__file__).parent.parent

    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = f"file://{test_repo}"

    async def mock_list_roots():
        return [mock_root]

    ctx.list_roots = mock_list_roots

    # Should work with context
    # Simple query that should execute successfully
    result = await _execute_freeform_query(
        query_yaml="- ['type=epic']",
        ctx=ctx
    )

    # Should succeed and return proper structure
    assert "status" in result
    assert result["status"] == "success"
