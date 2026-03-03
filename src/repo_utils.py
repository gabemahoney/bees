"""
Repository Root Detection Utilities

Transport-agnostic utilities for repository root detection.
Handles finding git repositories from paths.

MCP-specific functions (get_client_repo_root, get_repo_root, resolve_repo_root)
live in mcp_roots.py.
"""

import logging
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)


def get_repo_root_from_path(start_path: Path) -> Path:
    """
    Find the project root by walking up from a given path.

    Starts from the provided path and walks up the directory tree
    looking for a .git directory. If no git repo is found, returns
    the resolved start_path — this supports projects where hive config
    lives in ~/.bees/config.json with scope matching rather than in
    a repo-local .bees/ directory.

    Args:
        start_path: Path to start searching from

    Returns:
        Path: Absolute path to the git repository root, or the resolved
              start_path if not in a git repository

    Example:
        >>> repo_root = get_repo_root_from_path(Path('/Users/user/projects/myrepo/tickets'))
        >>> print(repo_root)
        /Users/username/projects/myrepo
    """
    resolved = start_path.resolve()
    current = resolved

    # Walk up directory tree looking for .git
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    # Check root directory
    if (current / ".git").exists():
        return current

    # No git repo found — return resolved start path for scope-based config matching
    logger.info(f"No .git found from {start_path}, using resolved path: {resolved}")
    return resolved
