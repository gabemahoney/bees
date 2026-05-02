"""Migration manifest for Bees config schema upgrades.

Each entry in MANIFEST describes one hop between adjacent schema versions.
The upgrade_script callable accepts the raw config dict and mutates it in
place. Scripts must be idempotent and must NOT bump schema_version — the
migration runner owns that step.
"""

from dataclasses import dataclass
from collections.abc import Callable


@dataclass
class ManifestEntry:
    """One version-to-version migration hop.

    Attributes:
        from_version: Schema version this hop upgrades from.
        to_version: Schema version this hop upgrades to.
        upgrade_script: Callable that accepts the raw config dict and mutates
            it in place. Must be idempotent. Must NOT set schema_version.
    """

    from_version: str
    to_version: str
    upgrade_script: Callable[[dict], None]


# Ordered list of migration hops. Epic 4 will populate this list.
MANIFEST: list[ManifestEntry] = []


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
