"""Path resolution utilities for ticket file management."""

import logging
import os
from collections.abc import Callable, Generator, Iterator
from pathlib import Path
from typing import Any, Literal

from .id_utils import is_ticket_id, normalize_hive_name
from .reader import get_ticket_type, read_ticket
from .types import TicketType

logger = logging.getLogger(__name__)

# Directory that marks a hive root; it holds the hive's identity.json
HIVE_MARKER_DIR = ".hive"

# Directories a deep walk never enters, besides hidden ones
_DEEP_WALK_EXCLUDED_DIRS = frozenset({"evicted", "cemetery"})


def _is_deep_walk_dir(name: str) -> bool:
    """Return True if a deep walk enters a subdirectory with this name."""
    return not name.startswith(".") and name not in _DEEP_WALK_EXCLUDED_DIRS


def _relpath_inside(path: str, base: str) -> str | None:
    """Return path relative to base if path is strictly inside base, else None."""
    try:
        rel = os.path.relpath(path, base)
    except ValueError:  # path and base are on different drives
        return None
    if rel in (os.curdir, os.pardir) or rel.startswith(os.pardir + os.sep):
        return None
    return rel


def _registered_hive_roots_inside(top: str) -> frozenset[str]:
    """Return the roots of registered hives strictly inside top, spelled as os.walk(top) spells them.

    Hive roots come from every scope of the global config, loaded once per call.
    top is matched both as given and with symlinks resolved.
    """
    from .config import ConfigLoadError, load_global_config

    try:
        global_config = load_global_config()
    except ConfigLoadError:
        # Not a degraded-mode case: an empty set would let a walk enter a nested hive
        raise
    except (OSError, ValueError) as e:
        logger.warning(f"Cannot read registered hive roots from the global config: {e}")
        return frozenset()

    bases = {os.path.abspath(top), os.path.realpath(top)}
    inside: set[str] = set()
    for scope_data in global_config.get("scopes", {}).values():
        hives = scope_data.get("hives") if isinstance(scope_data, dict) else None
        if not isinstance(hives, dict):
            continue
        for hive_data in hives.values():
            hive_path = hive_data.get("path") if isinstance(hive_data, dict) else None
            if not isinstance(hive_path, str) or not hive_path:
                continue
            for base in bases:
                rel = _relpath_inside(os.path.abspath(hive_path), base)
                if rel is not None:
                    inside.add(os.path.join(top, rel))
    return frozenset(inside)


def _is_other_hive_root(top: str, dirpath: str, dirnames: list[str], other_hive_roots: frozenset[str]) -> bool:
    """Return True if dirpath, as os.walk(top) yields it, is the root of a hive other than top.

    other_hive_roots is _registered_hive_roots_inside(top).
    """
    return dirpath != top and (HIVE_MARKER_DIR in dirnames or dirpath in other_hive_roots)


def walk_hive(
    hive_root: str | os.PathLike, enter: Callable[[str], bool] | None = None
) -> Iterator[tuple[str, list[str], list[str]]]:
    """Walk a hive's directory tree top-down like os.walk, never entering another hive.

    A directory below hive_root belongs to another hive when it holds its own
    .hive/ directory or is the root of a hive registered in any scope of the
    global config. Such a directory is not yielded and nothing under it is
    visited. hive_root itself is always walked, so it may be a hive root or a
    ticket directory inside one.

    The .hive/ check reads the directory listing os.walk already made, and the
    global config is loaded once per walk, so pruning adds no per-directory I/O.

    Args:
        hive_root: Directory to walk.
        enter: Predicate on a subdirectory name; only subdirectories it accepts
            are entered. None enters every subdirectory.

    Yields:
        (dirpath, dirnames, filenames) as os.walk yields them, with dirnames
        already filtered by enter and sorted. dirnames may still name another
        hive's root; that directory is pruned when the walk reaches it.
    """
    top = os.fspath(hive_root)
    other_hive_roots = _registered_hive_roots_inside(top)
    for dirpath, dirs, files in os.walk(top):
        if _is_other_hive_root(top, dirpath, dirs, other_hive_roots):
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if enter is None or enter(d))
        yield dirpath, dirs, files


def find_nested_hive_root(top: str | os.PathLike) -> Path | None:
    """Return the first root of another hive found strictly below top, or None.

    Walks every directory below top, hidden ones included, top-down. A
    directory is another hive's root when it holds its own .hive/ directory
    or is the root of a hive registered in any scope of the global config.
    Check this before deleting top, so another hive is never deleted with it.
    """
    top_str = os.fspath(top)
    other_hive_roots = _registered_hive_roots_inside(top_str)
    for dirpath, dirs, _files in os.walk(top_str):
        if _is_other_hive_root(top_str, dirpath, dirs, other_hive_roots):
            return Path(dirpath)
    return None


