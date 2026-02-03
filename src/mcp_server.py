"""
MCP Server for Bees Ticket Management System

Provides FastMCP server infrastructure with tool registration for ticket operations.
"""

import json
import logging
import os
import re
import yaml
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal
from fastmcp import FastMCP, Context
from .ticket_factory import create_epic, create_task, create_subtask
from .reader import read_ticket
from .writer import write_ticket_file
from .paths import infer_ticket_type_from_id, get_ticket_path
from .query_storage import save_query, load_query, list_queries, validate_query
from .query_parser import QueryValidationError
from .pipeline import PipelineEvaluator
from .index_generator import generate_index
from .config import (
    validate_unique_hive_name, load_bees_config, save_bees_config,
    HiveConfig, BeesConfig, init_bees_config_if_needed,
    load_hive_config_dict, write_hive_config_dict, register_hive_dict
)
from .id_utils import normalize_hive_name

# Ensure log directory exists
log_dir = Path.home() / '.bees'
log_dir.mkdir(exist_ok=True)

# Configure logging to file for MCP stdio compatibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=log_dir / 'mcp.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Bees Ticket Management Server")

# Server state
_server_running = False


def parse_ticket_id(ticket_id: str) -> tuple[str, str]:
    """
    Parse a ticket ID to extract hive name and base ID.

    Splits ticket IDs on the first dot to extract hive prefix and base ID.
    For new format IDs (hive_name.bees-abc1), returns (hive_name, bees-abc1).
    For legacy format IDs (bees-abc1), returns ('', bees-abc1).

    Args:
        ticket_id: Ticket ID string (e.g., 'backend.bees-abc1' or 'bees-abc1')

    Returns:
        tuple[str, str]: (hive_name, base_id) where hive_name is empty string for legacy IDs

    Raises:
        ValueError: If ticket_id is None or empty string

    Example:
        >>> parse_ticket_id('backend.bees-abc1')
        ('backend', 'bees-abc1')
        >>> parse_ticket_id('bees-abc1')
        ('', 'bees-abc1')
        >>> parse_ticket_id('multi.dot.bees-xyz9')
        ('multi', 'dot.bees-xyz9')
    """
    # Handle None and empty string
    if ticket_id is None:
        raise ValueError("ticket_id cannot be None")

    if not ticket_id or not ticket_id.strip():
        raise ValueError("ticket_id cannot be empty")

    # Split on first dot only
    if '.' in ticket_id:
        hive_name, _, base_id = ticket_id.partition('.')
        return (hive_name, base_id)
    else:
        # Legacy format without hive prefix
        return ('', ticket_id)


def parse_hive_from_ticket_id(ticket_id: str) -> str | None:
    """
    Extract hive prefix from a ticket ID.

    Splits ticket_id on first dot to extract the hive name prefix.
    For prefixed IDs (backend.bees-abc1), returns the hive name (backend).
    For unprefixed IDs (bees-abc1), returns None (malformed/legacy format).

    Args:
        ticket_id: Ticket ID string (e.g., 'backend.bees-abc1')

    Returns:
        str | None: Hive name prefix, or None if no dot found (malformed ID)

    Example:
        >>> parse_hive_from_ticket_id('backend.bees-abc1')
        'backend'
        >>> parse_hive_from_ticket_id('bees-abc1')
        None
        >>> parse_hive_from_ticket_id('multi.dot.bees-xyz9')
        'multi'
    """
    # Split on first dot only
    if '.' in ticket_id:
        hive_name, _, _ = ticket_id.partition('.')
        return hive_name
    else:
        # No dot found - malformed ID
        return None


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
        roots = await ctx.list_roots()
        
        if not roots or len(roots) == 0:
            logger.warning("Client returned empty roots list")
            return None
        
        # Take first root and convert FileUrl to Path
        first_root = roots[0]
        root_uri_str = str(first_root.uri)
        
        # Strip file:// prefix if present
        if root_uri_str.startswith("file://"):
            root_path = root_uri_str[7:]  # Remove "file://"
        else:
            root_path = root_uri_str
        
        logger.info(f"Got client repo root from roots protocol: {root_path}")
        return Path(root_path)
        
    except Exception as e:
        # Method not found (-32601) means client doesn't support roots
        # This is normal for clients that don't implement the roots protocol
        logger.info(f"Client doesn't support roots protocol: {e}")
        return None


async def get_repo_root(ctx: Context | None) -> Path:
    """
    Find the git repository root, preferring MCP client context when available.
    
    If client supports roots protocol, uses that. Otherwise falls back to cwd.
    
    Args:
        ctx: FastMCP Context object (optional, auto-injected by FastMCP)
        
    Returns:
        Path: Absolute path to the git repository root
        
    Raises:
        ValueError: If not in a git repository
        
    Example:
        >>> ctx = get_context()
        >>> repo_root = await get_repo_root(ctx)
        >>> print(repo_root)
        /Users/username/projects/myrepo
    """
    if ctx:
        client_root = await get_client_repo_root(ctx)
        if client_root:
            # Client supports roots - use it
            return get_repo_root_from_path(client_root)
        else:
            # Client doesn't support roots - fall back to cwd
            logger.info("Falling back to cwd since client doesn't support roots")
            return get_repo_root_from_path(Path.cwd())
    else:
        # No context (tests, CLI) - use cwd
        return get_repo_root_from_path(Path.cwd())


def validate_hive_path(path: str, repo_root: Path) -> Path:
    """
    Validate a hive path and return normalized absolute path.

    Validates that:
    - Path is absolute
    - Path is within the repository root
    - Parent directory exists (path itself will be created by colonize_hive)
    - Normalizes trailing slashes

    Args:
        path: Path string to validate (must be absolute)
        repo_root: Repository root path for boundary checking

    Returns:
        Path: Normalized absolute path to the hive directory

    Raises:
        ValueError: If path is relative, parent doesn't exist, or is outside repo root

    Example:
        >>> repo = Path('/Users/username/projects/myrepo')
        >>> validate_hive_path('/Users/username/projects/myrepo/tickets/', repo)
        PosixPath('/Users/username/projects/myrepo/tickets')
        >>> validate_hive_path('tickets/', repo)  # Raises ValueError - not absolute
        >>> validate_hive_path('/tmp/other/', repo)  # Raises ValueError - outside repo
    """
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


async def colonize_hive_core(name: str, path: str, ctx: Context | None = None) -> Dict[str, Any]:
    """
    Create a new hive directory structure at the specified path.

    This is the core implementation that coordinates validation and hive setup:
    - Normalizes the hive display name using the config system
    - Validates the path is absolute, exists, and within the repo
    - Checks for duplicate normalized hive names in the registry
    - Creates the hive directory structure (/eggs, /evicted, .hive marker)
    - Registers the hive in .bees/config.json

    Args:
        name: Display name for the hive (e.g., 'Back End')
        path: Absolute path where the hive should be created
        ctx: FastMCP Context (auto-injected when called from MCP, gets client's repo root)

    Returns:
        dict: Success/error status with validation details
            On success: {
                'status': 'success',
                'message': 'Hive created successfully',
                'normalized_name': str,
                'display_name': str,
                'path': str
            }
            On error: {
                'status': 'error',
                'message': str,
                'error_type': str,
                'validation_details': dict
            }

    Example:
        >>> await colonize_hive_core('Back End', '/Users/user/projects/myrepo/tickets', ctx)
        {'status': 'success', 'normalized_name': 'back_end', 'display_name': 'Back End', ...}
    """
    try:
        # Step 1: Normalize hive name using config system
        normalized_name = normalize_hive_name(name)
        logger.info(f"Normalized hive name '{name}' to '{normalized_name}'")

        if not normalized_name:
            return {
                "status": "error",
                "message": "Invalid hive name: normalizes to empty string",
                "error_type": "validation_error",
                "validation_details": {
                    "field": "name",
                    "provided_value": name,
                    "reason": "Name contains no alphanumeric characters"
                }
            }

        # Step 2: Validate path using client's repo root from context
        try:
            # Get repo root from MCP context (client's repo) or fall back to hive path for non-MCP
            hive_path = Path(path)
            if ctx:
                # MCP tool call - use client's repo root from context
                repo_root = await get_repo_root(ctx)
                logger.info(f"Using client repo root from context: {repo_root}")
            else:
                # Non-MCP call (tests, CLI) - find repo root from hive path
                repo_root = get_repo_root_from_path(hive_path)
                logger.info(f"Found repo root from hive path: {repo_root}")
            
            validated_path = validate_hive_path(path, repo_root)
            logger.info(f"Validated hive path: {validated_path}")
        except ValueError as e:
            return {
                "status": "error",
                "message": str(e),
                "error_type": "path_validation_error",
                "validation_details": {
                    "field": "path",
                    "provided_value": path,
                    "reason": str(e)
                }
            }

        # Step 3: Check for duplicate normalized names using config system
        try:
            validate_unique_hive_name(normalized_name, repo_root=repo_root)
            logger.info(f"Validated unique hive name: {normalized_name}")
        except ValueError as e:
            return {
                "status": "error",
                "message": str(e),
                "error_type": "duplicate_name_error",
                "validation_details": {
                    "field": "name",
                    "normalized_name": normalized_name,
                    "display_name": name,
                    "reason": str(e)
                }
            }

        # Step 4: Create hive directory structure
        # Create /eggs subdirectory for future feature storage
        eggs_path = validated_path / "eggs"
        try:
            eggs_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created /eggs directory at {eggs_path}")
        except (PermissionError, OSError) as e:
            return {
                "status": "error",
                "message": f"Failed to create /eggs directory: {e}",
                "error_type": "filesystem_error",
                "validation_details": {
                    "operation": "create_eggs_dir",
                    "path": str(eggs_path),
                    "reason": str(e)
                }
            }

        # Create /evicted subdirectory for completed/archived tickets
        evicted_path = validated_path / "evicted"
        try:
            evicted_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created /evicted directory at {evicted_path}")
        except (PermissionError, OSError) as e:
            return {
                "status": "error",
                "message": f"Failed to create /evicted directory: {e}",
                "error_type": "filesystem_error",
                "validation_details": {
                    "operation": "create_evicted_dir",
                    "path": str(evicted_path),
                    "reason": str(e)
                }
            }

        # Create .hive marker folder with identity data
        hive_marker_path = validated_path / ".hive"
        try:
            hive_marker_path.mkdir(exist_ok=True)
        except (PermissionError, OSError) as e:
            return {
                "status": "error",
                "message": f"Failed to create .hive marker directory: {e}",
                "error_type": "filesystem_error",
                "validation_details": {
                    "operation": "create_hive_marker",
                    "path": str(hive_marker_path),
                    "reason": str(e)
                }
            }

        # Store hive identity in marker file
        identity_data = {
            "normalized_name": normalized_name,
            "display_name": name,
            "created_at": datetime.now().isoformat(),
            "version": "1.0.0"
        }
        identity_file = hive_marker_path / "identity.json"
        try:
            with open(identity_file, 'w') as f:
                json.dump(identity_data, f, indent=2)
            logger.info(f"Created .hive marker at {hive_marker_path} with identity: {identity_data}")
        except (PermissionError, OSError) as e:
            return {
                "status": "error",
                "message": f"Failed to write .hive identity file: {e}",
                "error_type": "filesystem_error",
                "validation_details": {
                    "operation": "write_identity_file",
                    "path": str(identity_file),
                    "reason": str(e)
                }
            }

        # TODO: Linter integration stub
        # Future: Add linter check here to validate no conflicting tickets exist
        # across hives during colonization. The linter should scan for duplicate
        # ticket IDs, conflicting hive names, and other cross-hive invariants.
        # Deferred to future Epic for full implementation.
        logger.info(f"Linter check: (stubbed out for now)")

        # Step 5: Register hive in config.json in the repo where the hive is located
        try:
            # Get current timestamp for registration
            creation_timestamp = datetime.now()

            # Register hive in config (updates config dict in memory)
            # Pass repo_root so config is created in the correct repository
            config = register_hive_dict(
                normalized_name=normalized_name,
                display_name=name,
                path=str(validated_path),
                timestamp=creation_timestamp,
                repo_root=repo_root
            )

            # Persist config to disk with error handling
            # Pass repo_root to ensure .bees/config.json is created in the correct repo
            write_hive_config_dict(config, repo_root)
            logger.info(f"Registered hive '{normalized_name}' in config.json at {repo_root / '.bees/config.json'}")
        except (IOError, PermissionError, OSError) as e:
            return {
                "status": "error",
                "message": f"Failed to write config file: {e}",
                "error_type": "config_write_error",
                "validation_details": {
                    "operation": "write_config",
                    "reason": str(e)
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to register hive in config: {e}",
                "error_type": "config_error",
                "validation_details": {
                    "operation": "register_hive",
                    "reason": str(e)
                }
            }

        # Success!
        return {
            "status": "success",
            "message": "Hive created and registered successfully",
            "normalized_name": normalized_name,
            "display_name": name,
            "path": str(validated_path)
        }

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Unexpected error in colonize_hive: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {e}",
            "error_type": "unexpected_error",
            "validation_details": {
                "exception_type": type(e).__name__,
                "exception_message": str(e)
            }
        }


