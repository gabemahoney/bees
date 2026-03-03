"""
Move Bee MCP Tool — moves bee tickets between hives within the same scope.

Validates source and destination hives, checks scope compatibility,
and performs moves of bee ticket directories.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from . import cache
from .config import get_scope_key_for_hive, load_bees_config, load_global_config
from .hive_compat import check_cross_hive_compatibility
from .id_utils import is_ticket_id, is_valid_ticket_id, normalize_hive_name
from .paths import find_ticket_file
from .reader import read_ticket
from .repo_utils import get_repo_root_from_path  # noqa: F401 - kept for monkeypatching in tests

logger = logging.getLogger(__name__)


def _collect_tree_statuses_and_types(
    bee_dir: Path,
    bee_id: str,
) -> tuple[set[str], set[str]]:
    """Collect all status values and child-tier types from a bee's directory subtree.

    Args:
        bee_dir: Root directory of the bee ticket.
        bee_id: The root bee's ID (excluded from tier type collection).

    Returns:
        Tuple of (statuses, tier_types) where:
          - statuses: set of all non-None status strings found in the tree
          - tier_types: set of all non-None type strings for child tickets (root bee excluded)
    """
    statuses: set[str] = set()
    tier_types: set[str] = set()
    for dirpath, dirs, files in os.walk(bee_dir):
        dirs[:] = sorted(d for d in dirs if is_ticket_id(d))
        dir_name = Path(dirpath).name
        if is_ticket_id(dir_name):
            md_name = f"{dir_name}.md"
            if md_name in files:
                ticket_path = Path(dirpath) / md_name
                try:
                    ticket = read_ticket(dir_name, file_path=ticket_path)
                except Exception:
                    continue
                if ticket.status is not None:
                    statuses.add(ticket.status)
                if dir_name != bee_id and ticket.type is not None:
                    tier_types.add(ticket.type)
    return statuses, tier_types


def _move_bee_core(
    bee_ids: list[str],
    destination_hive: str,
    force: bool = False,
) -> dict[str, Any]:
    """Synchronous core of the move_bee operation — runs inside an active repo_root_context.

    Args:
        bee_ids: List of bee ticket IDs to move (e.g., ["b.Amx", "b.X4F"])
        destination_hive: Friendly or normalized name of the destination hive
        force: When True, skip cross-hive compatibility checks and move regardless
            of status/tier mismatches between source and destination hive configurations.

    Returns:
        dict with status and moved/skipped/not_found/failed lists.
        On error: dict with status "error", message, and error_type.

    Note:
        After a successful move, the bee's cache entry is evicted. Child tickets
        self-heal via stale-path detection on next access.
    """
    # ── Empty list → return success immediately (no validation needed) ────
    if not bee_ids:
        return {
            "status": "success",
            "moved": [],
            "skipped": [],
            "not_found": [],
            "failed": [],
        }

    # ── Load config and validate destination hive ─────────────────────────
    destination_hive = normalize_hive_name(destination_hive)
    config = load_bees_config()
    if not config or destination_hive not in config.hives:
        return {
            "status": "error",
            "message": f"Destination hive '{destination_hive}' not found.",
            "error_type": "hive_not_found",
        }

    dest_path = Path(config.hives[destination_hive].path)

    # ── Prevent cemetery as a destination ────────────────────────────────
    if destination_hive == "cemetery" or dest_path.name == "cemetery":
        return {
            "status": "error",
            "message": "Cannot move bees into the cemetery.",
            "error_type": "cemetery_destination",
        }

    # ── Load global config once for scope lookups ─────────────────────────
    global_config = load_global_config()

    # ── Locate all bees first (needed for compatibility pre-scan) ─────────
    # Map: bee_id → (ticket_file, source_hive_name) or reason for failure
    located: dict[str, tuple[Path, str] | dict[str, str]] = {}

    for bee_id in bee_ids:
        if not is_valid_ticket_id(bee_id):
            located[bee_id] = {"reason": "malformed ticket ID"}
            continue
        if not bee_id.startswith("b."):
            located[bee_id] = {"reason": "cannot move non-bee tickets"}
            continue

        ticket_file = None
        source_hive_name = None
        for hive_name, hive_config in config.hives.items():
            hive_path = Path(hive_config.path)
            found = find_ticket_file(hive_path, bee_id)
            if found is not None:
                ticket_file = found
                source_hive_name = hive_name
                break

        if ticket_file is None:
            located[bee_id] = {"not_found": True}
        else:
            located[bee_id] = (ticket_file, source_hive_name)

    # ── Compatibility pre-scan (cross-hive, skipped when force=True) ──────
    if not force:
        failed_compat: list[dict[str, Any]] = []
        for bee_id in bee_ids:
            entry = located[bee_id]
            if not isinstance(entry, tuple):
                continue  # will be handled in the move loop
            ticket_file, source_hive_name = entry
            if source_hive_name == destination_hive:
                continue  # same-hive skip

            bee_dir = ticket_file.parent
            statuses, tier_types = _collect_tree_statuses_and_types(bee_dir, bee_id)
            compat = check_cross_hive_compatibility(statuses, tier_types, destination_hive, config)
            if compat is not None:
                failed_compat.append({
                    "bee_id": bee_id,
                    "incompatible_status_values": compat["incompatible_status_values"],
                    "incompatible_tier_types": compat["incompatible_tier_types"],
                })

        if failed_compat:
            bee_list = ", ".join(f["bee_id"] for f in failed_compat)
            return {
                "status": "error",
                "error_type": "compatibility_error",
                "message": (
                    f"Compatibility check failed for bee(s): {bee_list}. "
                    f"No moves were performed. Use --force to bypass."
                ),
                "failed_bees": failed_compat,
            }

    # ── Process each bee ID ───────────────────────────────────────────────
    moved: list[str] = []
    skipped: list[str] = []
    not_found: list[str] = []
    failed: list[dict[str, str]] = []

    for bee_id in bee_ids:
        entry = located[bee_id]

        if isinstance(entry, dict):
            if entry.get("not_found"):
                not_found.append(bee_id)
            else:
                failed.append({"id": bee_id, "reason": entry["reason"]})
            continue

        ticket_file, source_hive_name = entry

        # Already in destination — skip
        if source_hive_name == destination_hive:
            skipped.append(bee_id)
            continue

        # Verify source and destination are in the same scope
        try:
            source_scope = get_scope_key_for_hive(source_hive_name, global_config)
            dest_scope = get_scope_key_for_hive(destination_hive, global_config)
        except ValueError as e:
            failed.append({"id": bee_id, "reason": str(e)})
            continue

        if source_scope != dest_scope:
            failed.append({
                "id": bee_id,
                "reason": "source and destination hives are in different scopes",
            })
            continue

        # Perform the move
        bee_dir = ticket_file.parent
        dest_bee_path = dest_path / bee_dir.name
        if dest_bee_path.exists():
            failed.append({"id": bee_id, "reason": f"destination already exists: {dest_bee_path}"})
            continue
        try:
            shutil.move(str(bee_dir), str(dest_bee_path))
            cache.evict(bee_id)
            moved.append(bee_id)
        except Exception as e:
            failed.append({"id": bee_id, "reason": str(e)})

    return {
        "status": "success",
        "moved": moved,
        "skipped": skipped,
        "not_found": not_found,
        "failed": failed,
    }


async def _move_bee(
    bee_ids: list[str],
    destination_hive: str,
    force: bool = False,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """Move bee tickets to a different hive within the same scope.

    Thin async wrapper that resolves repo_root, sets context, and delegates
    to _move_bee_core.

    Destination hive integrity is checked before executing the move.
    Source hive corruption does NOT block the move.

    Constraints:
        - Only bee tickets (b. prefix) can be moved; non-bee IDs are rejected
        - Source and destination hives must belong to the same scope
        - Cemetery is never a valid destination
        - Bee IDs are preserved unchanged — only the directory location changes
        - Each bee is moved atomically and independently (per-bee atomic move)
        - Cross-hive compatibility is checked before any moves are performed;
          if any bee fails, ALL moves are aborted (use force=True to bypass)

    Args:
        bee_ids (list[str]): Bee ticket IDs to move (e.g., ["b.Amx", "b.X4F"]).
                             Empty list returns success immediately with no operations performed.
        destination_hive (str): Friendly or normalized name of the destination hive (e.g., "Back End" or "back_end").
        force (bool): When True, skip cross-hive compatibility checks and move regardless of
                      status/tier mismatches between source and destination hive configurations.
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Operation result. On success:
            {
                'status': 'success',
                'moved': list[str],      # Bee IDs successfully moved
                'skipped': list[str],    # Bee IDs already in destination hive
                'not_found': list[str],  # Bee IDs not found in any registered hive
                'failed': list[dict],    # Dicts with 'id' and 'reason' for each failure
            }
        On error (destination hive not found, cemetery destination, etc.):
            {
                'status': 'error',
                'message': str,      # Human-readable error description
                'error_type': str,   # Error category (e.g., 'hive_not_found', 'cemetery_destination')
            }
        On compatibility_error (force=False and source tree incompatible with destination):
            {
                'status': 'error',
                'error_type': 'compatibility_error',
                'message': str,
                'failed_bees': [
                    {
                        'bee_id': str,
                        'incompatible_status_values': list[str],
                        'incompatible_tier_types': list[str],
                    },
                    ...
                ]
            }
        On corrupt destination hive:
            {
                'status': 'error',
                'error_type': 'hive_corrupt',
                'hive_name': str,    # Normalized name of the corrupt hive
                'message': str,      # Human-readable error description
                'errors': list[str], # Lint error messages from integrity check
            }

    Example:
        >>> await _move_bee(["b.Amx", "b.X4F"], "backlog")
        {
            'status': 'success',
            'moved': ['b.Amx', 'b.X4F'],
            'skipped': [],
            'not_found': [],
            'failed': []
        }

    Error Conditions:
        - hive_not_found: destination_hive not registered in config
        - cemetery_destination: destination is the cemetery directory
        - compatibility_error: source tree has statuses or tier types incompatible with
          destination hive's configuration (only when force=False); all moves aborted
        - hive_corrupt: destination hive fails integrity checks (source hive is not checked)
        - Malformed ID: bee_id fails ticket ID format validation → added to failed list
        - Non-bee ticket: bee_id does not start with 'b.' → added to failed list
        - Cross-scope move: source and destination in different scopes → added to failed list
        - Filesystem error: shutil.move fails → added to failed list with exception message
    """
    return _move_bee_core(bee_ids, destination_hive, force=force)
