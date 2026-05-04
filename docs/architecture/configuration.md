# Configuration Architecture

This document describes the configuration system architecture for the Bees ticket management system, covering the global scoped config, hive registry, name normalization rules, API design, and consistency guarantees.

## Global Scoped Configuration

Bees uses a single global config file at `~/.bees/config.json` with scoped directory pattern matching. Each scope maps a directory pattern to a set of hives and settings.

**Schema Structure**:
```json
{
  "schema_version": "2.0",
  "child_tiers": {
    "t1": ["Epic", "Epics"],
    "t2": ["Task", "Tasks"],
    "t3": ["Subtask", "Subtasks"]
  },
  "queries": {
    "global_open_bees": {"stages": [["type=bee", "status=open"]]}
  },
  "resolvers": {
    "guid_resolver": {
      "path": "/projects/myrepo/resolvers/guid_resolver.py",
      "timeout": 10,
      "convention": "Store the GUID string from the .guid file in the reference_materials value field."
    }
  },
  "scopes": {
    "/Users/dev/projects/myrepo": {
      "hives": {
        "normalized_name": {
          "display_name": "Display Name",
          "path": "/absolute/path/to/hive",
          "created_at": "2026-02-03T10:30:45.123456"
        }
      },
      "child_tiers": {
        "t1": ["Story", "Stories"],
        "t2": ["Feature", "Features"]
      },
      "queries": {
        "open_tasks": {"stages": [["type=t1", "status=open"]]},
        "all_bees_with_children": {"stages": [["type=bee"], ["children"]]}
      }
    },
    "/Users/dev/projects/bees/**": {
      "hives": { ... },
      "child_tiers": { ... }
    }
  }
}
```

**Top-Level Fields**:
- `schema_version`: Config format version, currently "2.0"
- `child_tiers`: (Optional) Global-level child_tiers configuration (dict or null). See Child Tiers Configuration below.
- `queries`: (Optional) Global-level named queries dictionary. See Named Queries Configuration below.
- `resolvers`: (Optional) Named resolver registry. Dict mapping resolver names to `{path, timeout?, convention?}` objects. Managed via `set-resolver` / `get-resolvers`. See Named Resolver Registry below.
- `delete_with_dependencies`: (Optional) Boolean, default `false`. When `true`, deleting a ticket automatically removes its ID from surviving tickets' `up_dependencies` and `down_dependencies` arrays before deletion. **Global-only** — cannot be set at scope or hive level.
- `auto_fix_dangling_refs`: (Optional) Boolean, default `false`. When `true`, `sanitize_hive` automatically removes dangling dependency and parent references from ticket files instead of reporting them as errors. Each fix is recorded in the response as `remove_dangling_dependency` or `clear_dangling_parent`. **Global-only** — cannot be set at scope or hive level.
- `queen_repos`: (Optional) List of queen repo entries granting elevated cross-scope access. Absent or empty means no queen repos. Non-existent paths are silently ignored; invalid entries produce an `invalid_config` error at tool call time. See Queen Repos Configuration below.
- `scopes`: Dictionary mapping directory patterns to scope configurations

**Scope Fields**:
- `hives`: Dictionary mapping normalized hive names to HiveConfig objects
- `child_tiers`: (Optional) Scope-level child_tiers configuration (dict or null). See Child Tiers Configuration below.
- `queries`: (Optional) Scope-level named queries dictionary. See Named Queries Configuration below.

**Hive Fields**:
- `path`: Absolute path to hive directory
- `display_name`: User-friendly display name
- `created_at`: ISO 8601 timestamp of hive creation
- `allowed_resolvers`: (Optional) List of resolver names permitted for this hive (list of strings or null). Each name must exist in the global `resolvers` registry or be one of the built-in names (`"file-path"`, `"github"`, `"bees"`, or `"default"`). When set, only the listed resolvers may be used with this hive. See Named Resolver Registry below.

**Note**: Ticket IDs are globally unique across all hives. Dependencies can reference tickets in any hive, with same-tier restriction (bee→bee, t1→t1, etc.).

**Implementation**: See `src/config.py` for BeesConfig, HiveConfig dataclasses, scope matching, and load/save functions.

## Queen Repos Configuration

The `queen_repos` field grants one or more "queen repos" elevated cross-scope access to all hive operations regardless of normal scope filtering. A queen repo can operate on every hive registered in the global config, not just the hives that would ordinarily match its own scope.

### Schema

`queen_repos` is a top-level list of objects. Each object has:

- `path` (required, string): Absolute path to the repository root that receives elevated access.
- `write` (optional, boolean, default `false`): When `false` (or absent), the repo has read-only elevated access. When `true`, the repo also has write access across all hives.

### Examples

```json
{
  "queen_repos": [
    { "path": "/Users/dev/projects/read-only-queen" },
    { "path": "/Users/dev/projects/write-queen", "write": true }
  ]
}
```

### Behavior

- **Non-existent paths**: If a `path` entry does not exist on disk, it is silently ignored. No error is raised and other entries continue to be evaluated normally.
- **Invalid entries**: Entries with the wrong type for any field, or entries missing the required `path` key, produce an `invalid_config` error at tool call time.

## Scope Pattern Matching

Scope keys are directory paths with optional wildcard suffixes. Every scope pattern has a canonical form, and the system uses specificity rules to select the best matching scope when multiple patterns match the same repository root.

### Canonical Forms

All scope patterns reduce to one of three canonical forms:

- **Exact / trailing-slash** (`/foo/`): matches only the named directory itself. No subdirectories or children are included. A bare path with no wildcard suffix (e.g., `/foo`) is treated as this form.
- **Single-level wildcard** (`/foo/*`): matches any immediate child directory of the prefix — exactly one path segment deeper. It does not match the prefix directory itself or any grandchildren.
- **Recursive wildcard** (`/foo/**`): matches the prefix directory itself and any descendant directory at any depth.

**Canonicalization rules**: `canonicalize_scope_pattern()` strips any trailing `/**`, `/*`, or `/` suffix from a raw pattern, then re-appends the appropriate suffix. A raw pattern with no recognized suffix is assigned the trailing-slash (exact) form. This means that `/foo`, `/foo/`, and any variant with redundant suffixes all reduce to the same canonical representation before any comparison or storage operation.

