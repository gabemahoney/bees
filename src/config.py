"""Configuration management for Bees MCP Server.

Handles ~/.bees/config.json for global scoped hive configuration.
"""

import json
import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.repo_context import get_repo_root

logger = logging.getLogger(__name__)

# Module-level path override for config file location
_CONFIG_PATH_OVERRIDE: str | None = None

# mtime-based cache for load_global_config()
_GLOBAL_CONFIG_CACHE: dict | None = None
_GLOBAL_CONFIG_CACHE_MTIME: float | None = None

# In-memory config override for tests (bypasses disk I/O entirely)
_GLOBAL_CONFIG_OVERRIDE: dict | None = None
_TEST_CONFIG_LOCK = threading.Lock()


def set_config_path(path: str | None) -> None:
    """Set config file path override. None resets to default."""
    global _CONFIG_PATH_OVERRIDE
    _CONFIG_PATH_OVERRIDE = path


def set_test_config_override(config: dict | None) -> None:
    """Set an in-memory config override, bypassing all disk I/O.

    When set, load_global_config() returns this dict directly and
    save_global_config() mutates it in place. Pass None to clear.

    Args:
        config: Dict to use as the global config, or None to disable override.
    """
    global _GLOBAL_CONFIG_OVERRIDE, _GLOBAL_CONFIG_CACHE, _GLOBAL_CONFIG_CACHE_MTIME
    with _TEST_CONFIG_LOCK:
        _GLOBAL_CONFIG_OVERRIDE = config
        _GLOBAL_CONFIG_CACHE = None
        _GLOBAL_CONFIG_CACHE_MTIME = None


# Hive Configuration (global ~/.bees/config.json with scoped patterns)


@dataclass
class ChildTierConfig:
    """Configuration for a single child tier.

    Attributes:
        singular: Singular friendly name (e.g., "Task") or None if no friendly name
        plural: Plural friendly name (e.g., "Tasks") or None if no friendly name
    """

    singular: str | None = None
    plural: str | None = None


@dataclass
class HiveConfig:
    """Configuration for a single hive."""

    path: str
    display_name: str
    created_at: str
    egg_resolver: str | None = None
    egg_resolver_timeout: int | float | None = None
    child_tiers: dict[str, ChildTierConfig] | None = None
    status_values: list[str] | None = None
    status_values_explicitly_null: bool = False
    undertaker_schedule_seconds: int | None = None
    undertaker_schedule_query_yaml: str | None = None
    undertaker_schedule_query_name: str | None = None
    undertaker_schedule_log_path: str | None = None


@dataclass
class BeesConfig:
    """Configuration for a single scope within ~/.bees/config.json.

    Attributes:
        hives: Dictionary of normalized hive names to HiveConfig objects
        schema_version: Schema version string
        child_tiers: Dictionary of tier keys (t1, t2, t3...) to ChildTierConfig objects
                     None means not configured, {} means explicitly bees-only
        egg_resolver: Scope-level egg resolver command (optional)
        egg_resolver_timeout: Scope-level egg resolver timeout in seconds (optional)
        status_values: Scope-level list of allowed status values (optional)
    """

    hives: dict[str, HiveConfig] = field(default_factory=dict)
    schema_version: str = "2.0"
    child_tiers: dict[str, ChildTierConfig] | None = None
    egg_resolver: str | None = None
    egg_resolver_timeout: int | float | None = None
    status_values: list[str] | None = None


@dataclass(frozen=True)
class ConflictRecord:
    """A single hive-name conflict between two scopes."""

    normalized_hive_name: str
    scope_a: str
    scope_b: str


# Constants
BEES_CONFIG_DIR = ".bees"
BEES_CONFIG_FILENAME = "config.json"
GLOBAL_SCHEMA_VERSION = "2.0"

# Regex for converting scope patterns to regex
_SCOPE_PATTERN_CACHE: dict[str, re.Pattern] = {}
_CACHE_LOCK = threading.Lock()

# Suffixes recognized by canonicalize_scope_pattern, in priority order
_WILDCARD_SUFFIXES = ("/**", "/*", "/")


def canonicalize_scope_pattern(pattern: str) -> str:
    """Return the canonical form of a scope pattern.

    Strips any trailing `/**`, `/*`, or `/` suffix, then re-appends the
    appropriate suffix.  A bare path with no wildcard suffix is treated as
    trailing-slash (exact-directory) form.

    Canonical forms:
        ``/foo/``    – exact directory match
        ``/foo/*``   – one level below
        ``/foo/**``  – any depth below

    Args:
        pattern: Raw scope pattern string.

    Returns:
        Canonical pattern string.
    """
    for suffix in _WILDCARD_SUFFIXES:
        if pattern.endswith(suffix):
            bare = pattern[: -len(suffix)]
            return bare + suffix
    # No recognized suffix → trailing-slash exact form
    return pattern + "/"


def validate_scope_pattern(pattern: str) -> None:
    """Raise ValueError if *pattern* contains invalid wildcard placement.

    Valid positions for ``*`` are only at the very end as ``/*`` or ``/**``.
    Mid-path wildcards (e.g. ``/foo/*/bar``) and bare ``**`` without a
    leading ``/`` are rejected.

    Args:
        pattern: Raw scope pattern string.

    Raises:
        ValueError: If the pattern contains misplaced wildcards.
    """
    # Strip the one valid terminal suffix before checking for stray wildcards
    bare = pattern
    for suffix in _WILDCARD_SUFFIXES:
        if pattern.endswith(suffix):
            bare = pattern[: -len(suffix)]
            break

    if "*" in bare:
        raise ValueError(
            f"Invalid scope pattern {pattern!r}: wildcards are only allowed as "
            "terminal '/*' or '/**' suffixes."
        )


def compute_scope_specificity(pattern: str) -> tuple[int, int]:
    """Return a specificity tuple for ranking scope patterns.

    The tuple ``(segment_count, wildcard_tier)`` allows direct comparison:
    higher is more specific.

    segment_count
        Number of literal path segments in the bare prefix (the pattern
        minus any terminal wildcard suffix).

    wildcard_tier
        0 – trailing-slash / exact form (``/foo/``)
        1 – single-level wildcard (``/foo/*``)
        2 – recursive wildcard (``/foo/**``)

    This function is intentionally *not* cached — call it fresh each time.

    Args:
        pattern: Raw scope pattern string (need not be canonicalized first).

    Returns:
        ``(segment_count, wildcard_tier)`` tuple.
    """
    if pattern.endswith("/**"):
        bare = pattern[:-3]
        tier = 2
    elif pattern.endswith("/*"):
        bare = pattern[:-2]
        tier = 1
    else:
        # trailing-slash or bare path
        bare = pattern.rstrip("/")
        tier = 0

    # Count non-empty segments in the bare prefix
    segment_count = len([s for s in bare.split("/") if s])
    return (segment_count, tier)


