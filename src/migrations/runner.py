"""Migration runner for Bees config schema upgrades.

Applies pending migration hops from the manifest to the global config,
persisting schema_version after each successful hop.
"""

from src.config import load_global_config, save_global_config
from src.migrations.manifest import find_pending_hops, get_pending_hops_info


def preview_pending_migrations() -> dict:
    """Return info about pending migrations without applying them.

    Loads the global config, determines which migration hops are pending,
    and returns their descriptions without modifying anything.

    Returns:
        Dict with status, current_version, and pending_hops list.
    """
    config_data = load_global_config()
    current_version = config_data.get("schema_version", "")
    info = get_pending_hops_info(current_version)

    if not info["pending_hops"]:
        return {
            "status": "success",
            "message": f"Config is up to date (version {current_version}). No pending migrations.",
            "current_version": current_version,
            "pending_hops": [],
        }

    return {
        "status": "success",
        "current_version": current_version,
        "pending_hops": [
            {"from_version": hop["from_version"], "to_version": hop["to_version"], "description": hop["description"]}
            for hop in info["pending_hops"]
        ],
    }


def run_pending_migrations() -> dict:
    """Apply all pending schema migrations to the global config.

    Loads the global config, determines which migration hops are pending,
    and applies them in order. Saves the config after each hop so that
    partial failures leave schema_version at the last successful hop.

    Returns:
        Dict with status, message, and version info.
    """
    config_data = load_global_config()
    current_version = config_data.get("schema_version", "")
    hops = find_pending_hops(current_version)

    if not hops:
        return {
            "status": "success",
            "message": "Already up to date",
            "version": current_version,
        }

    applied = []
    for hop in hops:
        try:
            hop.upgrade_script(config_data)
        except ValueError as e:
            return {"status": "error", "message": str(e), "version": current_version}
        config_data["schema_version"] = hop.to_version
        save_global_config(config_data)
        applied.append({"from_version": hop.from_version, "to_version": hop.to_version})

    return {
        "status": "success",
        "message": f"Applied {len(applied)} migration(s)",
        "applied_hops": applied,
        "final_version": config_data["schema_version"],
    }
