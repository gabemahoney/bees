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
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import (
    BeesConfig,
    HiveConfig,
    find_matching_scope,
    load_bees_config,
    load_global_config,
    save_bees_config,
    save_global_config,
    serialize_bees_config_to_scope,
    validate_unique_hive_name,
)
from .constants import SCHEMA_VERSION
from .id_utils import normalize_hive_name
from .mcp_hive_utils import validate_hive_path
from .repo_context import get_repo_root, repo_root_context
from .repo_utils import get_repo_root_from_path

logger = logging.getLogger(__name__)


async def colonize_hive_core(
    name: str,
    path: str,
    child_tiers: dict[str, list] | None = None,
    repo_root: Path | None = None,
    egg_resolver: str | None = None,
    egg_resolver_timeout: int | float | None = None,
) -> dict[str, Any]:
    """
    Create a new hive directory structure at the specified path.

    This is the core implementation that coordinates validation and hive setup:
    - Normalizes the hive display name using the config system
    - Validates the path is absolute and within the repo
    - The directory does not need to exist beforehand; it will be created automatically
    - Checks for duplicate normalized hive names in the registry
    - Creates the hive directory structure (.hive marker)
    - Registers the hive in ~/.bees/config.json

    Args:
        name: Display name for the hive (e.g., 'Back End')
        path: Absolute path where the hive should be created
        child_tiers: Optional per-hive child tiers configuration (e.g., {"t1": ["Task", "Tasks"]})
                     If None, hive inherits from scope/global config
                     If {}, hive is bees-only (no child tiers)
        repo_root: Pre-resolved repo root path (injected by adapter)
        egg_resolver: Optional path to egg resolver script for this hive (e.g., '/repo/resolve_eggs.sh')
                      Sets egg_resolver at the hive level in config. If None, hive inherits from scope/global.

    Returns:
        dict: Success/error status with validation details
            On success: {
                'status': 'success',
                'message': 'Hive created successfully',
                'normalized_name': str,
                'display_name': str,
                'path': str,
                'child_tiers': dict | None
            }
            On error: {
                'status': 'error',
                'message': str,
                'error_type': str,
                'validation_details': dict
            }

    Example:
        >>> await colonize_hive_core('Back End', '/Users/user/projects/myrepo/tickets', repo_root=root)
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
                    "reason": "Name contains no alphanumeric characters",
                },
            }

        # Step 2: Determine repo root for downstream operations
        if repo_root is None:
            # Try context first (set by CLI's _run_in_repo or MCP entry points)
            try:
                repo_root = get_repo_root()
                logger.info(f"colonize_hive: Found repo root from context: {repo_root}")
            except RuntimeError:
                # Context not set — fall back to deriving from hive path
                hive_path = Path(path)
                try:
                    repo_root = get_repo_root_from_path(hive_path)
                    logger.info(f"colonize_hive: Found repo root from hive path: {repo_root}")
                except ValueError as e:
                    return {
                        "status": "error",
                        "message": str(e),
                        "error_type": "repo_detection_error",
                        "validation_details": {"field": "path", "provided_value": path, "reason": str(e)},
                    }

        # Set repo_root context for all downstream operations
        with repo_root_context(repo_root):
            # Step 3: Validate path
            try:
                validated_path = validate_hive_path(path)
                logger.info(f"colonize_hive: Validated hive path: {validated_path}")
            except ValueError as e:
                return {
                    "status": "error",
                    "message": str(e),
                    "error_type": "path_validation_error",
                    "validation_details": {"field": "path", "provided_value": path, "reason": str(e)},
                }

            # Step 4: Check for duplicate normalized names using config system
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
                        "reason": str(e),
                    },
                }

            # Step 4.5: Validate child_tiers if provided
            parsed_child_tiers = None
            if child_tiers is not None:
                try:
                    from .config import _parse_child_tiers_data

                    parsed_child_tiers = _parse_child_tiers_data(child_tiers)
                    logger.info(f"Validated child_tiers: {child_tiers}")
                except ValueError as e:
                    return {
                        "status": "error",
                        "message": f"Invalid child_tiers configuration: {e}",
                        "error_type": "child_tiers_validation_error",
                        "validation_details": {"field": "child_tiers", "provided_value": child_tiers, "reason": str(e)},
                    }

            # Step 5: Create hive directory structure
            # Create .hive marker folder with identity data
            hive_marker_path = validated_path / ".hive"
            try:
                hive_marker_path.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError) as e:
                return {
                    "status": "error",
                    "message": f"Failed to create .hive marker directory: {e}",
                    "error_type": "filesystem_error",
                    "validation_details": {
                        "operation": "create_hive_marker",
                        "path": str(hive_marker_path),
                        "reason": str(e),
                    },
                }

            # Store hive identity in marker file
            identity_data = {
                "normalized_name": normalized_name,
                "display_name": name,
                "created_at": datetime.now().isoformat(),
                "version": SCHEMA_VERSION,
            }
            identity_file = hive_marker_path / "identity.json"
            try:
                with open(identity_file, "w") as f:
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
                        "reason": str(e),
                    },
                }

            # TODO: Linter integration stub
            # Future: Add linter check here to validate no conflicting tickets exist
            # across hives during colonization. The linter should scan for duplicate
            # ticket IDs, conflicting hive names, and other cross-hive invariants.
            # Deferred to future Bee for full implementation.
            logger.info("Linter check: (stubbed out for now)")

            # Step 6: Register hive in global scoped config
            try:
                creation_timestamp = datetime.now()
                new_hive = HiveConfig(
                    path=str(validated_path),
                    display_name=name,
                    created_at=creation_timestamp.isoformat(),
                    child_tiers=parsed_child_tiers,
                    egg_resolver=egg_resolver,
                    egg_resolver_timeout=egg_resolver_timeout,
                )

                # Load global config and find or create scope
                global_config = load_global_config()
                pattern = find_matching_scope(repo_root, global_config)

                if pattern is not None:
                    # Scope exists — load it, add hive, save back
                    config = load_bees_config()
                    if config is None:
                        config = BeesConfig()
                    config.hives[normalized_name] = new_hive
                    save_bees_config(config)
                else:
                    # No scope — create exact-path scope with this hive
                    config = BeesConfig(hives={normalized_name: new_hive})
                    scope_data = serialize_bees_config_to_scope(config)
                    global_config["scopes"][str(repo_root)] = scope_data
                    save_global_config(global_config)

                logger.info(f"colonize_hive: Registered hive '{normalized_name}' in global config")
                logger.info(f"colonize_hive: Final repo root used: {repo_root}")
            except (PermissionError, OSError) as e:
                return {
                    "status": "error",
                    "message": f"Failed to write config file: {e}",
                    "error_type": "config_write_error",
                    "validation_details": {"operation": "write_config", "reason": str(e)},
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Failed to register hive in config: {e}",
                    "error_type": "config_error",
                    "validation_details": {"operation": "register_hive", "reason": str(e)},
                }

            # Success!
            result = {
                "status": "success",
                "message": "Hive created and registered successfully",
                "normalized_name": normalized_name,
                "display_name": name,
                "path": str(validated_path),
                "child_tiers": child_tiers,
                "egg_resolver": egg_resolver,
            }
            if egg_resolver_timeout is not None:
                result["egg_resolver_timeout"] = egg_resolver_timeout
            return result

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Unexpected error in colonize_hive: {e}")
        return {
            "status": "error",
            "message": f"Unexpected error: {e}",
            "error_type": "unexpected_error",
            "validation_details": {"exception_type": type(e).__name__, "exception_message": str(e)},
        }


async def _colonize_hive(
    name: str,
    path: str,
    child_tiers: dict[str, list] | None = None,
    repo_root: Path | None = None,
    egg_resolver: str | None = None,
    egg_resolver_timeout: int | float | None = None,
) -> dict[str, Any]:
    """
    Create and register a new hive at the specified path.

    This MCP tool wrapper exposes the colonize_hive() core function, which:
    - Normalizes the hive display name
    - Validates the path is absolute, exists, and within the repository
    - Checks for duplicate normalized hive names
    - Creates the hive directory structure (.hive marker)
    - Registers the hive in ~/.bees/config.json

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
        child_tiers: Optional per-hive child tiers configuration
                     Format: {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}
                     If None: hive inherits from scope/global config
                     If {}: hive is bees-only (no child tiers)
        repo_root: Pre-resolved repo root path (injected by adapter)
        egg_resolver: Optional path to egg resolver script for this hive (e.g., '/repo/resolve_eggs.sh')
                      If None: hive inherits egg_resolver from scope/global config

    Returns:
        dict: Operation result with status and details
            On success: {
                'status': 'success',
                'message': 'Hive created and registered successfully',
                'normalized_name': str,  # Internal hive identifier
                'display_name': str,     # Original display name
                'path': str,             # Absolute path to hive directory
                'child_tiers': dict | None  # Child tiers config if provided
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
        - Invalid path: Path is not absolute, parent directory doesn't exist, or outside repo
        - Duplicate name: Normalized name already exists in registry
        - Invalid child_tiers: Gaps in tier keys, invalid format, or validation fails
        - Filesystem error: Cannot create directories or write files
        - Config error: Cannot read or write ~/.bees/config.json
    """
    try:
        result = await colonize_hive_core(
            name=name, path=path, child_tiers=child_tiers, repo_root=repo_root,
            egg_resolver=egg_resolver, egg_resolver_timeout=egg_resolver_timeout,
        )

        if result.get("status") == "error":
            logger.error(f"colonize_hive failed: {result.get('message', 'Unknown error')}")
            return result

        logger.info(f"Successfully colonized hive '{name}' at {path}")
        return result

    except Exception as e:
        error_msg = f"Failed to colonize hive: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "hive_error", "message": error_msg}


async def _list_hives(resolved_root: Path | None = None) -> dict[str, Any]:
    """
    List all registered hives in the repository.

    Reads ~/.bees/config.json from the client's repository to retrieve all
    registered hives and returns structured information about each hive
    including display name, normalized name, and path.

    Args:
        resolved_root: Pre-resolved repo root path (injected by adapter)

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
        >>> await _list_hives()
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
        # Load config from client's ~/.bees/config.json
        config = load_bees_config()

        # Handle case where config doesn't exist or has no hives
        if not config or not config.hives:
            logger.info("No hives configured")
            return {"status": "success", "hives": [], "message": "No hives configured"}

        # Build list of hives with their details
        hives_list = []
        for normalized_name, hive_config in config.hives.items():
            hives_list.append(
                {
                    "display_name": hive_config.display_name,
                    "normalized_name": normalized_name,
                    "path": hive_config.path,
                }
            )

        logger.info(f"Listed {len(hives_list)} hives")
        return {"status": "success", "hives": hives_list}

    except Exception as e:
        error_msg = f"Failed to list hives: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "list_hives_error", "message": error_msg}


async def _abandon_hive(hive_name: str, resolved_root: Path | None = None) -> dict[str, Any]:
    """
    Stop tracking a hive without deleting ticket files.

    Removes the hive entry from ~/.bees/config.json while leaving all ticket
    files and the .hive marker intact on the filesystem. This allows users
    to stop tracking a hive without data loss and re-colonize it later if needed.

    Args:
        hive_name: Display name or normalized name of the hive to abandon
        resolved_root: Pre-resolved repo root path (injected by adapter)

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
        - Config read error: Cannot read ~/.bees/config.json
        - Config write error: Cannot write updated config
    """
    # Normalize hive name for lookup
    normalized_name = normalize_hive_name(hive_name)
    logger.info(f"Attempting to abandon hive '{hive_name}' (normalized: '{normalized_name}')")

    config = load_bees_config()

    # Check if hive exists
    if not config or normalized_name not in config.hives:
        error_msg = f"Hive '{hive_name}' (normalized: '{normalized_name}') does not exist in config"
        logger.error(error_msg)
        return {"status": "error", "error_type": "hive_not_found", "message": error_msg}

    # Get hive details before removal
    hive_config = config.hives[normalized_name]
    display_name = hive_config.display_name
    hive_path = hive_config.path

    # Remove hive from config
    del config.hives[normalized_name]

    # Save updated config
    save_bees_config(config)
    logger.info(f"Removed hive '{normalized_name}' from config.json")

    # Success response
    return {
        "status": "success",
        "message": f'Hive "{display_name}" abandoned successfully',
        "display_name": display_name,
        "normalized_name": normalized_name,
        "path": hive_path,
    }


async def _rename_hive(
    old_name: str, new_name: str, resolved_root: Path | None = None, rename_folder: bool = True
) -> dict[str, Any]:
    """
    Rename a hive by updating its name in config and .hive marker, and optionally
    renaming the folder on disk.

    With the new ID system, hive names are NOT part of ticket IDs, so renaming
    a hive only requires updating configuration and metadata. Ticket files and
    IDs remain unchanged.

    This operation updates:
    - Config: changes hive key from old_name to new_name, updates display_name
    - .hive marker: updates normalized_name and display_name in hive directory marker file
    - Folder on disk: renames the hive directory to match the new normalized name (when rename_folder=True)

    This operation does NOT update:
    - Ticket IDs (no longer contain hive name)
    - Ticket filenames (unchanged, based on ID)
    - Frontmatter (id field unchanged)

    Args:
        old_name: Current hive name (will be normalized for lookup)
        new_name: Desired new hive name (will be normalized and validated for uniqueness)
        resolved_root: Pre-resolved repo root path (injected by adapter)
        rename_folder: If True (default), also renames the folder on disk to match the new
                       normalized hive name. If False, only updates config and .hive marker.

    Returns:
        dict: Success/error status with operation details
            On success: {
                'status': 'success',
                'message': 'Hive renamed successfully',
                'old_name': str,
                'new_name': str,
                'old_path': str,   # only when rename_folder=True
                'new_path': str    # only when rename_folder=True
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
    logger.info(
        f"Renaming hive from '{old_name}' (normalized: '{normalized_old}') "
        f"to '{new_name}' (normalized: '{normalized_new}')"
    )

    # Validate normalized names are not empty
    if not normalized_old:
        return {
            "status": "error",
            "message": f"Invalid old hive name: '{old_name}' normalizes to empty string",
            "error_type": "validation_error",
        }

    if not normalized_new:
        return {
            "status": "error",
            "message": f"Invalid new hive name: '{new_name}' normalizes to empty string",
            "error_type": "validation_error",
        }

    # Step 2: Load config and validate
    config = load_bees_config()
    if not config or normalized_old not in config.hives:
        return {
            "status": "error",
            "message": f"Hive '{old_name}' (normalized: '{normalized_old}') does not exist in config",
            "error_type": "hive_not_found",
        }

    # Step 3: Validate new name doesn't conflict with existing hives
    if normalized_new in config.hives:
        return {
            "status": "error",
            "message": (
                f"Hive '{new_name}' (normalized: '{normalized_new}') already exists. "
                f"Cannot rename to existing hive name."
            ),
            "error_type": "name_conflict",
        }

    # Get hive config for later operations
    hive_path = Path(config.hives[normalized_old].path)
    _old_display_name = config.hives[normalized_old].display_name
    logger.info(f"Validation passed. Hive path: {hive_path}")

    # Step 3.5: Rename folder on disk if requested
    old_path_str = str(hive_path)
    new_hive_path = hive_path  # default: unchanged
    if rename_folder:
        new_hive_path = hive_path.parent / normalized_new
        # Check if target path already exists (and isn't the same directory)
        if new_hive_path.exists() and new_hive_path.resolve() != hive_path.resolve():
            return {
                "status": "error",
                "message": f"Target path already exists: {new_hive_path}",
                "error_type": "path_conflict",
            }
        try:
            shutil.move(str(hive_path), str(new_hive_path))
            logger.info(f"Renamed folder on disk: {hive_path} → {new_hive_path}")
        except (OSError, shutil.Error) as e:
            return {
                "status": "error",
                "message": f"Failed to rename folder on disk: {e}",
                "error_type": "folder_rename_error",
            }
        # Update the in-memory path to point to the new location
        config.hives[normalized_old].path = str(new_hive_path)
        hive_path = new_hive_path

    # Step 4: Update config - move hive entry from old key to new key
    hive_config = config.hives[normalized_old]
    # Update display name to the new name
    hive_config.display_name = new_name

    # Remove old hive entry and add new one
    del config.hives[normalized_old]
    config.hives[normalized_new] = hive_config

    # Save updated config
    try:
        save_bees_config(config)
        logger.info(f"Updated config: renamed hive from '{normalized_old}' to '{normalized_new}'")
    except Exception as e:
        # Rollback: move folder back if we renamed it
        if rename_folder:
            try:
                shutil.move(str(new_hive_path), str(Path(old_path_str)))
                logger.info(f"Rolled back folder rename: {new_hive_path} → {old_path_str}")
            except (OSError, shutil.Error) as rollback_err:
                logger.error(f"Rollback failed: {rollback_err}")
        return {"status": "error", "message": f"Failed to save config: {e}", "error_type": "config_save_error"}

    # Step 5: Update .hive marker file with new identity
    # NOTE: With new ID format, we do NOT rename ticket files or rewrite IDs.
    # Ticket IDs are globally unique and independent of hive names.
    try:
        hive_marker_path = hive_path / ".hive"
        identity_file = hive_marker_path / "identity.json"

        if identity_file.exists():
            # Read current identity
            with open(identity_file, encoding="utf-8") as f:
                identity_data = json.load(f)

            # Update normalized_name and display_name
            identity_data["normalized_name"] = normalized_new
            identity_data["display_name"] = new_name

            # Write back
            with open(identity_file, "w", encoding="utf-8") as f:
                json.dump(identity_data, f, indent=2)

            logger.info(f"Updated .hive marker with new identity: {normalized_new}")
        else:
            # Create marker if it doesn't exist
            hive_marker_path.mkdir(exist_ok=True)
            identity_data = {
                "normalized_name": normalized_new,
                "display_name": new_name,
                "created_at": datetime.now().isoformat(),
                "version": SCHEMA_VERSION,
            }
            with open(identity_file, "w", encoding="utf-8") as f:
                json.dump(identity_data, f, indent=2)
            logger.info(f"Created .hive marker with new identity: {normalized_new}")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to update .hive marker: {e}",
            "error_type": "marker_update_error",
        }

    # Step 6: Operation complete - no linter needed since no ticket data changed
    logger.info(f"Hive rename complete: '{old_name}' → '{new_name}' (config and marker updated, tickets unchanged)")

    # Success! Return summary
    result = {
        "status": "success",
        "message": f"Hive renamed successfully from '{old_name}' to '{new_name}'",
        "old_name": old_name,
        "old_normalized": normalized_old,
        "new_name": new_name,
        "new_normalized": normalized_new,
        "path": str(hive_path),
    }
    if rename_folder:
        result["old_path"] = old_path_str
        result["new_path"] = str(new_hive_path)
    return result


async def _sanitize_hive(hive_name: str, resolved_root: Path | None = None) -> dict[str, Any]:
    """
    Validate and auto-fix malformed tickets in a hive.

    Runs the linter on all tickets in the specified hive with hive-aware validations:
    - Validates ticket IDs match hive prefix format (hive_name.bees-*)
    - Runs existing linter rules (structure, required fields, bidirectional relationships, etc.)
    - Attempts to automatically fix detected problems where possible

    Args:
        hive_name: Display name or normalized form of hive to sanitize
        resolved_root: Pre-resolved repo root path (injected by adapter)

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
    from .linter import Linter, TicketScanner

    # Normalize hive name
    normalized = normalize_hive_name(hive_name)

    config = load_bees_config()

    # Check if hive is registered
    if not config or normalized not in config.hives:
        return {
            "status": "error",
            "message": f"Hive '{hive_name}' (normalized: '{normalized}') is not registered. "
            f"Use colonize_hive() to register a new hive.",
            "error_type": "hive_not_found",
        }

    # Get hive configuration
    hive_config = config.hives[normalized]
    hive_path = Path(hive_config.path)

    # Verify hive directory exists
    if not hive_path.exists():
        return {
            "status": "error",
            "message": f"Hive directory does not exist: {hive_path}",
            "error_type": "directory_not_found",
        }

    # Build a map of all tickets across all hives in scope for cross-hive validation
    all_scope_ticket_map: dict | None = {}
    hive_load_errors = []
    for scan_hive_name, scan_hive_config in config.hives.items():
        if all_scope_ticket_map is None:
            continue
        scan_hive_path = Path(scan_hive_config.path)
        try:
            scanner = TicketScanner(str(scan_hive_path), scan_hive_name)
            for ticket in scanner.scan_all():
                all_scope_ticket_map[ticket.id] = ticket
        except Exception as e:
            all_scope_ticket_map = None
            hive_load_errors.append({
                "ticket_id": None,
                "error_type": "hive_load_failure",
                "message": f"Hive '{scan_hive_name}' failed to load: {str(e)}",
            })

    # Run linter with hive-aware validations and auto-fix enabled
    logger.info(f"Running linter on hive '{normalized}' with auto-fix enabled")
    global_config = load_global_config()
    auto_fix_dangling_refs = global_config.get("auto_fix_dangling_refs", False)

    try:
        linter = Linter(
            tickets_dir=str(hive_path),
            hive_name=normalized,
            config=config,
            auto_fix=True,
            all_scope_ticket_map=all_scope_ticket_map,
            auto_fix_dangling_refs=auto_fix_dangling_refs,
        )

        report = linter.run()

        # Build response with fixes and errors
        fixes_applied = [
            {"ticket_id": fix.ticket_id, "fix_type": fix.fix_type, "description": fix.description}
            for fix in report.fixes
        ]

        errors_remaining = hive_load_errors + [
            {
                "ticket_id": error.ticket_id,
                "error_type": error.error_type,
                "message": error.message,
                "severity": error.severity,
            }
            for error in report.errors
        ]

        is_corrupt = report.is_corrupt()

        # Build summary message
        if not fixes_applied and not errors_remaining:
            message = f"Hive '{hive_name}' is already clean. No issues found."
        elif fixes_applied and not errors_remaining:
            message = f"Hive '{hive_name}' sanitized successfully. Applied {len(fixes_applied)} fix(es)."
        elif fixes_applied and errors_remaining:
            message = (
                f"Hive '{hive_name}' partially sanitized. Applied {len(fixes_applied)} fix(es), "
                f"but {len(errors_remaining)} error(s) remain unfixable."
            )
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
            "error_count": len(errors_remaining),
        }

    except Exception as e:
        logger.error(f"Error during sanitization of hive '{normalized}': {e}", exc_info=True)
        return {"status": "error", "message": f"Failed to sanitize hive: {e}", "error_type": "sanitization_error"}
