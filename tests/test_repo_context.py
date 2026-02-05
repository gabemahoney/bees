"""Tests for repo_context module.

Verifies async-safe, request-scoped state management for repo_root.
"""

import asyncio
import pytest
from pathlib import Path
from src.repo_context import (
    get_repo_root,
    set_repo_root,
    reset_repo_root,
    repo_root_context,
)


@pytest.mark.no_repo_context
def test_get_repo_root_raises_when_not_set():
    """Verify get_repo_root() raises RuntimeError when context not set."""
    with pytest.raises(RuntimeError) as exc_info:
        get_repo_root()
    
    assert "repo_root not set in context" in str(exc_info.value)
    assert "MCP entry points must call set_repo_root()" in str(exc_info.value)


def test_set_and_get_repo_root():
    """Test set_repo_root() stores value and get_repo_root() retrieves it."""
    test_path = Path("/test/repo/path")
    token = set_repo_root(test_path)
    
    try:
        result = get_repo_root()
        assert result == test_path
    finally:
        reset_repo_root(token)


@pytest.mark.no_repo_context
def test_reset_repo_root():
    """Test reset_repo_root() clears context."""
    test_path = Path("/test/repo/path")
    token = set_repo_root(test_path)
    
    # Verify it's set
    assert get_repo_root() == test_path
    
    # Reset and verify it raises
    reset_repo_root(token)
    with pytest.raises(RuntimeError):
        get_repo_root()


@pytest.mark.no_repo_context
def test_repo_root_context_manager():
    """Test repo_root_context() sets and cleans up properly."""
    test_path = Path("/test/repo/path")
    
    # Verify not set before
    with pytest.raises(RuntimeError):
        get_repo_root()
    
    # Use context manager
    with repo_root_context(test_path):
        assert get_repo_root() == test_path
    
    # Verify cleaned up after
    with pytest.raises(RuntimeError):
        get_repo_root()


@pytest.mark.no_repo_context
def test_repo_root_context_cleanup_on_exception():
    """Test repo_root_context() cleans up even when exception raised."""
    test_path = Path("/test/repo/path")
    
    # Verify not set before
    with pytest.raises(RuntimeError):
        get_repo_root()
    
    # Raise exception inside context
    with pytest.raises(ValueError):
        with repo_root_context(test_path):
            assert get_repo_root() == test_path
            raise ValueError("Test exception")
    
    # Verify still cleaned up
    with pytest.raises(RuntimeError):
        get_repo_root()


@pytest.mark.asyncio
async def test_concurrent_async_tasks():
    """Test concurrent async tasks with different repo_roots don't interfere.
    
    This verifies that contextvars properly isolates state across
    concurrent async tasks, which is critical for handling multiple
    MCP requests simultaneously.
    """
    import random
    
    path1 = Path("/repo/one")
    path2 = Path("/repo/two")
    path3 = Path("/repo/three")
    
    results = []
    
    async def task_with_repo(path: Path, task_id: int):
        """Async task that sets a repo_root and verifies isolation."""
        with repo_root_context(path):
            # Multiple checks with random sleeps to increase interleaving
            for i in range(5):
                await asyncio.sleep(random.uniform(0.001, 0.01))
                actual = get_repo_root()
                results.append((task_id, actual == path, actual))
    
    # Run three tasks concurrently
    await asyncio.gather(
        task_with_repo(path1, 1),
        task_with_repo(path2, 2),
        task_with_repo(path3, 3),
    )
    
    # All tasks should have seen their own path
    assert len(results) == 15  # 5 checks per task * 3 tasks
    for task_id, is_correct, actual_path in results:
        assert is_correct, f"Task {task_id} saw wrong path: {actual_path}"


@pytest.mark.asyncio
async def test_concurrent_repo_contexts():
    """Test concurrent requests with different repos work correctly.
    
    This is a comprehensive test verifying that:
    - Multiple async tasks can run concurrently with different repo_roots
    - Each task's context is properly isolated
    - Random sleeps increase interleaving to catch race conditions
    - No context leakage occurs between concurrent tasks
    """
    import random
    
    # Create 5 different repo paths
    repos = [Path(f"/test/repo/{i}") for i in range(5)]
    
    async def verify_isolated_context(repo_path: Path, task_num: int):
        """
        Task that sets repo_root context and repeatedly verifies it stays correct.
        Uses random sleeps to maximize interleaving with other concurrent tasks.
        """
        with repo_root_context(repo_path):
            # Perform multiple checks with random delays
            for check_num in range(10):
                # Random sleep to increase chance of task interleaving
                await asyncio.sleep(random.uniform(0.0001, 0.005))
                
                # Call get_repo_root() multiple times within same iteration
                for _ in range(3):
                    current = get_repo_root()
                    assert current == repo_path, (
                        f"Task {task_num} check {check_num}: Expected {repo_path} "
                        f"but got {current}. Context leaked!"
                    )
    
    # Run 5 tasks concurrently, each with its own repo path
    await asyncio.gather(*[
        verify_isolated_context(repo, i)
        for i, repo in enumerate(repos)
    ])
    
    # If we get here, all assertions passed - no context leakage detected


@pytest.mark.no_repo_context
def test_nested_context_managers():
    """Test nested repo_root_context calls restore properly."""
    path1 = Path("/repo/outer")
    path2 = Path("/repo/inner")
    
    with repo_root_context(path1):
        assert get_repo_root() == path1
        
        with repo_root_context(path2):
            assert get_repo_root() == path2
        
        # Should restore to path1
        assert get_repo_root() == path1
    
    # Should be cleared completely
    with pytest.raises(RuntimeError):
        get_repo_root()