### Specificity

When multiple scope patterns match a repository root, the most specific pattern wins. Specificity is expressed as a two-key tuple:

1. **Segment count** (primary): the number of literal path segments in the bare prefix (the pattern minus its wildcard suffix). More segments means higher specificity.
2. **Wildcard tier** (secondary): a numeric rank for the terminal wildcard — exact/trailing-slash = 0, `/*` = 1, `/**` = 2. Within the same segment count, a lower wildcard tier is more specific: an exact/trailing-slash match (0) outranks `/*` (1), which outranks `/**` (2).

When two patterns produce identical `(segment_count, wildcard_tier)` values, the pattern that appears first in config dict insertion order wins silently (no error is raised).

### Conflict Detection

A **conflict** exists between a candidate pattern and an existing scope key when both canonicalize to the same bare prefix **and** the same wildcard tier, but the raw strings differ. A conflict is blocked because it would create an ambiguous duplicate scope — there is no way for specificity rules to distinguish them. An exact canonical match (same raw string after canonicalization) is not a conflict; it means the candidate can reuse the existing scope.

**Overlap** is a distinct, permitted condition. Two patterns overlap when they can match the same repository root path. Overlap is determined by whether one pattern's prefix is an ancestor of the other's, and whether the ancestor's wildcard tier reaches the child's depth:

- A `/**` pattern overlaps with any pattern whose prefix starts with its own prefix (any depth).
- A `/*` pattern overlaps with patterns whose prefix is exactly one level deeper.
- An exact/trailing-slash pattern overlaps with nothing below its own prefix.

Overlap is allowed and resolved at runtime by specificity ordering — the more specific pattern wins for any given repository root. Conflict, by contrast, is blocked at write time because no specificity difference exists to resolve it.

### Functions

- `match_scope_pattern(repo_root: Path, pattern: str) -> bool`: Check whether repo_root matches a scope pattern; results are cached per pattern
- `find_matching_scope(repo_root: Path, global_config: dict) -> str | None`: Return the most-specific scope pattern that matches repo_root; on specificity tie, first in insertion order wins
- `find_all_matching_scopes(repo_root: Path, global_config: dict) -> list[tuple[str, BeesConfig]]`: Return all scope patterns that match repo_root, ordered from least-specific to most-specific
- `get_scoped_config(repo_root) -> BeesConfig | None`: Load global config, match scope by specificity, return BeesConfig
- `canonicalize_scope_pattern(pattern: str) -> str`: Convert a raw scope pattern to its canonical form
- `validate_scope_pattern(pattern: str) -> None`: Raise ValueError if the pattern contains wildcards in invalid positions (only terminal `/*` or `/**` are allowed)
- `compute_scope_specificity(pattern: str) -> tuple[int, int]`: Return a `(segment_count, wildcard_tier)` tuple for ranking patterns by specificity
- `scopes_overlap(pattern_a: str, pattern_b: str) -> bool`: Return True if the two scope patterns can match the same repository root
- `check_scope_conflict(pattern: str, global_config: dict) -> str | None`: Return the first existing scope key that conflicts with the candidate pattern, or None if no conflict exists

## Child Tiers Configuration

Child tiers define the ticket hierarchy for a hive (e.g., t1=Epic, t2=Task, t3=Subtask). Configuration is supported at three levels with fallback behavior.

### Configuration Levels

**Global Level** (top-level in `~/.bees/config.json`):
```json
{
  "child_tiers": {
    "t1": ["Epic", "Epics"],
    "t2": ["Task", "Tasks"]
  },
  "scopes": { ... }
}
```

**Scope Level** (within a scope):
```json
{
  "scopes": {
    "/path/to/repo": {
      "child_tiers": {
        "t1": ["Story", "Stories"],
        "t2": ["Feature", "Features"]
      },
      "hives": { ... }
    }
  }
}
```

**Hive Level** (within `.hive/identity.json` in the hive directory):
```json
{
  "normalized_name": "normalized_name",
  "display_name": "Display Name",
  "created_at": "2026-02-03T10:30:45.123456",
  "child_tiers": {
    "t1": ["Task", "Tasks"],
    "t2": ["Subtask", "Subtasks"]
  }
}
```

Hive-level child_tiers are stored in `.hive/identity.json`, not in the config.json hive entry. The `colonize_hive` tool writes this value at creation time.

### Resolution Order

The `resolve_child_tiers_for_hive()` function determines which child_tiers to use via fallback chain:

1. **Hive level**: Read `child_tiers` from the hive's `.hive/identity.json`
2. **Scope level**: Check scope's `child_tiers`
3. **Global level**: Check top-level `child_tiers`
4. **Default**: Return `{}` (bees-only, no child tiers)

### Fallback Semantics

**null or omitted**: Fall through to next level in the chain
**{} (empty dict)**: Stop fallback chain and use bees-only (no child tiers)
**{tier_key: [names]}**: Stop fallback chain and use this exact configuration

### No Merging

Each level completely replaces the child_tiers configuration — there is NO merging of tier definitions between levels. When a level provides a non-null child_tiers value, that exact configuration is used and the fallback chain stops.

**Implementation**: See `resolve_child_tiers_for_hive()` in `src/config.py`.

### Ticket Operation Integration

Per-hive child_tiers resolution is enforced in ticket operations to ensure tickets match their hive's tier configuration.

**create_ticket Enforcement** (`src/mcp_ticket_ops.py`):
- Resolves child_tiers for target hive using `resolve_child_tiers_for_hive()`
- Validates ticket type against resolved tiers via `validate_ticket_type()`
- Rejects child tier creation in bees-only hives (child_tiers = {})

**Bees-Only Hives**:
- When resolved child_tiers is `{}`, hive only accepts bee (t0) tickets
- Attempting to create t1/t2/t3 raises: `"Hive '{name}' is configured as bees-only. Only bee (t0) tickets can be created."`
- Enables hierarchical project hubs without child tier clutter

