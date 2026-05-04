# Writing Config Migrations

This guide explains how to add a new config schema migration to Bees. Migrations are used when a change to `~/.bees/config.json` or ticket files is required to support new functionality.

## When to Write a Migration

A migration is needed when:
- The global config schema gains or loses a field that existing configs must be updated to reflect
- Ticket frontmatter fields are renamed or restructured
- Stored values need to be transformed (e.g., renaming a built-in resolver)

## Architecture Overview

The migration system has three components:

**`src/migrations/manifest.py`** — the registry. Contains `MANIFEST`, an ordered list of `ManifestEntry` objects, each representing one hop between adjacent schema versions. Also contains `find_pending_hops()`, which chains entries forward from a given version to build the list of hops that need to run.

**`src/migrations/runner.py`** — the executor. `run_pending_migrations()` loads the global config, calls `find_pending_hops()`, then applies each hop in order. After each successful hop, `schema_version` is updated and the config is saved — so a partial failure leaves the config at the last successful version rather than in an undefined state.

**`src/migrations/upgrade_vX_to_vY.py`** — the upgrade script. One file per hop. Contains the actual transformation logic. See the Upgrade Script section below.

The `update_config` MCP tool / `bees update-config` CLI command is the user-facing entry point — it calls `run_pending_migrations()`.

## Adding a New Migration Hop

### Step 1: Determine the version numbers

Each hop has a `from_version` and `to_version` matching the `schema_version` strings stored in `config.json`. The latest version is the `to_version` of the last entry in `MANIFEST`. Your hop's `from_version` must equal that value.

### Step 2: Write the upgrade script

Create `src/migrations/upgrade_vX_to_vY.py`. The module must expose a single public function:

```python
def upgrade(config: dict) -> None:
    ...
```

The function receives the raw global config dict and mutates it in place. It must be **idempotent** — running it twice must produce the same result as running it once. The runner may call it more than once in failure/retry scenarios.

**Do not set `schema_version`** inside the upgrade script. The runner owns that step.

### Step 3: Register in MANIFEST

Add a `ManifestEntry` to `MANIFEST` in `src/migrations/manifest.py`:

```python
from src.migrations.upgrade_vX_to_vY import upgrade as _upgrade_vX_to_vY

MANIFEST: list[ManifestEntry] = [
    # ... existing entries ...
    ManifestEntry(
        from_version="X.0",
        to_version="Y.0",
        upgrade_script=_upgrade_vX_to_vY,
        description="Short description of what this migration does",
    ),
]
```

The list must remain in version order. `find_pending_hops()` chains entries by matching `from_version` to the current schema version, so gaps or out-of-order entries will silently stop the chain.

## Writing an Idempotent Upgrade Script

The reference implementation is `src/migrations/upgrade_v2_to_v3.py`. It uses a four-phase pattern that scales well for complex migrations:

**Phase 1 — Validation (read-only)**
Scan the config and raise `ValueError` if any precondition is violated (e.g., name collisions that would corrupt the output). No mutations yet. A `ValueError` at this phase aborts the migration cleanly — the config is unchanged and `schema_version` stays at the previous version.

**Phase 2 — Config-level changes**
Mutate global config structure: add, rename, or remove keys at the global, scope, or hive level.

**Phase 3 — Cross-reference fixes**
Walk hive entries to update references that were affected by Phase 2 (e.g., renaming a value that appears in `allowed_resolvers` lists).

**Phase 4 — Ticket file migration**
Walk hive directories on disk and rewrite ticket frontmatter as needed. Use the hive `path` values from the config to locate hive directories.

Phases 3 and 4 are only needed when the migration touches ticket files or cross-references. Skip them if the change is config-only.

### Idempotency patterns

- **Key renaming**: Check for the new key before renaming. If the new key already exists, skip.
- **Key removal**: Use `dict.pop(key, None)` — safe to call even if the key is already absent.
- **File rewrites**: Check whether the old field is still present before writing. If it's already been converted, skip.
- **Registry population**: Use `if name not in existing_registry` before adding an entry.

## Error Handling

Raise `ValueError` for conditions that should block the migration entirely (e.g., name collisions in Phase 1). The runner catches `ValueError`, returns an error response, and leaves `schema_version` at the last successfully applied version. Other exceptions propagate.

Do not catch and swallow errors from ticket file reads/writes — let them surface so the runner can report them accurately.

## Testing

Write integration tests that:
1. Build a minimal config dict representing the `from_version` state
2. Call `upgrade(config)` directly
3. Assert the dict now matches the expected `to_version` state
4. Call `upgrade(config)` again and assert the result is unchanged (idempotency)

See `tests/migrations/test_upgrade_v2_to_v3.py` for the pattern used by the existing migration.
