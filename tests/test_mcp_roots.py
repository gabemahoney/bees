"""Tests for MCP roots protocol integration."""
import pytest
from pathlib import Path
from unittest.mock import Mock
from src.mcp_repo_utils import get_client_repo_root, get_repo_root
from src.config import load_bees_config
from src.repo_context import repo_root_context


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
    assert result is not None



@pytest.mark.asyncio
async def test_load_bees_config_with_repo_root():
    """Test load_bees_config uses explicit repo_root."""
    test_repo = Path(__file__).parent.parent

    # This should work with the test repo's actual config
    with repo_root_context(test_repo):
        config = load_bees_config()

    # Config might be None if no .bees/config.json exists yet, which is fine
    # The important thing is it doesn't raise an error about wrong directory
    assert config is None or hasattr(config, 'hives')



# Phase 2 Tests - Critical MCP Tools

@pytest.mark.asyncio
async def test_list_hives_uses_context():
    """Test that list_hives uses resolved_root to find hives."""
    from src.mcp_hive_ops import _list_hives

    test_repo = Path(__file__).parent.parent

    # Should use resolved_root to find hives
    with repo_root_context(test_repo):
        result = await _list_hives(resolved_root=test_repo)
    assert "status" in result
    # May have hives or not, but should succeed
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_create_ticket_uses_context():
    """Test that create_ticket uses repo_root_context."""
    from src.mcp_ticket_ops import _create_ticket

    test_repo = Path(__file__).parent.parent

    # Should use repo_root_context to find hive config
    # Returns error dict when hive doesn't exist, validating context was used
    with repo_root_context(test_repo):
        result = await _create_ticket(
            ticket_type="task",
            title="Test",
            hive_name="nonexistent_hive_for_test",
        )
    assert result["status"] == "error"
    assert result["error_type"] == "hive_not_found"


@pytest.mark.asyncio
async def test_colonize_hive_uses_context():
    """Test that colonize_hive uses repo_root to find repo root."""
    from src.mcp_hive_ops import colonize_hive_core

    test_repo = Path(__file__).parent.parent

    # Create a hive in the test repo
    hive_path = test_repo / "test_context_hive"
    hive_path.mkdir(exist_ok=True)

    try:
        with repo_root_context(test_repo):
            result = await colonize_hive_core(
                name="Test Context Hive",
                path=str(hive_path),
                repo_root=test_repo,
            )

        # Should succeed using context
        assert result["status"] == "success"
        assert result["normalized_name"] == "test_context_hive"

        # Clean up created hive
        import shutil
        if hive_path.exists():
            shutil.rmtree(hive_path)
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
    """Test _create_ticket works with repo_root_context."""
    from src.mcp_ticket_ops import _create_ticket

    test_repo = Path(__file__).parent.parent

    # Should work with repo_root_context
    # Returns error dict when hive doesn't exist, validating context was used
    with repo_root_context(test_repo):
        result = await _create_ticket(
            ticket_type="task",
            title="Test Task",
            hive_name="nonexistent_test_hive",
        )
    assert result["status"] == "error"
    assert result["error_type"] == "hive_not_found"


@pytest.mark.asyncio
async def test_show_ticket_works_with_context():
    """Test _show_ticket works with resolved_root."""
    from src.mcp_ticket_ops import _show_ticket

    test_repo = Path(__file__).parent.parent

    # Should work with resolved_root
    # Will return not_found for nonexistent ticket
    with repo_root_context(test_repo):
        result = await _show_ticket(
            ticket_ids=["b.zzz"],
            resolved_root=test_repo,
        )
    assert result["status"] == "success"
    assert "b.zzz" in result["not_found"]


@pytest.mark.asyncio
async def test_execute_freeform_query_works_with_context():
    """Test _execute_freeform_query works with resolved_root."""
    from src.mcp_query_ops import _execute_freeform_query

    test_repo = Path(__file__).parent.parent

    # Should work with resolved_root
    # Simple query that should execute successfully (needs stages key)
    with repo_root_context(test_repo):
        result = await _execute_freeform_query(
            query_yaml="stages:\n  - [type=epic]",
            resolved_root=test_repo,
        )

    # Should succeed and return proper structure
    assert "status" in result
    assert result["status"] == "success"