**update_ticket Resolution** (`src/mcp_ticket_ops.py`):
- Accepts optional `hive_name` parameter for O(1) config lookup
- Falls back to O(n) scan if hive_name not provided
- Does NOT enforce type validation (type is immutable after creation)
- Resolves hive purely for locating ticket file

**Example Scenarios**:

*Hive with custom tiers*:
```json
"hives": {
  "backend": {
    "child_tiers": {
      "t1": ["Task", "Tasks"],
      "t2": ["Subtask", "Subtasks"]
    }
  }
}
```
- create_ticket with type="t3" → Error: "Invalid ticket type 't3' for hive 'backend'"
- create_ticket with type="t1" → Success

*Bees-only hive*:
```json
"hives": {
  "hub": {
    "child_tiers": {}
  }
}
```
- create_ticket with type="bee" → Success
- create_ticket with type="t1" → Error: "Hive 'hub' is configured as bees-only. Only bee (t0) tickets can be created."

### get_types MCP Tool / get-types CLI

The `get_types` MCP tool (and `bees get-types` CLI command) reads raw `child_tiers` from all three configuration levels independently, without inheritance resolution. This provides visibility into how child tiers are configured at each level before fallback is applied.

**Parameters**:
- None. The tool uses the current repo root to locate the matching scope.

**Return value**:
- `global`: The raw `child_tiers` from the top-level config (dict or null)
- `scope`: The raw `child_tiers` from the matched scope block (dict or null)
- `hives`: A dictionary mapping each normalized hive name to its raw `child_tiers` (dict or null per hive)

All values are raw/stored — not resolved through the fallback chain. Null indicates the key is absent or unset at that level. `{}` (empty dict) indicates explicitly configured bees-only mode. Every registered hive in the matched scope appears in the `hives` dictionary regardless of whether it has explicit child_tiers.

**Scope targets**:
- Uses `find_matching_scope()` to locate the matching scope block for the current repo root
- Returns `no_matching_scope` error if no scope pattern matches

**Error types**: `no_matching_scope`

**CLI examples**:

View child tiers at all levels:
```
bees get-types
```

**Implementation**: See `_get_types()` in `src/mcp_ticket_ops.py`.

### set_types MCP Tool / set-types CLI

The `set_types` MCP tool (and `bees set-types` CLI command) writes or removes the `child_tiers` key at any of the three configuration levels without requiring manual edits to `~/.bees/config.json`.

**Parameters**:
- `scope` (required): `"global"`, `"repo_scope"`, or `"hive"`
- `hive_name`: Required when `scope="hive"`; normalized before lookup
- `child_tiers`: The value to write. `{}` is valid (bees-only). Required unless `unset=True`.
- `unset`: Remove the `child_tiers` key from the target level (idempotent)

**Scope targets**:
- `global`: Reads/writes the top-level `child_tiers` key in `~/.bees/config.json`
- `repo_scope`: Uses `find_matching_scope()` to locate the matching scope block; returns `no_matching_scope` if none matches
- `hive`: Normalizes `hive_name`, searches all scope blocks for the hive entry; returns `hive_not_found` if absent

**Write path**: All writes go through `save_global_config()`, which provides atomic write (tempfile + `os.replace`) and cache invalidation.

**Validation ordering** (per SR-2.3):
1. Parameter checks (`invalid_scope`, `conflicting_params`, `missing_child_tiers`, `missing_hive_name`) — before any config load
2. `invalid_child_tiers` validation via `_parse_child_tiers_data()` — after parameter checks, before config load
3. Config load and write

**Error types**: `invalid_scope`, `missing_hive_name`, `hive_not_found`, `no_matching_scope`, `invalid_child_tiers`, `missing_child_tiers`, `conflicting_params`

**Implementation**: See `_set_types()` in `src/mcp_ticket_ops.py`.

## Hive Registry

The hive registry tracks all registered hives within a scope, mapping normalized names to their filesystem locations and metadata.

**Structure**: The `hives` dictionary within a scope serves as the authoritative registry:
- Keys: Normalized hive names (see Name Normalization section)
- Values: HiveConfig objects with display_name, path, and created_at fields

**Lookup Strategy**:
1. Primary: Load global config → match scope → check hives dictionary using normalized name
2. Fallback: Scan filesystem for `.hive/identity.json` markers if config lookup fails

**Identity Markers**: Each hive directory contains `.hive/identity.json` with:
```json
{
  "normalized_name": "back_end",
  "display_name": "Back End",
  "created_at": "2026-02-03T10:30:45.123456",
  "child_tiers": {
    "t1": ["Task", "Tasks"],
    "t2": ["Subtask", "Subtasks"]
  },
  "status_values": ["pupa", "worker", "finished"]
}
```

The `child_tiers` and `status_values` keys in identity.json are the authoritative source for hive-level overrides of these settings. Absent keys mean the hive inherits from scope/global. See the Child Tiers Configuration and Status Values Configuration sections for resolution semantics.

**Operations**:
- `colonize_hive(name, path, child_tiers=None)`: Register new hive, create identity marker, write to global config. Creates exact-path scope if no scope matches. Optional `child_tiers` parameter allows setting per-hive tier configuration at creation time (see Hive Colonization section below).
- `abandon_hive(name)`: Remove from all matching scopes' hive registries, leave filesystem intact. See Hive Scope Inheritance section for multi-scope behavior.
- `rename_hive(old_name, new_name)`: Update scope registry and identity marker. Ticket IDs are globally unique and NOT rewritten during rename. When the hive exists in exactly one matching scope (the "owning scope"), the operation targets that scope automatically. Error types: `config_conflict` (hive exists in multiple overlapping scopes — use `abandon_hive` to resolve), `hive_not_found` (hive is not visible to the current repo).
- `sanitize_hive(name)`: Validate and auto-fix malformed tickets in a hive. When the hive exists in exactly one matching scope (the owning scope), the operation targets that scope automatically. Error types: `config_conflict` (hive exists in multiple overlapping scopes — use `abandon_hive` to resolve), `hive_not_found` (hive is not visible to the current repo).

The **owning scope** is the single scope that defines a hive when no conflict exists. In a multi-scope environment, if only one matching scope contains the hive, that scope is the owning scope and operations proceed without ambiguity.