def find_enclosing_hive_root(hive_root: Path, path: Path) -> Path | None:
    """Return the root of another hive that path lies in below hive_root, or None.

    Checks each directory from just below hive_root down to path itself,
    outermost first, and returns the first that holds its own .hive/ directory
    or is the root of a hive registered in any scope of the global config.
    Returns None when path is hive_root itself or is not inside it.
    """
    top = os.fspath(hive_root)
    rel = _relpath_inside(os.path.abspath(path), os.path.abspath(top))
    if rel is None:
        return None
    other_hive_roots = _registered_hive_roots_inside(top)
    candidate = top
    for part in Path(rel).parts:
        candidate = os.path.join(candidate, part)
        if candidate in other_hive_roots or os.path.isdir(os.path.join(candidate, HIVE_MARKER_DIR)):
            return Path(candidate)
    return None


def hive_crossing_reason(
    hive_root: Path, src: Path, dest: Path | None = None, operation: Literal["move", "delete"] = "move"
) -> str | None:
    """Return why moving src to dest, or deleting src, would cross into another hive, or None.

    Check this before moving or deleting a whole directory of the hive at
    hive_root, so another hive is never carried, deleted or entered with it.
    In order, the operation is refused when:

    - src, then dest, lies inside another hive nested below hive_root (see
      find_enclosing_hive_root()): that directory belongs to the other hive
    - another hive's root lies anywhere below src (see find_nested_hive_root()):
      the move would carry it off its path, the delete would remove it
    - dest already exists and another hive's root lies anywhere below it: src,
      or its entries, would land in a directory holding that hive

    Args:
        hive_root: Root of the hive src belongs to
        src: Directory to be moved or deleted
        dest: Where src would be moved, or None to skip the checks on dest
            (a delete, or a move whose dest lies in another hive)
        operation: "move" or "delete"; only changes the wording of the reason

    Returns:
        The reason the operation is refused, naming the other hive's root, or
        None if it may go ahead
    """
    for path in (src, dest):
        if path is None:
            continue
        other_hive_root = find_enclosing_hive_root(hive_root, path)
        if other_hive_root is not None:
            return f"{path} is inside another hive rooted at {other_hive_root}"
    other_hive_root = find_nested_hive_root(src)
    if other_hive_root is not None:
        consequence = "which the delete would remove" if operation == "delete" else "which the move would carry"
        return f"{src} holds another hive rooted at {other_hive_root}, {consequence}"
    if dest is not None and dest.exists():
        other_hive_root = find_nested_hive_root(dest)
        if other_hive_root is not None:
            return f"{dest} already exists and holds another hive rooted at {other_hive_root}"
    return None


def iter_ticket_files(hive_root: Path) -> Generator[Path, None, None]:
    """Yield all ticket .md files in a hive using selective directory traversal.

    Only recurses into directories whose names match the ticket ID pattern,
    naturally excluding /cemetery, eggs/, .hive/, evicted/, and any future
    special directories. Never enters another hive nested inside this one
    (a subdirectory with its own .hive/ or a registered hive root; see
    walk_hive()).

    Yields:
        Path objects for files matching {ticket_id}/{ticket_id}.md pattern.
        Skips index.md files.
    """
    for dirpath, _dirs, files in walk_hive(hive_root, enter=is_ticket_id):
        dir_name = Path(dirpath).name
        if is_ticket_id(dir_name):
            md_name = f"{dir_name}.md"
            if md_name in files:
                yield Path(dirpath) / md_name


def iter_ticket_files_deep(hive_root: Path) -> Generator[Path, None, None]:
    """Yield all ticket .md files, including misplaced ones.

    Broader traversal for the linter: enters all directories except hidden
    ones (naturally excludes .hive/), evicted/ and cemetery/, finding tickets
    even in wrong locations or with non-standard directory names. Never enters
    another hive nested inside this one (a subdirectory with its own .hive/
    or a registered hive root; see walk_hive()). Only yields files matching
    the {dirname}/{dirname}.md naming convention.

    Use iter_ticket_files() for normal operations on well-structured hives.
    Use this function when scanning for misplaced or invalid tickets.
    """
    for dirpath, _dirs, files in walk_hive(hive_root, enter=_is_deep_walk_dir):
        dir_name = Path(dirpath).name
        md_name = f"{dir_name}.md"
        if md_name in files:
            yield Path(dirpath) / md_name


