"""Shared cross-hive compatibility check utility."""

from .config import resolve_child_tiers_for_hive, resolve_status_values_for_hive


def check_cross_hive_compatibility(
    source_statuses: set[str],
    source_tier_types: set[str],
    dest_hive: str,
    config,
) -> dict | None:
    """Check whether a bee tree is compatible with a destination hive's configuration.

    Args:
        source_statuses: Set of status values found in the source tree.
        source_tier_types: Set of child-tier type strings found in the source tree
            (excludes the root bee type itself).
        dest_hive: Normalized destination hive name.
        config: BeesConfig instance.

    Returns:
        None if compatible.
        dict with keys 'incompatible_status_values' and 'incompatible_tier_types'
        (both always present as sorted lists) if not compatible.
    """
    dest_status_values = resolve_status_values_for_hive(dest_hive, config)
    dest_child_tiers = resolve_child_tiers_for_hive(dest_hive, config)

    incompatible_status_values: list[str] = []
    incompatible_tier_types: list[str] = []

    if dest_status_values is not None:
        incompatible_status_values = sorted(
            s for s in source_statuses if s not in dest_status_values
        )

    if dest_child_tiers:
        incompatible_tier_types = sorted(
            t for t in source_tier_types if t not in dest_child_tiers
        )

    if incompatible_status_values or incompatible_tier_types:
        return {
            "incompatible_status_values": incompatible_status_values,
            "incompatible_tier_types": incompatible_tier_types,
        }

    return None
