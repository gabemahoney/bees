"""
MCP Server for Bees Ticket Management System

Provides FastMCP server infrastructure with tool registration for ticket operations.
"""

import json
import logging
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from fastmcp import FastMCP
from .ticket_factory import create_epic, create_task, create_subtask
from .reader import read_ticket
from .writer import write_ticket_file
from .paths import infer_ticket_type_from_id, get_ticket_path
from .query_storage import save_query, load_query, list_queries, validate_query
from .query_parser import QueryValidationError
from .pipeline import PipelineEvaluator
from .index_generator import generate_index
from .config import validate_unique_hive_name, load_bees_config, save_bees_config, HiveConfig, BeesConfig, init_bees_config_if_needed
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


def get_repo_root() -> Path:
    """
    Find the git repository root by walking up directories.

    Starts from the current working directory and walks up the directory tree
    looking for a .git directory. Returns the path to the repository root
    when found.

    Returns:
        Path: Absolute path to the git repository root

    Raises:
        ValueError: If not in a git repository (no .git directory found)

    Example:
        >>> repo_root = get_repo_root()
        >>> print(repo_root)
        /Users/username/projects/myrepo
    """
    current = Path.cwd()

    # Walk up directory tree looking for .git
    while current != current.parent:
        if (current / '.git').exists():
            return current
        current = current.parent

    # Check root directory
    if (current / '.git').exists():
        return current

    raise ValueError("Not in a git repository - no .git directory found")