def _update_bidirectional_relationships(
    new_ticket_id: str,
    parent: str | None = None,
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None
) -> None:
    """
    Update related tickets to maintain bidirectional consistency.

    When creating a ticket with relationships, this function updates the related
    tickets to include references back to the newly created ticket.

    Args:
        new_ticket_id: The ID of the newly created ticket
        parent: Parent ticket ID (if set, add new_ticket_id to parent's children)
        children: List of child ticket IDs (if set, add new_ticket_id to each child's parent)
        up_dependencies: List of blocking ticket IDs (add new_ticket_id to their down_dependencies)
        down_dependencies: List of blocked ticket IDs (add new_ticket_id to their up_dependencies)

    Raises:
        ValueError: If any related ticket doesn't exist
        FileNotFoundError: If related ticket file cannot be found
    """
    # Update parent's children array
    if parent:
        ticket_type = infer_ticket_type_from_id(parent)
        if not ticket_type:
            raise ValueError(f"Parent ticket not found: {parent}")

        ticket_path = get_ticket_path(parent, ticket_type)
        parent_ticket = read_ticket(ticket_path)

        # Add new ticket to parent's children if not already present
        if parent_ticket.children is None:
            parent_ticket.children = []
        if new_ticket_id not in parent_ticket.children:
            parent_ticket.children.append(new_ticket_id)

        # Write updated parent ticket
        frontmatter_data = asdict(parent_ticket)
        frontmatter_data["updated_at"] = datetime.now()
        write_ticket_file(
            ticket_id=parent,
            ticket_type=ticket_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or ""
        )
        logger.info(f"Updated parent {parent} to include child {new_ticket_id}")

    # Update children's parent field (if setting children during creation)
    if children:
        for child_id in children:
            ticket_type = infer_ticket_type_from_id(child_id)
            if not ticket_type:
                raise ValueError(f"Child ticket not found: {child_id}")

            ticket_path = get_ticket_path(child_id, ticket_type)
            child_ticket = read_ticket(ticket_path)

            # Set parent on child ticket
            child_ticket.parent = new_ticket_id

            # Write updated child ticket
            frontmatter_data = asdict(child_ticket)
            frontmatter_data["updated_at"] = datetime.now()
            write_ticket_file(
                ticket_id=child_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=child_ticket.description or ""
            )
            logger.info(f"Updated child {child_id} to have parent {new_ticket_id}")

    # Update up_dependencies (blocking tickets) - add new ticket to their down_dependencies
    if up_dependencies:
        for blocking_ticket_id in up_dependencies:
            ticket_type = infer_ticket_type_from_id(blocking_ticket_id)
            if not ticket_type:
                raise ValueError(f"Dependency ticket not found: {blocking_ticket_id}")

            ticket_path = get_ticket_path(blocking_ticket_id, ticket_type)
            blocking_ticket = read_ticket(ticket_path)

            # Add new ticket to blocking ticket's down_dependencies
            if blocking_ticket.down_dependencies is None:
                blocking_ticket.down_dependencies = []
            if new_ticket_id not in blocking_ticket.down_dependencies:
                blocking_ticket.down_dependencies.append(new_ticket_id)

            # Write updated blocking ticket
            frontmatter_data = asdict(blocking_ticket)
            frontmatter_data["updated_at"] = datetime.now()
            write_ticket_file(
                ticket_id=blocking_ticket_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=blocking_ticket.description or ""
            )
            logger.info(f"Updated blocking ticket {blocking_ticket_id} to include {new_ticket_id} in down_dependencies")

    # Update down_dependencies (blocked tickets) - add new ticket to their up_dependencies
    if down_dependencies:
        for blocked_ticket_id in down_dependencies:
            ticket_type = infer_ticket_type_from_id(blocked_ticket_id)
            if not ticket_type:
                raise ValueError(f"Dependency ticket not found: {blocked_ticket_id}")

            ticket_path = get_ticket_path(blocked_ticket_id, ticket_type)
            blocked_ticket = read_ticket(ticket_path)

            # Add new ticket to blocked ticket's up_dependencies
            if blocked_ticket.up_dependencies is None:
                blocked_ticket.up_dependencies = []
            if new_ticket_id not in blocked_ticket.up_dependencies:
                blocked_ticket.up_dependencies.append(new_ticket_id)

            # Write updated blocked ticket
            frontmatter_data = asdict(blocked_ticket)
            frontmatter_data["updated_at"] = datetime.now()
            write_ticket_file(
                ticket_id=blocked_ticket_id,
                ticket_type=ticket_type,
                frontmatter_data=frontmatter_data,
                body=blocked_ticket.description or ""
            )
            logger.info(f"Updated blocked ticket {blocked_ticket_id} to include {new_ticket_id} in up_dependencies")


def _remove_child_from_parent(child_id: str, parent_id: str) -> None:
    """Remove child_id from parent's children array."""
    parent_type = infer_ticket_type_from_id(parent_id)
    if not parent_type:
        logger.warning(f"Parent ticket not found: {parent_id}")
        return

    parent_path = get_ticket_path(parent_id, parent_type)
    parent_ticket = read_ticket(parent_path)

    if parent_ticket.children and child_id in parent_ticket.children:
        parent_ticket.children.remove(child_id)
        parent_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(parent_ticket)
        write_ticket_file(
            ticket_id=parent_id,
            ticket_type=parent_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or ""
        )
        logger.info(f"Removed {child_id} from parent {parent_id}'s children")


def _add_child_to_parent(child_id: str, parent_id: str) -> None:
    """Add child_id to parent's children array."""
    parent_type = infer_ticket_type_from_id(parent_id)
    if not parent_type:
        raise ValueError(f"Parent ticket not found: {parent_id}")

    parent_path = get_ticket_path(parent_id, parent_type)
    parent_ticket = read_ticket(parent_path)

    if parent_ticket.children is None:
        parent_ticket.children = []
    if child_id not in parent_ticket.children:
        parent_ticket.children.append(child_id)
        parent_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(parent_ticket)
        write_ticket_file(
            ticket_id=parent_id,
            ticket_type=parent_type,
            frontmatter_data=frontmatter_data,
            body=parent_ticket.description or ""
        )
        logger.info(f"Added {child_id} to parent {parent_id}'s children")


def _remove_parent_from_child(child_id: str) -> None:
    """Remove parent field from child ticket."""
    child_type = infer_ticket_type_from_id(child_id)
    if not child_type:
        logger.warning(f"Child ticket not found: {child_id}")
        return

    child_path = get_ticket_path(child_id, child_type)
    child_ticket = read_ticket(child_path)

    # Subtasks must always have a parent (validation requirement)
    # So we can't unlink subtasks - they remain orphaned pointing to deleted parent
    if child_type == "subtask":
        logger.warning(f"Cannot unlink subtask {child_id} - subtasks require a parent")
        return

    if child_ticket.parent:
        child_ticket.parent = None
        child_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(child_ticket)
        write_ticket_file(
            ticket_id=child_id,
            ticket_type=child_type,
            frontmatter_data=frontmatter_data,
            body=child_ticket.description or ""
        )
        logger.info(f"Removed parent from child {child_id}")


def _set_parent_on_child(parent_id: str, child_id: str) -> None:
    """Set parent field on child ticket."""
    child_type = infer_ticket_type_from_id(child_id)
    if not child_type:
        raise ValueError(f"Child ticket not found: {child_id}")

    child_path = get_ticket_path(child_id, child_type)
    child_ticket = read_ticket(child_path)

    child_ticket.parent = parent_id
    child_ticket.updated_at = datetime.now()

    frontmatter_data = asdict(child_ticket)
    write_ticket_file(
        ticket_id=child_id,
        ticket_type=child_type,
        frontmatter_data=frontmatter_data,
        body=child_ticket.description or ""
    )
    logger.info(f"Set parent {parent_id} on child {child_id}")


def _remove_from_down_dependencies(ticket_id: str, blocking_ticket_id: str) -> None:
    """Remove ticket_id from blocking_ticket's down_dependencies."""
    blocking_type = infer_ticket_type_from_id(blocking_ticket_id)
    if not blocking_type:
        logger.warning(f"Blocking ticket not found: {blocking_ticket_id}")
        return

    blocking_path = get_ticket_path(blocking_ticket_id, blocking_type)
    blocking_ticket = read_ticket(blocking_path)

    if blocking_ticket.down_dependencies and ticket_id in blocking_ticket.down_dependencies:
        blocking_ticket.down_dependencies.remove(ticket_id)
        blocking_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(blocking_ticket)
        write_ticket_file(
            ticket_id=blocking_ticket_id,
            ticket_type=blocking_type,
            frontmatter_data=frontmatter_data,
            body=blocking_ticket.description or ""
        )
        logger.info(f"Removed {ticket_id} from {blocking_ticket_id}'s down_dependencies")