def scopes_overlap(pattern_a: str, pattern_b: str) -> bool:
    """Return True if the two scope patterns can match the same repository path.

    One pattern must be an ancestor-or-equal of the other, *and* the parent
    pattern's wildcard tier must reach the child's depth.

    Wildcard semantics:
        ``/**`` – matches any depth below the prefix (tier 2)
        ``/*``  – matches exactly one level below (tier 1)
        exact/trailing-slash – matches nothing below the prefix (tier 0)

    Args:
        pattern_a: First scope pattern.
        pattern_b: Second scope pattern.

    Returns:
        True if the patterns overlap.
    """
    canon_a = canonicalize_scope_pattern(pattern_a)
    canon_b = canonicalize_scope_pattern(pattern_b)

    seg_a, tier_a = compute_scope_specificity(canon_a)
    seg_b, tier_b = compute_scope_specificity(canon_b)

    # Derive bare prefixes (strip wildcard suffix + trailing slash)
    prefix_a = _bare_prefix(canon_a)
    prefix_b = _bare_prefix(canon_b)

    # Determine which is the shallower (potential ancestor)
    if seg_a <= seg_b:
        ancestor_prefix, ancestor_tier = prefix_a, tier_a
        child_prefix = prefix_b
        depth_diff = seg_b - seg_a
    else:
        ancestor_prefix, ancestor_tier = prefix_b, tier_b
        child_prefix = prefix_a
        depth_diff = seg_a - seg_b

    # Child must start with ancestor's prefix
    if not (child_prefix == ancestor_prefix or child_prefix.startswith(ancestor_prefix + "/")):
        return False

    # Ancestor's wildcard must reach the child
    if depth_diff == 0:
        return True  # same depth → identical prefixes overlap by definition
    if ancestor_tier == 2:
        return True  # /** reaches any depth
    if ancestor_tier == 1 and depth_diff == 1:
        return True  # /* reaches exactly one level deeper
    return False


def get_global_bees_dir() -> Path:
    """Get the global bees config directory path (~/.bees/)."""
    return Path.home() / BEES_CONFIG_DIR


def get_global_config_path() -> Path:
    """Get the path to the global config file (~/.bees/config.json)."""
    return get_global_bees_dir() / BEES_CONFIG_FILENAME


def ensure_global_bees_dir() -> None:
    """Create ~/.bees/ directory if it doesn't exist."""
    get_global_bees_dir().mkdir(exist_ok=True)


def match_scope_pattern(repo_root: Path, pattern: str) -> bool:
    """Check if repo_root matches a scope directory pattern.

    Pattern syntax:
        * = matches within a single path segment (not /)
        ** = matches recursively through subdirectories (including /)
        Trailing-slash / exact paths match with or without trailing slash.

    Args:
        repo_root: The repository root path to test
        pattern: The scope pattern (directory path with optional * or ** wildcards)

    Returns:
        True if repo_root matches the pattern
    """
    with _CACHE_LOCK:
        if pattern in _SCOPE_PATTERN_CACHE:
            compiled = _SCOPE_PATTERN_CACHE[pattern]
        else:
            # Convert pattern to regex
            # Handle /** (slash + double-star) as optional recursive match
            # Handle ** as recursive match
            # Handle /* as single non-empty segment match
            # Trailing-slash exact form matches with or without trailing slash
            regex_parts = []
            i = 0
            while i < len(pattern):
                if (
                    i + 2 < len(pattern)
                    and pattern[i] == "/"
                    and pattern[i + 1] == "*"
                    and pattern[i + 2] == "*"
                ):
                    # /** → optionally match / followed by anything (matches parent dir too)
                    regex_parts.append("(/.*)?")
                    i += 3
                elif i + 1 < len(pattern) and pattern[i] == "*" and pattern[i + 1] == "*":
                    # ** at start or mid-pattern → match anything
                    regex_parts.append(".*")
                    i += 2
                elif pattern[i] == "*":
                    # Terminal /* suffix → require non-empty segment ([^/]+)
                    # Other * → allow empty within segment ([^/]*)
                    if i == len(pattern) - 1 and i > 0 and pattern[i - 1] == "/":
                        regex_parts.append("[^/]+")
                    else:
                        regex_parts.append("[^/]*")
                    i += 1
                elif pattern[i] == "/" and i == len(pattern) - 1:
                    # Trailing slash in exact form → match with or without trailing slash
                    regex_parts.append("/?")
                    i += 1
                else:
                    regex_parts.append(re.escape(pattern[i]))
                    i += 1
            compiled = re.compile("^" + "".join(regex_parts) + "$")
            _SCOPE_PATTERN_CACHE[pattern] = compiled

    return bool(compiled.match(str(repo_root)))


def find_matching_scope(repo_root: Path, global_config: dict) -> str | None:
    """Find the most-specific scope pattern that matches repo_root.

    All matching patterns are collected; the one with the highest segment
    count and lowest wildcard_tier wins (exact match preferred over ``/*``
    preferred over ``/**``).  The sort key is ``(segment_count,
    -wildcard_tier)``.  On a tie, the pattern that appears first in dict
    insertion order wins.

    Args:
        repo_root: The repository root path to match
        global_config: The full global config dict with 'scopes' key

    Returns:
        The matching scope pattern string, or None if no match
    """
    scopes = global_config.get("scopes", {})
    best_pattern: str | None = None
    best_key: tuple[int, int] = (-1, -1)
    for pattern in scopes:
        if match_scope_pattern(repo_root, pattern):
            seg, tier = compute_scope_specificity(pattern)
            key = (seg, -tier)
            if key > best_key:
                best_key = key
                best_pattern = pattern
    return best_pattern


def find_all_matching_scopes(
    repo_root: Path, global_config: dict
) -> list[tuple[str, "BeesConfig"]]:
    """Find all scope patterns that match repo_root, sorted least-specific first.

    Iterates all scopes in global_config["scopes"], calls match_scope_pattern
    for each, collects all matches, and sorts by specificity ascending using
    compute_scope_specificity key (segment_count, -wildcard_tier).

    Args:
        repo_root: The repository root path to match
        global_config: The full global config dict with 'scopes' key

    Returns:
        List of (pattern_string, parsed_BeesConfig) tuples sorted
        least-specific first (ascending specificity).
    """
    scopes = global_config.get("scopes", {})
    matches: list[tuple[str, BeesConfig, tuple[int, int]]] = []
    for pattern, scope_data in scopes.items():
        if match_scope_pattern(repo_root, pattern):
            seg, tier = compute_scope_specificity(pattern)
            parsed = parse_scope_to_bees_config(scope_data)
            matches.append((pattern, parsed, (seg, -tier)))
    matches.sort(key=lambda m: m[2])
    return [(pattern, config) for pattern, config, _key in matches]


