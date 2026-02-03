"""Markdown file writer with YAML frontmatter serialization."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .constants import BEES_SCHEMA_VERSION
from .paths import ensure_ticket_directory_exists, get_ticket_path
from .types import TicketType


def serialize_frontmatter(data: dict[str, Any]) -> str:
    """
    Serialize a Python dict to YAML frontmatter format.

    Handles special characters, multiline strings, arrays, and nested fields.
    Formats with leading and trailing --- separators.

    Args:
        data: Dictionary containing ticket metadata

    Returns:
        YAML frontmatter string with --- delimiters

    Examples:
        >>> data = {"id": "bees-250", "type": "epic", "title": "Test"}
        >>> frontmatter = serialize_frontmatter(data)
        >>> frontmatter.startswith("---\\n")
        True
        >>> frontmatter.endswith("---\\n")
        True
    """
    # Convert datetime objects to ISO format strings for YAML serialization
    serializable_data = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            serializable_data[key] = value.isoformat()
        elif value is None:
            # Skip None values to keep frontmatter clean
            continue
        elif isinstance(value, list) and not value:
            # Skip empty lists to keep frontmatter clean
            continue
        else:
            serializable_data[key] = value

    # Use safe_dump for security and proper formatting
    # default_flow_style=False ensures arrays and objects use block style
    # sort_keys=False preserves field order
    # allow_unicode=True handles special characters
    yaml_content = yaml.safe_dump(
        serializable_data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=80,  # Wrap long lines
    )

    # Wrap with --- delimiters
    return f"---\n{yaml_content}---\n"


def write_ticket_file(
    ticket_id: str,
    ticket_type: TicketType,
    frontmatter_data: dict[str, Any],
    body: str = "",
    repo_root: Path | None = None,
) -> Path:
    """
    Write a ticket markdown file with YAML frontmatter and body content.

    Uses atomic write operations (temp file + rename) for safety.
    Creates parent directories if they don't exist.

    Args:
        ticket_id: The ticket ID (e.g., "bees-250")
        ticket_type: The type of ticket ("epic", "task", or "subtask")
        frontmatter_data: Dictionary of ticket metadata for YAML frontmatter
        body: Optional markdown body content
        repo_root: Optional repository root path (defaults to cwd if None)

    Returns:
        Path to the created ticket file

    Raises:
        ValueError: If ticket_id or ticket_type is invalid
        OSError: If file write operation fails

    Examples:
        >>> data = {"id": "bees-250", "type": "epic", "title": "Test Epic"}
        >>> path = write_ticket_file("bees-250", "epic", data, "# Description")
        >>> path.exists()
        True
    """
    # Get the target file path first (this includes hive-specific path logic)
    target_path = get_ticket_path(ticket_id, ticket_type, repo_root)

    # Ensure the directory exists (use parent directory of target path)
    # With flat storage, this creates the hive root directory
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure bees_version is present in frontmatter
    if 'bees_version' not in frontmatter_data:
        frontmatter_data = {**frontmatter_data, 'bees_version': BEES_SCHEMA_VERSION}

    # Serialize frontmatter
    frontmatter = serialize_frontmatter(frontmatter_data)

    # Combine frontmatter and body
    content = frontmatter
    if body:
        # Ensure body starts on a new line after frontmatter
        content += f"\n{body}\n"

    # Atomic write: write to temp file, then rename
    # This ensures we never have partial/corrupted files
    temp_fd, temp_path = tempfile.mkstemp(
        dir=target_path.parent,
        prefix=f".{ticket_id}_",
        suffix=".md.tmp",
    )

    try:
        # Write content to temp file
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(content)

        # Atomically move temp file to target location
        os.rename(temp_path, target_path)

        return target_path

    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
