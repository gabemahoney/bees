"""Installed bees-md version lookup, shared by the CLI and the MCP server.

Kept dependency-free so the CLI can report its version without importing fastmcp.
"""

from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    """Return the installed bees-md version, or "unknown" if package metadata is unavailable."""
    try:
        return version("bees-md")
    except PackageNotFoundError:
        return "unknown"