def validate_hive_path(path: str, repo_root: Path) -> Path:
    """
    Validate a hive path and return normalized absolute path.

    Validates that:
    - Path is absolute
    - Path exists
    - Path is within the repository root
    - Normalizes trailing slashes

    Args:
        path: Path string to validate (must be absolute)
        repo_root: Repository root path for boundary checking

    Returns:
        Path: Normalized absolute path to the hive directory

    Raises:
        ValueError: If path is relative, doesn't exist, or is outside repo root

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

    # Check if path exists
    if not hive_path.exists():
        raise ValueError(
            f"Hive path does not exist: {path}"
        )

    # Resolve both paths to handle symlinks and normalize
    resolved_hive = hive_path.resolve()
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
        repo_root = get_repo_root()
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
                    config = json.load(f)
                    registered_hives = set(config.get('hives', {}).keys())
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


def colonize_hive(name: str, path: str) -> Dict[str, Any]:
    """
    Create a new hive directory structure at the specified path.

    This is an orchestration function that coordinates validation and hive setup:
    - Normalizes the hive display name using the config system
    - Validates the path is absolute, exists, and within the repo
    - Checks for duplicate normalized hive names in the registry
    - Creates the hive directory structure (/eggs, /evicted, .hive marker)
    - Registers the hive in .bees/config.json

    Args:
        name: Display name for the hive (e.g., 'Back End')
        path: Absolute path where the hive should be created

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
        >>> colonize_hive('Back End', '/Users/user/projects/myrepo/tickets')
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

        # Step 2: Validate path using config system
        try:
            repo_root = get_repo_root()
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
            validate_unique_hive_name(normalized_name)
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

        # Step 5: Register hive in config.json
        try:
            config = init_bees_config_if_needed()
            config.hives[normalized_name] = HiveConfig(
                path=str(validated_path),
                display_name=name
            )
            save_bees_config(config)
            logger.info(f"Registered hive '{normalized_name}' in config.json")
        except (IOError, ValueError) as e:
            return {
                "status": "error",
                "message": f"Failed to register hive in config: {e}",
                "error_type": "config_error",
                "validation_details": {
                    "operation": "save_config",
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
health_check = mcp.tool()(_health_check)


# Tool stubs - implementations will be added in later tasks

def _create_ticket(
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
    status: str | None = None
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
create_ticket = mcp.tool()(_create_ticket)


# Sentinel value to distinguish "not provided" from "explicitly set to None"
_UNSET = object()

def _update_ticket(
    ticket_id: str,
    title: str | None = _UNSET,
    description: str | None = _UNSET,
    parent: str | None = _UNSET,
    children: list[str] | None = _UNSET,
    up_dependencies: list[str] | None = _UNSET,
    down_dependencies: list[str] | None = _UNSET,
    labels: list[str] | None = _UNSET,
    owner: str | None = _UNSET,
    priority: int | None = _UNSET,
    status: str | None = _UNSET
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

    Returns:
        dict: Updated ticket information

    Raises:
        ValueError: If ticket_id doesn't exist or validation fails

    Note:
        When updating relationships (parent, children, dependencies), the change
        is automatically reflected bidirectionally in related tickets.
    """
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

    if children is not _UNSET:
        for child_id in children:
            child_type = infer_ticket_type_from_id(child_id)
            if not child_type:
                error_msg = f"Child ticket does not exist: {child_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if up_dependencies is not _UNSET:
        for dep_id in up_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    if down_dependencies is not _UNSET:
        for dep_id in down_dependencies:
            dep_type = infer_ticket_type_from_id(dep_id)
            if not dep_type:
                error_msg = f"Dependency ticket does not exist: {dep_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    # Check for circular dependencies if both up and down are being updated
    if up_dependencies is not _UNSET and down_dependencies is not _UNSET:
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            error_msg = f"Circular dependency detected: ticket cannot both depend on and be depended on by the same tickets: {circular_deps}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Update basic fields (non-relationship fields)
    if title is not _UNSET:
        if not title.strip():
            error_msg = "Ticket title cannot be empty"
            logger.error(error_msg)
            raise ValueError(error_msg)
        ticket.title = title

    if description is not _UNSET:
        ticket.description = description

    if labels is not _UNSET:
        ticket.labels = labels

    if owner is not _UNSET:
        ticket.owner = owner

    if priority is not _UNSET:
        ticket.priority = priority

    if status is not _UNSET:
        ticket.status = status

    # Handle relationship updates with bidirectional consistency
    # Track old relationships to determine what changed
    old_parent = ticket.parent
    old_children = set(ticket.children or [])
    old_up_deps = set(ticket.up_dependencies or [])
    old_down_deps = set(ticket.down_dependencies or [])

    # Update relationship fields if provided
    if parent is not _UNSET:
        ticket.parent = parent if parent else None
    if children is not _UNSET:
        ticket.children = children
    if up_dependencies is not _UNSET:
        ticket.up_dependencies = up_dependencies
    if down_dependencies is not _UNSET:
        ticket.down_dependencies = down_dependencies

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
update_ticket = mcp.tool()(_update_ticket)


def _delete_ticket(
    ticket_id: str,
    cascade: bool = False
) -> Dict[str, Any]:
    """
    Delete a ticket and clean up relationships in related tickets.

    Args:
        ticket_id: ID of the ticket to delete (required)
        cascade: If True, recursively delete all child tickets. If False and ticket
                has children, the operation will fail or unlink children (default: False)

    Returns:
        dict: Deletion status and information about cleaned relationships

    Raises:
        ValueError: If ticket_id doesn't exist or deletion validation fails

    Note:
        When a ticket is deleted:
        - It's removed from parent's children array
        - It's removed from all dependency arrays in related tickets
        - If cascade=True, all child tickets are recursively deleted
        - If cascade=False and children exist, deletion may be prevented
    """
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

    # Handle children tickets based on cascade parameter
    if ticket.children:
        if cascade:
            # Recursively delete all child tickets
            for child_id in ticket.children:
                try:
                    _delete_ticket(child_id, cascade=True)
                    logger.info(f"Cascade deleted child ticket: {child_id}")
                except Exception as e:
                    logger.warning(f"Failed to cascade delete child {child_id}: {e}")
        else:
            # Unlink children by removing parent reference
            for child_id in ticket.children:
                _remove_parent_from_child(child_id)
                logger.info(f"Unlinked child {child_id} from parent {ticket_id}")

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
delete_ticket = mcp.tool()(_delete_ticket)


def _add_named_query(
    name: str,
    query_yaml: str,
    validate: bool = True
) -> Dict[str, Any]:
    """
    Register a new named query for reuse.

    Args:
        name: Name for the query (used to execute it later)
        query_yaml: YAML string representing the query structure
        validate: Whether to validate query (set False for parameterized queries with placeholders)

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
        # This will validate structure and raise QueryValidationError if invalid (unless validate=False)
        save_query(name.strip(), query_yaml, validate)
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
add_named_query = mcp.tool()(_add_named_query)


def _execute_query(
    query_name: str,
    params: str | None = None,
    hive_names: list[str] | None = None
) -> Dict[str, Any]:
    """
    Execute a named query with optional parameter substitution.

    Args:
        query_name: Name of the registered query to execute
        params: JSON string of parameters for variable substitution (e.g., '{"status": "open", "label": "beta"}')
        hive_names: Optional list of hive names to filter results (default: None = all hives)

    Returns:
        dict: Query results with list of matching ticket IDs and metadata

    Raises:
        ValueError: If query name not found, hive not found, or execution fails

    Example:
        execute_query("open_tasks", '{"status": "open"}')
        execute_query("beta_work_items", '{"label": "beta"}')
        execute_query("open_tasks", '{"status": "open"}', ["backend", "frontend"])
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
        config = load_bees_config()
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

    # Perform parameter substitution if params provided
    if params:
        try:
            params_dict = json.loads(params)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in params: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        stages = _substitute_query_params(stages, params_dict)

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


def _substitute_query_params(stages: list, params: Dict[str, str]) -> list:
    """Substitute parameters in query stages.

    Replaces {param_name} placeholders with actual values.

    Args:
        stages: List of stages with potential placeholders
        params: Dictionary of parameter name -> value mappings

    Returns:
        List of stages with substituted values

    Raises:
        ValueError: If required parameter is missing
    """
    import re

    substituted_stages = []

    for stage in stages:
        substituted_stage = []
        for term in stage:
            # Find all {param} placeholders in term
            placeholders = re.findall(r'\{(\w+)\}', term)

            # Check all required params are provided
            for placeholder in placeholders:
                if placeholder not in params:
                    raise ValueError(
                        f"Missing required parameter: {placeholder}. "
                        f"Provided: {', '.join(params.keys())}"
                    )

            # Substitute all placeholders
            substituted_term = term
            for param_name, param_value in params.items():
                substituted_term = substituted_term.replace(
                    f"{{{param_name}}}",
                    str(param_value)
                )

            substituted_stage.append(substituted_term)

        substituted_stages.append(substituted_stage)

    return substituted_stages


# Register the execute_query tool with FastMCP
execute_query = mcp.tool()(_execute_query)


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
generate_index_tool = mcp.tool()(_generate_index)


if __name__ == "__main__":
    logger.info("Running Bees MCP Server directly")
    start_server()
    mcp.run()