def build_ticket_path_map(
    ticket_ids: set[str],
    hive_collection: list[tuple[str, Any]] | None = None,
) -> dict[str, tuple[str, Path]]:
    """Walk all hives once to find paths for multiple tickets.

    Returns {ticket_id: (hive_name, path)} for all found tickets.

    Args:
        ticket_ids: Set of ticket IDs to locate.
        hive_collection: Optional list of (hive_name, hive_config) pairs. When
            provided, used instead of calling load_bees_config(). Allows callers
            (e.g. queen repos) to supply a merged collection spanning multiple
            scopes, including duplicate normalized names.
    """
    if hive_collection is not None:
        hive_items: list[tuple[str, Any]] = hive_collection
    else:
        from .config import load_bees_config

        config = load_bees_config()
        if not config or not config.hives:
            return {}
        hive_items = list(config.hives.items())

    result: dict[str, tuple[str, Path]] = {}
    needed = set(ticket_ids)
    for hive_name, hive_config in hive_items:
        if not needed:
            break
        hive_path = Path(hive_config.path)
        if not hive_path.exists():
            continue
        for tid in list(needed):
            candidate = compute_ticket_path(tid, hive_path)
            if candidate.exists():
                result[tid] = (hive_name, candidate)
                needed.discard(tid)
    return result


def _build_queen_hive_collection(resolved_root: Path | None) -> list[tuple[str, Any]] | None:
    """Return a merged hive collection for queen repos, or None for non-queens.

    When resolved_root is a queen repo, flattens all hive configs from every
    scope in global config into a flat list of (hive_name, hive_config) pairs.
    Hives with the same normalized name from different scopes are both included
    so all paths are walked. Returns None for non-queen repos (existing behavior).

    Args:
        resolved_root: Repo root path, or None if unknown.

    Returns:
        List of (hive_name, hive_config) pairs for queen repos, else None.
    """
    if resolved_root is None:
        return None
    from .config import check_queen_elevation, get_all_scopes_config, load_global_config

    global_config = load_global_config()
    is_queen, _ = check_queen_elevation(resolved_root, global_config)
    if not is_queen:
        return None
    all_scopes = get_all_scopes_config(global_config)
    merged: list[tuple[str, Any]] = []
    for scope_config in all_scopes.values():
        for hive_name, hive_config in scope_config.hives.items():
            merged.append((hive_name, hive_config))
    return merged


def _build_queen_hive_scope_map(resolved_root: Path | None) -> "dict[str, Any] | None":
    """Return {hive_name: BeesConfig} for queen repos for per-hive scope config lookup.

    Returns None for non-queen repos. When multiple scopes share the same normalized
    hive name, the first scope encountered wins (consistent with _build_queen_hive_collection).
    """
    if resolved_root is None:
        return None
    from .config import BeesConfig, check_queen_elevation, get_all_scopes_config, load_global_config

    global_config = load_global_config()
    is_queen, _ = check_queen_elevation(resolved_root, global_config)
    if not is_queen:
        return None
    scope_map: dict[str, BeesConfig] = {}
    for scope_cfg in get_all_scopes_config(global_config).values():
        for hive_name in scope_cfg.hives:
            scope_map.setdefault(hive_name, scope_cfg)
    return scope_map


def compute_ticket_path(ticket_id: str, hive_root: Path) -> Path:
    """Compute the expected filesystem path for a ticket without any directory scan.

    Since child IDs encode the full parent hierarchy, the path is fully deterministic:

        b.abc        → hive_root/b.abc/b.abc.md
        t1.abc.de    → hive_root/b.abc/t1.abc.de/t1.abc.de.md
        t2.abc.de.fg → hive_root/b.abc/t1.abc.de/t2.abc.de.fg/t2.abc.de.fg.md

    No filesystem access is performed — call ``.exists()`` on the result to check.
    """
    if "." not in ticket_id:
        raise ValueError(f"Malformed ticket ID (no dot separator): {ticket_id!r}")
    dot_idx = ticket_id.index(".")
    prefix = ticket_id[:dot_idx]  # "b", "t1", "t2", …
    short_id = ticket_id[dot_idx + 1 :]  # "abc", "abc.de", "abc.de.fg", …
    segments = short_id.split(".")

    # Start at hive root, then descend through the bee directory
    path = hive_root / f"b.{segments[0]}"

    if prefix != "b":
        tier_num = int(prefix[1:])
        for level in range(1, tier_num + 1):
            level_id = f"t{level}." + ".".join(segments[: level + 1])
            path = path / level_id

    return path / f"{ticket_id}.md"


