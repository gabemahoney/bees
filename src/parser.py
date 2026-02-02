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

    Args:
        file_path: Path to the markdown file

    Returns:
        Tuple of (frontmatter dict, markdown body string)

    Raises:
        ParseError: If file doesn't exist, has invalid format, or YAML parsing fails
        FileNotFoundError: If file doesn't exist

    Examples:
        >>> frontmatter, body = parse_frontmatter("backend/backend.bees-250.md")
        >>> frontmatter['id']
        'backend.bees-250'
        >>> frontmatter['type']
        'epic'
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Ticket file not found: {path}")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise ParseError(f"Failed to read file {path}: {e}")

    # Check for frontmatter delimiters
    if not content.startswith("---"):
        raise ParseError(f"File {path} does not start with '---' frontmatter delimiter")

    # Split on frontmatter delimiters
    parts = content.split("---", 2)

    if len(parts) < 3:
        raise ParseError(
            f"File {path} has invalid frontmatter format. "
            "Expected format: ---\\n[YAML]\\n---\\n[body]"
        )

    # parts[0] is empty (before first ---), parts[1] is YAML, parts[2] is body
    yaml_content = parts[1].strip()
    body = parts[2].strip()

    # Parse YAML
    try:
        frontmatter = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ParseError(f"Failed to parse YAML in {path}: {e}")

    if not isinstance(frontmatter, dict):
        raise ParseError(
            f"YAML frontmatter in {path} must be a dictionary, got {type(frontmatter)}"
        )

    return frontmatter, body
