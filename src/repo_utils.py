"""
Repository Root Detection Utilities

Transport-agnostic utilities for repository root detection.

MCP-specific functions (get_client_repo_root, get_repo_root, resolve_repo_root)
live in mcp_roots.py.
"""

from pathlib import Path


def get_repo_root_from_path(start_path: Path) -> Path:
    """
    Return the resolved absolute path for the given start_path.

    Args:
        start_path: Path to resolve

    Returns:
        Path: Resolved absolute path of start_path

    Example:
        >>> repo_root = get_repo_root_from_path(Path('/Users/user/projects/myrepo/tickets'))
        >>> print(repo_root)
        /Users/user/projects/myrepo/tickets
    """
    return start_path.resolve()