**Functions**:
- `get_scope_key_for_hive(normalized_hive_name: str, global_config: dict, repo_root: Path) -> list[str]`: Returns all matching scope keys that contain the given hive, filtered to scopes that match repo_root.

## Name Normalization

Hive names are normalized to ensure consistent identification across the system while preserving user-friendly display names.

**Normalization Rules** (`normalize_hive_name()` in `src/id_utils.py`):
1. Convert to lowercase
2. Replace spaces and hyphens with underscores
3. Remove all special characters (keep only letters, numbers, underscores)
4. Ensure name starts with letter or underscore (prefix with underscore if starts with digit)

**Examples**:
- "Back End" → "back_end"
- "front-end" → "front_end"
- "Multi Word Name" → "multi_word_name"
- "2024-project" → "_2024_project"

**Collision Prevention**:
- `colonize_hive_core` performs a pre-write cross-scope conflict check: before any filesystem writes, it scans all global scopes for overlapping scope patterns with the same normalized hive name
- `duplicate_hive_name` is returned when the same normalized name exists in the exact same scope pattern
- `cross_scope_hive_conflict` is returned when the same normalized name exists in an overlapping (but not identical) scope pattern
- Non-overlapping scopes may freely define the same hive name without conflict
- Display names are preserved in `HiveConfig.display_name` for UI/reports

## Config API

The config module provides a type-safe dataclass API for all config operations.

**Global Config (low-level)**:
- `load_global_config() -> dict`: Read entire `~/.bees/config.json` as raw dict
- `save_global_config(global_config: dict)`: Atomically write entire global config

**Scoped Config (high-level)**:
- `load_bees_config() -> BeesConfig | None`: Load config for current repo_root from context
- `save_bees_config(config: BeesConfig, scope_pattern: str)`: Save config to the specified scope pattern (required parameter, no longer infers scope internally).
- `parse_scope_to_bees_config(scope_data: dict) -> BeesConfig`: Parse a scope dict into BeesConfig
- `serialize_bees_config_to_scope(config: BeesConfig) -> dict`: Serialize BeesConfig to scope dict

**Context Management**: `repo_root` flows through Python's `contextvars.ContextVar` (see `src/repo_context.py`), eliminating the need to thread it through function parameters. MCP entry points set the context via `repo_root_context(resolved_root)`.

## Reference Materials Resolution

The reference_materials system enables per-entry resolution of values from bee tickets. Each entry in the `reference_materials` list can specify its own named resolver; resolution happens automatically when tickets are read via `show_ticket`.

### Per-Entry Resolution

Resolution is driven by each entry's `resolver` key (defaults to `"file-path"` when absent):

```json
{
  "reference_materials": [
    {"value": "src/main.py"},
    {"value": "abc-guid-123", "resolver": "guid_resolver"}
  ]
}
```

**Resolver selection per entry**:
- No `resolver` key, `"file-path"`, or `"default"`: Use the built-in `file-path` resolver (file-path validation)
- `"github"`: Use the built-in GitHub resolver (fetches issue/PR data via `gh api`)
- `"bees"`: Use the built-in bees resolver (identity — returns value as-is)
- Named resolver (e.g., `"guid_resolver"`): Look up in the global `resolvers` registry and invoke as subprocess

There is no fallback chain at the scope or hive level for resolver selection. The resolver is chosen per entry, not per hive.

### Custom Resolver Interface

Custom resolvers are invoked as subprocesses with two arguments:
- `--repo-root {path}`: Absolute path to repository root
- `--value {shlex.quote(value)}`: The entry's `value` field (shell-quoted; non-string values are JSON-encoded)

**Output Requirements**:
- Must print valid JSON to stdout
- Exit code must be 0 for success
- Non-zero exit code treated as error

**Timeout Handling**:
- Configured per resolver in the global `resolvers` registry via the `timeout` field
- Process killed if execution exceeds configured timeout

### Implementation

**Functions**:
- `_resolve_references(reference_materials, repo_root) -> list | None`: Resolve all entries in a `reference_materials` list. Each entry is resolved independently; a failure on one does not affect others.
- `resolve_file_path(value, repo_root) -> dict`: Built-in default resolver; validates file path existence.
- `_invoke_custom_resolver(command, value, repo_root, timeout) -> Any`: Invoke a named resolver script as a subprocess.

**Integration**: `show_ticket` in `src/mcp_ticket_ops.py` calls `_resolve_references()` for each bee ticket when `allowed_resolvers` is configured for the hive. The `reference_materials` field in the response contains the original entries augmented with a `resolved` key for each entry.

## Status Values Configuration

Status values configuration constrains which status strings are valid for tickets in a given hive. This enables project-specific status workflows while maintaining flexibility for different team needs.

### Configuration Levels

Status values can be configured at three levels:

**Global Level** (top-level in `~/.bees/config.json`):
```json
{
  "status_values": ["pupa", "larva", "worker", "finished"],
  "scopes": { ... }
}
```

**Scope Level** (within a scope in `~/.bees/config.json`):
```json
{
  "scopes": {
    "/path/to/repo": {
      "status_values": ["todo", "in_progress", "done"],
      "hives": { ... }
    }
  }
}
```

**Hive Level** (within `.hive/identity.json` in the hive directory):
```json
{
  "normalized_name": "normalized_name",
  "display_name": "Display Name",
  "created_at": "2026-02-03T10:30:45.123456",
  "status_values": ["open", "closed"]
}
```

Hive-level status_values are stored in `.hive/identity.json`, not in the config.json hive entry. The `colonize_hive` tool writes this value at creation time.

### Resolution Order

Status values are resolved using a 3-level fallback chain with a default:

1. **Hive level**: Read `status_values` from the hive's `.hive/identity.json`
2. **Scope level**: Check scope's `status_values`
3. **Global level**: Check top-level `status_values`
4. **Default**: Return `None` (freeform - any string accepted)

### Fallback Semantics

