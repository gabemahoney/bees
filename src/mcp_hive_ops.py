"""
Hive Lifecycle Operations Module

This module handles all hive lifecycle management operations including:
- Hive creation (colonization)
- Hive listing
- Hive abandonment
- Hive renaming
- Hive sanitization/validation

These operations are complex (~700-800 lines) and need focused isolation
from the main MCP server infrastructure.
"""

import json
import logging
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from fastmcp import Context
from .config import (
    load_bees_config, save_bees_config,
    write_hive_config_dict, register_hive_dict,
    validate_unique_hive_name
)
from .id_utils import normalize_hive_name
from .mcp_repo_utils import get_repo_root_from_path, get_repo_root
from .mcp_hive_utils import validate_hive_path


logger = logging.getLogger(__name__)


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
            # Get repo root from MCP context (client's repo) or use hive path
            hive_path = Path(path)
            if ctx:
                # MCP tool call - try client's repo root from context first
                repo_root = await get_repo_root(ctx)

                if repo_root:
                    logger.info(f"colonize_hive: Got repo root from MCP context: {repo_root}")

                    # Verify the hive path is within the detected repo root
                    # If not, the context may have returned wrong repo - use hive path instead
                    try:
                        hive_path.resolve(strict=False).relative_to(repo_root.resolve())
                    except ValueError:
                        # Hive path is outside detected repo root - use hive path to find correct repo
                        logger.warning(f"colonize_hive: Hive path {hive_path} outside repo root {repo_root}, using hive path")
                        repo_root = get_repo_root_from_path(hive_path)
                        logger.info(f"colonize_hive: Found repo root from hive path: {repo_root}")
                else:
                    # Roots protocol unavailable - use hive path to find repo
                    logger.warning("colonize_hive: Roots protocol unavailable, using hive path to find repo root")
                    repo_root = get_repo_root_from_path(hive_path)
                    logger.info(f"colonize_hive: Found repo root from hive path: {repo_root}")
            else:
                # Non-MCP call (tests, CLI) - find repo root from hive path
                repo_root = get_repo_root_from_path(hive_path)
                logger.info(f"colonize_hive: Found repo root from hive path: {repo_root}")

            validated_path = validate_hive_path(path, repo_root)
            logger.info(f"colonize_hive: Validated hive path: {validated_path}")
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
            logger.info(f"colonize_hive: Registered hive '{normalized_name}' in config at {repo_root / '.bees/config.json'}")
            logger.info(f"colonize_hive: Final repo root used: {repo_root}")
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
    # Get repo root
    if ctx:
        repo_root = await get_repo_root(ctx)
        if not repo_root:
            raise ValueError("Cannot determine client repository root - MCP roots protocol unavailable")
    else:
        repo_root = get_repo_root_from_path(Path.cwd())

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
    # Get repo root
    if ctx:
        repo_root = await get_repo_root(ctx)
        if not repo_root:
            raise ValueError("Cannot determine client repository root - MCP roots protocol unavailable")
    else:
        repo_root = get_repo_root_from_path(Path.cwd())

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
    # Get repo root
    if ctx:
        repo_root = await get_repo_root(ctx)
        if not repo_root:
            raise ValueError("Cannot determine client repository root - MCP roots protocol unavailable")
    else:
        repo_root = get_repo_root_from_path(Path.cwd())

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