def find_ticket_file(hive_root: Path, ticket_id: str, deep: bool = False) -> Path | None:
    """Find a specific ticket's .md file using selective directory traversal.

    Returns the first matching {ticket_id}/{ticket_id}.md file found. Never
    enters another hive nested inside this one (see walk_hive()).

    Args:
        hive_root: Root path of the hive to search
        ticket_id: Ticket ID to find
        deep: If False (default), only enters ticket-ID directories.
              If True, enters all non-hidden directories except evicted/ and
              cemetery/ (for finding misplaced tickets).

    Returns:
        Path to the ticket's .md file, or None if not found
    """
    md_name = f"{ticket_id}.md"
    for dirpath, _dirs, files in walk_hive(hive_root, enter=_is_deep_walk_dir if deep else is_ticket_id):
        if Path(dirpath).name == ticket_id and md_name in files:
            return Path(dirpath) / md_name

    return None


def get_ticket_path(ticket_id: str, ticket_type: TicketType, hive_name: str) -> Path:
    """
    Get the full file path for a ticket based on its ID and hive name.

    Tickets are stored in hierarchical directory structure where each ticket
    has its own directory: {ticket_id}/{ticket_id}.md

    For existing tickets, scans the hive recursively to find the ticket file.
    For new tickets (file doesn't exist), use compute_ticket_directory() instead.

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx", "t1.X4F2")
        ticket_type: The type of ticket (kept for API compatibility)
        hive_name: The hive name for storage location (required)

    Returns:
        Path object pointing to the ticket's markdown file

    Raises:
        ValueError: If ticket_id is empty or hive not found in config
        FileNotFoundError: If ticket file doesn't exist in the hive

    Examples:
        >>> get_ticket_path("b.Amx", "bee", "backend")
        PosixPath('/path/to/backend/b.Amx/b.Amx.md')
    """
    if not ticket_id:
        raise ValueError("ticket_id cannot be empty")

    if not hive_name:
        raise ValueError("hive_name cannot be empty")

    # Normalize hive_name for config lookup (handles display names like "Back End" -> "back_end")
    normalized_hive = normalize_hive_name(hive_name)

    # Load config to get hive path
    from .config import load_bees_config

    config = load_bees_config()

    if not config or normalized_hive not in config.hives:
        raise ValueError(f"Hive '{hive_name}' (normalized: '{normalized_hive}') not found in config")

    base_dir = Path(config.hives[normalized_hive].path)

    result = compute_ticket_path(ticket_id, base_dir)
    if result.exists():
        return result

    raise FileNotFoundError(f"Ticket file for '{ticket_id}' not found in hive '{hive_name}'")


def compute_ticket_directory(ticket_id: str, parent_id: str | None, hive_name: str) -> Path:
    """
    Compute the target directory path for a ticket within a hive.

    Used for new ticket creation to determine where the ticket directory should be created.

    Hierarchical structure:
    - Bees (no parent): {hive_root}/{ticket_id}/
    - Children (with parent): {parent_dir}/{ticket_id}/

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx", "t1.X4F2")
        parent_id: The parent ticket ID (None for bees at root level)
        hive_name: The hive name for storage location

    Returns:
        Path object pointing to the ticket's directory

    Raises:
        ValueError: If ticket_id is empty or hive not found in config
        FileNotFoundError: If parent ticket doesn't exist (for child tickets)

    Examples:
        >>> compute_ticket_directory("b.Amx", None, "backend")
        PosixPath('/path/to/backend/b.Amx')

        >>> compute_ticket_directory("t1.X4F2", "b.Amx", "backend")
        PosixPath('/path/to/backend/b.Amx/t1.X4F2')
    """
    if not ticket_id:
        raise ValueError("ticket_id cannot be empty")

    if not hive_name:
        raise ValueError("hive_name cannot be empty")

    # Normalize hive_name for config lookup
    normalized_hive = normalize_hive_name(hive_name)

    # Load config to get hive path
    from .config import load_bees_config

    config = load_bees_config()

    if not config or normalized_hive not in config.hives:
        raise ValueError(f"Hive '{hive_name}' (normalized: '{normalized_hive}') not found in config")

    base_dir = Path(config.hives[normalized_hive].path)

    # If no parent, ticket directory is at hive root
    if parent_id is None:
        return base_dir / ticket_id

    # If parent exists, find parent's directory and nest under it
    try:
        # Use a dummy type since we're just finding the path
        parent_path = get_ticket_path(parent_id, "bee", hive_name)
        parent_dir = parent_path.parent
        return parent_dir / ticket_id
    except FileNotFoundError as err:
        raise FileNotFoundError(f"Parent ticket '{parent_id}' not found in hive '{hive_name}'") from err


