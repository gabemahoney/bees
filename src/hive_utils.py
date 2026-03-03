"""Hive configuration helper utilities for sanitize_hive and other hive management commands."""

from typing import Any

from .config import BeesConfig, load_bees_config
from .id_utils import normalize_hive_name


def get_hive_config(hive_name: str) -> dict[str, Any] | None:
    """
    Get configuration for a specific hive by name.

    Normalizes the hive name and looks it up in ~/.bees/config.json.

    Args:
        hive_name: The hive name (display name or normalized form accepted)

    Returns:
        Dict with 'path', 'display_name', 'created_at' if hive is registered,
        None if hive not registered or config doesn't exist

    Examples:
        >>> get_hive_config("Backend")
        {'path': '/path/to/backend', 'display_name': 'Backend', 'created_at': '2026-02-01T...'}
        >>> get_hive_config("back_end")  # Same result with normalized name
        {'path': '/path/to/backend', 'display_name': 'Backend', 'created_at': '2026-02-01T...'}
        >>> get_hive_config("nonexistent")
        None
    """
    # Normalize hive name
    normalized = normalize_hive_name(hive_name)

    # Load config
    config = load_bees_config()

    # Return None if config doesn't exist
    if config is None:
        return None

    # Look up hive in config
    if normalized not in config.hives:
        return None

    # Return hive config as dict
    hive_config = config.hives[normalized]
    return {"path": hive_config.path, "display_name": hive_config.display_name, "created_at": hive_config.created_at}


def load_hives_config() -> BeesConfig | None:
    """
    Load entire ~/.bees/config.json configuration.

    Returns:
        BeesConfig object if file exists, None if not found
    """
    return load_bees_config()


