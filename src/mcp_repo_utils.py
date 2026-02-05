"""
MCP Repository Root Detection Utilities

Provides repository root detection functions used by MCP server operations.
Handles finding git repositories from paths, extracting roots from MCP client
context, and coordinating fallback logic.
"""

import logging
from pathlib import Path
from fastmcp import Context
from fastmcp.exceptions import NotFoundError

# Configure logging
logger = logging.getLogger(__name__)


def get_repo_root_from_path(start_path: Path) -> Path:
    """
    Find the git repository root by walking up from a given path.

    Starts from the provided path and walks up the directory tree
    looking for a .git directory. Returns the path to the repository root
    when found.

    Args:
        start_path: Path to start searching from

    Returns:
        Path: Absolute path to the git repository root

    Raises:
        ValueError: If not in a git repository (no .git directory found)

    Example:
        >>> repo_root = get_repo_root_from_path(Path('/Users/user/projects/myrepo/tickets'))
        >>> print(repo_root)
        /Users/username/projects/myrepo
    """
    current = start_path.resolve()

    # Walk up directory tree looking for .git
    while current != current.parent:
        if (current / '.git').exists():
            return current
        current = current.parent

    # Check root directory
    if (current / '.git').exists():
        return current

    raise ValueError(f"Not in a git repository - no .git directory found starting from {start_path}")


async def get_client_repo_root(ctx: Context) -> Path | None:
    """
    Extract repository root from MCP client context if client supports roots protocol.

    Args:
        ctx: FastMCP Context object provided by MCP client

    Returns:
        Path if client supports roots and provides them, None otherwise

    Example:
        >>> ctx = get_context()  # From MCP client
        >>> repo = await get_client_repo_root(ctx)
        >>> if repo:
        >>>     print(f"Client repo: {repo}")
        >>> else:
        >>>     print("Client doesn't support roots protocol")
    """
    try:
        logger.info(f"Calling ctx.list_roots() - ctx type: {type(ctx)}, ctx: {ctx}")
        roots = await ctx.list_roots()
        logger.info(f"ctx.list_roots() returned: {roots}")

        if not roots or len(roots) == 0:
            logger.warning("Client returned empty roots list")
            return None

        # Log all roots for debugging
        logger.info(f"Client provided {len(roots)} root(s):")
        for i, root in enumerate(roots):
            logger.info(f"  Root {i}: {root.uri}")

        # Take first root and convert FileUrl to Path
        first_root = roots[0]
        root_uri_str = str(first_root.uri)

        # Strip file:// prefix if present
        if root_uri_str.startswith("file://"):
            root_path = root_uri_str[7:]  # Remove "file://"
        else:
            root_path = root_uri_str

        logger.info(f"Using first root as client repo root: {root_path}")
        return Path(root_path)

    except NotFoundError as e:
        # Method not found (-32601) means client doesn't support roots
        # This is normal for clients that don't implement the roots protocol
        logger.info(f"Client doesn't support roots protocol - NotFoundError: {e}")
        return None
    except Exception as e:
        # Catch any other exceptions to help debug
        logger.error(f"Unexpected error in get_client_repo_root: {type(e).__name__}: {e}")
        raise


async def resolve_repo_root(ctx: Context, explicit_root: str | None) -> Path:
    """
    Resolve repository root from MCP client context or explicit parameter.

    Tries to get repo root from MCP client's roots protocol first. If that fails
    (client doesn't support roots), falls back to explicit repo_root parameter.
    If neither is available, raises error with clear instructions.

    Args:
        ctx: FastMCP Context object provided by MCP client
        explicit_root: Optional explicit repo_root path string (fallback for non-Roots clients)

    Returns:
        Path: Resolved repository root path

    Raises:
        ValueError: If neither roots protocol nor explicit_root are available

    Example:
        >>> # Roots protocol supported
        >>> resolved = await resolve_repo_root(ctx, None)
        >>> # Explicit param fallback
        >>> resolved = await resolve_repo_root(ctx, "/path/to/repo")
    """
    # Try Roots protocol first
    client_root = await get_client_repo_root(ctx)
    if client_root:
        # Client supports roots - verify it's a git repo and return
        try:
            repo_root = get_repo_root_from_path(client_root)
            logger.info(f"Resolved repo root from MCP client roots: {repo_root}")
            return repo_root
        except ValueError as e:
            # Client provided a root but it's not a git repo
            logger.error(f"Client root {client_root} is not a git repository: {e}")
            raise

    # Roots not available, try explicit parameter
    if explicit_root:
        explicit_path = Path(explicit_root)
        logger.info(f"Resolved repo root from explicit parameter: {explicit_path}")
        return explicit_path

    # Neither available - raise error
    raise ValueError(
        "Your MCP client does not support the roots protocol. "
        "Please provide repo_root parameter when calling this tool."
    )


async def get_repo_root(ctx: Context | None) -> Path | None:
    """
    Find the git repository root from MCP client context.

    When called with MCP context, uses the roots protocol. If the client
    doesn't support roots or the protocol fails, returns None so the caller
    can implement appropriate fallback logic (since MCP server runs in a
    different repo than the client, we can't just use server's cwd).

    Args:
        ctx: FastMCP Context object (optional, auto-injected by FastMCP)

    Returns:
        Path if repo root can be determined, None if roots protocol unavailable

    Raises:
        ValueError: If not in a git repository (only when ctx is None)

    Example:
        >>> ctx = get_context()
        >>> repo_root = await get_repo_root(ctx)
        >>> if repo_root:
        >>>     print(repo_root)
        >>> else:
        >>>     # Handle roots protocol unavailable
    """
    if ctx:
        client_root = await get_client_repo_root(ctx)
        if client_root:
            # Client supports roots - use it
            try:
                repo_root = get_repo_root_from_path(client_root)
                logger.info(f"Using client repo root from MCP context: {repo_root}")
                return repo_root
            except ValueError as e:
                # Client provided a root but it's not a git repo
                logger.error(f"Client root {client_root} is not a git repository: {e}")
                raise
        else:
            # Client doesn't support roots protocol or list_roots() failed
            # Return None so caller can implement appropriate fallback
            # (We can't fall back to server's cwd since MCP server runs in different repo)
            logger.warning("MCP client doesn't support roots protocol or list_roots() failed")
            return None
    else:
        # No context (tests, CLI) - use cwd
        return get_repo_root_from_path(Path.cwd())
