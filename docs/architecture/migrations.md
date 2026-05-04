# Migration System

## Overview

Bees uses a linear migration system to evolve the global config schema (`~/.bees/config.json`) across versions. Migrations are defined as ordered hops in a manifest, each transforming the config from one version to the next.

## ManifestEntry

Each migration hop is a `ManifestEntry` dataclass (`src/migrations/manifest.py`):

- **from_version**: Schema version this hop upgrades from (e.g., `"3.0"`)
- **to_version**: Schema version this hop upgrades to (e.g., `"4.0"`)
- **upgrade_script**: Callable that accepts the raw config dict and mutates it in place
- **description**: Human-readable summary of what this migration does

## Runner Sequencing

The migration runner (`src/migrations/runner.py`) applies hops in order:

1. Loads global config and reads `schema_version`
2. Calls `find_pending_hops(current_version)` to chain forward through the manifest
3. For each hop in sequence:
   - Executes `hop.upgrade_script(config_data)`
   - Sets `config_data["schema_version"] = hop.to_version`
   - Saves config to disk immediately
4. Returns summary of applied hops

**Crash resilience**: Because `schema_version` is persisted after each successful hop, a crash mid-sequence leaves the config at the last completed version. On next run, the runner picks up from that point — no hops are re-applied or skipped.

## Idempotency Requirement

Every upgrade script must be idempotent: running it twice on the same config produces the same result as running it once.

**Rationale**: If a hop succeeds but the process crashes before `schema_version` is persisted (unlikely but possible), the runner will re-execute that hop on next startup. Idempotency guarantees this re-execution is safe.

In practice this means: check whether a transformation has already been applied before applying it. For example, only move a key if it exists in the source location.

## Upgrade Function Contract

An upgrade function has this signature:

```python
def upgrade(config: dict) -> None:
```

Rules:
- **Mutate in place**: Modify the `config` dict directly. Do not return a new dict.
- **No self-version-bump**: Never set `config["schema_version"]`. The runner owns version advancement.
- **Preview support**: The function may be called for inspection without persisting (via `preview_pending_migrations()`). Side effects beyond config mutation (e.g., writing identity.json files) are acceptable when semantically required by the migration.
- **Raise on unrecoverable error**: Raise `ValueError` with a descriptive message if the config is in an unexpected state that cannot be migrated. The runner catches this and halts.

## Worked Example: v3 to v4

The v3→v4 migration (`src/migrations/upgrade_v3_to_v4.py`) moves hive-level configuration from `config.json` into each hive's `identity.json`:

**What it does**:
- For each registered hive in every scope:
  - If accessible (`.hive/` dir exists): reads identity.json, copies `child_tiers` / `status_values` / `status_values_explicitly_null` from the config entry into identity.json, removes those keys from the config entry
  - If inaccessible (`.hive/` dir missing): deregisters the hive entirely from config
- Scope-level and global-level keys are left untouched (they remain as fallback)

**Idempotency**: A second run finds no hive-level keys to migrate in config.json (they were already removed), so it is a no-op.

## Adding a New Migration

1. **Create the upgrade script** at `src/migrations/upgrade_vN_to_vM.py` with a top-level `upgrade(config: dict) -> None` function. Ensure it is idempotent and does not set `schema_version`.

2. **Register the hop** in `src/migrations/manifest.py`:
   ```python
   from src.migrations.upgrade_vN_to_vM import upgrade as _upgrade_vN_to_vM

   # Add to the end of the MANIFEST list:
   ManifestEntry(
       from_version="N.0",
       to_version="M.0",
       upgrade_script=_upgrade_vN_to_vM,
       description="Short description of what this migration does",
   ),
   ```

3. **Update `GLOBAL_SCHEMA_VERSION`** in `src/config.py` to match the new latest version.

4. **Test**: Write tests that exercise the upgrade function on representative config dicts, verifying both the fresh-run case and the idempotent re-run case.
