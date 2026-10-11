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

# Line breaks other than "\n": "\r", which reads back as "\n" because ticket files are
# read with universal newlines, and the breaks YAML counts as well as "\n" (NEL, LS, PS).
# Written raw, any of them could start a frontmatter line with "---", which
# parse_frontmatter takes for the closing delimiter.
_OTHER_LINE_BREAKS = re.compile("[\r\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]")


class BlockScalarDumper(yaml.SafeDumper):
    """Custom YAML dumper that uses block scalar style (|) for multi-line strings."""

    pass


def str_representer(dumper, data):
    """Represent strings using block scalar style if they contain newlines."""
    if _OTHER_LINE_BREAKS.search(data):
        # Double quotes escape these, so they read back exactly
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    if "\n" in data:
        # Use literal block scalar style (|) for multi-line strings
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    # Use default style for single-line strings
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


# Register the custom string representer
BlockScalarDumper.add_representer(str, str_representer)

# The fast serializer writes a string in the first of these styles that reads back as
# exactly that string, and leaves the rest to the yaml.dump fallback:
# - plain, when _is_plain_safe proves it: only printable characters with no tab, no YAML
#   indicator where YAML would act on it, and yaml.safe_load resolves it to a string;
# - single-quoted, when it is one line of printable characters (tabs included);
# - a literal block scalar (|), when it holds "\n" and otherwise only printable characters;
# - anything else (control characters, a byte order mark, line breaks other than "\n",
#   a multi-line list item) raises ValueError, and yaml.dump double-quotes it with escapes.

# YAML's printable characters (PyYAML's reader rejects the others) minus tab, the line
# breaks ("\n", NEL, LS, PS) and the byte order mark, as regex character-class ranges.
_PRINTABLE_RANGES = "\x20-\x7e\xa0-\u2027\u202a-\ud7ff\ue000-\ufefe\uff00-\ufffd\U00010000-\U0010ffff"
_PLAIN_CHARS = re.compile(f"[{_PRINTABLE_RANGES}]+")
# PyYAML ends a plain scalar at a tab, but keeps it inside quotes and block scalars
_QUOTABLE_CHARS = re.compile(f"[\t{_PRINTABLE_RANGES}]*")
_BLOCK_CHARS = re.compile(f"[\t\n{_PRINTABLE_RANGES}]*")

# Indicators that YAML acts on at the start of a plain scalar, whatever follows them.
# '-' is not here: it starts a block sequence only when a space or nothing follows it,
# so "-test" stays plain (see _is_plain_safe).
_LEADING_SPECIAL = frozenset('?:,[]{}#&*!|>\'"@`%')

# YAML 1.1 keywords (compared lower-case) that older versions always quoted; see _is_plain_safe
_YAML_KEYWORDS = frozenset(["null", "~", "true", "false", "yes", "no", "on", "off"])

# yaml.safe_load resolves plain scalars with this resolver (SafeLoader inherits it)
_RESOLVER = yaml.resolver.Resolver()
_STR_TAG = "tag:yaml.org,2002:str"


def _is_plain_safe(s: str) -> bool:
    """Return True if s, written plain as a mapping value or block sequence item, reads back as s."""
    if not _PLAIN_CHARS.fullmatch(s):
        return False
    if s[0] in _LEADING_SPECIAL or s != s.strip():
        return False
    # "- x" or a lone "-" starts a block sequence
    if s[0] == "-" and s[1:2] in ("", " "):
        return False
    # ": " (or ":" at the end) starts a mapping value, " #" a comment
    if ": " in s or s.endswith(":") or " #" in s:
        return False
    # Not null, bool, int, float, timestamp, merge ("<<") or value ("=")
    if _RESOLVER.resolve(yaml.ScalarNode, s, (True, False)) != _STR_TAG:
        return False
    # Also quote what looks like a keyword or number to a reader that is not PyYAML (YAML
    # 1.2 reads "1e3" as a float) and to keep the quotes older versions wrote
    if s.lower() in _YAML_KEYWORDS:
        return False
    try:
        float(s)
    except ValueError:
        return True
    return False


