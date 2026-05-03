"""Migration: egg_resolver config keys and egg ticket fields → reference_materials,
and rename built-in resolver "default" → "file-path".

Upgrades the global config from schema version 2.0 to 3.0.

Phase 1 — Collision check:
    Scan every level of the config for egg_resolver keys and assert that no
    two different script paths share the same filename stem (which becomes the
    resolver name).  Raises ValueError before any mutations if a collision is
    detected.

Phase 2 — Config migration:
    For each unique egg_resolver path, extract the RESOLVER CONVENTION from
    the script docstring, read the associated timeout, and write an entry into
    config["resolvers"].  Existing resolvers are not overwritten.  All
    egg_resolver / egg_resolver_timeout keys are removed.

    Additionally, if config["resolvers"] contains an entry named "default" and
    "file-path" does not already exist, rename "default" to "file-path".

Phase 3 — allowed_resolvers migration:
    Walk every hive in every scope.  For each allowed_resolvers list that
    contains "default", replace it with "file-path" (unless "file-path" is
    already present in the list).

Phase 4 — Ticket migration:
    Walk every hive path found in the config scopes.  For each .md file whose
    YAML frontmatter contains an ``egg`` key, convert it to
    ``reference_materials`` (a list with a single {"value": ...} entry, or
    null when the egg value was null).  If the hive previously had an
    egg_resolver, the resolver name is added to each entry as "resolver".
    Files that already use reference_materials and have no egg key are
    skipped.

    Additionally, for each .md file whose reference_materials list contains an
    entry with ``resolver: default``, rename it to ``resolver: file-path``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _name_from_path(script_path: str) -> str:
    """Derive resolver name from script filename (stem without .py extension)."""
    return Path(script_path).stem


def _get_timeout(level_data: dict) -> int | float | None:
    """Extract egg_resolver_timeout from a config level dict, or None."""
    return level_data.get("egg_resolver_timeout")


def _collect_egg_resolvers(config: dict) -> dict[str, dict[str, Any]]:
    """Collect all egg_resolver entries across every config level.

    Returns a mapping of ``{script_path: {"timeout": ..., "name": ...,
    "hive_names": [...]}}`` where hive_names records every hive that
    references this resolver (used in Phase 3).

    Raises:
        ValueError: If two different paths share the same filename stem.
    """
    # name → path (for collision detection)
    name_to_path: dict[str, str] = {}
    # path → {timeout, name, hive_names}
    resolvers: dict[str, dict[str, Any]] = {}

    def _register(path: str, timeout: int | float | None, hive_name: str | None = None) -> None:
        name = _name_from_path(path)
        if name in name_to_path and name_to_path[name] != path:
            raise ValueError(
                f"egg_resolver collision: resolver name '{name}' would be derived from two "
                f"different script paths: '{name_to_path[name]}' and '{path}'. "
                "Rename one of the scripts so the filenames are unique before migrating."
            )
        name_to_path[name] = path
        if path not in resolvers:
            resolvers[path] = {"timeout": timeout, "name": name, "hive_names": []}
        else:
            # Use first non-None timeout found
            if resolvers[path]["timeout"] is None and timeout is not None:
                resolvers[path]["timeout"] = timeout
        if hive_name is not None:
            if hive_name not in resolvers[path]["hive_names"]:
                resolvers[path]["hive_names"].append(hive_name)

    # Global level
    global_path = config.get("egg_resolver")
    if global_path:
        _register(global_path, _get_timeout(config))

    for _scope_key, scope_data in config.get("scopes", {}).items():
        if not isinstance(scope_data, dict):
            continue

        # Scope level
        scope_path = scope_data.get("egg_resolver")
        if scope_path:
            _register(scope_path, _get_timeout(scope_data))

        # Hive level
        for hive_name, hive_data in scope_data.get("hives", {}).items():
            if not isinstance(hive_data, dict):
                continue
            hive_path = hive_data.get("egg_resolver")
            if hive_path:
                _register(hive_path, _get_timeout(hive_data), hive_name)

    return resolvers


def _remove_egg_keys(d: dict) -> None:
    """Remove egg_resolver and egg_resolver_timeout from a dict in place."""
    d.pop("egg_resolver", None)
    d.pop("egg_resolver_timeout", None)


def _parse_md_frontmatter(text: str) -> tuple[dict, str] | None:
    """Parse YAML frontmatter from a markdown file's text.

    Returns (frontmatter_dict, body_text) or None if no valid frontmatter.
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    yaml_text = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data, body


def _dump_frontmatter(data: dict, body: str) -> str:
    """Re-serialise frontmatter dict + body back to markdown text."""
    yaml_text = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_text}---\n{body}"


