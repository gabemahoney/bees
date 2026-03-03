"""Markdown file writer with YAML frontmatter serialization."""

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from . import cache
from .constants import SCHEMA_VERSION
from .paths import compute_ticket_directory, get_ticket_path
from .types import TicketType
from .validator import validate_id_format


class BlockScalarDumper(yaml.SafeDumper):
    """Custom YAML dumper that uses block scalar style (|) for multi-line strings."""

    pass


def str_representer(dumper, data):
    """Represent strings using block scalar style if they contain newlines."""
    if "\n" in data:
        # Use literal block scalar style (|) for multi-line strings
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    # Use default style for single-line strings
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


# Register the custom string representer
BlockScalarDumper.add_representer(str, str_representer)

# Characters that require quoting when they appear at the start of a YAML plain scalar.
# Excludes '-' because yaml.SafeDumper allows plain '-test' style strings.
_LEADING_SPECIAL = frozenset('?:,[]{}#&*!|>\'"@`%')

# YAML 1.1 special keyword values (case-insensitive) that would be misinterpreted.
_YAML_KEYWORDS = frozenset([
    'null', '~', 'true', 'false', 'yes', 'no', 'on', 'off',
])

# Matches ISO 8601 date/datetime prefixes that YAML would parse as timestamps.
_TIMESTAMP_RE = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}(?:[T t]|$)')


def _needs_quoting(s: str) -> bool:
    """Return True if YAML plain scalar s requires single-quote quoting."""
    if not s:
        return True
    if s.lower() in _YAML_KEYWORDS:
        return True
    if s[0] in _LEADING_SPECIAL:
        return True
    if ': ' in s or s.endswith(':'):
        return True
    if ' #' in s:
        return True
    if s != s.strip():
        return True
    # Looks like a number (int or float including scientific notation)
    try:
        float(s)
        return True
    except ValueError:
        pass
    # Looks like a YAML timestamp
    if _TIMESTAMP_RE.match(s):
        return True
    return False


def _serialize_list_item(item: Any, parts: list[str]) -> None:
    """Append a single block-sequence item line to parts. Raises ValueError for unsupported types."""
    if item is None:
        parts.append("- null\n")
    elif isinstance(item, bool):
        parts.append(f"- {'true' if item else 'false'}\n")
    elif isinstance(item, (int, float)):
        parts.append(f"- {item}\n")
    elif isinstance(item, str):
        if _needs_quoting(item):
            parts.append(f"- '{item.replace(chr(39), chr(39)*2)}'\n")
        else:
            parts.append(f"- {item}\n")
    elif isinstance(item, dict):
        raise ValueError("Dict items in lists not supported by fast serializer")
    else:
        raise ValueError(f"Unsupported list item type: {type(item).__name__}")


def fast_serialize_frontmatter(data: dict[str, Any]) -> str:
    """
    Fast hand-written YAML frontmatter serializer for typical ticket data.

    Builds YAML string directly using string formatting instead of yaml.dump.
    Handles: scalars, null, booleans, lists (block style), datetime (quoted ISO),
    and multi-line strings (literal block |).

    Raises ValueError for unsupported types (nested dicts, complex list items)
    so callers can fall back to yaml.dump.

    Args:
        data: Raw ticket metadata dictionary (may contain datetime objects)

    Returns:
        YAML frontmatter string with --- delimiters

    Raises:
        ValueError: If data contains types not handled by the fast serializer
    """
    parts: list[str] = ["---\n"]
    for key, value in data.items():
        if value is None:
            parts.append(f"{key}: null\n")
        elif isinstance(value, bool):
            parts.append(f"{key}: {'true' if value else 'false'}\n")
        elif isinstance(value, datetime):
            parts.append(f"{key}: '{value.isoformat()}'\n")
        elif isinstance(value, int):
            parts.append(f"{key}: {value}\n")
        elif isinstance(value, float):
            parts.append(f"{key}: {value}\n")
        elif isinstance(value, str):
            if "\n" in value:
                has_trailing = value.endswith("\n")
                chomp = "" if has_trailing else "-"
                lines = value.rstrip("\n").split("\n")
                parts.append(f"{key}: |{chomp}\n")
                for line in lines:
                    if line:
                        parts.append(f"  {line}\n")
                    else:
                        parts.append("\n")
            elif _needs_quoting(value):
                parts.append(f"{key}: '{value.replace(chr(39), chr(39)*2)}'\n")
            else:
                parts.append(f"{key}: {value}\n")
        elif isinstance(value, list):
            if not value:
                # Skip empty lists to match existing serialize_frontmatter behavior
                continue
            parts.append(f"{key}:\n")
            for item in value:
                _serialize_list_item(item, parts)
        elif isinstance(value, dict):
            raise ValueError(f"Nested dict not supported by fast serializer: key={key!r}")
        else:
            raise ValueError(f"Unsupported type {type(value).__name__} for key {key!r}")
    parts.append("---\n")
    return "".join(parts)


