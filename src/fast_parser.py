"""Fast line-based frontmatter parser for bees ticket files.

Parses only the YAML frontmatter block using string/line operations.
No yaml library, no Ticket construction, no schema validation.
"""

from pathlib import Path
from typing import Any

__all__ = ["fast_parse_frontmatter"]

_KNOWN_FIELDS = frozenset(
    [
        "id",
        "type",
        "title",
        "status",
        "tags",
        "parent",
        "children",
        "up_dependencies",
        "down_dependencies",
        "guid",
        "schema_version",
    ]
)

_LIST_FIELDS = frozenset(
    ["tags", "children", "up_dependencies", "down_dependencies"]
)


def _unquote(value: str) -> str:
    """Strip single or double quotes from a YAML scalar string."""
    if len(value) >= 2:
        if (value[0] == "'" and value[-1] == "'") or (
            value[0] == '"' and value[-1] == '"'
        ):
            return value[1:-1]
    return value


def _parse_scalar(value: str) -> Any:
    """Convert a YAML scalar string to a Python value."""
    stripped = value.strip()
    if stripped in ("null", "~", ""):
        return None
    if stripped in ("true", "True"):
        return True
    if stripped in ("false", "False"):
        return False
    return _unquote(stripped)


def fast_parse_frontmatter(file_path: Path | str) -> dict[str, Any] | None:
    """Parse a bees ticket markdown file and return frontmatter fields.

    Uses line-based parsing — no yaml library involved. Returns only the
    fields relevant to the pipeline query engine.

    Args:
        file_path: Path to the markdown ticket file.

    Returns:
        Dict with ticket fields, or None if schema_version is absent
        (indicating this is not a bees ticket file).
    """
    path = Path(file_path)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if not content.startswith("---"):
        return None

    # Find the closing ---
    lines = content.splitlines()
    # lines[0] is "---"; find the next "---"
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None

    fm_lines = lines[1:end_idx]

    result: dict[str, Any] = {}
    current_list_key: str | None = None

    for line in fm_lines:
        # Continuation of a multi-line list
        if current_list_key is not None:
            stripped = line.strip()
            if stripped.startswith("- "):
                item = _unquote(stripped[2:].strip())
                result[current_list_key].append(item)
                continue
            elif stripped == "-":
                result[current_list_key].append(None)
                continue
            else:
                # Not a list item — end of the list block
                current_list_key = None

        if ":" not in line:
            continue

        colon_idx = line.index(":")
        key = line[:colon_idx].strip()

        if key not in _KNOWN_FIELDS:
            continue

        value_part = line[colon_idx + 1 :]
        value_stripped = value_part.strip()

        if value_stripped == "[]":
            result[key] = []
        elif value_stripped == "" and key in _LIST_FIELDS:
            # Multi-line list: collect items on following lines
            result[key] = []
            current_list_key = key
        else:
            result[key] = _parse_scalar(value_stripped)

    if "schema_version" not in result:
        return None

    # Ensure list fields default to empty list when absent
    for field in _LIST_FIELDS:
        if field not in result:
            result[field] = []

    return result