def resolve_owning_scope(
    normalized_hive_name: str, global_config: dict, repo_root: Path
) -> tuple[str, None] | tuple[None, dict]:
    """Resolve a hive to its single owning scope, or return an error dict.

    Wraps get_scope_key_for_hive with the standard 0/1/>1 guard pattern:
    - 0 matches  → (None, {hive_not_found error})
    - >1 matches → (None, {config_conflict error})
    - 1 match    → (scope_pattern, None)

    Returns:
        (scope_pattern, None) on success, or (None, error_dict) on failure.
    """
    try:
        scopes = get_scope_key_for_hive(normalized_hive_name, global_config, repo_root)
    except ValueError:
        return (None, {
            "status": "error",
            "error_type": "hive_not_found",
            "message": f"Hive '{normalized_hive_name}' does not exist in any scope visible to this repo.",
        })
    if len(scopes) > 1:
        return (None, {
            "status": "error",
            "error_type": "config_conflict",
            "message": (
                f"Hive '{normalized_hive_name}' exists in multiple overlapping scopes: "
                f"'{scopes[0]}' and '{scopes[1]}'. "
                f"Call abandon_hive to resolve the conflict."
            ),
        })
    return (scopes[0], None)


def get_scope_key_for_hive(normalized_hive_name: str, global_config: dict, repo_root: Path) -> list[str]:
    """Find all matching scope keys that define the given hive name.

    Filters scopes using match_scope_pattern(repo_root, scope_key) and
    returns all matching scope patterns that contain the hive.

    Args:
        normalized_hive_name: The normalized hive name to search for
        global_config: The full global config dict with 'scopes' key
        repo_root: The repository root path to filter scopes by

    Returns:
        List of scope key strings that contain the hive and match repo_root

    Raises:
        ValueError: If the hive name is not found in any matching scope
    """
    scopes = global_config.get("scopes", {})
    result: list[str] = []
    for scope_key, scope_data in scopes.items():
        if not match_scope_pattern(repo_root, scope_key):
            continue
        hives = scope_data.get("hives", {})
        if normalized_hive_name in hives:
            result.append(scope_key)
    if not result:
        raise ValueError(
            f"Hive '{normalized_hive_name}' not found in any scope in the global config."
        )
    return result


def detect_hive_conflicts(
    matching_scopes: list[tuple[str, "BeesConfig"]],
) -> list[ConflictRecord]:
    """Detect hive names that appear in more than one matching scope.

    Args:
        matching_scopes: Output of find_all_matching_scopes — list of
            (scope_pattern, BeesConfig) tuples.

    Returns:
        List of ConflictRecord for every unique (hive_name, scope_a, scope_b)
        pair. Empty list means no conflicts.
    """
    # Build mapping: hive_name → list of scope patterns it appears in
    hive_scopes: dict[str, list[str]] = {}
    for pattern, config in matching_scopes:
        for hive_name in config.hives:
            hive_scopes.setdefault(hive_name, []).append(pattern)

    conflicts: list[ConflictRecord] = []
    for hive_name, scopes in sorted(hive_scopes.items()):
        if len(scopes) < 2:
            continue
        # Emit a ConflictRecord for each unique pair
        for i in range(len(scopes)):
            for j in range(i + 1, len(scopes)):
                conflicts.append(
                    ConflictRecord(
                        normalized_hive_name=hive_name,
                        scope_a=scopes[i],
                        scope_b=scopes[j],
                    )
                )
    return conflicts


def check_for_config_conflicts(resolved_root: Path | None = None) -> dict | None:
    """Check whether the current repo has hive-name conflicts across scopes.

    Loads the global config, finds all matching scopes for the repo root,
    and runs detect_hive_conflicts.  Returns an error dict if conflicts
    exist, or None when the config is clean.

    Args:
        resolved_root: Pre-resolved repo root path.  Falls back to
            get_repo_root() when None.

    Returns:
        None if no conflicts; otherwise a dict with keys
        ``status``, ``error_type``, and ``message``.
    """
    if resolved_root is None:
        resolved_root = get_repo_root()
    global_config = load_global_config()
    matching = find_all_matching_scopes(resolved_root, global_config)
    conflicts = detect_hive_conflicts(matching)
    if not conflicts:
        return None
    lines = []
    for c in conflicts:
        lines.append(f"  - hive '{c.normalized_hive_name}' in '{c.scope_a}' and '{c.scope_b}'")
    return {
        "status": "error",
        "error_type": "config_conflict",
        "message": "Config conflict detected — the same hive name appears in multiple scopes:\n"
        + "\n".join(lines)
        + "\nCall abandon_hive to resolve the conflict.",
    }


def _bare_prefix(canonical: str) -> str:
    """Return the bare prefix of an already-canonicalized scope pattern.

    Strips the wildcard suffix and any trailing slash:
        ``/foo/``   → ``/foo``
        ``/foo/*``  → ``/foo``
        ``/foo/**`` → ``/foo``
    """
    if canonical.endswith("/**"):
        return canonical[:-3].rstrip("/")
    if canonical.endswith("/*"):
        return canonical[:-2].rstrip("/")
    return canonical.rstrip("/")


def check_scope_conflict(pattern: str, global_config: dict) -> str | None:
    """Check whether *pattern* conflicts with an existing scope key.

    A conflict exists when a different scope key has the same bare prefix
    string **and** the same wildcard tier as *pattern* (after canonicalization).
    In practice, this condition is equivalent to the canonical forms being
    identical, so this function always returns ``None`` — identical canonical
    forms are treated as valid re-use, not a conflict. The function is kept
    for API compatibility and to make the re-use check explicit.

    Args:
        pattern: Candidate scope pattern to check.
        global_config: The full global config dict with 'scopes' key.

    Returns:
        Always ``None`` — re-using an existing scope is valid, not an error.
    """
    canon_candidate = canonicalize_scope_pattern(pattern)

    scopes = global_config.get("scopes", {})
    for existing_key in scopes:
        canon_existing = canonicalize_scope_pattern(existing_key)

        # Exact canonical match → re-use, not a conflict
        if canon_existing == canon_candidate:
            return None

    return None