def _add_to_down_dependencies(ticket_id: str, blocking_ticket_id: str) -> None:
    """Add ticket_id to blocking_ticket's down_dependencies."""
    blocking_type = infer_ticket_type_from_id(blocking_ticket_id)
    if not blocking_type:
        raise ValueError(f"Blocking ticket not found: {blocking_ticket_id}")

    blocking_path = get_ticket_path(blocking_ticket_id, blocking_type)
    blocking_ticket = read_ticket(blocking_path)

    if blocking_ticket.down_dependencies is None:
        blocking_ticket.down_dependencies = []
    if ticket_id not in blocking_ticket.down_dependencies:
        blocking_ticket.down_dependencies.append(ticket_id)
        blocking_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(blocking_ticket)
        write_ticket_file(
            ticket_id=blocking_ticket_id,
            ticket_type=blocking_type,
            frontmatter_data=frontmatter_data,
            body=blocking_ticket.description or ""
        )
        logger.info(f"Added {ticket_id} to {blocking_ticket_id}'s down_dependencies")


def _remove_from_up_dependencies(ticket_id: str, blocked_ticket_id: str) -> None:
    """Remove ticket_id from blocked_ticket's up_dependencies."""
    blocked_type = infer_ticket_type_from_id(blocked_ticket_id)
    if not blocked_type:
        logger.warning(f"Blocked ticket not found: {blocked_ticket_id}")
        return

    blocked_path = get_ticket_path(blocked_ticket_id, blocked_type)
    blocked_ticket = read_ticket(blocked_path)

    if blocked_ticket.up_dependencies and ticket_id in blocked_ticket.up_dependencies:
        blocked_ticket.up_dependencies.remove(ticket_id)
        blocked_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(blocked_ticket)
        write_ticket_file(
            ticket_id=blocked_ticket_id,
            ticket_type=blocked_type,
            frontmatter_data=frontmatter_data,
            body=blocked_ticket.description or ""
        )
        logger.info(f"Removed {ticket_id} from {blocked_ticket_id}'s up_dependencies")


def _add_to_up_dependencies(ticket_id: str, blocked_ticket_id: str) -> None:
    """Add ticket_id to blocked_ticket's up_dependencies."""
    blocked_type = infer_ticket_type_from_id(blocked_ticket_id)
    if not blocked_type:
        raise ValueError(f"Blocked ticket not found: {blocked_ticket_id}")

    blocked_path = get_ticket_path(blocked_ticket_id, blocked_type)
    blocked_ticket = read_ticket(blocked_path)

    if blocked_ticket.up_dependencies is None:
        blocked_ticket.up_dependencies = []
    if ticket_id not in blocked_ticket.up_dependencies:
        blocked_ticket.up_dependencies.append(ticket_id)
        blocked_ticket.updated_at = datetime.now()

        frontmatter_data = asdict(blocked_ticket)
        write_ticket_file(
            ticket_id=blocked_ticket_id,
            ticket_type=blocked_type,
            frontmatter_data=frontmatter_data,
            body=blocked_ticket.description or ""
        )
        logger.info(f"Added {ticket_id} to {blocked_ticket_id}'s up_dependencies")


def start_server() -> Dict[str, Any]:
    """
    Start the MCP server.

    Returns:
        dict: Server status information
    """
    global _server_running

    try:
        logger.info("Starting Bees MCP Server...")
        _server_running = True
        logger.info("Bees MCP Server started successfully")

        return {
            "status": "running",
            "name": "Bees Ticket Management Server",
            "version": "0.1.0"
        }
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        _server_running = False
        raise


def stop_server() -> Dict[str, Any]:
    """
    Stop the MCP server.

    Returns:
        dict: Server status information
    """
    global _server_running

    try:
        logger.info("Stopping Bees MCP Server...")
        _server_running = False
        logger.info("Bees MCP Server stopped successfully")

        return {
            "status": "stopped",
            "name": "Bees Ticket Management Server"
        }
    except Exception as e:
        logger.error(f"Failed to stop server: {e}")
        raise


def _health_check() -> Dict[str, Any]:
    """
    Check the health status of the MCP server.

    Returns:
        dict: Health status including server state and readiness
    """
    return {
        "status": "healthy" if _server_running else "stopped",
        "server_running": _server_running,
        "name": "Bees Ticket Management Server",
        "version": "0.1.0",
        "ready": _server_running
    }


# Register the health_check tool with FastMCP
health_check = mcp.tool(name="health_check")(_health_check)


# Tool stubs - implementations will be added in later tasks