**Key absent from identity.json**: Fall through to next level in the chain
**null in identity.json**: Explicit override — stop inheritance and return `None` (freeform)
**Non-empty list in identity.json**: Stop fallback chain and use this exact configuration
**[] (empty list) at scope/global**: Fall through to next level (treated as absent)
**Non-empty list at scope/global**: Stop fallback chain and use this exact configuration

### No Merging

Each level completely replaces the status_values configuration — there is NO merging of status values between levels. When a level provides a non-empty status_values list, that exact configuration is used and the fallback chain stops.

### Validation Rules

**status_values**:
- Must be list of strings or null
- Empty list `[]` is treated as absent (falls through to next level)
- Global validation: `load_global_config()` checks global-level field
- Scope validation: `parse_scope_to_bees_config()` checks scope-level field
- Hive validation: Hive-level status_values are read from `.hive/identity.json` at resolution time

### Implementation

**Function**:
- `resolve_status_values_for_hive(normalized_hive, config) -> list[str] | None`: Resolve status_values using 3-level fallback. Returns None for freeform mode (any string accepted).

### Linter Integration

The linter validates ticket status fields against resolved status_values configuration:
- Calls `resolve_status_values_for_hive()` to get allowed values for each ticket's hive
- If resolved list is non-empty: Validates status is in the allowed list (error: `invalid_status`)
- If resolved list is None (freeform mode): Accepts any string value
- Type validation: status must always be a string regardless of configuration (error: `invalid_field_type`)

### set_status_values MCP Tool / set-status-values CLI

The `set_status_values` MCP tool (and `bees set-status-values` CLI command) writes or removes the `status_values` key at any of the three configuration levels without requiring manual edits to `~/.bees/config.json`.

**Parameters**:
- `scope` (required): `"global"`, `"repo_scope"`, or `"hive"`
- `hive_name`: Required when `scope="hive"`; normalized before lookup
- `status_values`: List of allowed status strings to write (e.g., `["open", "worker", "finished"]`). Required unless `unset=True`. Empty list `[]` is treated identically to `unset=True`.
- `unset`: If True, remove `status_values` from the target level (idempotent)

**Scope targets**:
- `global`: Reads/writes the top-level `status_values` key in `~/.bees/config.json`
- `repo_scope`: Uses `find_matching_scope()` to locate the matching scope block; returns `no_matching_scope` if none matches
- `hive`: Normalizes `hive_name`, searches the matched scope's hive entries; returns `hive_not_found` if absent

**Write path**: All writes go through `save_global_config()`, which provides atomic write (tempfile + `os.replace`) and cache invalidation.

**Input normalization**:
- **Empty list equals unset**: Passing `status_values=[]` is treated identically to `unset=True` — the `status_values` key is removed from the target level rather than written as an empty list
- **Deduplication**: Duplicate entries are silently removed, preserving first occurrence (e.g., `["open", "open", "done"]` → `["open", "done"]`)

**Validation ordering**:
1. Parameter checks (`invalid_scope`, `conflicting_params`, `missing_status_values`, `missing_hive_name`) — before any config load
2. `invalid_status_values` validation — after parameter checks, before config load
3. Config load and write

**Error types**: `invalid_scope`, `missing_hive_name`, `hive_not_found`, `no_matching_scope`, `invalid_status_values`, `missing_status_values`, `conflicting_params`

**Examples**:

Global set:
```
bees set-status-values --scope=global --values '["pupa","worker","finished"]'
```

Hive set:
```
bees set-status-values --scope=hive --hive features --values '["pupa","worker"]'
```

Global unset:
```
bees set-status-values --scope=global --unset
```

**Implementation**: See `_set_status_values()` in `src/mcp_ticket_ops.py`.

### get_status_values MCP Tool / get-status-values CLI

The `get_status_values` MCP tool (and `bees get-status-values` CLI command) reads raw `status_values` from all three configuration levels independently, without inheritance resolution. This provides visibility into how status values are configured at each level before fallback is applied.

**Parameters**:
- None. The tool uses the current repo root to locate the matching scope.

**Return value**:
- `global`: The raw `status_values` from the top-level config (list of strings or null)
- `scope`: The raw `status_values` from the matched scope block (list of strings or null)
- `hives`: A dictionary mapping each normalized hive name to its raw `status_values` (list of strings or null per hive)

All values are raw/stored — not resolved through the fallback chain. Null indicates the key is absent or unset at that level. Every registered hive in the matched scope appears in the `hives` dictionary regardless of whether it has explicit status_values.

**Scope targets**:
- Uses `find_matching_scope()` to locate the matching scope block for the current repo root
- Returns `no_matching_scope` error if no scope pattern matches

**Error types**: `no_matching_scope`

**CLI examples**:

View status values at all levels:
```
bees get-status-values
```

**Implementation**: See `_get_status_values()` in `src/mcp_ticket_ops.py`.

## Named Queries Configuration

Named queries allow reusable query pipelines to be stored in config and executed by name. Queries are stored at two levels: global (top-level) and repo scope.

### Data Structure

The `queries` key is a dictionary mapping query name strings to query dicts. Each query dict has a `stages` key containing a list of stages (list of lists of strings), matching the output of `QueryParser.parse_and_validate()`.

**Global Level** (top-level in `~/.bees/config.json`):
```json
{
  "queries": {
    "open_bees": {"stages": [["type=bee", "status=open"]]},
    "bees_with_children": {"stages": [["type=bee"], ["children"]]}
  },
  "scopes": { ... }
}
```

**Repo Scope Level** (within a scope):
```json
{
  "scopes": {
    "/path/to/repo": {
      "queries": {
        "open_tasks": {"stages": [["type=t1", "status=open"]]},
        "finished_epics": {"stages": [["type=t1", "status=finished"]]}
      },
      "hives": { ... }
    }
  }
}
```

### Resolution Order

The `resolve_named_query()` function determines which query to use:

1. **Repo scope**: Check the matched scope's `queries` dict
2. **Global level**: Check the top-level `queries` dict
3. **Out-of-scope detection**: If found in a different repo's scope, return `out_of_scope` (not accessible)
4. **Not found**: Query does not exist anywhere

Repo scope queries shadow global queries of the same name — if the same name exists at both levels, the repo scope version is used.

### Conflict Detection

