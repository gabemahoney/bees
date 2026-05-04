"""Migration manifest for Bees config schema upgrades.

Each entry in MANIFEST describes one hop between adjacent schema versions.
The upgrade_script callable accepts the raw config dict and mutates it in
place. Scripts must be idempotent and must NOT bump schema_version — the
migration runner owns that step.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ManifestEntry:
    """One version-to-version migration hop.

    Attributes:
        from_version: Schema version this hop upgrades from.
        to_version: Schema version this hop upgrades to.
        upgrade_script: Callable that accepts the raw config dict and mutates
            it in place. Must be idempotent. Must NOT set schema_version.
        description: Human-readable description of what this migration does.
    """

    from_version: str
    to_version: str
    upgrade_script: Callable[[dict], None]
    description: str = ""


from src.migrations.upgrade_v2_to_v3 import upgrade as _upgrade_v2_to_v3
from src.migrations.upgrade_v3_to_v4 import upgrade as _upgrade_v3_to_v4

# Ordered list of migration hops.
MANIFEST: list[ManifestEntry] = [
    ManifestEntry(
        from_version="2.0",
        to_version="3.0",
        upgrade_script=_upgrade_v2_to_v3,
        description="Egg to Reference Materials: converts egg_resolver config keys to named resolver registry, renames 'egg' ticket field to 'reference_materials', and renames built-in resolver 'default' to 'file-path'",
    ),
    ManifestEntry(
        from_version="3.0",
        to_version="4.0",
        upgrade_script=_upgrade_v3_to_v4,
        description="Hive Portability: moves hive-level child_tiers and status_values from config.json to each hive's identity.json, deregisters inaccessible hives",
    ),
]


def find_pending_hops(current_version: str) -> list[ManifestEntry]:
    """Return the ordered list of hops needed to reach the latest version.

    Chains hops forward starting from current_version: finds the first entry
    whose from_version matches current_version, then continues from there
    until no further hop is found.

    Args:
        current_version: The schema_version currently stored in the config.

    Returns:
        Ordered list of ManifestEntry hops to apply. Empty list when already
        up to date or no matching hops exist.
    """
    index: dict[str, ManifestEntry] = {entry.from_version: entry for entry in MANIFEST}
    hops: list[ManifestEntry] = []
    seen: set[str] = set()
    version = current_version
    while version in index:
        if version in seen:
            raise ValueError(f"Cycle detected in migration manifest at version {version}")
        seen.add(version)
        hop = index[version]
        hops.append(hop)
        version = hop.to_version
    return hops


def get_pending_hops_info(current_version: str) -> dict:
    """Return info about pending hops without applying them.

    Returns dict with current_version, pending_hops list (each with
    from_version, to_version, description).

    Args:
        current_version: The schema_version currently stored in the config.

    Returns:
        Dict with current_version and pending_hops list.
    """
    hops = find_pending_hops(current_version)
    return {
        "current_version": current_version,
        "pending_hops": [
            {
                "from_version": hop.from_version,
                "to_version": hop.to_version,
                "description": hop.description,
            }
            for hop in hops
        ],
    }
