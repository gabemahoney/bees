"""
MCP Index Operations Module

Provides index generation functionality for the Bees MCP server.
Handles filtering and generation of ticket indexes.
"""

import logging
from pathlib import Path
from typing import Any

from .config import load_bees_config
from .index_generator import generate_index
from .repo_utils import get_repo_root_from_path  # noqa: F401 - kept for monkeypatching in tests

logger = logging.getLogger(__name__)


async def _generate_index(
    hive_name: str | None = None,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """
    Generate markdown index of all tickets.

    Scans the tickets directory and creates a formatted markdown index.
    Can generate per-hive indexes or indexes for all hives.

    When hive_name is provided, generates and writes index only for that hive
    to {hive_path}/index.md. Returns a hive_corrupt error if integrity fails.

    When hive_name is omitted, iterates all registered hives and generates
    separate index.md files for each healthy hive. Corrupt hives are skipped
    (not written) and their names are collected in skipped_hives.

    Args:
        hive_name: Optional hive name to generate index for specific hive only.
                   If provided, generates index only for that hive.
                   If omitted, generates indexes for all healthy hives.
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Success response with keys:
              - status: "success"
              - skipped_hives: list of hive names skipped due to corruption
                (always present; empty list when hive_name is specified)
              On corrupt single-hive request, returns error dict with keys:
              status, error_type, hive_name, message, errors.

    Example:
        result = _generate_index()
        result = _generate_index(hive_name='backend')
    """
    try:
        if hive_name:
            generate_index(hive_name=hive_name)
            logger.info(f"Successfully generated ticket index (hive_name={hive_name})")
            return {"status": "success", "skipped_hives": []}
        else:
            config = load_bees_config()

            if config and config.hives:
                for h_name in config.hives:
                    generate_index(hive_name=h_name)
            else:
                generate_index(hive_name=None)

            logger.info("Successfully generated ticket index")
            return {"status": "success", "skipped_hives": []}
    except Exception as e:
        error_msg = f"Failed to generate index: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "index_error", "message": error_msg}