Before saving a new query, `check_query_name_conflict()` prevents name collisions:

**For scope="repo"**: Checks the caller's own repo scope `queries` and the global `queries`. Other repo scopes are invisible (mutually inaccessible).

**For scope="global"**: Checks the global `queries` and every scope entry in the entire config. A global query cannot shadow or be shadowed by any existing query.

If a conflict is detected, the operation returns a `query_name_conflict` error with the conflict level and location.

### Validation

Queries are validated at registration time via `QueryParser.parse_and_validate()`. Only structurally valid query pipelines can be stored. The validated query is persisted as a dict with a `stages` key — `{"stages": [...]}`. The original YAML string is not retained.

### Implementation

**Functions**:
- `resolve_named_query(name, repo_root, global_config) -> dict`: Resolve a query name using 2-level fallback with out-of-scope detection. In `src/config.py`.
- `check_query_name_conflict(name, scope, repo_root, global_config) -> dict | None`: Check for name conflicts before saving. In `src/config.py`.
- `_add_named_query(name, query_yaml, scope, resolved_root) -> dict`: Register a new named query in config-backed storage. In `src/mcp_query_ops.py`.
- `_delete_named_query(name, resolved_root) -> dict`: Remove a named query from config-backed storage with empty-dict cleanup; searches global then repo scope. In `src/mcp_query_ops.py`.
- `_list_named_queries(resolved_root) -> dict`: List queries accessible from the current repo scope (matched repo-scoped queries + global queries). In `src/mcp_query_ops.py`.

## Named Resolver Registry

The named resolver registry stores resolver scripts by name in the top-level `resolvers` key of `~/.bees/config.json`. This is global — resolver names are shared across all scopes.

### Schema

```json
{
  "resolvers": {
    "guid_resolver": {
      "path": "/projects/myrepo/resolvers/guid_resolver.py",
      "timeout": 10,
      "convention": "Store the GUID from the .guid file in the reference_materials value field."
    },
    "path_resolver": {
      "path": "/projects/myrepo/resolvers/path_resolver.py"
    }
  }
}
```

Each resolver entry:
- `path` (required): Absolute path to the resolver script.
- `timeout` (optional): Execution timeout in seconds. Must be positive.
- `convention` (optional): Free-text description of what to store in the `reference_materials` value field. Auto-extracted from the script's `## RESOLVER CONVENTION` docstring block when registering.

The names `"file-path"`, `"github"`, `"bees"`, and `"default"` are reserved for built-in resolvers and cannot be registered or overwritten. (`"default"` is a backward-compatible alias for `"file-path"`.)

### Commands

- `bees set-resolver --name <name> --path <path> [--timeout <s>]` — Register or update a resolver.
- `bees set-resolver --name <name> --unset` — Remove a resolver. Fails if any hive's `allowed_resolvers` still references the name.
- `bees get-resolvers` — List all registered resolvers plus the three built-in entries (`file-path`, `github`, `bees`).

### Built-in Resolvers

`get-resolvers` always returns the built-in entries with `built_in: true` and `path: null`. They cannot be overwritten via `set-resolver`.

- **`file-path`** (also aliased as `"default"`): Used when no `resolver` key is specified in a `reference_materials` entry. Accepts a string file path (absolute or relative), resolves relative paths against `repo_root`, and checks for existence.
- **`github`**: Resolves GitHub issue and pull request URLs. Invokes `gh api` to fetch issue/PR data and returns `{"issue": ..., "comments": ...}`. Requires the `gh` CLI on PATH.
- **`bees`**: Identity resolver for Bee ticket IDs. Returns the value as-is.

### allowed_resolvers on HiveConfig

`allowed_resolvers` on a hive entry restricts which resolver names may be used for that hive. Each name must exist in the registry or be one of the built-in names (`"file-path"`, `"github"`, `"bees"`, or `"default"`). Validated at colonize time — unknown names return `unknown_resolver`.

```json
{
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "my_hive": {
          "path": "/path/to/repo/.bees/hives/my_hive",
          "display_name": "My Hive",
          "created_at": "2026-01-01T00:00:00",
          "allowed_resolvers": ["guid_resolver", "file-path"]
        }
      }
    }
  }
}
```

Set via `colonize-hive --allowed-resolvers '["guid_resolver","file-path"]'`.

### Implementation

- `ResolverEntry` dataclass in `src/config.py`
- `load_resolver_registry()` / `save_resolver_registry()` in `src/config.py`
- `_set_resolver()` / `_get_resolvers()` in `src/mcp_resolver_ops.py`

### Config Migration: `default` → `file-path`

When bees upgrades a config that was written before the `file-path` rename, it migrates any `"default"` references in the resolver registry and `allowed_resolvers` lists to `"file-path"`. This migration is applied by the v2→v3 schema upgrade, which runs when `update-config` is invoked. No manual action is required.

## Hive Colonization

The `colonize_hive` MCP tool creates and registers new hives with optional per-hive child_tiers configuration.

### colonize_hive Parameters

```python
colonize_hive(
    name: str,
    path: str,
    child_tiers: dict[str, list] | None = None,
    scope: str | None = None,
    allowed_resolvers: list[str] | None = None,
)
```

**Required Parameters**:
- `name`: Display name for the hive (e.g., "Back End", "Frontend")
- `path`: Absolute path to the directory where the hive should be created

**Optional Parameters**:
- `child_tiers`: Per-hive child tiers configuration (dict or None)
- `scope`: Scope pattern under which to register the hive (str or None)
- `allowed_resolvers`: List of resolver names permitted for this hive (list of strings or None). Each name must exist in the global resolver registry or be one of the built-in names (`"file-path"`, `"github"`, `"bees"`, or `"default"`). Returns `unknown_resolver` error if any name is unregistered.

### scope Parameter Semantics

The `scope` parameter controls which scope key the hive is registered under in `~/.bees/config.json`.

**When omitted (None, default)**: The hive is registered under an exact-path scope derived from the current repo root. If no scope matching the repo root exists, a new exact-path scope is created automatically.

