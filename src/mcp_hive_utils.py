"""
Hive Utilities for Bees Ticket Management System

Provides path validation and filesystem scanning utilities for hive operations.
These utilities are used by MCP server hive management functions.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .config import BeesConfig, load_bees_config, save_bees_config
from .mcp_repo_utils import get_repo_root_from_path
from .repo_context import get_repo_root

logger = logging.getLogger(__name__)


def validate_hive_path(path: str) -> Path:
    """
    Validate a hive path and return normalized absolute path.

    Validates that:
    - Path is absolute
    - Path is within the repository root
    - Parent directory exists (path itself will be created by colonize_hive)
    - Normalizes trailing slashes

    Args:
        path: Path string to validate (must be absolute)

    Returns:
        Path: Normalized absolute path to the hive directory

    Raises:
        ValueError: If path is relative, parent doesn't exist, or is outside repo root

    Example:
        >>> validate_hive_path('/Users/username/projects/myrepo/tickets/')
        PosixPath('/Users/username/projects/myrepo/tickets')
        >>> validate_hive_path('tickets/')  # Raises ValueError - not absolute
        >>> validate_hive_path('/tmp/other/')  # Raises ValueError - outside repo
    """
    repo_root = get_repo_root()
    hive_path = Path(path)

    # Check if path is absolute
    if not hive_path.is_absolute():
        raise ValueError(
            f"Hive path must be absolute, got relative path: {path}"
        )

    # Create parent directory if it doesn't exist (we'll create the hive directory itself later)
    if not hive_path.parent.exists():
        try:
            hive_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created parent directory: {hive_path.parent}")
        except (PermissionError, OSError) as e:
            raise ValueError(
                f"Failed to create parent directory {hive_path.parent}: {e}"
            )

    # Resolve both paths to handle symlinks and normalize
    # Use strict=False since the hive path itself doesn't exist yet
    resolved_hive = hive_path.resolve(strict=False)
    resolved_repo = repo_root.resolve()

    # Check if hive path is within repo root
    try:
        resolved_hive.relative_to(resolved_repo)
    except ValueError:
        raise ValueError(
            f"Hive path must be within repository root. "
            f"Path: {resolved_hive}, Repo root: {resolved_repo}"
        )

    # Return normalized path (resolve() already removes trailing slashes)
    return resolved_hive


def scan_for_hive(name: str, config: BeesConfig | None = None) -> Path | None:
    """
    Recursively scan repository directories for a .hive marker matching a hive name.

    When a hive cannot be found in config.json, this function scans the repository
    for .hive markers to recover the hive's new location. It also logs warnings
    for any orphaned .hive markers not registered in config.

    Args:
        name: Normalized hive name to search for (e.g., 'back_end')
        config: Optional BeesConfig object to avoid reloading from disk. If provided,
                uses config.hives to get registered hive names.

    Returns:
        Path to the hive directory if found, None otherwise

    Raises:
        ValueError: If not in a git repository

    Example:
        >>> scan_for_hive('back_end')
        PosixPath('/Users/user/projects/myrepo/tickets')
        >>> config = BeesConfig(hives={'back_end': HiveConfig(...)})
        >>> scan_for_hive('back_end', config=config)
        PosixPath('/Users/user/projects/myrepo/tickets')
    """
    try:
        repo_root = get_repo_root_from_path(Path.cwd())
    except ValueError as e:
        logger.error(f"Cannot scan for hive: {e}")
        raise

    # Load config to check for registered hives
    # Use provided config if available to avoid redundant disk reads
    registered_hives = set()
    if config:
        # Config was provided, use it directly
        registered_hives = set(config.hives.keys())
    elif config is None:
        # Load config from disk
        config_path = Path('.bees/config.json')
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config_dict = json.load(f)
                    registered_hives = set(config_dict.get('hives', {}).keys())
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not read config.json: {e}")

    # Recursively search for .hive markers with depth limit
    # Limit depth to prevent excessive scanning if repo_root is '/' or a high-level directory
    MAX_SCAN_DEPTH = 10
    found_hive_path = None
    for hive_marker_path in repo_root.rglob('.hive'):
        if not hive_marker_path.is_dir():
            continue

        # Check depth relative to repo_root
        try:
            relative_path = hive_marker_path.relative_to(repo_root)
            depth = len(relative_path.parts)
            if depth > MAX_SCAN_DEPTH:
                logger.debug(f"Skipping .hive marker beyond depth limit: {hive_marker_path}")
                continue
        except ValueError:
            # Path is not relative to repo_root, skip it
            continue

        identity_file = hive_marker_path / 'identity.json'
        if not identity_file.exists():
            logger.warning(f"Found .hive marker without identity.json: {hive_marker_path}")
            continue

        try:
            with open(identity_file, 'r') as f:
                identity_data = json.load(f)
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning(f"Could not read identity from {identity_file}: {e}")
            continue

        marker_name = identity_data.get('normalized_name')

        if marker_name == name:
            # Found the hive we're looking for
            found_hive_path = hive_marker_path.parent
            logger.info(f"Found hive '{name}' at {found_hive_path}")

            # Update config.json with the recovered path
            try:
                config = load_bees_config()
                if config and name in config.hives:
                    config.hives[name].path = str(found_hive_path)
                    save_bees_config(config)
                    logger.info(f"Updated config.json with new path for hive '{name}': {found_hive_path}")
                else:
                    logger.warning(f"Hive '{name}' not found in config, cannot update path")
            except (IOError, json.JSONDecodeError, AttributeError) as e:
                logger.error(f"Failed to update config.json for hive '{name}': {e}")
                raise

            return found_hive_path
        elif marker_name not in registered_hives:
            # Found an orphaned .hive marker
            logger.warning(
                f"Found orphaned .hive marker for '{marker_name}' at {hive_marker_path.parent}. "
                f"Not registered in config.json."
            )

    return found_hive_path
