"""Context-based repository root management using contextvars.

This module provides async-safe, request-scoped state management for repo_root
to eliminate the need to thread repo_root through 24+ functions across 6+ files.

Usage in MCP entry points:
    async def _create_ticket(ctx: Context, ...):
        resolved_root = await resolve_repo_root(ctx, repo_root)
        with repo_root_context(resolved_root):
            # Call downstream functions without passing repo_root
            create_epic(...)  # This can now call get_repo_root() internally

Usage in downstream functions:
    def get_config_path() -> Path:
        repo_root = get_repo_root()
        return repo_root / ".bees" / "config.json"
"""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Generator

# Async-safe, request-scoped storage for repo_root
_repo_root: ContextVar[Path | None] = ContextVar('repo_root', default=None)


def get_repo_root() -> Path:
    """Get the current repo_root from context.
    
    Returns:
        Path: The repository root path
        
    Raises:
        RuntimeError: If repo_root has not been set in context. This indicates
            a bug - MCP entry points must call set_repo_root() before invoking
            core functions.
    """
    root = _repo_root.get()
    if root is None:
        raise RuntimeError(
            "repo_root not set in context. This is a bug - "
            "MCP entry points must call set_repo_root() before invoking core functions."
        )
    return root


def set_repo_root(path: Path) -> Token:
    """Set the repo_root in context.
    
    Args:
        path: The repository root path to set
        
    Returns:
        Token: A token that can be used with reset_repo_root() to restore
            the previous context state
    """
    return _repo_root.set(path)


def reset_repo_root(token: Token) -> None:
    """Reset repo_root to its previous state.
    
    Args:
        token: The token returned from set_repo_root()
    """
    _repo_root.reset(token)


@contextmanager
def repo_root_context(path: Path) -> Generator[None, None, None]:
    """Context manager for setting repo_root with automatic cleanup.
    
    This ensures the context is properly cleaned up even if an exception
    is raised within the context block.
    
    Args:
        path: The repository root path to set
        
    Yields:
        None
        
    Example:
        with repo_root_context(Path("/path/to/repo")):
            # repo_root is set here
            do_work()
        # repo_root is automatically reset here
    """
    token = set_repo_root(path)
    try:
        yield
    finally:
        reset_repo_root(token)
