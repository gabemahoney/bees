"""Migration: rename built-in resolver "default" → "file-path".

Upgrades the global config from schema version 3.0 to 4.0.

Phase 1 — Config migration:
    If ``config["resolvers"]`` contains an entry named ``"default"`` and
    ``"file-path"`` does not already exist, rename ``"default"`` to
    ``"file-path"``.  Idempotent: if ``"file-path"`` already exists, the
    ``"default"`` entry is simply removed (no data loss — file-path wins).

Phase 2 — allowed_resolvers migration:
    Walk every hive in every scope.  For each ``allowed_resolvers`` list that
    contains ``"default"``, replace it with ``"file-path"`` (unless
    ``"file-path"`` is already present in the list).

Phase 3 — Ticket migration:
    Walk every hive path found in the config scopes.  For each .md file whose
    YAML frontmatter ``reference_materials`` list contains an entry with
    ``resolver: default``, rename it to ``resolver: file-path``.
"""

from __future__ import annotations

from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Internal helpers (shared with upgrade_v2_to_v3 pattern)
# ---------------------------------------------------------------------------


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


def _migrate_ticket_file(md_path: Path) -> bool:
    """Rename ``resolver: default`` → ``resolver: file-path`` in reference_materials.

    Returns True if the file was modified, False if skipped.
    """
    text = md_path.read_text(encoding="utf-8")
    parsed = _parse_md_frontmatter(text)
    if parsed is None:
        return False
    frontmatter, body = parsed

    ref_mats = frontmatter.get("reference_materials")
    if not isinstance(ref_mats, list):
        return False

    modified = False
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
    """Upgrade the raw config dict from schema 3.0 to 4.0 in place.

    Idempotent: if no ``"default"`` resolver or ``resolver: default`` ticket
    entries are found, this function is a no-op.

    Args:
        config: The raw global config dict (mutated in place).
    """
    # ------------------------------------------------------------------
    # Phase 1: Config resolver registry migration
    # ------------------------------------------------------------------
    resolvers = config.get("resolvers")
    if isinstance(resolvers, dict) and "default" in resolvers:
        if "file-path" not in resolvers:
            resolvers["file-path"] = resolvers["default"]
        del resolvers["default"]

    # ------------------------------------------------------------------
    # Phase 2: allowed_resolvers migration
    # ------------------------------------------------------------------
    for scope_data in config.get("scopes", {}).values():
        if not isinstance(scope_data, dict):
            continue
        for hive_data in scope_data.get("hives", {}).values():
            if not isinstance(hive_data, dict):
                continue
            allowed = hive_data.get("allowed_resolvers")
            if not isinstance(allowed, list):
                continue
            if "default" not in allowed:
                continue
            # Replace "default" with "file-path", deduplicating if "file-path" already present
            new_allowed: list[str] = []
            seen: set[str] = set()
            for item in allowed:
                effective = "file-path" if item == "default" else item
                if effective not in seen:
                    new_allowed.append(effective)
                    seen.add(effective)
            hive_data["allowed_resolvers"] = new_allowed

    # ------------------------------------------------------------------
    # Phase 3: Ticket migration
    # ------------------------------------------------------------------
    for scope_data in config.get("scopes", {}).values():
        if not isinstance(scope_data, dict):
            continue
        for hive_data in scope_data.get("hives", {}).values():
            if not isinstance(hive_data, dict):
                continue
            hive_path_str = hive_data.get("path")
            if not hive_path_str:
                continue
            hive_dir = Path(hive_path_str)
            if not hive_dir.is_dir():
                continue

            for md_file in hive_dir.rglob("*.md"):
                _migrate_ticket_file(md_file)
