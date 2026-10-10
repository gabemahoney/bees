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

    The file must start with ``---``. The frontmatter runs from there to the closing
    delimiter: the first later line that starts with ``---``. Three dashes anywhere else
    (inside a value, or on an indented line of a multi-line value) are part of the YAML,
    and write_ticket_file never starts a frontmatter line with ``---``.

    The body is the exact inverse of write_ticket_file: only the end of the closing
    ``---`` line, the blank separator line and one trailing newline are removed (if the
    closing line holds more than whitespace after ``---``, that text starts the body).
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

    # The closing delimiter starts a line, so a "---" inside a value never closes the
    # frontmatter: search for "\n---" from the end of the opening line. The file is read
    # with universal newlines, so "\n" is the only line break here.
    opening_line_end = content.find("\n")
    closing_start = -1 if opening_line_end == -1 else content.find("\n---", opening_line_end)

    if closing_start == -1:
        raise ParseError(f"File {path} has invalid frontmatter format. Expected format: ---\\n[YAML]\\n---\\n[body]")

    # Keep the newline that ends the last frontmatter line and any empty lines before the
    # closing delimiter: they belong to a keep-chomped (|+) block scalar written last
    yaml_content = content[len("---") : closing_start + 1].lstrip()
    # The rest of the closing delimiter line, then the body section
    after_delimiter = content[closing_start + len("\n---") :]

    # Undo exactly what write_ticket_file adds around the body, and nothing else, so the
    # body round-trips verbatim (CR line endings aside, see the docstring): the end of the
    # closing delimiter line, the blank separator line (absent in some hand-written files)
    # and one trailing newline.
    delimiter_rest, _, body = after_delimiter.partition("\n")
    if delimiter_rest.strip():
        # Text on the closing delimiter line itself is part of the body
        body = after_delimiter
    if body.startswith("\n"):
        body = body[1:]
    if body.endswith("\n"):
        body = body[:-1]

    # Parse YAML
    try:
        try:
            frontmatter = yaml.safe_load(yaml_content)
        except yaml.YAMLError:
            # A hand-edited file may end its last line, or an empty line, with a tab that
            # YAML rejects: retry once with the whitespace stripped, as older versions read it
            frontmatter = yaml.safe_load(content[len("---") : closing_start].strip())
    except yaml.YAMLError as e:
        raise ParseError(f"Failed to parse YAML in {path}: {e}") from e

    if not isinstance(frontmatter, dict):
        raise ParseError(f"YAML frontmatter in {path} must be a dictionary, got {type(frontmatter)}")

    return frontmatter, body
