"""Migration: move hive-level child_tiers / status_values from config.json
to each hive's identity.json.

Upgrades the global config from schema version 3.0 to 4.0.

For each registered hive in every scope:
  - Accessible hives (.hive dir exists): read identity.json, copy
    child_tiers / status_values / status_values_explicitly_null from the
    config.json hive entry into the identity dict (config.json values
    overwrite any existing marker values — config.json is authoritative
    pre-migration per SR-6.2), write identity.json back, remove the
    migrated keys from the config.json hive entry.
  - Inaccessible hives (.hive dir missing): deregister entirely from
    config.json with a logged warning.

Scope-level and global-level child_tiers / status_values are left
untouched — they still serve as fallback levels in the resolution chain.

Idempotent: a second run finds no hive-level keys to migrate (no-op).
Does NOT set schema_version — the migration runner owns that.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def upgrade(config: dict) -> None:
    """Upgrade the raw config dict from schema 3.0 to 4.0 in place.

    Moves hive-level child_tiers, status_values, and
    status_values_explicitly_null from config.json hive entries into each
    hive's identity.json.  Deregisters hives whose .hive directory is
    inaccessible.

    Idempotent: safe to run multiple times.

    Args:
        config: The raw global config dict (mutated in place).
    """
    from src.mcp_hive_ops import read_identity, write_identity  # noqa: PLC0415

    _MIGRATED_KEYS = ("child_tiers", "status_values", "status_values_explicitly_null")

    for scope_key, scope_data in config.get("scopes", {}).items():
        if not isinstance(scope_data, dict):
            continue

        hives = scope_data.get("hives", {})
        hives_to_remove: list[str] = []

        for hive_name, hive_data in list(hives.items()):
            if not isinstance(hive_data, dict):
                continue

            hive_path_str = hive_data.get("path", "")
            if not hive_path_str:
                logger.warning(
                    "Migration v3->v4: deregistering hive '%s' with empty path "
                    "from scope '%s'",
                    hive_name,
                    scope_key,
                )
                hives_to_remove.append(hive_name)
                continue

            hive_marker = Path(hive_path_str) / ".hive"

            if not hive_marker.is_dir():
                logger.warning(
                    "Migration v3->v4: deregistering inaccessible hive '%s' "
                    "(path: %s) from scope '%s'",
                    hive_name,
                    hive_path_str,
                    scope_key,
                )
                hives_to_remove.append(hive_name)
                continue

            # Check whether this hive entry has anything to migrate
            has_any = any(k in hive_data for k in _MIGRATED_KEYS)
            if not has_any:
                continue

            # Read existing identity.json (may be None for old hives)
            identity = read_identity(hive_marker)
            if identity is None:
                # Build minimal identity so write_identity produces a valid file
                identity = {
                    "normalized_name": hive_name,
                    "display_name": hive_data.get("display_name", ""),
                    "created_at": hive_data.get("created_at", ""),
                }

            # Config.json values overwrite identity.json values (authoritative)
            if "child_tiers" in hive_data:
                identity["child_tiers"] = hive_data["child_tiers"]

            if hive_data.get("status_values_explicitly_null"):
                # Explicit null override — tell write_identity to emit null
                identity["status_values_explicitly_null"] = True
                identity.pop("status_values", None)
            elif "status_values" in hive_data:
                identity["status_values"] = hive_data["status_values"]
                identity.pop("status_values_explicitly_null", None)

            write_identity(hive_marker, identity)

            # Remove migrated keys from config.json hive entry
            for key in _MIGRATED_KEYS:
                hive_data.pop(key, None)

        # Deregister inaccessible hives
        for name in hives_to_remove:
            del hives[name]