def ensure_ticket_directory_exists(hive_name: str) -> None:
    """
    Ensure the hive root directory exists, creating it if necessary.

    With flat storage, all tickets are stored in hive root, so we only need
    to ensure the hive directory itself exists (no type-specific subdirectories).

    Args:
        hive_name: Name of the hive (required)

    Raises:
        ValueError: If hive_name is not provided
    """
    if not hive_name:
        raise ValueError("hive_name is required")

    hive_dir = Path.cwd() / hive_name
    hive_dir.mkdir(parents=True, exist_ok=True)


def infer_ticket_type_from_id(ticket_id: str) -> TicketType | None:
    """
    Infer ticket type from its ID by reading YAML frontmatter from ticket file.

    Searches all configured hives recursively to find the ticket file using
    the hierarchical pattern {ticket_id}/{ticket_id}.md. Type is determined
    from the 'type' field in the YAML frontmatter.

    Args:
        ticket_id: The ticket ID (e.g., "b.Amx", "t1.X4F2")

    Returns:
        The ticket type ('bee', 't1', 't2', etc.) if found, None if not found

    Examples:
        >>> infer_ticket_type_from_id("b.Amx")
        'bee'

        >>> infer_ticket_type_from_id("nonexistent.id")
        None
    """
    if not ticket_id:
        return None

    return get_ticket_type(ticket_id)


def list_tickets(ticket_type: TicketType | None = None) -> list[Path]:
    """
    List all ticket files from all configured hives, optionally filtered by type.

    Scans hive directories recursively for hierarchical ticket storage.
    Excludes special directories (eggs, evicted, .hive), other hives nested
    inside a hive, and index.md files.
    Only includes files matching the pattern {ticket_id}/{ticket_id}.md.

    Args:
        ticket_type: Optional ticket type to filter by. If None, returns all tickets.
                    Valid types: "bee" or any tier from child_tiers config (t1, t2, t3, etc.)

    Returns:
        List of Path objects pointing to ticket markdown files across all hives

    Raises:
        ValueError: If ticket_type is not a valid type according to child_tiers config

    Examples:
        >>> list_tickets("bee")
        [PosixPath('/path/to/backend/b.Amx/b.Amx.md'), ...]

        >>> list_tickets("t1")  # Filter by tier
        [PosixPath('/path/to/backend/b.Amx/t1.X4F2/t1.X4F2.md'), ...]

        >>> list_tickets()  # All tickets from all hives
        [PosixPath('backend/b.Amx/b.Amx.md'), ...]
    """
    from .config import load_bees_config

    all_tickets = []

    # Load hive configuration
    config = load_bees_config()

    if not config or not config.hives:
        # No hives configured - return empty list
        return []

    # Validate ticket_type if provided
    if ticket_type is not None:
        from .validator import BASE_TIER

        # Build valid types: base tier + tier IDs + friendly names
        valid_types = {BASE_TIER}
        if config.child_tiers:
            # Add tier IDs (t1, t2, t3...)
            valid_types.update(config.child_tiers.keys())

            # Add friendly names (singular/plural if provided)
            for tier_config in config.child_tiers.values():
                if tier_config.singular:
                    valid_types.add(tier_config.singular)
                if tier_config.plural:
                    valid_types.add(tier_config.plural)

        if ticket_type not in valid_types:
            available = ", ".join(sorted(valid_types))
            raise ValueError(f"Invalid ticket type '{ticket_type}'. Valid types for this configuration: {available}")

    # Iterate all hives
    for _hive_name, hive_config in config.hives.items():
        hive_path = Path(hive_config.path)

        if not hive_path.exists():
            continue

        # Selective traversal: only enters ticket-ID directories
        ticket_files = list(iter_ticket_files(hive_path))

        for ticket_file in ticket_files:
            try:
                ticket_id = ticket_file.stem
                ticket = read_ticket(ticket_id, file_path=ticket_file)
                if ticket_type is None or ticket.type == ticket_type:
                    all_tickets.append(ticket_file)
            except Exception as e:
                import warnings

                warnings.warn(f"Failed to load ticket {ticket_file}: {e}. Skipping.", stacklevel=2)
                continue

    return sorted(all_tickets)