**When provided**: The hive is registered directly under the given scope key. The pattern must be a valid canonical scope form — exact/trailing-slash (e.g. `/projects/myrepo/`), single-level wildcard (`/projects/*`), or recursive wildcard (`/projects/**`). If the scope key does not yet exist in config, it is created. Use this to share a hive across multiple repos that all fall under a common wildcard scope.

**Scope validation order**:
1. Pattern syntax is validated — wildcards are only allowed as terminal `/*` or `/**` suffixes. Violations return `invalid_scope_pattern`.
2. The normalized hive name is checked against all scope keys that overlap the candidate pattern. If the same name exists in the exact same scope, `duplicate_hive_name` is returned. If it exists in an overlapping but different scope, `cross_scope_hive_conflict` is returned. Non-overlapping scopes may freely share the same hive name.

**Error types**:
- `invalid_scope_pattern`: The scope string contains wildcards in invalid positions (mid-path or without a leading `/`)
- `duplicate_hive_name`: The normalized hive name already exists in the exact same scope pattern
- `cross_scope_hive_conflict`: The normalized hive name already exists in an overlapping (but not identical) scope, which would make the hive inaccessible or ambiguous for repos that match both scopes

### child_tiers Parameter Semantics

The `child_tiers` parameter supports three semantic states that control how the hive resolves its tier configuration:

**1. `None` (default, parameter omitted)**:
- Hive does NOT store a child_tiers key in identity.json
- Enables fallback chain: hive → scope → global → default
- Hive inherits tier configuration from parent scope or global level
- Use when hive should follow standard project tier configuration

**2. `{}` (empty dictionary)**:
- Hive stores `"child_tiers": {}` in identity.json (empty dict persisted)
- Stops fallback chain immediately
- Hive operates in bees-only mode (no child tiers allowed)
- Use for project hub hives that only track top-level bees

**3. Populated dictionary (e.g., `{"t1": ["Task", "Tasks"]}`)**:
- Hive stores exact tier configuration in identity.json
- Stops fallback chain immediately
- Hive uses its own custom tier hierarchy
- Use when hive needs different tier structure than project default

### Validation

When `child_tiers` is provided (not None), validation occurs at Step 4.5 in `colonize_hive_core()`:
- Calls `_parse_child_tiers_data()` to validate structure
- Validates tier keys follow pattern `t[0-9]+` (t1, t2, t3, etc.)
- Validates no gaps in tier sequence (t1, t2 valid; t1, t3 invalid)
- Validates friendly names are 2-element arrays `[singular, plural]`
- Returns error if validation fails

### Storage

**Config Storage** (`~/.bees/config.json`):
```json
{
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "backend": {
          "path": "/path/to/repo/tickets/backend",
          "display_name": "Back End",
          "created_at": "2026-02-16T12:00:00"
        },
        "hub": {
          "path": "/path/to/repo/tickets/hub",
          "display_name": "Project Hub",
          "created_at": "2026-02-16T12:00:00"
        },
        "frontend": {
          "path": "/path/to/repo/tickets/frontend",
          "display_name": "Frontend",
          "created_at": "2026-02-16T12:00:00"
        }
      }
    }
  }
}
```

Hive entries in config.json store path, display name, and metadata. Hive-level `child_tiers` and `status_values` are stored in each hive's `.hive/identity.json` file (see Identity Markers in the Hive Registry section).

**Identity Storage** (`.hive/identity.json` within each hive directory):

In this example:
- `backend` hive has custom tiers (t1, t2) in its identity.json → Uses own configuration
- `hub` hive has `"child_tiers": {}` in its identity.json → Bees-only mode
- `frontend` hive has no `child_tiers` key in its identity.json → Inherits from scope/global

**Note**: The `.hive/identity.json` marker stores `child_tiers` and `status_values` as the authoritative source for hive-level overrides. The runtime resolution functions read from identity.json at the hive level, not from config.json hive entries.

### Usage Examples

**Default behavior (inherit from scope/global)**:
```python
colonize_hive("Frontend", "/path/to/repo/tickets/frontend")
# child_tiers omitted → inherits from scope/global config
```

**Bees-only hive (project hub)**:
```python
colonize_hive(
    "Project Hub",
    "/path/to/repo/tickets/hub",
    child_tiers={}
)
# Empty dict → bees-only mode, no child tiers allowed
```

**Custom hive-specific tiers**:
```python
colonize_hive(
    "Backend",
    "/path/to/repo/tickets/backend",
    child_tiers={
        "t1": ["Task", "Tasks"],
        "t2": ["Subtask", "Subtasks"]
    }
)
# Custom tiers → hive uses own tier configuration
```

### Integration with Tier Resolution

The `child_tiers` parameter integrates with the 3-level fallback chain described in the "Child Tiers Configuration" section:

1. If hive has `child_tiers` key in identity.json (empty or populated), use that value
2. If hive has no `child_tiers` key in identity.json, fall back to scope level
3. If scope has no `child_tiers`, fall back to global level
4. If global has no `child_tiers`, default to `{}` (bees-only)

The distinction between "key absent" and "key present with empty dict" ({}) in identity.json is critical for correct fallback behavior.

### Implementation

**Functions**:
- `colonize_hive_core(name, path, child_tiers, ctx)`: Core implementation in `src/mcp_hive_ops.py`
- `_colonize_hive(name, path, child_tiers, ctx)`: MCP tool wrapper
- `_parse_child_tiers_data(data)`: Validation function in `src/config.py`

## Atomic Write Strategy

Configuration writes use an atomic write-to-temp-then-rename pattern to prevent corruption from crashes or interrupted operations.

### Write Pattern

1. **Create temp file**: `tempfile.mkstemp()` in `~/.bees/` directory with prefix `.config.json.`
2. **Write JSON**: `json.dump()` with `indent=2` formatting and trailing newline
3. **Atomic rename**: `os.replace()` atomically moves temp file to `config.json`
4. **Cleanup on error**: Delete temp file in except block if write fails

### Consistency Guarantees

**POSIX Atomicity**: `os.replace()` uses the rename syscall, which is atomic on POSIX systems. This ensures:
- No partial file states visible to readers
- Either old config remains intact or new config is complete
- No race conditions between concurrent readers/writers