def load_global_config() -> dict:
    """Load the entire global config from ~/.bees/config.json.

    Uses mtime-based caching to avoid redundant disk reads when the
    config file has not changed.

    Returns:
        The global config dict. Returns empty scopes structure if file missing.
        Returns default structure on JSON errors with logged warning.
    """
    global _GLOBAL_CONFIG_CACHE, _GLOBAL_CONFIG_CACHE_MTIME

    with _TEST_CONFIG_LOCK:
        if _GLOBAL_CONFIG_OVERRIDE is not None:
            return _GLOBAL_CONFIG_OVERRIDE

    if _CONFIG_PATH_OVERRIDE is not None:
        config_path = Path(_CONFIG_PATH_OVERRIDE)
    else:
        config_path = get_global_config_path()
    default_struct = {"scopes": {}, "schema_version": GLOBAL_SCHEMA_VERSION}

    if not config_path.exists():
        _GLOBAL_CONFIG_CACHE = None
        _GLOBAL_CONFIG_CACHE_MTIME = None
        return default_struct

    try:
        current_mtime = config_path.stat().st_mtime
    except OSError:
        _GLOBAL_CONFIG_CACHE = None
        _GLOBAL_CONFIG_CACHE_MTIME = None
        return default_struct

    if _GLOBAL_CONFIG_CACHE is not None and _GLOBAL_CONFIG_CACHE_MTIME == current_mtime:
        return _GLOBAL_CONFIG_CACHE

    try:
        with open(config_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"Malformed JSON in {config_path}: {e}. Returning default structure.")
        return default_struct

    # Ensure scopes key exists
    if "scopes" not in data:
        data["scopes"] = {}

    # Validate global-level egg_resolver if present
    if "egg_resolver" in data:
        egg_resolver = data["egg_resolver"]
        if egg_resolver is not None and not isinstance(egg_resolver, str):
            raise ValueError(f"Global egg_resolver must be a string or null, got {type(egg_resolver)}")

    # Validate global-level egg_resolver_timeout if present
    if "egg_resolver_timeout" in data:
        egg_resolver_timeout = data["egg_resolver_timeout"]
        if egg_resolver_timeout is not None:
            if not isinstance(egg_resolver_timeout, (int, float)):
                raise ValueError(
                    f"Global egg_resolver_timeout must be a number or null, got {type(egg_resolver_timeout)}"
                )
            if egg_resolver_timeout <= 0:
                raise ValueError(f"Global egg_resolver_timeout must be positive, got {egg_resolver_timeout}")

    # Validate global-level child_tiers if present
    if "child_tiers" in data:
        child_tiers = data["child_tiers"]
        if child_tiers is not None:
            if not isinstance(child_tiers, dict):
                raise ValueError(f"Global child_tiers must be a dict or null, got {type(child_tiers)}")
            # Delegate to _parse_child_tiers_data for format validation
            _parse_child_tiers_data(child_tiers)

    # Validate global-level status_values if present
    if "status_values" in data:
        status_values = data["status_values"]
        if status_values is not None:
            _validate_status_values(status_values, "Global")

    # Validate global-level delete_with_dependencies if present
    if "delete_with_dependencies" in data:
        val = data["delete_with_dependencies"]
        if not isinstance(val, bool):
            raise ValueError(f"Global delete_with_dependencies must be a boolean, got {type(val)}")

    # Validate global-level auto_fix_dangling_refs if present
    if "auto_fix_dangling_refs" in data:
        val = data["auto_fix_dangling_refs"]
        if not isinstance(val, bool):
            raise ValueError(f"Global auto_fix_dangling_refs must be a boolean, got {type(val)}")

    # Validate global-level elevated_repos if present
    if "elevated_repos" in data:
        elevated_repos = data["elevated_repos"]
        if not isinstance(elevated_repos, list):
            raise ValueError(f"Global elevated_repos must be a list, got {type(elevated_repos)}")
        for i, entry in enumerate(elevated_repos):
            if not isinstance(entry, dict):
                raise ValueError(f"elevated_repos[{i}] must be a dict, got {type(entry)}")
            if "path" not in entry:
                raise ValueError(f"elevated_repos[{i}] missing required 'path' key")
            if not isinstance(entry["path"], str):
                raise ValueError(
                    f"elevated_repos[{i}]['path'] must be a string, got {type(entry['path'])}"
                )
            if not os.path.isabs(entry["path"]):
                raise ValueError(f"elevated_repos entry 'path' must be absolute, got: {entry['path']!r}")
            if "write" in entry and not isinstance(entry["write"], bool):
                raise ValueError(
                    f"elevated_repos[{i}]['write'] must be a boolean, got {type(entry['write'])}"
                )

    _GLOBAL_CONFIG_CACHE = data
    _GLOBAL_CONFIG_CACHE_MTIME = current_mtime
    return data


def save_global_config(global_config: dict) -> None:
    """Atomically write the entire global config to ~/.bees/config.json.

    Uses temp file + os.replace pattern for crash safety.

    Args:
        global_config: The full global config dict to write
    """
    global _GLOBAL_CONFIG_CACHE, _GLOBAL_CONFIG_CACHE_MTIME

    if "schema_version" not in global_config:
        global_config["schema_version"] = GLOBAL_SCHEMA_VERSION

    with _TEST_CONFIG_LOCK:
        if _GLOBAL_CONFIG_OVERRIDE is not None:
            if global_config is not _GLOBAL_CONFIG_OVERRIDE:
                _GLOBAL_CONFIG_OVERRIDE.clear()
                _GLOBAL_CONFIG_OVERRIDE.update(global_config)
            return

    if _CONFIG_PATH_OVERRIDE is not None:
        config_path = Path(_CONFIG_PATH_OVERRIDE)
        bees_dir = config_path.parent
    else:
        ensure_global_bees_dir()
        config_path = get_global_config_path()
        bees_dir = config_path.parent
    temp_fd = None
    temp_path = None

    try:
        temp_fd, temp_path = tempfile.mkstemp(dir=str(bees_dir), prefix=".config.json.", text=True)

        with os.fdopen(temp_fd, "w") as f:
            temp_fd = None
            json.dump(global_config, f, indent=2)
            f.write("\n")

        os.replace(temp_path, config_path)
        temp_path = None

        _GLOBAL_CONFIG_CACHE = None
        _GLOBAL_CONFIG_CACHE_MTIME = None

    except Exception as e:
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except Exception:
                pass
        if temp_path is not None and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise OSError(f"Failed to write global config to {config_path}: {e}") from e


def _parse_child_tiers_data(child_tiers_data: dict) -> dict[str, ChildTierConfig]:
    """Parse child_tiers from raw dict into ChildTierConfig objects."""
    if not isinstance(child_tiers_data, dict):
        raise ValueError(f"child_tiers must be a dict, got {type(child_tiers_data)}")

    child_tiers = {}
    for tier_key, tier_value in child_tiers_data.items():
        if isinstance(tier_value, list):
            if len(tier_value) == 0:
                child_tiers[tier_key] = ChildTierConfig(None, None)
            elif len(tier_value) == 2:
                child_tiers[tier_key] = ChildTierConfig(singular=tier_value[0], plural=tier_value[1])
            else:
                raise ValueError(
                    f"child_tiers['{tier_key}'] must be array of length 0 or 2, got length {len(tier_value)}"
                )
        else:
            raise ValueError(f"child_tiers['{tier_key}'] must be an array, got {type(tier_value)}")

    validate_child_tiers(child_tiers)
    return child_tiers


def _validate_status_values(values: Any, context_label: str) -> None:
    """Validate that status_values is a list of non-empty strings."""
    if not isinstance(values, list):
        raise ValueError(f"{context_label} status_values must be a list or null, got {type(values)}")
    for value in values:
        if not isinstance(value, str):
            raise ValueError(
                f"{context_label} status_values must be a list of strings, got element of type {type(value)}"
            )
        if not value.strip():
            raise ValueError(f"{context_label} status_values must not contain empty strings")