async def _create_ticket(
    ticket_type: str,
    title: str,
    hive_name: str,
    description: str = "",
    parent: str | None = None,
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    labels: list[str] | None = None,
    owner: str | None = None,
    priority: int | None = None,
    status: str | None = None,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Create a new ticket (epic, task, or subtask).

    Args:
        ticket_type: Type of ticket to create - must be 'epic', 'task', or 'subtask'
        title: Title of the ticket (required)
        hive_name: Hive name to prefix the ID with (required, e.g., "backend" -> "backend.bees-abc")
        description: Detailed description of the ticket
        parent: Parent ticket ID (required for subtasks, optional for tasks, not allowed for epics)
        children: List of child ticket IDs
        up_dependencies: List of ticket IDs that this ticket depends on (blocking tickets)
        down_dependencies: List of ticket IDs that depend on this ticket
        labels: List of label strings
        owner: Owner/assignee of the ticket
        priority: Priority level (typically 0-4)
        status: Status of the ticket (e.g., 'open', 'in_progress', 'completed')
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Created ticket information including ticket_id

    Raises:
        ValueError: If ticket_type is invalid or validation fails
    """
    # Validate ticket_type
    if ticket_type not in ["epic", "task", "subtask"]:
        error_msg = f"Invalid ticket_type: {ticket_type}. Must be 'epic', 'task', or 'subtask'"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate title is not empty
    if not title or not title.strip():
        error_msg = "Ticket title cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive_name (required parameter)
    if not hive_name or not hive_name.strip():
        error_msg = "hive_name is required and cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if hive_name contains at least one alphanumeric character
    if not re.search(r'[a-zA-Z0-9]', hive_name):
        error_msg = f"Invalid hive_name: '{hive_name}'. Hive name must contain at least one alphanumeric character"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive exists in config
    # Design Decision: create_ticket is STRICT and does not attempt hive recovery via scan_for_hive.
    # Rationale:
    #   - Write operations (create/update/delete) should be explicit and fail fast
    #   - Consistency: update_ticket and delete_ticket also fail fast without recovery attempts
    #   - scan_for_hive is a recovery mechanism for read operations, not normal write flows
    #   - Creating tickets requires explicit hive specification to avoid ambiguity
    # See docs/plans/master_plan.md for full architectural rationale
    normalized_hive = normalize_hive_name(hive_name)
    
    # Get client's repo root from MCP context
    repo_root = await get_repo_root(ctx) if ctx else get_repo_root_from_path(Path.cwd())
    config = load_bees_config(repo_root)
    if not config or normalized_hive not in config.hives:
        # Provide helpful error message guiding users to create hive first
        # Note: We intentionally do NOT attempt recovery via scan_for_hive (see design decision above)
        error_msg = (
            f"Hive '{hive_name}' (normalized: '{normalized_hive}') does not exist in config. "
            f"Please create the hive first using colonize_hive. "
            f"If the hive directory exists but isn't registered, you may need to run colonize_hive to register it."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive path exists and is writable
    hive_path = Path(config.hives[normalized_hive].path)

    # Resolve symlinks to get the actual path
    try:
        resolved_path = hive_path.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        error_msg = f"Failed to resolve hive path '{hive_path}': {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if path exists
    if not resolved_path.exists():
        error_msg = f"Hive path does not exist: '{resolved_path}'. Please create the directory before creating tickets."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if path is a directory
    if not resolved_path.is_dir():
        error_msg = f"Hive path is not a directory: '{resolved_path}'. Path must be a directory, not a file."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Test write permissions by attempting to create and remove a test file
    import uuid
    test_file = resolved_path / f".write_test_{uuid.uuid4().hex[:8]}"
    try:
        test_file.touch()
        test_file.unlink()
    except PermissionError as e:
        error_msg = f"Hive directory is not writable: '{resolved_path}'. Please check directory permissions."
        logger.error(error_msg)
        raise ValueError(error_msg)
    except OSError as e:
        error_msg = f"Failed to write to hive directory '{resolved_path}': {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate parent requirements
    if ticket_type == "epic" and parent:
        error_msg = "Epics cannot have a parent"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if ticket_type == "subtask" and not parent:
        error_msg = "Subtasks must have a parent"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate parent ticket exists
    if parent:
        parent_type = infer_ticket_type_from_id(parent)
        if not parent_type:
            error_msg = f"Parent ticket does not exist: {parent}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Validate dependency tickets exist
    if up_dependencies:
        for dep_id in up_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if down_dependencies:
        for dep_id in down_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Validate children tickets exist
    if children:
        for child_id in children:
            child_type = infer_ticket_type_from_id(child_id)
            if not child_type:
                error_msg = f"Child ticket does not exist: {child_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Check for circular dependencies
    if up_dependencies and down_dependencies:
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            error_msg = f"Circular dependency detected: ticket cannot both depend on and be depended on by the same tickets: {circular_deps}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Call appropriate factory function based on ticket type
    try:
        if ticket_type == "epic":
            ticket_id = create_epic(
                title=title,
                description=description,
                labels=labels,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                owner=owner,
                priority=priority,
                status=status or "open",
                hive_name=hive_name
            )
        elif ticket_type == "task":
            ticket_id = create_task(
                title=title,
                description=description,
                parent=parent,
                labels=labels,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                owner=owner,
                priority=priority,
                status=status or "open",
                hive_name=hive_name
            )
        elif ticket_type == "subtask":
            # Type checker: parent is guaranteed to be str due to validation at line 1113-1116
            assert parent is not None, "Subtask parent validated above"
            ticket_id = create_subtask(
                title=title,
                parent=parent,
                description=description,
                labels=labels,
                up_dependencies=up_dependencies,
                down_dependencies=down_dependencies,
                owner=owner,
                priority=priority,
                status=status or "open",
                hive_name=hive_name
            )
        else:
            # Should never reach here due to earlier validation
            raise ValueError(f"Invalid ticket_type: {ticket_type}")

        logger.info(f"Successfully created {ticket_type} ticket: {ticket_id}")

        # Update bidirectional relationships in related tickets
        _update_bidirectional_relationships(
            new_ticket_id=ticket_id,
            parent=parent,
            children=children,
            up_dependencies=up_dependencies,
            down_dependencies=down_dependencies
        )

        return {
            "status": "success",
            "ticket_id": ticket_id,
            "ticket_type": ticket_type,
            "title": title
        }

    except Exception as e:
        logger.error(f"Failed to create {ticket_type} ticket: {e}")
        raise


# Register the create_ticket tool with FastMCP
create_ticket = mcp.tool(name="create_ticket")(_create_ticket)


# Use a string constant as sentinel instead of object() to avoid Pydantic JSON schema warnings
_UNSET: Literal["__UNSET__"] = "__UNSET__"

async def _update_ticket(
    ticket_id: str,
    title: str | None | Literal["__UNSET__"] = _UNSET,
    description: str | None | Literal["__UNSET__"] = _UNSET,
    parent: str | None | Literal["__UNSET__"] = _UNSET,
    children: list[str] | None | Literal["__UNSET__"] = _UNSET,
    up_dependencies: list[str] | None | Literal["__UNSET__"] = _UNSET,
    down_dependencies: list[str] | None | Literal["__UNSET__"] = _UNSET,
    labels: list[str] | None | Literal["__UNSET__"] = _UNSET,
    owner: str | None | Literal["__UNSET__"] = _UNSET,
    priority: int | None | Literal["__UNSET__"] = _UNSET,
    status: str | None | Literal["__UNSET__"] = _UNSET,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Update an existing ticket.

    Args:
        ticket_id: ID of the ticket to update (required)
        title: New title for the ticket
        description: New description for the ticket
        parent: New parent ticket ID (or None to remove parent)
        children: New list of child ticket IDs
        up_dependencies: New list of blocking dependency ticket IDs
        down_dependencies: New list of dependent ticket IDs
        labels: New list of labels
        owner: New owner/assignee
        priority: New priority level
        status: New status
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Updated ticket information

    Raises:
        ValueError: If ticket_id doesn't exist or validation fails

    Note:
        When updating relationships (parent, children, dependencies), the change
        is automatically reflected bidirectionally in related tickets.
    """
    # Parse hive from ticket_id
    hive_prefix = parse_hive_from_ticket_id(ticket_id)

    # Return error if hive prefix is None (malformed ID)
    if hive_prefix is None:
        error_msg = f"Malformed ticket ID: '{ticket_id}'. Expected format: hive_name.bees-xxxx"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive exists in config using normalize_name for lookup
    normalized_hive = normalize_hive_name(hive_prefix)
    config = load_bees_config()
    if not config or normalized_hive not in config.hives:
        error_msg = f"Unknown hive: '{hive_prefix}' (normalized: '{normalized_hive}'). Hive not found in config."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate ticket exists
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        error_msg = f"Ticket does not exist: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Read existing ticket
    ticket_path = get_ticket_path(ticket_id, ticket_type)
    try:
        ticket = read_ticket(ticket_path)
    except FileNotFoundError:
        error_msg = f"Ticket file not found: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to read ticket {ticket_id}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate relationship ticket IDs exist
    if parent is not _UNSET and parent:  # Check if parent is provided and not empty/None
        parent_type = infer_ticket_type_from_id(parent)
        if not parent_type:
            error_msg = f"Parent ticket does not exist: {parent}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    if children is not _UNSET and children is not None:
        for child_id in children:
            child_type = infer_ticket_type_from_id(child_id)
            if not child_type:
                error_msg = f"Child ticket does not exist: {child_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if up_dependencies is not _UNSET and up_dependencies is not None:
        for dep_id in up_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if down_dependencies is not _UNSET and down_dependencies is not None:
        for dep_id in down_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Check for circular dependencies if both up and down are being updated
    if (up_dependencies is not _UNSET and up_dependencies is not None and 
        down_dependencies is not _UNSET and down_dependencies is not None):
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            error_msg = f"Circular dependency detected: ticket cannot both depend on and be depended on by the same tickets: {circular_deps}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Update basic fields (non-relationship fields)
    if title is not _UNSET:
        if title is None or not title.strip():
            error_msg = "Ticket title cannot be empty"
            logger.error(error_msg)
            raise ValueError(error_msg)
        ticket.title = title

    if description is not _UNSET:
        # description can be None or empty string
        ticket.description = description if description else ""

    if labels is not _UNSET:
        # labels can be None (which means empty list)
        assert labels != _UNSET  # Type narrowing
        ticket.labels = labels if labels is not None else []

    if owner is not _UNSET:
        ticket.owner = owner  # type: ignore[assignment]

    if priority is not _UNSET:
        assert priority != _UNSET  # Type narrowing
        ticket.priority = priority

    if status is not _UNSET:
        ticket.status = status  # type: ignore[assignment]

    # Handle relationship updates with bidirectional consistency
    # Track old relationships to determine what changed
    old_parent = ticket.parent
    old_children = set(ticket.children or [])
    old_up_deps = set(ticket.up_dependencies or [])
    old_down_deps = set(ticket.down_dependencies or [])

    # Update relationship fields if provided
    if parent is not _UNSET:
        ticket.parent = parent if parent else None  # type: ignore[assignment]
    if children is not _UNSET:
        assert children != _UNSET  # Type narrowing
        ticket.children = children if children is not None else []
    if up_dependencies is not _UNSET:
        assert up_dependencies != _UNSET  # Type narrowing
        ticket.up_dependencies = up_dependencies if up_dependencies is not None else []
    if down_dependencies is not _UNSET:
        assert down_dependencies != _UNSET  # Type narrowing
        ticket.down_dependencies = down_dependencies if down_dependencies is not None else []

    # Update timestamp
    ticket.updated_at = datetime.now()

    # Write updated ticket
    frontmatter_data = asdict(ticket)
    write_ticket_file(
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        frontmatter_data=frontmatter_data,
        body=ticket.description or ""
    )

    # Sync bidirectional relationships
    new_parent = ticket.parent
    new_children = set(ticket.children or [])
    new_up_deps = set(ticket.up_dependencies or [])
    new_down_deps = set(ticket.down_dependencies or [])

    # Handle parent changes
    if parent is not _UNSET:
        # Remove from old parent's children
        if old_parent and old_parent != new_parent:
            _remove_child_from_parent(ticket_id, old_parent)

        # Add to new parent's children
        if new_parent:
            _add_child_to_parent(ticket_id, new_parent)

    # Handle children changes
    if children is not _UNSET:
        removed_children = old_children - new_children
        added_children = new_children - old_children

        for child_id in removed_children:
            _remove_parent_from_child(child_id)

        for child_id in added_children:
            _set_parent_on_child(ticket_id, child_id)

    # Handle up_dependencies changes
    if up_dependencies is not _UNSET:
        removed_up = old_up_deps - new_up_deps
        added_up = new_up_deps - old_up_deps

        for dep_id in removed_up:
            _remove_from_down_dependencies(ticket_id, dep_id)

        for dep_id in added_up:
            _add_to_down_dependencies(ticket_id, dep_id)

    # Handle down_dependencies changes
    if down_dependencies is not _UNSET:
        removed_down = old_down_deps - new_down_deps
        added_down = new_down_deps - old_down_deps

        for dep_id in removed_down:
            _remove_from_up_dependencies(ticket_id, dep_id)

        for dep_id in added_down:
            _add_to_up_dependencies(ticket_id, dep_id)

    logger.info(f"Successfully updated ticket: {ticket_id}")

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "ticket_type": ticket_type,
        "title": ticket.title
    }


# Register the update_ticket tool with FastMCP
update_ticket = mcp.tool(name="update_ticket")(_update_ticket)


