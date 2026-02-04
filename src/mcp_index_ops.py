"""
MCP Index Operations Module

Provides index generation functionality for the Bees MCP server.
Handles filtering and generation of ticket indexes.
"""

import logging
from typing import Dict, Any
from .index_generator import generate_index

logger = logging.getLogger(__name__)


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