def _parse_hives_data(hives_data: dict) -> dict[str, HiveConfig]:
    """Parse hives from raw dict into HiveConfig objects."""
    hives = {}
    for name, hive_data in hives_data.items():
        if not isinstance(hive_data, dict):
            raise ValueError(f"Hive '{name}' data must be a dict, got {type(hive_data)}")

        # Validate egg_resolver if present
        egg_resolver = hive_data.get("egg_resolver")
        if egg_resolver is not None and not isinstance(egg_resolver, str):
            raise ValueError(f"Hive '{name}' egg_resolver must be a string or null, got {type(egg_resolver)}")

        # Validate egg_resolver_timeout if present
        egg_resolver_timeout = hive_data.get("egg_resolver_timeout")
        if egg_resolver_timeout is not None:
            if not isinstance(egg_resolver_timeout, (int, float)):
                raise ValueError(
                    f"Hive '{name}' egg_resolver_timeout must be a number or null, got {type(egg_resolver_timeout)}"
                )
            if egg_resolver_timeout <= 0:
                raise ValueError(f"Hive '{name}' egg_resolver_timeout must be positive, got {egg_resolver_timeout}")

        # Parse and validate child_tiers if present
        # None/null means absent (fall through to scope/global)
        # {} means bees-only (stops the chain)
        child_tiers = None
        if "child_tiers" in hive_data and hive_data["child_tiers"] is not None:
            child_tiers = _parse_child_tiers_data(hive_data["child_tiers"])
            validate_child_tiers(child_tiers)

        # Parse and validate status_values if present.
        # Distinguish absent key (fall through to scope) from explicit null (no constraints).
        status_values = None
        status_values_explicitly_null = False
        if "status_values" in hive_data:
            if hive_data["status_values"] is None:
                status_values_explicitly_null = True
            else:
                status_values = hive_data["status_values"]
                _validate_status_values(status_values, f"Hive '{name}'")

        # Parse undertaker_schedule sub-dict if present
        ut_sched_seconds = None
        ut_sched_query_yaml = None
        ut_sched_query_name = None
        ut_sched_log_path = None
        ut_sched = hive_data.get("undertaker_schedule")
        if ut_sched is not None:
            if not isinstance(ut_sched, dict):
                raise ValueError(
                    f"Hive '{name}' undertaker_schedule must be a dict or null, got {type(ut_sched)}"
                )
            ut_sched_seconds = ut_sched.get("interval_seconds")
            if ut_sched_seconds is not None:
                if not isinstance(ut_sched_seconds, int) or ut_sched_seconds <= 0:
                    raise ValueError(
                        f"Hive '{name}' undertaker_schedule.interval_seconds must be a positive integer, "
                        f"got {ut_sched_seconds!r}"
                    )
            ut_sched_query_yaml = ut_sched.get("query_yaml")
            if ut_sched_query_yaml is not None and not isinstance(ut_sched_query_yaml, str):
                raise ValueError(
                    f"Hive '{name}' undertaker_schedule.query_yaml must be a string or null, "
                    f"got {type(ut_sched_query_yaml)}"
                )
            ut_sched_query_name = ut_sched.get("query_name")
            if ut_sched_query_name is not None and not isinstance(ut_sched_query_name, str):
                raise ValueError(
                    f"Hive '{name}' undertaker_schedule.query_name must be a string or null, "
                    f"got {type(ut_sched_query_name)}"
                )
            ut_sched_log_path = ut_sched.get("log_path")
            if ut_sched_log_path is not None and not isinstance(ut_sched_log_path, str):
                raise ValueError(
                    f"Hive '{name}' undertaker_schedule.log_path must be a string or null, "
                    f"got {type(ut_sched_log_path)}"
                )

        hives[name] = HiveConfig(
            path=hive_data.get("path", ""),
            display_name=hive_data.get("display_name", ""),
            created_at=hive_data.get("created_at", ""),
            egg_resolver=egg_resolver,
            egg_resolver_timeout=egg_resolver_timeout,
            child_tiers=child_tiers,
            status_values=status_values,
            status_values_explicitly_null=status_values_explicitly_null,
            undertaker_schedule_seconds=ut_sched_seconds,
            undertaker_schedule_query_yaml=ut_sched_query_yaml,
            undertaker_schedule_query_name=ut_sched_query_name,
            undertaker_schedule_log_path=ut_sched_log_path,
        )
    return hives


def parse_scope_to_bees_config(scope_data: dict) -> BeesConfig:
    """Parse a single scope's dict into a BeesConfig object.

    Args:
        scope_data: Dict with hives, child_tiers, etc.

    Returns:
        BeesConfig parsed from the scope data
    """
    schema_version = scope_data.get("schema_version", GLOBAL_SCHEMA_VERSION)
    if not isinstance(schema_version, str):
        raise ValueError(f"schema_version must be a string, got {type(schema_version)}")

    hives = _parse_hives_data(scope_data.get("hives", {}))

    if "child_tiers" not in scope_data:
        child_tiers = None
    else:
        child_tiers = _parse_child_tiers_data(scope_data["child_tiers"])

    # Validate and parse scope-level egg_resolver
    egg_resolver = scope_data.get("egg_resolver")
    if egg_resolver is not None and not isinstance(egg_resolver, str):
        raise ValueError(f"Scope egg_resolver must be a string or null, got {type(egg_resolver)}")

    # Validate and parse scope-level egg_resolver_timeout
    egg_resolver_timeout = scope_data.get("egg_resolver_timeout")
    if egg_resolver_timeout is not None:
        if not isinstance(egg_resolver_timeout, (int, float)):
            raise ValueError(f"Scope egg_resolver_timeout must be a number or null, got {type(egg_resolver_timeout)}")
        if egg_resolver_timeout <= 0:
            raise ValueError(f"Scope egg_resolver_timeout must be positive, got {egg_resolver_timeout}")

    # Validate and parse scope-level status_values
    status_values = scope_data.get("status_values")
    if status_values is not None:
        _validate_status_values(status_values, "Scope")

    return BeesConfig(
        hives=hives,
        schema_version=schema_version,
        child_tiers=child_tiers,
        egg_resolver=egg_resolver,
        egg_resolver_timeout=egg_resolver_timeout,
        status_values=status_values,
    )


def _serialize_child_tiers(child_tiers: dict[str, ChildTierConfig]) -> dict:
    """Serialize a child_tiers dict to JSON-compatible format."""
    return {
        tier_key: [] if (tc.singular is None and tc.plural is None) else [tc.singular, tc.plural]
        for tier_key, tc in child_tiers.items()
    }


