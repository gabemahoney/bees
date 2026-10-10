"""YAML frontmatter parser for markdown ticket files."""

from pathlib import Path
from typing import Any

import yaml

__all__ = ["parse_frontmatter", "ParseError"]


class ParseError(Exception):
    """Raised when parsing fails."""

    pass


def parse_frontmatter(file_path: Path | str) -> tuple[dict[str, Any], str]:
    """
    Parse markdown file and extract YAML frontmatter and body.

    The body is the exact inverse of write_ticket_file: only the end of the closing
    ``---`` line, the blank separator line and one trailing newline are removed.
    Leading and trailing whitespace inside the body is kept, so a body written with
    write_ticket_file reads back unchanged, except that the file is read with universal
    newlines: "\\r\\n" and a lone "\\r" read back as "\\n", and a "\\r" that ends the body
    merges with the trailing newline and is dropped. A file with no body reads as "".

    Args:
        file_path: Path to the markdown file

    Returns:
        Tuple of (frontmatter dict, markdown body string)

    Raises:
        ParseError: If file doesn't exist, has invalid format, or YAML parsing fails
        FileNotFoundError: If file doesn't exist

    Examples:
        >>> frontmatter, body = parse_frontmatter("backend/b.Amx.md")
        >>> frontmatter['id']
        'b.Amx'
        >>> frontmatter['type']
        'bee'
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Ticket file not found: {path}")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise ParseError(f"Failed to read file {path}: {e}") from e

    # Check for frontmatter delimiters
    if not content.startswith("---"):
        raise ParseError(f"File {path} does not start with '---' frontmatter delimiter")

    # Split on frontmatter delimiters
    parts = content.split("---", 2)

    if len(parts) < 3:
        raise ParseError(f"File {path} has invalid frontmatter format. Expected format: ---\\n[YAML]\\n---\\n[body]")

    # parts[0] is empty (before first ---), parts[1] is YAML, parts[2] is the rest of the
    # closing delimiter line plus the body section
    yaml_content = parts[1].strip()

    # Undo exactly what write_ticket_file adds around the body, and nothing else, so the
    # body round-trips verbatim (CR line endings aside, see the docstring): the end of the
    # closing delimiter line, the blank separator line (absent in some hand-written files)
    # and one trailing newline.
    delimiter_rest, _, body = parts[2].partition("\n")
    if delimiter_rest.strip():
        # Text on the closing delimiter line itself is part of the body
        body = parts[2]
    if body.startswith("\n"):
        body = body[1:]
    if body.endswith("\n"):
        body = body[:-1]

    # Parse YAML
    try:
        frontmatter = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ParseError(f"Failed to parse YAML in {path}: {e}") from e

    if not isinstance(frontmatter, dict):
        raise ParseError(f"YAML frontmatter in {path} must be a dictionary, got {type(frontmatter)}")

    return frontmatter, body
