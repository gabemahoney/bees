"""
MCP Index Operations Module

Provides index generation functionality for the Bees MCP server.
Handles filtering and generation of ticket indexes.
"""

import logging
from pathlib import Path
from typing import Any

from .config import (
    check_for_config_conflicts,
    check_schema_version,
    hive_not_found_error,
    load_bees_config,
    no_matching_scope_message,
)
from .id_utils import normalize_hive_name
from .index_generator import generate_index
from .queen_write import queen_write_scope
from .repo_context import get_repo_root
from .repo_utils import get_repo_root_from_path  # noqa: F401 - kept for monkeypatching in tests

logger = logging.getLogger(__name__)


@queen_write_scope(hive_param="hive_name")
async def _generate_index(
    hive_name: str | None = None,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """
    Generate markdown index of all tickets.

    Scans the tickets directory and creates a formatted markdown index.
    Can generate per-hive indexes or indexes for all hives.

    When hive_name is provided, normalizes and resolves it in the caller's
    configuration, then writes only to {hive_path}/index.md. An unresolved
    name returns hive_not_found without writing any index.

    When hive_name is omitted, iterates all registered hives and generates
    separate index.md files at their roots. If no hives are visible because
    no scope matches the caller, returns no_matching_scope naming the caller's
    directory. A matched scope with no hives is a successful no-op.

    Args:
        hive_name: Optional hive name to generate index for specific hive only.
                   If provided, generates index only for that hive.
                   If omitted, generates indexes for all registered hives.
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Success response with keys:
              - status: "success"
              - skipped_hives: empty list, retained for compatibility
              Resolution and generation errors return status, error_type,
              and message. Unexpected generation failures use index_error.

    Example:
        result = _generate_index()
        result = _generate_index(hive_name='backend')
    """
    # Check for config conflicts before proceeding
    conflict_error = check_for_config_conflicts(resolved_root)
    if conflict_error is not None:
        return conflict_error
    schema_error = check_schema_version()
    if schema_error is not None:
        return schema_error

    try:
        config = load_bees_config()
        repo_root = resolved_root if resolved_root is not None else get_repo_root()
        if hive_name:
            normalized_name = normalize_hive_name(hive_name)
            if not config or normalized_name not in config.hives:
                return hive_not_found_error(
                    f"Hive '{hive_name}' not found in configuration", repo_root
                )
            generate_index(hive_name=normalized_name)
            logger.info(f"Successfully generated ticket index (hive_name={normalized_name})")
            return {"status": "success", "skipped_hives": []}
        else:
            if config and config.hives:
                for h_name in config.hives:
                    generate_index(hive_name=h_name)
            else:
                scope_message = no_matching_scope_message(repo_root)
                if scope_message is not None:
                    return {
                        "status": "error",
                        "error_type": "no_matching_scope",
                        "message": scope_message,
                    }
                generate_index(hive_name=None)

            logger.info("Successfully generated ticket index")
            return {"status": "success", "skipped_hives": []}
    except Exception as e:
        error_msg = f"Failed to generate index: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "index_error", "message": error_msg}