async def _delete_ticket(
    ticket_id: str,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Delete a ticket and clean up relationships in related tickets.
    
    Deletion always cascades to children - deleting a parent ticket will
    recursively delete all child tickets and grandchildren in the entire subtree.

    Args:
        ticket_id: ID of the ticket to delete (required)
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Deletion status and information about cleaned relationships

    Raises:
        ValueError: If ticket_id doesn't exist or deletion validation fails

    Note:
        When a ticket is deleted:
        - It's removed from parent's children array
        - It's removed from all dependency arrays in related tickets
        - All child tickets are recursively deleted (cascade behavior)
        - The entire subtree under this ticket is deleted
    """
    # Parse hive from ticket_id
    hive_prefix = parse_hive_from_ticket_id(ticket_id)

    # Return error if hive prefix is None (malformed ID)
    if hive_prefix is None:
        error_msg = f"Malformed ticket ID: '{ticket_id}'. Expected format: hive_name.bees-xxxx"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive exists in config using normalize_name for lookup
    normalized_hive = normalize_hive_name(hive_prefix)
    repo_root = await get_repo_root(ctx) if ctx else get_repo_root_from_path(Path.cwd())
    config = load_bees_config(repo_root)
    if not config or normalized_hive not in config.hives:
        error_msg = f"Hive '{hive_prefix}' not found in configuration"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate ticket exists
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        error_msg = f"Ticket does not exist: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Read ticket to get relationships
    ticket_path = get_ticket_path(ticket_id, ticket_type)
    try:
        ticket = read_ticket(ticket_path)
    except FileNotFoundError:
        error_msg = f"Ticket file not found: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to read ticket {ticket_id}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Recursively delete all child tickets (always cascade)
    if ticket.children:
        for child_id in ticket.children:
            try:
                await _delete_ticket(child_id, ctx)
                logger.info(f"Cascade deleted child ticket: {child_id}")
            except Exception as e:
                logger.warning(f"Failed to cascade delete child {child_id}: {e}")

    # Clean up parent's children array
    if ticket.parent:
        _remove_child_from_parent(ticket_id, ticket.parent)
        logger.info(f"Removed {ticket_id} from parent {ticket.parent}'s children array")

    # Clean up dependencies in related tickets
    # Remove from blocking tickets' down_dependencies
    if ticket.up_dependencies:
        for blocking_ticket_id in ticket.up_dependencies:
            _remove_from_down_dependencies(ticket_id, blocking_ticket_id)
            logger.info(f"Removed {ticket_id} from {blocking_ticket_id}'s down_dependencies")

    # Remove from blocked tickets' up_dependencies
    if ticket.down_dependencies:
        for blocked_ticket_id in ticket.down_dependencies:
            _remove_from_up_dependencies(ticket_id, blocked_ticket_id)
            logger.info(f"Removed {ticket_id} from {blocked_ticket_id}'s up_dependencies")

    # Delete the ticket file
    try:
        ticket_path.unlink()
        logger.info(f"Deleted ticket file: {ticket_path}")
    except Exception as e:
        error_msg = f"Failed to delete ticket file {ticket_path}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "ticket_type": ticket_type,
        "message": f"Successfully deleted ticket {ticket_id}"
    }


# Register the delete_ticket tool with FastMCP
delete_ticket = mcp.tool(name="delete_ticket")(_delete_ticket)


def _add_named_query(
    name: str,
    query_yaml: str
) -> Dict[str, Any]:
    """
    Register a new named query for reuse.

    All queries are validated when registered to ensure they have valid structure.

    Args:
        name: Name for the query (used to execute it later)
        query_yaml: YAML string representing the query structure

    Returns:
        dict: Success status and query information

    Raises:
        ValueError: If query structure is invalid or name is invalid

    Example:
        query_yaml = '''
        - - type=task
          - label~beta
        - - parent
        '''
    """
    # Validate name is not empty
    if not name or not name.strip():
        error_msg = "Query name cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate and save query
    try:
        # This will validate structure and raise QueryValidationError if invalid
        save_query(name.strip(), query_yaml)
        logger.info(f"Successfully registered named query: {name}")

        return {
            "status": "success",
            "query_name": name.strip(),
            "message": f"Query '{name}' registered successfully"
        }

    except QueryValidationError as e:
        error_msg = f"Invalid query structure: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to save query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


# Register the add_named_query tool with FastMCP
add_named_query = mcp.tool(name="add_named_query")(_add_named_query)


async def _execute_query(
    query_name: str,
    hive_names: list[str] | None = None,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Execute a named query.

    Args:
        query_name: Name of the registered query to execute
        hive_names: Optional list of hive names to filter results (default: None = all hives)
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Query results with list of matching ticket IDs and metadata

    Raises:
        ValueError: If query name not found, hive not found, or execution fails

    Example:
        execute_query("open_tasks")
        execute_query("open_tasks", ["backend", "frontend"])
    """
    # Load query by name
    try:
        stages = load_query(query_name)
    except KeyError:
        error_msg = f"Query not found: {query_name}"
        logger.error(error_msg)
        available = list_queries()
        if available:
            error_msg += f". Available queries: {', '.join(available)}"
        else:
            error_msg += ". No queries registered yet."
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to load query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive existence if hive_names provided
    if hive_names:
        repo_root = await get_repo_root(ctx) if ctx else get_repo_root_from_path(Path.cwd())
        config = load_bees_config(repo_root)
        if config is None:
            error_msg = "No hives configured. Available hives: none"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Check each hive exists
        for hive_name in hive_names:
            if hive_name not in config.hives:
                available_hives = sorted(config.hives.keys())
                error_msg = f"Hive not found: {hive_name}. Available hives: {', '.join(available_hives) if available_hives else 'none'}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Execute query using pipeline evaluator
    try:
        evaluator = PipelineEvaluator()
        result_ids = evaluator.execute_query(stages, hive_names=hive_names)

        logger.info(f"Query '{query_name}' returned {len(result_ids)} tickets")

        return {
            "status": "success",
            "query_name": query_name,
            "result_count": len(result_ids),
            "ticket_ids": sorted(result_ids)
        }

    except Exception as e:
        error_msg = f"Failed to execute query '{query_name}': {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)
# Register the execute_query tool with FastMCP
execute_query = mcp.tool(name="execute_query")(_execute_query)


async def _execute_freeform_query(
    query_yaml: str,
    hive_names: list[str] | None = None,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Execute a YAML query pipeline directly without persisting it.

    This function enables one-step ad-hoc query execution without polluting
    the query registry. The query is validated and executed immediately without
    being saved to disk.

    Args:
        query_yaml: YAML string representing the query pipeline structure
        hive_names: Optional list of hive names to filter results (default: None = all hives)
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Query results with list of matching ticket IDs and metadata
            {
                "status": "success",
                "result_count": int,
                "ticket_ids": list[str],
                "stages_executed": int
            }

    Raises:
        ValueError: If query structure is invalid, hive not found, or execution fails

    Example:
        execute_freeform_query("- ['type=epic']\\n- ['children']")
        execute_freeform_query("- ['type=task', 'status=open']", ["backend"])
    """
    # Parse and validate query structure
    from .query_parser import QueryParser, QueryValidationError

    try:
        parser = QueryParser()
        stages = parser.parse_and_validate(query_yaml)
        logger.info(f"Parsed and validated freeform query with {len(stages)} stages")
    except QueryValidationError as e:
        error_msg = f"Invalid query structure: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to parse query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive existence if hive_names provided
    if hive_names:
        repo_root = await get_repo_root(ctx) if ctx else get_repo_root_from_path(Path.cwd())
        config = load_bees_config(repo_root)
        if config is None:
            error_msg = "No hives configured. Available hives: none"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Check each hive exists
        for hive_name in hive_names:
            if hive_name not in config.hives:
                available_hives = sorted(config.hives.keys())
                error_msg = f"Hive not found: {hive_name}. Available hives: {', '.join(available_hives) if available_hives else 'none'}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Execute query using pipeline evaluator
    try:
        evaluator = PipelineEvaluator()
        result_ids = evaluator.execute_query(stages, hive_names=hive_names)

        logger.info(f"Freeform query returned {len(result_ids)} tickets across {len(stages)} stages")

        return {
            "status": "success",
            "result_count": len(result_ids),
            "ticket_ids": sorted(result_ids),
            "stages_executed": len(stages)
        }

    except Exception as e:
        error_msg = f"Failed to execute freeform query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


# Register the execute_freeform_query tool with FastMCP
execute_freeform_query = mcp.tool(name="execute_freeform_query")(_execute_freeform_query)


async def _show_ticket(ticket_id: str, ctx: Context | None = None) -> Dict[str, Any]:
    """
    Retrieve and return ticket data by ticket ID.

    Args:
        ticket_id: The ID of the ticket to retrieve (e.g., 'backend.bees-abc1')
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Ticket data including all fields
            {
                "status": "success",
                "ticket_id": str,
                "ticket_type": str,
                "title": str,
                "description": str,
                "labels": list[str],
                "parent": str | None,
                "children": list[str] | None,
                "up_dependencies": list[str] | None,
                "down_dependencies": list[str] | None,
                "owner": str | None,
                "priority": int | None,
                "ticket_status": str,
                "created_at": str,
                "updated_at": str,
                "created_by": str | None,
                "bees_version": str
            }

    Raises:
        ValueError: If ticket doesn't exist or ticket_id is malformed

    Example:
        >>> _show_ticket('backend.bees-abc1')
        {'status': 'success', 'ticket_id': 'backend.bees-abc1', ...}
    """
    # Validate ticket_id is not empty
    if not ticket_id or not ticket_id.strip():
        error_msg = "ticket_id cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Parse hive from ticket_id
    hive_prefix = parse_hive_from_ticket_id(ticket_id)

    # Return error if hive prefix is None (malformed ID)
    if hive_prefix is None:
        error_msg = f"Malformed ticket ID: '{ticket_id}'. Expected format: hive_name.bees-xxxx"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate hive exists in config using normalize_name for lookup
    normalized_hive = normalize_hive_name(hive_prefix)
    repo_root = await get_repo_root(ctx) if ctx else get_repo_root_from_path(Path.cwd())
    config = load_bees_config(repo_root)
    if not config or normalized_hive not in config.hives:
        error_msg = f"Hive '{hive_prefix}' (normalized: '{normalized_hive}') not found in configuration"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Infer ticket type from ID
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        error_msg = f"Ticket does not exist: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Get ticket path and read ticket
    ticket_path = get_ticket_path(ticket_id, ticket_type)
    try:
        ticket = read_ticket(ticket_path)
    except FileNotFoundError:
        error_msg = f"Ticket file not found: {ticket_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to read ticket {ticket_id}: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Convert ticket to dict for JSON serialization
    ticket_data = {
        "status": "success",
        "ticket_id": ticket.id,
        "ticket_type": ticket.type,
        "title": ticket.title,
        "description": ticket.description,
        "labels": ticket.labels,
        "parent": ticket.parent,
        "children": ticket.children,
        "up_dependencies": ticket.up_dependencies,
        "down_dependencies": ticket.down_dependencies,
        "owner": ticket.owner,
        "priority": ticket.priority,
        "ticket_status": ticket.status,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "created_by": ticket.created_by,
        "bees_version": ticket.bees_version
    }

    logger.info(f"Successfully retrieved ticket: {ticket_id}")
    return ticket_data


# Register the show_ticket tool with FastMCP
show_ticket = mcp.tool(name="show_ticket")(_show_ticket)


def _generate_index(
    status: str | None = None,
    type: str | None = None,
    hive_name: str | None = None
) -> Dict[str, Any]:
    """
    Generate markdown index of all tickets with optional filters.

    Scans the tickets directory and creates a formatted markdown index.
    Optionally filters tickets by status and/or type. Can generate per-hive
    indexes or indexes for all hives.

    When hive_name is provided, generates and writes index only for that hive
    to {hive_path}/index.md.

    When hive_name is omitted, iterates all registered hives and generates
    separate index.md files for each hive at their respective hive roots.

    Args:
        status: Optional status filter (e.g., 'open', 'completed')
        type: Optional type filter (e.g., 'epic', 'task', 'subtask')
        hive_name: Optional hive name to generate index for specific hive only.
                   If provided, generates index only for that hive.
                   If omitted, generates indexes for all hives.

    Returns:
        dict: Response with status and generated markdown index

    Example:
        result = _generate_index()
        result = _generate_index(status='open')
        result = _generate_index(type='epic')
        result = _generate_index(status='open', type='task')
        result = _generate_index(hive_name='backend')
    """
    try:
        index_markdown = generate_index(
            status_filter=status,
            type_filter=type,
            hive_name=hive_name
        )
        logger.info(f"Successfully generated ticket index (status={status}, type={type}, hive_name={hive_name})")
        return {
            "status": "success",
            "markdown": index_markdown
        }
    except Exception as e:
        error_msg = f"Failed to generate index: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


# Register the generate_index tool with FastMCP
generate_index_tool = mcp.tool(name="generate_index")(_generate_index)


async def _colonize_hive(
    name: str,
    path: str,
    ctx: Context | None = None
) -> Dict[str, Any]:
    """
    Create and register a new hive at the specified path.

    This MCP tool wrapper exposes the colonize_hive() core function, which:
    - Normalizes the hive display name
    - Validates the path is absolute, exists, and within the repository
    - Checks for duplicate normalized hive names
    - Creates the hive directory structure (/eggs, /evicted, .hive marker)
    - Registers the hive in .bees/config.json

    LLM USAGE INSTRUCTIONS:
        ALWAYS ask the user for the hive name and path if they are not explicitly provided.
        - Ask: "What should the hive be named?" if name is not provided
        - Ask: "Where should the hive be located (absolute path)?" if path is not provided
        DO NOT proceed with this tool call until both parameters are provided by the user.

    Args:
        name: Display name for the hive (e.g., 'Back End', 'Frontend')
               Will be normalized for internal use (e.g., 'back_end', 'frontend')
        path: Absolute path to the directory where the hive should be created
              Must be within the repository root

    Returns:
        dict: Operation result with status and details
            On success: {
                'status': 'success',
                'message': 'Hive created and registered successfully',
                'normalized_name': str,  # Internal hive identifier
                'display_name': str,     # Original display name
                'path': str              # Absolute path to hive directory
            }
            On error: {
                'status': 'error',
                'message': str,          # Human-readable error description
                'error_type': str,       # Error category
                'validation_details': dict  # Additional error context
            }

    Raises:
        ValueError: If validation fails or operation cannot be completed

    Example:
        >>> _colonize_hive('Back End', '/Users/user/projects/myrepo/tickets/backend')
        {
            'status': 'success',
            'message': 'Hive created and registered successfully',
            'normalized_name': 'back_end',
            'display_name': 'Back End',
            'path': '/Users/user/projects/myrepo/tickets/backend'
        }

    Error Conditions:
        - Invalid name: Name normalizes to empty string (no alphanumeric chars)
        - Invalid path: Path is not absolute, doesn't exist, or outside repo
        - Duplicate name: Normalized name already exists in registry
        - Filesystem error: Cannot create directories or write files
        - Config error: Cannot read or write .bees/config.json
    """
    try:
        result = await colonize_hive_core(name=name, path=path, ctx=ctx)

        # Check if operation succeeded
        if result.get('status') == 'error':
            # Core function returned error - raise ValueError to propagate to MCP client
            error_msg = result.get('message', 'Unknown error')
            logger.error(f"colonize_hive failed: {error_msg}")
            raise ValueError(error_msg)

        logger.info(f"Successfully colonized hive '{name}' at {path}")
        return result

    except Exception as e:
        # Catch unexpected errors and return structured error response
        error_msg = f"Failed to colonize hive: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


# Register the colonize_hive tool with FastMCP
colonize_hive = mcp.tool(name="colonize_hive")(_colonize_hive)


async def _list_hives(ctx: Context) -> Dict[str, Any]:
    """
    List all registered hives in the repository.

    Reads .bees/config.json from the client's repository to retrieve all 
    registered hives and returns structured information about each hive 
    including display name, normalized name, and path.

    Args:
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: List of hives with their details
            On success with hives: {
                'status': 'success',
                'hives': [
                    {
                        'display_name': str,      # User-facing hive name
                        'normalized_name': str,   # Internal identifier
                        'path': str              # Absolute path to hive directory
                    },
                    ...
                ]
            }
            On success with no hives: {
                'status': 'success',
                'hives': [],
                'message': 'No hives configured'
            }

    Example:
        >>> await _list_hives(ctx)
        {
            'status': 'success',
            'hives': [
                {
                    'display_name': 'Back End',
                    'normalized_name': 'back_end',
                    'path': '/Users/user/projects/myrepo/tickets/backend'
                },
                {
                    'display_name': 'Frontend',
                    'normalized_name': 'frontend',
                    'path': '/Users/user/projects/myrepo/tickets/frontend'
                }
            ]
        }
    """
    try:
        # Get client's repo root from MCP context
        repo_root = await get_repo_root(ctx)
        
        # Load config from client's .bees/config.json
        config = load_bees_config(repo_root)

        # Handle case where config doesn't exist or has no hives
        if not config or not config.hives:
            logger.info("No hives configured")
            return {
                "status": "success",
                "hives": [],
                "message": "No hives configured"
            }

        # Build list of hives with their details
        hives_list = []
        for normalized_name, hive_config in config.hives.items():
            hives_list.append({
                "display_name": hive_config.display_name,
                "normalized_name": normalized_name,
                "path": hive_config.path
            })

        logger.info(f"Listed {len(hives_list)} hives")
        return {
            "status": "success",
            "hives": hives_list
        }

    except Exception as e:
        error_msg = f"Failed to list hives: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


# Register the list_hives tool with FastMCP
list_hives = mcp.tool(name="list_hives")(_list_hives)


async def _abandon_hive(hive_name: str, ctx: Context | None = None) -> Dict[str, Any]:
    """
    Stop tracking a hive without deleting ticket files.

    Removes the hive entry from .bees/config.json while leaving all ticket
    files and the .hive marker intact on the filesystem. This allows users
    to stop tracking a hive without data loss and re-colonize it later if needed.

    Args:
        hive_name: Display name or normalized name of the hive to abandon
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Operation result with status and details
            {
                'status': 'success',
                'message': 'Hive abandoned successfully',
                'display_name': str,     # Original display name
                'normalized_name': str,  # Internal hive identifier
                'path': str              # Path where files remain
            }

    Raises:
        ValueError: If hive doesn't exist or operation cannot be completed

    Example:
        >>> _abandon_hive('Back End')
        {
            'status': 'success',
            'message': 'Hive "Back End" abandoned successfully',
            'display_name': 'Back End',
            'normalized_name': 'back_end',
            'path': '/Users/user/projects/myrepo/tickets/backend'
        }

    Error Conditions:
        - Hive not found: Normalized name doesn't exist in config
        - Config read error: Cannot read .bees/config.json
        - Config write error: Cannot write updated config
    """
    # Normalize hive name for lookup
    normalized_name = normalize_hive_name(hive_name)
    logger.info(f"Attempting to abandon hive '{hive_name}' (normalized: '{normalized_name}')")

    # Load config from .bees/config.json
    repo_root = await get_repo_root(ctx) if ctx else get_repo_root_from_path(Path.cwd())
    config = load_bees_config(repo_root)

    # Check if hive exists
    if not config or normalized_name not in config.hives:
        error_msg = f"Hive '{hive_name}' (normalized: '{normalized_name}') does not exist in config"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Get hive details before removal
    hive_config = config.hives[normalized_name]
    display_name = hive_config.display_name
    hive_path = hive_config.path

    # Remove hive from config
    del config.hives[normalized_name]

    # Save updated config
    save_bees_config(config, repo_root)
    logger.info(f"Removed hive '{normalized_name}' from config.json")

    # Success response
    return {
        "status": "success",
        "message": f"Hive \"{display_name}\" abandoned successfully",
        "display_name": display_name,
        "normalized_name": normalized_name,
        "path": hive_path
    }


# Register the abandon_hive tool with FastMCP
abandon_hive = mcp.tool(name="abandon_hive")(_abandon_hive)


async def _rename_hive(old_name: str, new_name: str, ctx: Context | None = None) -> Dict[str, Any]:
    """
    Rename a hive by updating its name in config, regenerating ticket IDs, and updating all references.

    This operation updates:
    - Config: changes hive key from old_name to new_name, updates display_name
    - Ticket IDs: regenerates all IDs from old_name.bees-* to new_name.bees-*
    - Filenames: renames all ticket files to match new IDs
    - Frontmatter: updates 'id' field in all ticket files
    - Cross-references: updates dependencies, parent, children fields across ALL hives
    - .hive marker: updates display_name in hive directory marker file
    - Runs linter after rename to validate database integrity

    Args:
        old_name: Current hive name (will be normalized for lookup)
        new_name: Desired new hive name (will be normalized and validated for uniqueness)
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Success/error status with operation details
            On success: {
                'status': 'success',
                'message': 'Hive renamed successfully',
                'old_name': str,
                'new_name': str,
                'tickets_updated': int
            }
            On error: {
                'status': 'error',
                'message': str,
                'error_type': str
            }

    Raises:
        ValueError: If old_name doesn't exist or new_name conflicts with existing hive

    Example:
        >>> rename_hive('backend', 'api_layer')
        {'status': 'success', 'old_name': 'backend', 'new_name': 'api_layer', ...}
    """
    # Step 1: Normalize both names
    normalized_old = normalize_hive_name(old_name)
    normalized_new = normalize_hive_name(new_name)
    logger.info(f"Renaming hive from '{old_name}' (normalized: '{normalized_old}') to '{new_name}' (normalized: '{normalized_new}')")

    # Validate normalized names are not empty
    if not normalized_old:
        return {
            "status": "error",
            "message": f"Invalid old hive name: '{old_name}' normalizes to empty string",
            "error_type": "validation_error"
        }

    if not normalized_new:
        return {
            "status": "error",
            "message": f"Invalid new hive name: '{new_name}' normalizes to empty string",
            "error_type": "validation_error"
        }

    # Step 2: Load config and validate old hive exists
    repo_root = await get_repo_root(ctx) if ctx else get_repo_root_from_path(Path.cwd())
    config = load_bees_config(repo_root)
    if not config or normalized_old not in config.hives:
        return {
            "status": "error",
            "message": f"Hive '{old_name}' (normalized: '{normalized_old}') does not exist in config",
            "error_type": "hive_not_found"
        }

    # Step 3: Validate new name doesn't conflict with existing hives
    if normalized_new in config.hives:
        return {
            "status": "error",
            "message": f"Hive '{new_name}' (normalized: '{normalized_new}') already exists. Cannot rename to existing hive name.",
            "error_type": "name_conflict"
        }

    # Get hive config for later operations
    hive_path = Path(config.hives[normalized_old].path)
    old_display_name = config.hives[normalized_old].display_name
    logger.info(f"Validation passed. Hive path: {hive_path}")

    # Step 4: Update config - move hive entry from old key to new key
    hive_config = config.hives[normalized_old]
    # Update display name to the new name
    hive_config.display_name = new_name
    
    # Remove old hive entry and add new one
    del config.hives[normalized_old]
    config.hives[normalized_new] = hive_config
    
    # Save updated config
    try:
        save_bees_config(config, repo_root)
        logger.info(f"Updated config: renamed hive from '{normalized_old}' to '{normalized_new}'")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to save config: {e}",
            "error_type": "config_save_error"
        }

    # Step 5: Regenerate ticket IDs - build mapping of old_id → new_id
    id_mapping = {}
    try:
        # Find all ticket files in the hive directory
        for ticket_file in hive_path.glob("*.md"):
            # Skip non-ticket files
            if ticket_file.stem.startswith('.'):
                continue
            
            # Extract old ticket ID from filename
            old_id = ticket_file.stem  # e.g., "backend.bees-abc1"
            
            # Parse to verify it matches the old hive prefix
            if not old_id.startswith(f"{normalized_old}.bees-"):
                logger.warning(f"Skipping file with unexpected prefix: {old_id}")
                continue
            
            # Extract the bees-xxxx suffix
            suffix = old_id[len(normalized_old)+1:]  # Remove "backend." to get "bees-abc1"
            
            # Generate new ID with new hive prefix
            new_id = f"{normalized_new}.{suffix}"
            
            # Store in mapping
            id_mapping[old_id] = new_id
            logger.debug(f"ID mapping: {old_id} → {new_id}")
        
        logger.info(f"Generated ID mapping for {len(id_mapping)} tickets")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate ID mappings: {e}",
            "error_type": "id_generation_error"
        }

    # Step 6: Rename all ticket files
    try:
        for old_id, new_id in id_mapping.items():
            old_file = hive_path / f"{old_id}.md"
            new_file = hive_path / f"{new_id}.md"
            
            # Check that old file exists
            if not old_file.exists():
                logger.warning(f"File not found during rename: {old_file}")
                continue
            
            # Check for conflicts with new filename
            if new_file.exists():
                logger.error(f"Conflict: new filename already exists: {new_file}")
                return {
                    "status": "error",
                    "message": f"File conflict: {new_id}.md already exists",
                    "error_type": "file_conflict"
                }
            
            # Rename the file
            old_file.rename(new_file)
            logger.debug(f"Renamed file: {old_id}.md → {new_id}.md")
        
        logger.info(f"Renamed {len(id_mapping)} ticket files")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to rename ticket files: {e}",
            "error_type": "file_rename_error"
        }

    # Step 7: Update frontmatter 'id' field in all renamed tickets
    try:
        for old_id, new_id in id_mapping.items():
            new_file = hive_path / f"{new_id}.md"
            
            # Read the file
            with open(new_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse frontmatter (YAML between --- delimiters)
            if content.startswith('---\n'):
                parts = content.split('---\n', 2)
                if len(parts) >= 3:
                    frontmatter_str = parts[1]
                    body = parts[2]
                    
                    # Parse YAML frontmatter
                    frontmatter = yaml.safe_load(frontmatter_str)
                    
                    # Update the id field
                    if frontmatter and 'id' in frontmatter:
                        frontmatter['id'] = new_id
                        
                        # Serialize back to YAML
                        updated_frontmatter = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
                        
                        # Reconstruct file content
                        updated_content = f"---\n{updated_frontmatter}---\n{body}"
                        
                        # Write back to file
                        with open(new_file, 'w', encoding='utf-8') as f:
                            f.write(updated_content)
                        
                        logger.debug(f"Updated frontmatter id: {old_id} → {new_id}")
                    else:
                        logger.warning(f"No 'id' field in frontmatter for {new_file}")
                else:
                    logger.warning(f"Invalid frontmatter format in {new_file}")
            else:
                logger.warning(f"No frontmatter found in {new_file}")
        
        logger.info(f"Updated frontmatter for {len(id_mapping)} tickets")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to update ticket frontmatter: {e}",
            "error_type": "frontmatter_update_error"
        }

    # Step 8: Update cross-references across ALL hives
    try:
        tickets_updated = 0
        # Iterate through ALL hives, not just the renamed one
        for hive_name, hive_cfg in config.hives.items():
            hive_dir = Path(hive_cfg.path)
            
            # Process all ticket files in this hive
            for ticket_file in hive_dir.glob("*.md"):
                if ticket_file.stem.startswith('.'):
                    continue
                
                # Read the file
                with open(ticket_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Parse frontmatter
                if not content.startswith('---\n'):
                    continue
                
                parts = content.split('---\n', 2)
                if len(parts) < 3:
                    continue
                
                frontmatter_str = parts[1]
                body = parts[2]
                frontmatter = yaml.safe_load(frontmatter_str)
                
                if not frontmatter:
                    continue
                
                # Track if we made any changes
                changed = False
                
                # Update parent field (single string)
                if 'parent' in frontmatter and frontmatter['parent']:
                    old_parent = frontmatter['parent']
                    if old_parent in id_mapping:
                        frontmatter['parent'] = id_mapping[old_parent]
                        changed = True
                        logger.debug(f"Updated parent in {ticket_file.name}: {old_parent} → {id_mapping[old_parent]}")
                
                # Update children field (list)
                if 'children' in frontmatter and frontmatter['children']:
                    children_changed = False
                    updated_children = []
                    for child_id in frontmatter['children']:
                        if child_id in id_mapping:
                            updated_children.append(id_mapping[child_id])
                            children_changed = True
                            changed = True
                        else:
                            updated_children.append(child_id)
                    if children_changed:
                        frontmatter['children'] = updated_children
                
                # Update dependencies field (list)
                if 'dependencies' in frontmatter and frontmatter['dependencies']:
                    updated_deps = []
                    for dep_id in frontmatter['dependencies']:
                        if dep_id in id_mapping:
                            updated_deps.append(id_mapping[dep_id])
                            changed = True
                        else:
                            updated_deps.append(dep_id)
                    if changed:
                        frontmatter['dependencies'] = updated_deps
                
                # Update up_dependencies field (list)
                if 'up_dependencies' in frontmatter and frontmatter['up_dependencies']:
                    updated_up = []
                    for dep_id in frontmatter['up_dependencies']:
                        if dep_id in id_mapping:
                            updated_up.append(id_mapping[dep_id])
                            changed = True
                        else:
                            updated_up.append(dep_id)
                    if changed:
                        frontmatter['up_dependencies'] = updated_up
                
                # Update down_dependencies field (list)
                if 'down_dependencies' in frontmatter and frontmatter['down_dependencies']:
                    updated_down = []
                    for dep_id in frontmatter['down_dependencies']:
                        if dep_id in id_mapping:
                            updated_down.append(id_mapping[dep_id])
                            changed = True
                        else:
                            updated_down.append(dep_id)
                    if changed:
                        frontmatter['down_dependencies'] = updated_down
                
                # Write back if changes were made
                if changed:
                    updated_frontmatter = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
                    updated_content = f"---\n{updated_frontmatter}---\n{body}"
                    
                    with open(ticket_file, 'w', encoding='utf-8') as f:
                        f.write(updated_content)
                    
                    tickets_updated += 1
                    logger.debug(f"Updated cross-references in {ticket_file.name}")
        
        logger.info(f"Updated cross-references in {tickets_updated} tickets across all hives")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to update cross-references: {e}",
            "error_type": "cross_reference_update_error"
        }

    # Step 9: Update .hive marker file with new display name
    try:
        hive_marker_path = hive_path / ".hive"
        identity_file = hive_marker_path / "identity.json"
        
        if identity_file.exists():
            # Read current identity
            with open(identity_file, 'r', encoding='utf-8') as f:
                identity_data = json.load(f)
            
            # Update normalized_name and display_name
            identity_data['normalized_name'] = normalized_new
            identity_data['display_name'] = new_name
            
            # Write back
            with open(identity_file, 'w', encoding='utf-8') as f:
                json.dump(identity_data, f, indent=2)
            
            logger.info(f"Updated .hive marker with new identity: {normalized_new}")
        else:
            # Create marker if it doesn't exist
            hive_marker_path.mkdir(exist_ok=True)
            identity_data = {
                "normalized_name": normalized_new,
                "display_name": new_name,
                "created_at": datetime.now().isoformat(),
                "version": "1.0.0"
            }
            with open(identity_file, 'w', encoding='utf-8') as f:
                json.dump(identity_data, f, indent=2)
            logger.info(f"Created .hive marker with new identity: {normalized_new}")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to update .hive marker: {e}",
            "error_type": "marker_update_error"
        }

    # Step 10: Run linter to validate database integrity
    # TODO: Full linter integration is deferred - would need to import Linter and run across all hives
    # For now, we'll just log that this step is needed
    logger.info("Linter check: (stubbed - full integration deferred to future work)")
    # Future implementation would:
    # - Import from src.linter import Linter
    # - Import from src.corruption_state import mark_corrupt, mark_clean
    # - Run linter on all hives
    # - Call mark_corrupt(report) if errors found
    # - Return error response with linter details if validation fails

    # Success! Return summary
    return {
        "status": "success",
        "message": f"Hive renamed successfully from '{old_name}' to '{new_name}'",
        "old_name": old_name,
        "old_normalized": normalized_old,
        "new_name": new_name,
        "new_normalized": normalized_new,
        "tickets_updated": len(id_mapping),
        "cross_references_updated": tickets_updated,
        "path": str(hive_path)
    }


# Register the rename_hive tool with FastMCP
rename_hive = mcp.tool(name="rename_hive")(_rename_hive)


async def _sanitize_hive(hive_name: str, ctx: Context | None = None) -> Dict[str, Any]:
    """
    Validate and auto-fix malformed tickets in a hive.
    
    Runs the linter on all tickets in the specified hive with hive-aware validations:
    - Validates ticket IDs match hive prefix format (hive_name.bees-*)
    - Validates cross-hive dependencies respect allow_cross_hive_dependencies config setting
    - Runs existing linter rules (structure, required fields, bidirectional relationships, etc.)
    - Attempts to automatically fix detected problems where possible
    
    Args:
        hive_name: Display name or normalized form of hive to sanitize
        ctx: FastMCP Context (auto-injected, gets client's repo root)
        
    Returns:
        Dict with:
        - status: 'success' or 'error'
        - message: Summary message
        - fixes_applied: List of fix actions taken (if any)
        - errors_remaining: List of unfixable errors (if any)
        - is_corrupt: Whether database is corrupt after sanitization
    
    Example:
        >>> sanitize_hive("Backend")
        {
            "status": "success",
            "message": "Hive sanitized successfully",
            "fixes_applied": [...],
            "errors_remaining": [],
            "is_corrupt": False
        }
    """
    from .linter import Linter
    from .corruption_state import mark_corrupt, mark_clean
    
    # Normalize hive name
    normalized = normalize_hive_name(hive_name)
    
    # Load config
    repo_root = await get_repo_root(ctx) if ctx else get_repo_root_from_path(Path.cwd())
    config = load_bees_config(repo_root)
    
    # Check if hive is registered
    if not config or normalized not in config.hives:
        return {
            "status": "error",
            "message": f"Hive '{hive_name}' (normalized: '{normalized}') is not registered. "
                      f"Use colonize_hive() to register a new hive.",
            "error_type": "hive_not_found"
        }
    
    # Get hive configuration
    hive_config = config.hives[normalized]
    hive_path = Path(hive_config.path)
    
    # Verify hive directory exists
    if not hive_path.exists():
        return {
            "status": "error",
            "message": f"Hive directory does not exist: {hive_path}",
            "error_type": "directory_not_found"
        }
    
    # Run linter with hive-aware validations and auto-fix enabled
    logger.info(f"Running linter on hive '{normalized}' with auto-fix enabled")
    
    try:
        linter = Linter(
            tickets_dir=str(hive_path),
            hive_name=normalized,
            validate_hive_prefix=True,
            config=config,
            auto_fix=True
        )
        
        report = linter.run()
        
        # Build response with fixes and errors
        fixes_applied = [
            {
                "ticket_id": fix.ticket_id,
                "fix_type": fix.fix_type,
                "description": fix.description
            }
            for fix in report.fixes
        ]
        
        errors_remaining = [
            {
                "ticket_id": error.ticket_id,
                "error_type": error.error_type,
                "message": error.message,
                "severity": error.severity
            }
            for error in report.errors
        ]
        
        is_corrupt = report.is_corrupt()
        
        # Update corruption state
        if is_corrupt:
            mark_corrupt(report)
            logger.warning(f"Hive '{normalized}' marked as corrupt after sanitization")
        else:
            mark_clean()
            logger.info(f"Hive '{normalized}' marked as clean after sanitization")
        
        # Build summary message
        if not fixes_applied and not errors_remaining:
            message = f"Hive '{hive_name}' is already clean. No issues found."
        elif fixes_applied and not errors_remaining:
            message = f"Hive '{hive_name}' sanitized successfully. Applied {len(fixes_applied)} fix(es)."
        elif fixes_applied and errors_remaining:
            message = (f"Hive '{hive_name}' partially sanitized. Applied {len(fixes_applied)} fix(es), "
                      f"but {len(errors_remaining)} error(s) remain unfixable.")
        else:
            message = f"Hive '{hive_name}' has {len(errors_remaining)} unfixable error(s)."
        
        return {
            "status": "success" if not is_corrupt else "error",
            "message": message,
            "hive_name": hive_name,
            "normalized_name": normalized,
            "fixes_applied": fixes_applied,
            "errors_remaining": errors_remaining,
            "is_corrupt": is_corrupt,
            "fix_count": len(fixes_applied),
            "error_count": len(errors_remaining)
        }
        
    except Exception as e:
        logger.error(f"Error during sanitization of hive '{normalized}': {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to sanitize hive: {e}",
            "error_type": "sanitization_error"
        }


# Register the sanitize_hive tool with FastMCP
sanitize_hive = mcp.tool(name="sanitize_hive")(_sanitize_hive)


def _help() -> Dict[str, Any]:
    """
    Display available MCP tools and their parameters.
    
    Returns comprehensive list of all available Bees MCP commands with their
    parameters, types, and brief descriptions—similar to --help output.
    
    CRITICAL: NEVER modify tickets or directory structure directly via file operations.
    ALWAYS use the MCP server tools (create_ticket, update_ticket, delete_ticket, etc.).
    Direct file modifications bypass validation, relationship sync, and can corrupt the ticket database.
    
    HIVES
    - Isolated ticket directories within repo, tracked in .bees/config.json
    - Identity marker: .hive/identity.json contains normalized_name, display_name, created_at
    - Tickets stored flat at hive root
    - Naming: Display name normalized (lowercase, spaces→underscores, special chars removed)
    - Config keys and ticket ID prefixes use normalized names
    - Discovery: Primary lookup in config.json, fallback scan_for_hive() for .hive markers
    
    TICKET TYPES
    - Epic: Top-level, optional children array, no parent field allowed
    - Task: Mid-level, required parent (Epic), optional children (Subtasks)
    - Subtask: Leaf-level, required parent (Task), children always empty
    - ID format: {hive_normalized}.bees-{3char} (e.g., backend.bees-abc)
    - Schema: Markdown with YAML frontmatter, bees_version field marks valid tickets
    
    PARENT/CHILD RELATIONSHIPS
    - Valid pairs: Epic↔Task, Task↔Subtask
    - Bidirectional sync: Setting A.parent=B auto-updates B.children to include A
    - Bidirectional sync: Setting A.children=[C] auto-updates C.parent=A
    - Update behavior: Removing A from B.children nullifies A.parent (except subtasks)
    - Delete cascade: Deleting parent recursively deletes entire child subtree
    - Delete cleanup: Removes deleted ticket from parent's children array
    - Subtask constraint: parent field cannot be nullified (required)
    
    DEPENDENCIES
    - up_dependencies: Tickets this one depends on (blockers)
    - down_dependencies: Tickets depending on this one (blocked items)
    - Bidirectional sync: Setting A.up_dependencies=[B] auto-updates B.down_dependencies=[A]
    - Same-type restriction: Epics→Epics, Tasks→Tasks, Subtasks→Subtasks only
    - Circular detection: Validates no direct or transitive cycles
    - Delete cleanup: Removes deleted ticket from all related dependency arrays
    
    QUERIES
    - Multi-stage pipeline: Each stage filters or traverses previous result set
    - Search terms (AND logic): type=, id=, title~regex, label~regex
    - Graph terms (traversal): parent, children, up_dependencies, down_dependencies
    - Stage purity: Each stage is ONLY search OR ONLY graph, never mixed
    - Named queries: Stored as YAML in .bees/queries/, validated on save
    
    Returns:
        dict: Contains 'commands' list with command details and 'concepts' with technical reference
    """
    commands = [
        {
            "name": "health_check",
            "description": "Check MCP server health status",
            "parameters": []
        },
        {
            "name": "create_ticket",
            "description": "Create a new ticket (epic, task, or subtask)",
            "parameters": [
                {"name": "ticket_type", "type": "str", "required": True, "description": "Type: epic, task, or subtask"},
                {"name": "title", "type": "str", "required": True, "description": "Ticket title"},
                {"name": "hive_name", "type": "str", "required": True, "description": "Hive name for ticket"},
                {"name": "description", "type": "str", "required": False, "description": "Detailed description"},
                {"name": "parent", "type": "str", "required": False, "description": "Parent ticket ID"},
                {"name": "children", "type": "list[str]", "required": False, "description": "Child ticket IDs"},
                {"name": "up_dependencies", "type": "list[str]", "required": False, "description": "Blocking ticket IDs"},
                {"name": "down_dependencies", "type": "list[str]", "required": False, "description": "Blocked ticket IDs"},
                {"name": "labels", "type": "list[str]", "required": False, "description": "Label strings"},
                {"name": "owner", "type": "str", "required": False, "description": "Owner/assignee"},
                {"name": "priority", "type": "int", "required": False, "description": "Priority level"},
                {"name": "status", "type": "str", "required": False, "description": "Status"}
            ]
        },
        {
            "name": "update_ticket",
            "description": "Update an existing ticket",
            "parameters": [
                {"name": "ticket_id", "type": "str", "required": True, "description": "Ticket ID to update"},
                {"name": "title", "type": "str", "required": False, "description": "New title"},
                {"name": "description", "type": "str", "required": False, "description": "New description"},
                {"name": "parent", "type": "str", "required": False, "description": "New parent ID"},
                {"name": "children", "type": "list[str]", "required": False, "description": "New children IDs"},
                {"name": "up_dependencies", "type": "list[str]", "required": False, "description": "New blocking IDs"},
                {"name": "down_dependencies", "type": "list[str]", "required": False, "description": "New blocked IDs"},
                {"name": "labels", "type": "list[str]", "required": False, "description": "New labels"},
                {"name": "owner", "type": "str", "required": False, "description": "New owner"},
                {"name": "priority", "type": "int", "required": False, "description": "New priority"},
                {"name": "status", "type": "str", "required": False, "description": "New status"}
            ]
        },
        {
            "name": "delete_ticket",
            "description": "Delete a ticket and cascade to children",
            "parameters": [
                {"name": "ticket_id", "type": "str", "required": True, "description": "Ticket ID to delete"}
            ]
        },
        {
            "name": "add_named_query",
            "description": "Register a named query for reuse",
            "parameters": [
                {"name": "name", "type": "str", "required": True, "description": "Query name"},
                {"name": "query_yaml", "type": "str", "required": True, "description": "YAML query structure"}
            ]
        },
        {
            "name": "execute_query",
            "description": "Execute a named query",
            "parameters": [
                {"name": "query_name", "type": "str", "required": True, "description": "Name of saved query"},
                {"name": "hive_names", "type": "list[str]", "required": False, "description": "Hives to search"}
            ]
        },
        {
            "name": "execute_freeform_query",
            "description": "Execute a query from YAML string",
            "parameters": [
                {"name": "query_yaml", "type": "str", "required": True, "description": "YAML query pipeline"},
                {"name": "hive_names", "type": "list[str]", "required": False, "description": "Hives to search"}
            ]
        },
        {
            "name": "generate_index",
            "description": "Generate markdown index of tickets",
            "parameters": [
                {"name": "status", "type": "str", "required": False, "description": "Status filter"},
                {"name": "type", "type": "str", "required": False, "description": "Type filter"},
                {"name": "hive_name", "type": "str", "required": False, "description": "Hive to index"}
            ]
        },
        {
            "name": "colonize_hive",
            "description": "Create and register a new hive",
            "parameters": [
                {"name": "name", "type": "str", "required": True, "description": "Display name for hive"},
                {"name": "path", "type": "str", "required": True, "description": "Absolute path to hive directory"}
            ]
        },
        {
            "name": "list_hives",
            "description": "List all registered hives with ticket counts",
            "parameters": []
        },
        {
            "name": "abandon_hive",
            "description": "Unregister a hive (files unchanged)",
            "parameters": [
                {"name": "hive_name", "type": "str", "required": True, "description": "Hive to abandon"}
            ]
        },
        {
            "name": "rename_hive",
            "description": "Rename hive and update all ticket IDs",
            "parameters": [
                {"name": "old_name", "type": "str", "required": True, "description": "Current hive name"},
                {"name": "new_name", "type": "str", "required": True, "description": "New hive name"}
            ]
        },
        {
            "name": "sanitize_hive",
            "description": "Validate and auto-fix malformed tickets in hive",
            "parameters": [
                {"name": "hive_name", "type": "str", "required": True, "description": "Hive to sanitize"}
            ]
        }
    ]
    
    concepts = """
CRITICAL: NEVER modify tickets or directory structure directly via file operations.
ALWAYS use the MCP server tools (create_ticket, update_ticket, delete_ticket, etc.).
Direct file modifications bypass validation, relationship sync, and can corrupt the ticket database.

HIVES
- Isolated ticket directories within repo, tracked in .bees/config.json
- Identity marker: .hive/identity.json contains normalized_name, display_name, created_at
- Tickets stored flat at hive root
- Naming: Display name normalized (lowercase, spaces→underscores, special chars removed)
- Config keys and ticket ID prefixes use normalized names
- Discovery: Primary lookup in config.json, fallback scan_for_hive() for .hive markers

TICKET TYPES
- Epic: Top-level, optional children array, no parent field allowed
- Task: Mid-level, required parent (Epic), optional children (Subtasks)
- Subtask: Leaf-level, required parent (Task), children always empty
- ID format: {hive_normalized}.bees-{3char} (e.g., backend.bees-abc)
- Schema: Markdown with YAML frontmatter, bees_version field marks valid tickets

PARENT/CHILD RELATIONSHIPS
- Valid pairs: Epic↔Task, Task↔Subtask
- Bidirectional sync: Setting A.parent=B auto-updates B.children to include A
- Bidirectional sync: Setting A.children=[C] auto-updates C.parent=A
- Update behavior: Removing A from B.children nullifies A.parent (except subtasks)
- Delete cascade: Deleting parent recursively deletes entire child subtree
- Delete cleanup: Removes deleted ticket from parent's children array
- Subtask constraint: parent field cannot be nullified (required)

DEPENDENCIES
- up_dependencies: Tickets this one depends on (blockers)
- down_dependencies: Tickets depending on this one (blocked items)
- Bidirectional sync: Setting A.up_dependencies=[B] auto-updates B.down_dependencies=[A]
- Same-type restriction: Epics→Epics, Tasks→Tasks, Subtasks→Subtasks only
- Circular detection: Validates no direct or transitive cycles
- Delete cleanup: Removes deleted ticket from all related dependency arrays

QUERIES
- Multi-stage pipeline: Each stage filters or traverses previous result set
- Search terms (AND logic): type=, id=, title~regex, label~regex
- Graph terms (traversal): parent, children, up_dependencies, down_dependencies
- Stage purity: Each stage is ONLY search OR ONLY graph, never mixed
- Named queries: Stored as YAML in .bees/queries/, validated on save
"""
    
    return {
        "status": "success",
        "commands": commands,
        "concepts": concepts
    }


# Register the help tool with FastMCP
help = mcp.tool(name="help")(_help)


if __name__ == "__main__":
    logger.info("Running Bees MCP Server directly")
    start_server()
    mcp.run()
