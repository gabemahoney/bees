"""Clone Bee MCP Tool — clones a bee and its entire subtree within the same hive or to another hive.

Creates a deep copy of a bee ticket and all its child-tier tickets,
generating fresh IDs and GUIDs while preserving titles, descriptions,
tags, statuses, and internal cross-references (remapped to new IDs).
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import (
    get_scope_key_for_hive,
    load_bees_config,
    load_global_config,
)
from .constants import SCHEMA_VERSION
from .hive_compat import check_cross_hive_compatibility
from .id_utils import (
    generate_child_tier_id,
    generate_guid,
    generate_unique_ticket_id,
    is_ticket_id,
    is_valid_ticket_id,
    normalize_hive_name,
)
from .paths import find_ticket_file
from .reader import read_ticket
from .writer import write_ticket_file

logger = logging.getLogger(__name__)


def _collect_tree(bee_dir: Path) -> list[tuple[str, Path]]:
    """Collect all tickets in a bee's directory subtree in parent-before-children order.

    Uses os.walk top-down traversal, only entering directories whose names
    match the ticket ID pattern (same filtering as iter_ticket_files).

    Args:
        bee_dir: Root directory of the source bee ticket.

    Returns:
        List of (ticket_id, file_path) tuples ordered parent-before-children.
    """
    tree: list[tuple[str, Path]] = []
    for dirpath, dirs, files in os.walk(bee_dir):
        dirs[:] = sorted(d for d in dirs if is_ticket_id(d))
        dir_name = Path(dirpath).name
        if is_ticket_id(dir_name):
            md_name = f"{dir_name}.md"
            if md_name in files:
                tree.append((dir_name, Path(dirpath) / md_name))
    return tree


def _clone_bee_core(
    bee_id: str,
    destination_hive: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Synchronous core of the clone_bee operation — runs inside an active repo_root_context.

    Args:
        bee_id: Bee ticket ID to clone (must start with "b.").
        destination_hive: Optional destination hive name. When None, clones into the
            source hive (same behavior as Epic 1). When provided, clones into the
            named hive (must be in the same scope as the source hive).
        force: When True, skip compatibility check and clone regardless of status/tier
            mismatches between source and destination hive configurations.

    Returns:
        dict with operation result. See _clone_bee docstring for full schema.
    """
    # ── Input validation ────────────────────────────────────────────────
    if not is_valid_ticket_id(bee_id) or not bee_id.startswith("b."):
        return {
            "status": "error",
            "error_type": "invalid_source_type",
            "message": f"'{bee_id}' is not a valid bee ticket ID. Only bee tickets (b. prefix) can be cloned.",
        }

    # ── Source lookup ────────────────────────────────────────────────────
    config = load_bees_config()
    if not config or not config.hives:
        return {
            "status": "error",
            "error_type": "bee_not_found",
            "message": f"Bee '{bee_id}' not found: no hives configured.",
        }

    source_file: Path | None = None
    source_hive: str | None = None
    for hive_name, hive_config in config.hives.items():
        hive_path = Path(hive_config.path)
        found = find_ticket_file(hive_path, bee_id)
        if found is not None:
            source_file = found
            source_hive = hive_name
            break

    if source_file is None or source_hive is None:
        return {
            "status": "error",
            "error_type": "bee_not_found",
            "message": f"Bee '{bee_id}' not found in any registered hive.",
        }

    # ── Destination hive resolution ──────────────────────────────────────
    if destination_hive is None:
        dest_hive = source_hive
    else:
        dest_hive = normalize_hive_name(destination_hive)
        if dest_hive not in config.hives:
            return {
                "status": "error",
                "error_type": "hive_not_found",
                "message": f"Destination hive '{destination_hive}' (normalized: '{dest_hive}') not found in config.",
            }

        # Scope check — must run before any write attempt
        global_config = load_global_config()
        try:
            source_scope = get_scope_key_for_hive(source_hive, global_config)
            dest_scope = get_scope_key_for_hive(dest_hive, global_config)
        except ValueError:
            return {
                "status": "error",
                "error_type": "cross_scope_error",
                "message": (
                    f"Cannot clone from hive '{source_hive}' to '{dest_hive}': "
                    "unable to determine scope for one or both hives."
                ),
            }

        if source_scope != dest_scope:
            return {
                "status": "error",
                "error_type": "cross_scope_error",
                "message": (
                    f"Cannot clone from hive '{source_hive}' (scope '{source_scope}') "
                    f"to '{dest_hive}' (scope '{dest_scope}'): cross-scope cloning is not allowed."
                ),
            }

    source_bee_dir = source_file.parent
    dest_hive_root = Path(config.hives[dest_hive].path)

    # ── Tree collection ──────────────────────────────────────────────────
    tree = _collect_tree(source_bee_dir)

    # ── Compatibility scan and check (cross-hive only, skipped when force=True) ──
    if dest_hive != source_hive and not force:
        source_statuses: set[str] = set()
        source_tier_types: set[str] = set()
        for old_id, file_path in tree:
            try:
                ticket = read_ticket(old_id, file_path=file_path)
            except Exception:
                continue
            if ticket.status is not None:
                source_statuses.add(ticket.status)
            if old_id != bee_id and ticket.type is not None:
                source_tier_types.add(ticket.type)

        compat = check_cross_hive_compatibility(source_statuses, source_tier_types, dest_hive, config)
        if compat is not None:
            return {
                "status": "error",
                "error_type": "compatibility_error",
                "message": (
                    f"Source tree is incompatible with destination hive '{dest_hive}'. "
                    f"Incompatible statuses: {compat['incompatible_status_values']}. "
                    f"Incompatible tier types: {compat['incompatible_tier_types']}."
                ),
                "incompatible_status_values": compat["incompatible_status_values"],
                "incompatible_tier_types": compat["incompatible_tier_types"],
            }

    # ── ID map building ──────────────────────────────────────────────────
    id_map: dict[str, str] = {}    # old_id → new_id
    dir_map: dict[str, Path] = {}  # new_id → new_directory
    guid_map: dict[str, str] = {}  # new_id → guid

    # Generate new root bee ID and create its directory in the destination hive
    new_bee_id = generate_unique_ticket_id("bee", hive_name=dest_hive)
    id_map[bee_id] = new_bee_id
    new_bee_dir = dest_hive_root / new_bee_id
    new_bee_dir.mkdir(parents=True, exist_ok=True)
    dir_map[new_bee_id] = new_bee_dir
    guid_map[new_bee_id] = generate_guid(new_bee_id.split(".", 1)[1])

    # Generate child IDs in tree order (parent dirs exist from prior iterations
    # because generate_child_tier_id creates child directories as a side effect)
    for old_id, file_path in tree:
        if old_id == bee_id:
            continue  # Root already handled

        # Parent is the ticket whose directory contains this one
        old_parent_name = file_path.parent.parent.name
        if old_parent_name not in id_map:
            continue  # Should not happen with top-down traversal

        new_parent_id = id_map[old_parent_name]
        new_parent_dir = dir_map[new_parent_id]

        new_child_id = generate_child_tier_id(new_parent_id, new_parent_dir)
        id_map[old_id] = new_child_id
        dir_map[new_child_id] = new_parent_dir / new_child_id
        guid_map[new_child_id] = generate_guid(new_child_id.split(".", 1)[1])

    # ── Clone writing ────────────────────────────────────────────────────
    written = 0
    failed: list[dict[str, str]] = []

    for old_id, file_path in tree:
        new_id = id_map.get(old_id)
        if new_id is None:
            failed.append({"id": old_id, "reason": "no mapped ID found"})
            continue

        # Read source ticket
        try:
            source = read_ticket(old_id, file_path=file_path)
        except Exception as e:
            if old_id == bee_id:
                return {
                    "status": "error",
                    "error_type": "clone_write_error",
                    "message": f"Failed to read source bee '{bee_id}': {e}",
                }
            failed.append({"id": old_id, "reason": f"read error: {e}"})
            continue

        # Build new frontmatter — fresh id, guid, created_at, schema_version
        frontmatter: dict[str, Any] = {
            "id": new_id,
            "type": source.type,
            "title": source.title,
            "tags": list(source.tags) if source.tags else [],
            "status": source.status,
            "created_at": datetime.now(),
            "schema_version": SCHEMA_VERSION,
            "guid": guid_map[new_id],
        }

        # Remap parent (internal ref → new ID; external ref → preserved)
        if source.parent is not None:
            frontmatter["parent"] = id_map.get(source.parent, source.parent)

        # Remap children
        if source.children:
            frontmatter["children"] = [id_map.get(c, c) for c in source.children]

        # Remap dependencies
        if source.up_dependencies:
            frontmatter["up_dependencies"] = [
                id_map.get(d, d) for d in source.up_dependencies
            ]
        if source.down_dependencies:
            frontmatter["down_dependencies"] = [
                id_map.get(d, d) for d in source.down_dependencies
            ]

        # Egg: copy on root bee only; omit on child tier tickets
        if old_id == bee_id:
            frontmatter["egg"] = source.egg

        # Write cloned ticket to destination hive
        try:
            write_ticket_file(
                ticket_id=new_id,
                ticket_type=source.type,
                frontmatter_data=frontmatter,
                body=source.description or "",
                hive_name=dest_hive,
            )
            written += 1
        except Exception as e:
            if old_id == bee_id:
                return {
                    "status": "error",
                    "error_type": "clone_write_error",
                    "message": f"Failed to write cloned root bee: {e}",
                }
            failed.append({"id": old_id, "reason": str(e)})

    return {
        "status": "success",
        "ticket_id": new_bee_id,
        "written": written,
        "failed": failed,
    }