def serialize_bees_config_to_scope(config: BeesConfig) -> dict:
    """Serialize a BeesConfig into a scope dict for storage in the global config.

    Args:
        config: BeesConfig object to serialize

    Returns:
        Dict suitable for storing as a scope value in the global config
    """
    hives_dict = {}
    for name, hive_config in config.hives.items():
        hive_entry = {
            "path": hive_config.path,
            "display_name": hive_config.display_name,
            "created_at": hive_config.created_at,
        }
        # Only include egg_resolver fields if they are not None
        if hive_config.egg_resolver is not None:
            hive_entry["egg_resolver"] = hive_config.egg_resolver
        if hive_config.egg_resolver_timeout is not None:
            hive_entry["egg_resolver_timeout"] = hive_config.egg_resolver_timeout
        # Only include child_tiers if not None
        if hive_config.child_tiers is not None:
            hive_entry["child_tiers"] = _serialize_child_tiers(hive_config.child_tiers)
        # Preserve explicit null (unset overrides scope inheritance) vs absent (fall through)
        if hive_config.status_values_explicitly_null:
            hive_entry["status_values"] = None
        elif hive_config.status_values is not None:
            hive_entry["status_values"] = hive_config.status_values
        # Only include undertaker_schedule if any field is non-None
        ut_sched = {}
        if hive_config.undertaker_schedule_seconds is not None:
            ut_sched["interval_seconds"] = hive_config.undertaker_schedule_seconds
        if hive_config.undertaker_schedule_query_yaml is not None:
            ut_sched["query_yaml"] = hive_config.undertaker_schedule_query_yaml
        if hive_config.undertaker_schedule_query_name is not None:
            ut_sched["query_name"] = hive_config.undertaker_schedule_query_name
        if hive_config.undertaker_schedule_log_path is not None:
            ut_sched["log_path"] = hive_config.undertaker_schedule_log_path
        if ut_sched:
            hive_entry["undertaker_schedule"] = ut_sched
        hives_dict[name] = hive_entry

    scope_dict = {
        "hives": hives_dict,
    }

    # Only include scope-level child_tiers if not None
    if config.child_tiers is not None:
        scope_dict["child_tiers"] = _serialize_child_tiers(config.child_tiers)

    # Only include scope-level egg_resolver fields if they are not None
    if config.egg_resolver is not None:
        scope_dict["egg_resolver"] = config.egg_resolver
    if config.egg_resolver_timeout is not None:
        scope_dict["egg_resolver_timeout"] = config.egg_resolver_timeout

    # Only include scope-level status_values if not None
    if config.status_values is not None:
        scope_dict["status_values"] = config.status_values

    return scope_dict


def get_scoped_config(repo_root: Path) -> BeesConfig | None:
    """Load global config, find all matching scopes for repo_root, return merged BeesConfig.

    Merges hives from all matching scopes (least-specific to most-specific), so hives
    defined in parent scopes (e.g. /Users/foo/**) are visible alongside hives in more
    specific scopes (e.g. /Users/foo/projects/myrepo/**).  More-specific scopes win on
    hive name conflicts.  Non-hive settings (child_tiers, egg_resolver, etc.) come from
    the most-specific scope.

    Args:
        repo_root: The repository root to match against scope patterns

    Returns:
        BeesConfig with merged hives from all matching scopes, or None if no scope matches
    """
    global_config = load_global_config()
    scope_configs = find_all_matching_scopes(repo_root, global_config)
    if not scope_configs:
        return None

    # Use most-specific scope as the base config (non-hive settings)
    _, base_config = scope_configs[-1]

    # Merge hives from least-specific to most-specific (most-specific wins conflicts)
    merged_hives: dict[str, HiveConfig] = {}
    for _, config in scope_configs:
        merged_hives.update(config.hives)

    base_config.hives = merged_hives
    return base_config


def load_bees_config() -> BeesConfig | None:
    """Load BeesConfig for the current repo_root from the global scoped config.

    Gets repo_root from context, finds matching scope in ~/.bees/config.json,
    and returns the parsed BeesConfig.

    Returns:
        BeesConfig for the matching scope, or None if no match.

    Raises:
        RuntimeError: If repo_root not set in context
    """
    repo_root = get_repo_root()
    return get_scoped_config(repo_root)


def save_bees_config(config: BeesConfig, scope_pattern: str) -> None:
    """Save BeesConfig to the specified scope in ~/.bees/config.json.

    Writes directly to the given scope_pattern key in global config.
    Uses atomic write for crash safety.

    Args:
        config: BeesConfig object to save
        scope_pattern: The scope pattern key to write to (must already exist
            in global config scopes)

    Raises:
        ValueError: If scope_pattern is not in global config scopes
        OSError: If writing fails
    """
    global_config = load_global_config()

    if scope_pattern not in global_config.get("scopes", {}):
        raise ValueError(
            f"Scope pattern '{scope_pattern}' not found in global config. "
            "Use colonize_hive to create a scope entry first."
        )

    global_config["scopes"][scope_pattern] = serialize_bees_config_to_scope(config)
    save_global_config(global_config)


def check_queen_elevation(resolved_root: Path, global_config: dict) -> tuple[bool, bool]:
    """Check whether resolved_root is listed as a queen (elevated) repo.

    Args:
        resolved_root: Absolute path to the repo root to check.
        global_config: The loaded global config dict.

    Returns:
        (is_queen, has_write): is_queen is True if resolved_root matches an
        elevated_repos entry whose path exists on disk. has_write is True only
        if the matching entry has "write": true. If is_queen is False,
        has_write is always False.
    """
    elevated_repos = global_config.get("elevated_repos", [])
    resolved = resolved_root.resolve()
    for entry in elevated_repos:
        entry_path = Path(entry["path"])
        if not entry_path.exists():
            logger.warning("elevated_repos path does not exist, skipping: %s", entry_path)
            continue
        if entry_path.resolve() == resolved:
            return True, bool(entry.get("write", False))
    return False, False


def get_all_scopes_config(global_config: dict) -> dict[str, BeesConfig]:
    """Return a BeesConfig for every scope in global_config, unfiltered.

    Args:
        global_config: The loaded global config dict.

    Returns:
        Mapping of scope_pattern → BeesConfig. Empty dict when no scopes.
    """
    result: dict[str, BeesConfig] = {}
    for pattern, scope_data in global_config.get("scopes", {}).items():
        result[pattern] = parse_scope_to_bees_config(scope_data)
    return result


def check_queen_write_access(resolved_root: Path, global_config: dict) -> dict | None:
    """Check whether a queen repo has write access.

    Non-queen repos always have write access (returns None).
    Queen repos with write=true also return None.
    Queen repos without write access return a permission_denied error dict.

    Args:
        resolved_root: Absolute path to the repo root to check.
        global_config: The loaded global config dict.

    Returns:
        None if write is allowed, or an error dict if permission is denied.
    """
    is_queen, has_write = check_queen_elevation(resolved_root, global_config)
    if not is_queen:
        return None
    if has_write:
        return None
    return {
        "status": "error",
        "error_type": "permission_denied",
        "message": f"Write access denied: '{resolved_root}' is a queen repo without write permission",
    }