def _migrate_ticket_file(
    md_path: Path,
    resolver_name: str | None,
) -> bool:
    """Migrate a single ticket file: egg → reference_materials, default → file-path resolver.

    Performs two mutations if needed:
    1. Converts ``egg`` frontmatter key to ``reference_materials``.
    2. Renames ``resolver: default`` entries in ``reference_materials`` to
       ``resolver: file-path``.

    Returns True if the file was modified, False if skipped.
    """
    text = md_path.read_text(encoding="utf-8")
    parsed = _parse_md_frontmatter(text)
    if parsed is None:
        return False
    frontmatter, body = parsed

    modified = False

    # --- egg → reference_materials ---
    if "egg" in frontmatter:
        if "reference_materials" in frontmatter:
            # Both keys present — remove egg, leave reference_materials untouched
            del frontmatter["egg"]
        else:
            egg_value = frontmatter.pop("egg")
            if egg_value is None:
                frontmatter["reference_materials"] = None
            else:
                entry: dict[str, Any] = {"value": egg_value}
                if resolver_name is not None:
                    entry["resolver"] = resolver_name
                frontmatter["reference_materials"] = [entry]
        modified = True

    # --- resolver: default → resolver: file-path ---
    ref_mats = frontmatter.get("reference_materials")
    if isinstance(ref_mats, list):
        for entry in ref_mats:
            if isinstance(entry, dict) and entry.get("resolver") == "default":
                entry["resolver"] = "file-path"
                modified = True

    if modified:
        md_path.write_text(_dump_frontmatter(frontmatter, body), encoding="utf-8")

    return modified


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def upgrade(config: dict) -> None:
    """Upgrade the raw config dict from schema 2.0 to 3.0 in place.

    Idempotent: if no egg_resolver keys are found, no ticket egg fields exist,
    and no "default" resolver references remain, this function is a no-op.

    Args:
        config: The raw global config dict (mutated in place).

    Raises:
        ValueError: If two different egg_resolver scripts share a filename
            stem (name collision that would corrupt the resolver registry).
    """
    # ------------------------------------------------------------------
    # Phase 1: Collision check (read-only — no mutations yet)
    # ------------------------------------------------------------------
    resolvers = _collect_egg_resolvers(config)

    # Build hive_name → resolver_name mapping before we remove any keys
    # (used in Phase 4 to annotate ticket reference_materials entries).
    hive_to_resolver: dict[str, str] = {}
    for _path, info in resolvers.items():
        for hive_name in info["hive_names"]:
            hive_to_resolver[hive_name] = info["name"]

    # ------------------------------------------------------------------
    # Phase 2: Config migration
    # ------------------------------------------------------------------
    if resolvers:
        existing_resolvers: dict = config.setdefault("resolvers", {})

        for script_path, info in resolvers.items():
            name = info["name"]
            if name in existing_resolvers:
                # Don't overwrite an already-registered entry
                continue

            from src.mcp_resolver_ops import _extract_convention  # noqa: PLC0415

            convention = _extract_convention(script_path)
            entry: dict[str, Any] = {"path": script_path}
            if info["timeout"] is not None:
                entry["timeout"] = info["timeout"]
            if convention is not None:
                entry["convention"] = convention
            existing_resolvers[name] = entry

        # Remove egg_resolver / egg_resolver_timeout from global level
        _remove_egg_keys(config)

        # Remove from every scope and hive
        for scope_data in config.get("scopes", {}).values():
            if not isinstance(scope_data, dict):
                continue
            _remove_egg_keys(scope_data)
            for hive_data in scope_data.get("hives", {}).values():
                if isinstance(hive_data, dict):
                    _remove_egg_keys(hive_data)

    # Rename "default" → "file-path" in resolver registry
    registry = config.get("resolvers")
    if isinstance(registry, dict) and "default" in registry:
        if "file-path" not in registry:
            registry["file-path"] = registry["default"]
        del registry["default"]

    # ------------------------------------------------------------------
    # Phase 3: allowed_resolvers migration
    # ------------------------------------------------------------------
    for scope_data in config.get("scopes", {}).values():
        if not isinstance(scope_data, dict):
            continue
        for hive_data in scope_data.get("hives", {}).values():
            if not isinstance(hive_data, dict):
                continue
            allowed = hive_data.get("allowed_resolvers")
            if not isinstance(allowed, list) or "default" not in allowed:
                continue
            new_allowed: list[str] = []
            seen: set[str] = set()
            for item in allowed:
                effective = "file-path" if item == "default" else item
                if effective not in seen:
                    new_allowed.append(effective)
                    seen.add(effective)
            hive_data["allowed_resolvers"] = new_allowed

    # ------------------------------------------------------------------
    # Phase 4: Ticket migration
    # ------------------------------------------------------------------
    for scope_data in config.get("scopes", {}).values():
        if not isinstance(scope_data, dict):
            continue
        for hive_name, hive_data in scope_data.get("hives", {}).items():
            if not isinstance(hive_data, dict):
                continue
            hive_path_str = hive_data.get("path")
            if not hive_path_str:
                continue
            hive_dir = Path(hive_path_str)
            if not hive_dir.is_dir():
                continue

            resolver_name = hive_to_resolver.get(hive_name)

            for md_file in hive_dir.rglob("*.md"):
                _migrate_ticket_file(md_file, resolver_name)