async def _clone_bee(
    bee_id: str,
    destination_hive: str | None = None,
    force: bool = False,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """Clone a bee ticket and its entire subtree within the same hive or to another hive.

    Creates a deep copy with fresh IDs and GUIDs. Internal cross-references
    (parent, children, dependencies) are remapped to new IDs. External
    references are preserved unchanged.

    Thin async wrapper that delegates to _clone_bee_core.

    Constraints:
        - Only bee tickets (b. prefix) can be cloned
        - Source and destination hives must be in the same scope
        - IDs and GUIDs are freshly generated (no reuse)
        - created_at is set to current time (not copied from source)
        - schema_version uses current constant (not copied from source)
        - egg field is copied on root bee only, omitted on child tiers

    Args:
        bee_id: The bee ticket ID to clone (e.g., "b.Amx").
        destination_hive: Optional destination hive name. When None, clones into
            the source hive (preserving Epic 1 behavior). When provided, clones
            into the named hive after validating it exists and is in the same scope.
        force: When True, skip compatibility check and clone regardless of status/tier
            mismatches between source and destination hive configurations.
        resolved_root: Pre-resolved repo root path (injected by adapter).

    Returns:
        dict: Operation result.
        On success:
            {
                'status': 'success',
                'ticket_id': str,       # New root bee ID
                'written': int,         # Count of successfully written tickets
                'failed': list[dict],   # Dicts with 'id' and 'reason' for each child failure
            }
        On error (invalid source, not found, write failure, scope mismatch, compatibility):
            {
                'status': 'error',
                'error_type': str,
                'message': str,
            }
        On compatibility_error specifically:
            {
                'status': 'error',
                'error_type': 'compatibility_error',
                'message': str,
                'incompatible_status_values': list[str],
                'incompatible_tier_types': list[str],
            }

    Error Conditions:
        - invalid_source_type: bee_id is not a valid bee ticket ID (wrong format or not b. prefix)
        - bee_not_found: bee_id not found in any registered hive, or no hives configured
        - clone_write_error: failed to read or write the root bee (fatal — no children written)
        - hive_not_found: destination_hive is not in the config
        - cross_scope_error: source and destination hives are in different scopes
        - compatibility_error: source tree has statuses or tier types incompatible with
          destination hive's configuration (only when force=False)
        - Child write failures are non-fatal: recorded in the 'failed' list, remaining children proceed
    """
    return _clone_bee_core(bee_id, destination_hive=destination_hive, force=force)
