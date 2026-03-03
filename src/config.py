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


# Constants
BEES_CONFIG_DIR = ".bees"
BEES_CONFIG_FILENAME = "config.json"
GLOBAL_SCHEMA_VERSION = "2.0"

# Regex for converting scope patterns to regex
_SCOPE_PATTERN_CACHE: dict[str, re.Pattern] = {}
_CACHE_LOCK = threading.Lock()


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
        Exact paths match exactly.

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
            # Handle * as single-segment match
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
                    regex_parts.append("[^/]*")
                    i += 1
                else:
                    regex_parts.append(re.escape(pattern[i]))
                    i += 1
            compiled = re.compile("^" + "".join(regex_parts) + "$")
            _SCOPE_PATTERN_CACHE[pattern] = compiled

    return bool(compiled.match(str(repo_root)))


def find_matching_scope(repo_root: Path, global_config: dict) -> str | None:
    """Find the first scope pattern that matches repo_root.

    Scopes are evaluated in declaration order (dict insertion order).
    First match wins.

    Args:
        repo_root: The repository root path to match
        global_config: The full global config dict with 'scopes' key

    Returns:
        The matching scope pattern string, or None if no match
    """
    scopes = global_config.get("scopes", {})
    for pattern in scopes:
        if match_scope_pattern(repo_root, pattern):
            return pattern
    return None


def get_scope_key_for_hive(normalized_hive_name: str, global_config: dict) -> str:
    """Find the scope key whose hives dict contains the given hive name.

    Scopes are evaluated in declaration order (dict insertion order).
    First match wins.

    Args:
        normalized_hive_name: The normalized hive name to search for
        global_config: The full global config dict with 'scopes' key

    Returns:
        The scope key string that contains the hive

    Raises:
        ValueError: If the hive name is not found in any scope
    """
    scopes = global_config.get("scopes", {})
    for scope_key, scope_data in scopes.items():
        hives = scope_data.get("hives", {})
        if normalized_hive_name in hives:
            return scope_key
    raise ValueError(
        f"Hive '{normalized_hive_name}' not found in any scope in the global config."
    )


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
    """Load global config, find matching scope for repo_root, return its BeesConfig.

    Args:
        repo_root: The repository root to match against scope patterns

    Returns:
        BeesConfig for the matching scope, or None if no scope matches
    """
    global_config = load_global_config()
    pattern = find_matching_scope(repo_root, global_config)
    if pattern is None:
        return None
    return parse_scope_to_bees_config(global_config["scopes"][pattern])


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


def save_bees_config(config: BeesConfig) -> None:
    """Save BeesConfig to the matching scope in ~/.bees/config.json.

    Finds the scope matching the current repo_root and updates it.
    Uses atomic write for crash safety.

    Args:
        config: BeesConfig object to save

    Raises:
        ValueError: If no scope matches the current repo_root
        OSError: If writing fails
        RuntimeError: If repo_root not set in context
    """
    repo_root = get_repo_root()
    global_config = load_global_config()
    pattern = find_matching_scope(repo_root, global_config)

    if pattern is None:
        raise ValueError(
            f"No scope matches repo_root '{repo_root}' in global config. "
            "Use colonize_hive to create a scope entry first."
        )

    global_config["scopes"][pattern] = serialize_bees_config_to_scope(config)
    save_global_config(global_config)


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


def validate_unique_hive_name(normalized_name: str, config: BeesConfig | None = None) -> None:
    """Validate that a normalized hive name is unique.

    Args:
        normalized_name: The normalized name to check (e.g., 'back_end')
        config: BeesConfig object to check against (loads from disk if None)

    Raises:
        ValueError: If the normalized name already exists in the hive registry
        RuntimeError: If repo_root not set in context
    """
    get_repo_root()
    if config is None:
        config = load_bees_config()

    # If no config exists yet, name is unique by default
    if config is None:
        return

    # Check if normalized name already exists as a hive key
    if normalized_name in config.hives:
        raise ValueError(
            f"A hive with normalized name '{normalized_name}' already exists. "
            f"Display name: '{config.hives[normalized_name].display_name}'"
        )


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