def _format_scalar(s: str) -> str:
    """
    Return single-line string s as a YAML scalar: plain if that is safe, else single-quoted.

    Raises:
        ValueError: If s holds a line break or a character a single-quoted scalar cannot
            (a control character, a byte order mark), so the caller falls back to yaml.dump
    """
    if _is_plain_safe(s):
        return s
    if not _QUOTABLE_CHARS.fullmatch(s):
        raise ValueError("String with line breaks or non-printable characters not supported by fast serializer")
    return "'" + s.replace("'", "''") + "'"


def _append_block_scalar(key: str, value: str, parts: list[str]) -> None:
    """
    Append multi-line string value as a literal block scalar (|) that reads back exactly.

    Raises:
        ValueError: If value holds a character a block scalar cannot (see _format_scalar)
    """
    if not _BLOCK_CHARS.fullmatch(value):
        raise ValueError(f"Non-printable characters not supported by fast serializer: key={key!r}")
    # Chomping: strip (-) with no final "\n", clip with exactly one, keep (+) with more
    # than one or when the value is only newlines (clip would read those back as "")
    if value.endswith("\n"):
        text = value[:-1]
        chomp = "+" if text == "" or text.endswith("\n") else ""
    else:
        text = value
        chomp = "-"
    lines = text.split("\n")
    # YAML takes a block's indentation from its first non-empty line, so a first line that
    # starts with a space needs the indentation given explicitly
    first_line = next((line for line in lines if line), "")
    indent = "2" if first_line.startswith(" ") else ""
    parts.append(f"{key}: |{indent}{chomp}\n")
    for line in lines:
        # Empty lines are written bare (no trailing whitespace); others are indented
        parts.append(f"  {line}\n" if line else "\n")


def _serialize_list_item(item: Any, parts: list[str]) -> None:
    """Append a single block-sequence item line to parts. Raises ValueError for unsupported types."""
    if item is None:
        parts.append("- null\n")
    elif isinstance(item, bool):
        parts.append(f"- {'true' if item else 'false'}\n")
    elif isinstance(item, (int, float)):
        parts.append(f"- {item}\n")
    elif isinstance(item, str):
        if "\n" in item:
            # Written raw, a later line of the item would start at column 0
            raise ValueError("Multi-line list items not supported by fast serializer")
        parts.append(f"- {_format_scalar(item)}\n")
    elif isinstance(item, dict):
        raise ValueError("Dict items in lists not supported by fast serializer")
    else:
        raise ValueError(f"Unsupported list item type: {type(item).__name__}")


def _is_unset_priority(key: str, value: Any) -> bool:
    """Return True for a null or empty ``priority``: an unset priority is never written."""
    return key == "priority" and (value is None or (isinstance(value, str) and value == ""))


def fast_serialize_frontmatter(data: dict[str, Any]) -> str:
    """
    Fast hand-written YAML frontmatter serializer for typical ticket data.

    Builds YAML string directly using string formatting instead of yaml.dump.
    Handles: scalars, null, booleans, lists (block style), datetime (quoted ISO),
    and multi-line strings (literal block |).

    Every string it writes reads back exactly through yaml.safe_load: plain only when
    that is provably safe, else single-quoted, or for multi-line strings a literal
    block with the chomping and indentation indicators the value needs (see the
    style list above _PRINTABLE_RANGES).

    Raises ValueError for unsupported types (nested dicts, complex list items) and
    for strings it cannot write safely (multi-line list items, line breaks other
    than "\\n", control characters, a byte order mark) so callers can fall back to
    yaml.dump. No line it writes between the delimiters starts with "---": keys
    come first, list items start with "- " and the lines of a multi-line value are
    indented.

    Args:
        data: Raw ticket metadata dictionary (may contain datetime objects)

    Returns:
        YAML frontmatter string with --- delimiters

    Raises:
        ValueError: If data contains types or strings not handled by the fast serializer
    """
    parts: list[str] = ["---\n"]
    for key, value in data.items():
        if _is_unset_priority(key, value):
            continue
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
                _append_block_scalar(key, value, parts)
            else:
                parts.append(f"{key}: {_format_scalar(value)}\n")
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
        if _is_unset_priority(key, value):
            # An unset priority is never written (no "priority: null")
            continue
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
        # Blank separator line, body, trailing newline. parse_frontmatter removes
        # exactly these, so the body round-trips verbatim (except CR line endings,
        # which read back as "\n"; see parse_frontmatter).
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