def validate_child_tiers(child_tiers: dict[str, ChildTierConfig]) -> None:
    """Validate child_tiers configuration structure.

    Validation Rules:
    1. Keys must match pattern t[0-9]+ and be sequential starting at t1 (no gaps)
    2. Friendly names (if provided) must be non-empty strings
    3. Friendly names must be unique across all tiers
    4. Tier depth must not exceed T9 (tier numbers 1-9 only)

    Args:
        child_tiers: Dictionary of tier keys to ChildTierConfig objects

    Raises:
        ValueError: If validation fails with descriptive error message
    """
    # Empty dict is valid (bees-only system)
    if not child_tiers:
        return

    # Extract tier keys and validate format
    tier_pattern = re.compile(r"^t(\d+)$")
    tier_numbers = []

    for key in child_tiers.keys():
        match = tier_pattern.match(key)
        if not match:
            raise ValueError(f"Invalid child_tiers key '{key}': keys must match pattern 't[0-9]+' (e.g., 't1', 't2')")
        tier_num = int(match.group(1))
        if tier_num > 9:
            raise ValueError(f"Invalid child_tiers key '{key}': tier depth exceeds T9 maximum")
        tier_numbers.append(tier_num)

    # Check T9 maximum depth
    _MAX_TIER = 9
    for num in tier_numbers:
        if num > _MAX_TIER:
            raise ValueError(
                f"Child tier t{num} exceeds maximum supported depth of T{_MAX_TIER}. "
                f"Tiers must be t1 through t{_MAX_TIER}."
            )

    # Check sequential ordering starting at 1
    tier_numbers.sort()
    expected = list(range(1, len(tier_numbers) + 1))

    if tier_numbers != expected:
        if tier_numbers[0] != 1:
            raise ValueError(f"Invalid child_tiers: tier keys must start at 't1', found: {sorted(child_tiers.keys())}")
        # Find the gap
        for _, (actual, exp) in enumerate(zip(tier_numbers, expected, strict=False)):
            if actual != exp:
                raise ValueError(
                    f"Invalid child_tiers: tier keys must be sequential with no gaps. "
                    f"Expected 't{exp}' but found 't{actual}'. Keys: {sorted(child_tiers.keys())}"
                )

    # Validate friendly names are non-empty strings if provided
    seen_names = set()

    for key, tier_config in child_tiers.items():
        # Both singular and plural must be set or both must be None
        if (tier_config.singular is None) != (tier_config.plural is None):
            raise ValueError(
                f"Invalid child_tiers['{key}']: singular and plural must both be set or both be None. "
                f"Got singular={tier_config.singular}, plural={tier_config.plural}"
            )

        # If friendly names provided, validate they're non-empty
        if tier_config.singular is not None:
            if not isinstance(tier_config.singular, str) or not tier_config.singular.strip():
                raise ValueError(
                    f"Invalid child_tiers['{key}']: singular must be a non-empty string, got: {tier_config.singular}"
                )
            if not isinstance(tier_config.plural, str) or not tier_config.plural.strip():
                raise ValueError(
                    f"Invalid child_tiers['{key}']: plural must be a non-empty string, got: {tier_config.plural}"
                )

            # Check uniqueness (case-sensitive)
            if tier_config.singular in seen_names:
                raise ValueError(
                    f"Invalid child_tiers: duplicate friendly name '{tier_config.singular}' found in tier '{key}'"
                )
            if tier_config.plural in seen_names:
                raise ValueError(
                    f"Invalid child_tiers: duplicate friendly name '{tier_config.plural}' found in tier '{key}'"
                )

            seen_names.add(tier_config.singular)
            seen_names.add(tier_config.plural)


def resolve_egg_resolver(normalized_hive: str, config: BeesConfig | None = None) -> str | None:
    """Resolve egg_resolver for a given hive using 3-level fallback.

    Resolution order:
    1. Hive level: Check the hive's egg_resolver
    2. Scope level: Check the scope's (BeesConfig) egg_resolver
    3. Global level: Check the global config's egg_resolver
    4. Default: Return None

    If any level has the special value "default", stop the fallback chain
    and treat it as None (use the system default).

    Args:
        normalized_hive: The normalized hive name to resolve for
        config: BeesConfig object (loads from disk if None)

    Returns:
        The resolved egg_resolver string, or None if not configured

    Raises:
        ValueError: If hive doesn't exist
        RuntimeError: If repo_root not set in context
    """
    get_repo_root()

    if config is None:
        config = load_bees_config()

    if config is None:
        return None

    # Check if hive exists
    if normalized_hive not in config.hives:
        raise ValueError(f"Hive '{normalized_hive}' does not exist")

    # Level 1: Check hive-level egg_resolver
    hive_config = config.hives[normalized_hive]
    if hive_config.egg_resolver is not None:
        if hive_config.egg_resolver == "default":
            return None
        return hive_config.egg_resolver

    # Level 2: Check scope-level egg_resolver
    if config.egg_resolver is not None:
        if config.egg_resolver == "default":
            return None
        return config.egg_resolver

    # Level 3: Check global-level egg_resolver
    global_config = load_global_config()
    global_egg_resolver = global_config.get("egg_resolver")
    if global_egg_resolver is not None:
        if global_egg_resolver == "default":
            return None
        return global_egg_resolver

    # Level 4: No configuration found
    return None


def resolve_egg_resolver_timeout(normalized_hive: str, config: BeesConfig | None = None) -> int | float | None:
    """Resolve egg_resolver_timeout for a given hive using 3-level fallback.

    Resolution order:
    1. Hive level: Check the hive's egg_resolver_timeout
    2. Scope level: Check the scope's (BeesConfig) egg_resolver_timeout
    3. Global level: Check the global config's egg_resolver_timeout
    4. Default: Return None

    Args:
        normalized_hive: The normalized hive name to resolve for
        config: BeesConfig object (loads from disk if None)

    Returns:
        The resolved egg_resolver_timeout value, or None if not configured

    Raises:
        ValueError: If hive doesn't exist
        RuntimeError: If repo_root not set in context
    """
    get_repo_root()

    if config is None:
        config = load_bees_config()

    if config is None:
        return None

    # Check if hive exists
    if normalized_hive not in config.hives:
        raise ValueError(f"Hive '{normalized_hive}' does not exist")

    # Level 1: Check hive-level egg_resolver_timeout
    hive_config = config.hives[normalized_hive]
    if hive_config.egg_resolver_timeout is not None:
        return hive_config.egg_resolver_timeout

    # Level 2: Check scope-level egg_resolver_timeout
    if config.egg_resolver_timeout is not None:
        return config.egg_resolver_timeout

    # Level 3: Check global-level egg_resolver_timeout
    global_config = load_global_config()
    global_timeout = global_config.get("egg_resolver_timeout")
    if global_timeout is not None:
        return global_timeout

    # Level 4: No configuration found
    return None


