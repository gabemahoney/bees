"""Tests for MCP roots protocol integration."""
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from src.mcp_server import get_client_repo_root, get_repo_root
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
async def test_get_client_repo_root_raises_on_empty_roots():
    """Test error when client doesn't provide roots."""
    ctx = Mock()
    
    # Mock the async list_roots method returning empty list
    async def mock_list_roots():
        return []
    
    ctx.list_roots = mock_list_roots
    
    with pytest.raises(ValueError, match="Unable to determine repository location"):
        await get_client_repo_root(ctx)


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


def test_get_config_path_raises_without_git_repo():
    """Test get_config_path raises ValueError when not in git repo and no repo_root provided."""
    import tempfile
    import os
    
    # Create a temporary directory that's not in a git repo
    with tempfile.TemporaryDirectory() as tmpdir:
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            
            # Should raise ValueError since tmpdir is not in a git repo
            with pytest.raises(ValueError, match="Not in a git repository"):
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
    result = await _list_hives(ctx)
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
    with pytest.raises(ValueError, match="does not exist in config"):
        await _create_ticket(
            ticket_type="task",
            title="Test",
            hive_name="nonexistent_hive_for_test",
            ctx=ctx
        )


@pytest.mark.asyncio
async def test_colonize_hive_uses_context():
    """Test that colonize_hive uses client context."""
    from src.mcp_server import colonize_hive_core
    import tempfile
    
    ctx = Mock()
    mock_root = Mock()
    test_repo = Path(__file__).parent.parent
    mock_root.uri = f"file://{test_repo}"
    
    # Mock the async list_roots method
    async def mock_list_roots():
        return [mock_root]
    
    ctx.list_roots = mock_list_roots
    
    # Try to colonize with an invalid path (outside repo) - should fail validation
    with tempfile.TemporaryDirectory() as tmpdir:
        result = await colonize_hive_core(
            name="Test Hive",
            path=tmpdir,  # Path outside repo
            ctx=ctx
        )
        
        # Should fail because path is outside repo
        assert result["status"] == "error"
        assert "outside" in result["message"].lower() or "within" in result["message"].lower()