def serialize_frontmatter(data: dict[str, Any]) -> str:
    """
    Serialize a Python dict to YAML frontmatter format.

    Handles special characters, multiline strings, arrays, and nested fields.
    Formats with leading and trailing --- separators.

    Tries fast_serialize_frontmatter first for common ticket data shapes,
    falling back to yaml.dump for complex types (nested dicts, etc.).

    Args:
        data: Dictionary containing ticket metadata

    Returns:
        YAML frontmatter string with --- delimiters

    Examples:
        >>> data = {"id": "b.Amx", "type": "bee", "title": "Test"}
        >>> frontmatter = serialize_frontmatter(data)
        >>> frontmatter.startswith("---\\n")
        True
        >>> frontmatter.endswith("---\\n")
        True
    """
    try:
        return fast_serialize_frontmatter(data)
    except ValueError:
        pass

    # Fallback: yaml.dump for complex types (nested dicts, etc.)
    serializable_data = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            serializable_data[key] = value.isoformat()
        elif value is None:
            serializable_data[key] = value
        elif isinstance(value, list) and not value:
            # Skip empty lists to keep frontmatter clean
            continue
        else:
            serializable_data[key] = value

    yaml_content = yaml.dump(
        serializable_data,
        Dumper=BlockScalarDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    return f"---\n{yaml_content}---\n"


def write_ticket_file(
    ticket_id: str,
    ticket_type: TicketType,
    frontmatter_data: dict[str, Any],
    body: str = "",
    hive_name: str = "",
    file_path: Path | None = None,
) -> Path:
    """
    Write a ticket markdown file with YAML frontmatter and body content.

    Uses atomic write operations (temp file + rename) for safety.
    Creates hierarchical directory structure where each ticket has its own directory.

    For new tickets, computes directory path from parent chain in frontmatter.
    For existing tickets (updates), finds current location via recursive scan.

    Directory structure:
    - Bees: {hive_root}/{ticket_id}/{ticket_id}.md
    - Children: {hive_root}/{parent_id}/{ticket_id}/{ticket_id}.md

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx")
        ticket_type: The type of ticket ("bee", "t1", "t2", etc.)
        frontmatter_data: Dictionary of ticket metadata for YAML frontmatter
            (must include 'parent' field for child tickets)
        body: Optional markdown body content
        hive_name: Hive name for storage location (required)

    Returns:
        Path to the created ticket file

    Raises:
        ValueError: If ticket_id or ticket_type is invalid
        OSError: If file write operation fails
        FileNotFoundError: If parent ticket doesn't exist (for new child tickets)

    Examples:
        >>> data = {"id": "b.Amx", "type": "bee", "title": "Test Bee"}
        >>> path = write_ticket_file("b.Amx", "bee", data, "# Description", "backend")
        >>> path.exists()
        True
    """
    # Validate ticket_id format before any filesystem operations
    if not validate_id_format(ticket_id):
        raise ValueError(f"Invalid ticket ID format: {ticket_id}")

    # Try to get path for existing ticket, or compute path for new ticket
    if file_path is not None:
        target_path = file_path
    else:
        try:
            # For existing tickets (updates), find via recursive scan
            target_path = get_ticket_path(ticket_id, ticket_type, hive_name)
        except FileNotFoundError:
            # For new tickets, compute the directory path from parent chain
            parent_id = frontmatter_data.get("parent") if isinstance(frontmatter_data, dict) else None
            ticket_dir = compute_ticket_directory(ticket_id, parent_id, hive_name)
            target_path = ticket_dir / f"{ticket_id}.md"

    # Ensure the ticket's directory exists (creates full directory chain)
    # For hierarchical storage, this creates {hive_root}/{bee_id}/{task_id}/... structure
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure schema_version is present in frontmatter
    if "schema_version" not in frontmatter_data:
        frontmatter_data = {**frontmatter_data, "schema_version": SCHEMA_VERSION}

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
        cache.evict(ticket_id)

        return target_path

    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