def resolve_child_tiers_for_hive(normalized_hive: str, config: BeesConfig | None = None) -> dict[str, ChildTierConfig]:
    """Resolve child_tiers for a given hive using 4-level fallback.

    Resolution order:
    1. Hive level: Check the hive's child_tiers
    2. Scope level: Check the scope's (BeesConfig) child_tiers
    3. Global level: Check the global config's child_tiers
    4. Default: Return {} (bees-only)

    None at any level falls through to next level.
    {} at any level stops the chain (bees-only).
    No merging between levels.

    Args:
        normalized_hive: The normalized hive name to resolve for
        config: BeesConfig object (loads from disk if None)

    Returns:
        The resolved child_tiers dict, or {} if not configured

    Raises:
        ValueError: If hive doesn't exist
        RuntimeError: If repo_root not set in context
    """
    get_repo_root()

    if config is None:
        config = load_bees_config()

    if config is None:
        return {}

    # Check if hive exists
    if normalized_hive not in config.hives:
        raise ValueError(f"Hive '{normalized_hive}' does not exist")

    # Level 1: Check hive-level child_tiers
    hive_config = config.hives[normalized_hive]
    if hive_config.child_tiers is not None:
        return hive_config.child_tiers

    # Level 2: Check scope-level child_tiers
    if config.child_tiers is not None:
        return config.child_tiers

    # Level 3: Check global-level child_tiers
    global_config = load_global_config()
    global_child_tiers = global_config.get("child_tiers")
    if global_child_tiers is not None:
        return _parse_child_tiers_data(global_child_tiers)

    # Level 4: Default (bees-only)
    return {}


def resolve_status_values_for_hive(normalized_hive: str, config: BeesConfig | None = None) -> list[str] | None:
    """Resolve status_values for a given hive using 3-level fallback.

    Resolution order:
    1. Hive level: Check the hive's status_values
    2. Scope level: Check the scope's (BeesConfig) status_values
    3. Global level: Check the global config's status_values
    4. Default: Return None (freeform, any string accepted)

    None or empty list [] at any level falls through to next level.
    Non-empty list at any level stops the chain.
    No merging between levels.

    Args:
        normalized_hive: The normalized hive name to resolve for
        config: BeesConfig object (loads from disk if None)

    Returns:
        The resolved status_values list, or None if not configured

    Raises:
        ValueError: If hive doesn't exist
        RuntimeError: If repo_root not set in context
    """
    get_repo_root()

    if config is None:
        config = load_bees_config()

    if config is None:
        return None

    # Check if hive exists
    if normalized_hive not in config.hives:
        raise ValueError(f"Hive '{normalized_hive}' does not exist")

    # Level 1: Check hive-level status_values
    hive_config = config.hives[normalized_hive]
    if hive_config.status_values_explicitly_null:
        # Explicitly unset — override scope/global inheritance, no constraints
        return None
    if hive_config.status_values is not None and len(hive_config.status_values) > 0:
        return hive_config.status_values

    # Level 2: Check scope-level status_values
    if config.status_values is not None and len(config.status_values) > 0:
        return config.status_values

    # Level 3: Check global-level status_values
    global_config = load_global_config()
    global_status_values = global_config.get("status_values")
    if global_status_values is not None and len(global_status_values) > 0:
        return global_status_values

    # Level 4: Default (freeform)
    return None


def get_mermaid_charts_enabled() -> bool:
    """Check if mermaid chart generation is enabled in global config.

    Reads the top-level ``mermaid_charts`` key from ``~/.bees/config.json``.
    Defaults to ``False`` when the key is absent.

    Returns:
        True if mermaid charts should be generated, False otherwise.
    """
    global_config = load_global_config()
    return bool(global_config.get("mermaid_charts", False))


def resolve_named_query(name: str, repo_root: Path, global_config: dict) -> dict:
    """Resolve a named query by searching repo scope, then global, then out-of-scope.

    Resolution order:
    1. Caller's matched repo scope `queries` dict
    2. Top-level `queries` dict (global)
    3. All other scope entries (out-of-scope detection)

    Args:
        name: The query name to resolve
        repo_root: The repository root path for scope matching
        global_config: The full global config dict

    Returns:
        One of:
        - {"status": "found", "stages": [...], "scope": "repo"} if found in caller's repo scope
        - {"status": "found", "stages": [...], "scope": "global"} if found at global level
        - {"status": "out_of_scope"} if found only in another repo's scope
        - {"status": "not_found"} if not found anywhere
    """
    matched_pattern = find_matching_scope(repo_root, global_config)

    # Check caller's repo scope queries
    if matched_pattern is not None:
        scope_data = global_config.get("scopes", {}).get(matched_pattern, {})
        repo_queries = scope_data.get("queries", {})
        if name in repo_queries:
            return {"status": "found", "stages": repo_queries[name], "scope": "repo"}

    # Check top-level global queries
    global_queries = global_config.get("queries", {})
    if name in global_queries:
        return {"status": "found", "stages": global_queries[name], "scope": "global"}

    # Scan all other scope entries for out-of-scope detection
    scopes = global_config.get("scopes", {})
    for pattern, scope_data in scopes.items():
        if pattern == matched_pattern:
            continue
        other_queries = scope_data.get("queries", {})
        if name in other_queries:
            return {"status": "out_of_scope"}

    return {"status": "not_found"}


def check_query_name_conflict(
    name: str, scope: str, repo_root: Path, global_config: dict
) -> dict | None:
    """Check if a query name conflicts with an existing query.

    For scope="repo": checks caller's matched repo scope and the top-level
    global queries. Other repo scopes are invisible (mutually inaccessible).

    For scope="global": checks top-level global queries and every scope entry
    in the entire config.

    Args:
        name: The query name to check
        scope: Where the query would be saved ("repo" or "global")
        repo_root: The repository root path for scope matching
        global_config: The full global config dict

    Returns:
        None if no conflict.
        {"level": "repo"|"global", "location": str} if conflict found.
    """
    matched_pattern = find_matching_scope(repo_root, global_config)
    scopes = global_config.get("scopes", {})
    global_queries = global_config.get("queries", {})

    if scope == "repo":
        # Check caller's own repo scope
        if matched_pattern is not None:
            scope_data = scopes.get(matched_pattern, {})
            repo_queries = scope_data.get("queries", {})
            if name in repo_queries:
                return {"level": "repo", "location": matched_pattern}

        # Check top-level global queries
        if name in global_queries:
            return {"level": "global", "location": "global"}

        return None

    if scope == "global":
        # Check top-level global queries
        if name in global_queries:
            return {"level": "global", "location": "global"}

        # Check every scope entry in config
        for pattern, scope_data in scopes.items():
            scope_queries = scope_data.get("queries", {})
            if name in scope_queries:
                return {"level": "repo", "location": pattern}

        return None

    return None