**Crash Safety**: If process crashes during write:
- Before rename: Old config remains unchanged, temp file orphaned
- After rename: New config is complete and consistent

**Implementation**: See `save_global_config()` in `src/config.py`.

## Test Mode (--test-config)

The `--test-config` flag activates an in-memory config mode for isolated testing. When active, `~/.bees/config.json` is never read from or written to for the lifetime of the process.

### Accepted Value Forms

The flag accepts three value forms:

- **Bare flag or no value**: Produces an empty in-memory config — `{"schema_version": "2.0", "scopes": {}}`
- **Value starting with `{`**: Parsed as inline JSON
- **Any other value**: Treated as a file path; the file is read and parsed as JSON

### Schema Validation

After resolving the config dict from whichever form is provided, the dict is validated (must contain `schema_version` and `scopes` keys at minimum) before the server starts. Invalid configs cause an error and early exit.

### In-Memory Behavior

The resolved config dict is installed into `_GLOBAL_CONFIG_OVERRIDE`. For the remainder of the process lifetime:

- `load_global_config()` returns `_GLOBAL_CONFIG_OVERRIDE` directly, skipping disk I/O and the mtime cache
- `save_global_config()` mutates `_GLOBAL_CONFIG_OVERRIDE` in place instead of writing to disk

All config mutations (hive registration, named query additions, etc.) are applied to the in-memory dict only.

### Ephemeral State

Config state is discarded on process exit. Nothing is written to `~/.bees/config.json` on shutdown. Each server invocation with `--test-config` starts from the provided initial config.

### Mutual Exclusion with --config

`--test-config` and `--config` cannot be used together. Providing both flags causes an error on stderr and process exit before any initialization work begins.

### Thread Safety

`_TEST_CONFIG_LOCK` (a `threading.Lock`) protects `_GLOBAL_CONFIG_OVERRIDE` from concurrent access. Both `load_global_config()` and `save_global_config()` acquire this lock when checking or mutating the override, ensuring safe concurrent access from the undertaker daemon thread and the async event loop.

### Scope

`--test-config` applies to `bees serve` and all non-serve CLI subcommands. Ticket file reads and writes are unaffected — only the global config layer is redirected to memory.

**Implementation**: See `_GLOBAL_CONFIG_OVERRIDE`, `_TEST_CONFIG_LOCK`, and `set_test_config_override()` in `src/config.py`.

## Hive Scope Inheritance

When multiple scope patterns in the global config match a repository root, bees collects hives from all of them. This produces a merged union of hives visible to the repo — the hive scope inheritance model.

### Multi-Scope Hive Collection

The function `find_all_matching_scopes()` returns every scope pattern that matches the current repo root, ordered from least-specific to most-specific. Bees iterates these scopes and merges their hive registries into a single view. When the same normalized hive name appears in multiple matching scopes, the most-specific scope wins (last-write-wins during iteration). The `list_hives` tool returns a `scope` field on each hive entry indicating which scope pattern owns the definition.

### Hive Name Conflict Rule

A conflict exists when two overlapping scopes that both match the current repo root define a hive with the same normalized name. Because both scopes contribute hives to the merged view, the system cannot safely determine which definition to use. The function `detect_hive_conflicts()` in `src/config.py` scans all matching scopes and returns a `ConflictRecord` for every conflicting (hive name, scope A, scope B) pair. Conflicts in scopes that do not match the current repo root are invisible and have no effect.

### Degraded State

When one or more hive name conflicts exist, the system enters degraded state. In degraded state, all hive-dependent operations are blocked and return an error with `error_type: config_conflict`. The error message enumerates each conflict, listing the hive name and the two scope patterns involved.

**Blocked operations** (return `config_conflict` error in degraded state):

- Ticket operations: `create_ticket`, `show_ticket`
- Hive management: `list_hives`, `rename_hive`, `sanitize_hive`
- Movement and indexing: `move_bee`, `generate_index`
- Query operations: `add_named_query`, `delete_named_query`, `list_named_queries`, `execute_named_query`, `execute_freeform_query`

**Not blocked** (continue to work in degraded state):

- `abandon_hive` and `colonize_hive` — these are the primary tools for resolving conflicts
- `update_ticket`, `delete_ticket`, `clone_bee` — ticket mutations that do not require hive registry resolution
- `set_types`, `set_status_values`, `get_types`, `get_status_values` — config-only operations that do not depend on the hive registry
- `health_check`

The conflict guard is implemented by `check_for_config_conflicts()` in `src/config.py`, which each blocked operation calls before executing any business logic.

### Resolving Conflicts

The primary resolution mechanism is `abandon_hive`. Because it is not blocked in degraded state, an operator can call it on the conflicting hive name to remove the duplicate definition. When `abandon_hive` removes a hive that exists in multiple matching scopes, it removes the hive from all of them in a single config save, resolving the conflict atomically.

Alternatively, `colonize_hive` can be used to re-register a hive under a different scope or with a different name, depending on the operator's intent.

After the conflict is resolved, subsequent operations resume normal behavior.

### The scope Field in list_hives Output

Each hive entry returned by `list_hives` includes a `scope` field — the scope pattern string that owns the hive definition. This makes it possible to identify which scope contributed each hive when multiple scopes match the repo root. The field is always present on every hive entry.

### abandon_hive Multi-Scope Behavior

The `abandon_hive` tool removes a hive from the config registry across all matching scopes in a single operation. Its success response includes two fields that reflect this multi-scope behavior:

- `scopes_modified` (int): The count of scope patterns from which the hive was removed. A value of 1 means the hive existed in a single scope; a value of 2 or more indicates the hive was defined in multiple overlapping scopes (the conflict scenario).
- `scopes` (list of strings): The scope pattern strings that were modified. Each entry is a canonical scope pattern from which the hive entry was removed.

The tool uses `get_scope_key_for_hive()` to find all matching scopes that define the target hive, removes the hive from every such scope, and applies all removals in a single `save_global_config()` call.

**Error types**: `hive_not_found` — returned when the normalized hive name does not exist in any scope matching the current repo root.

**Implementation**: See `_abandon_hive()` in `src/mcp_hive_ops.py`.
