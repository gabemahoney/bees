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
    "global_open_bees": [["type=bee", "status=open"]]
  },
  "scopes": {
    "/Users/dev/projects/myrepo": {
      "hives": {
        "normalized_name": {
          "display_name": "Display Name",
          "path": "/absolute/path/to/hive",
          "created_at": "2026-02-03T10:30:45.123456",
          "child_tiers": {
            "t1": ["Task", "Tasks"],
            "t2": ["Subtask", "Subtasks"]
          }
        }
      },
      "child_tiers": {
        "t1": ["Story", "Stories"],
        "t2": ["Feature", "Features"]
      },
      "queries": {
        "open_tasks": [["type=t1", "status=open"]],
        "all_bees_with_children": [["type=bee"], ["children"]]
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
- `delete_with_dependencies`: (Optional) Boolean, default `false`. When `true`, deleting a ticket automatically removes its ID from surviving tickets' `up_dependencies` and `down_dependencies` arrays before deletion. **Global-only** — cannot be set at scope or hive level.
- `auto_fix_dangling_refs`: (Optional) Boolean, default `false`. When `true`, `sanitize_hive` automatically removes dangling dependency and parent references from ticket files instead of reporting them as errors. Each fix is recorded in the response as `remove_dangling_dependency` or `clear_dangling_parent`. **Global-only** — cannot be set at scope or hive level.
- `scopes`: Dictionary mapping directory patterns to scope configurations

**Scope Fields**:
- `hives`: Dictionary mapping normalized hive names to HiveConfig objects
- `child_tiers`: (Optional) Scope-level child_tiers configuration (dict or null). See Child Tiers Configuration below.
- `queries`: (Optional) Scope-level named queries dictionary. See Named Queries Configuration below.
- `egg_resolver`: (Optional) Scope-level egg resolver command (string or null). See Egg Resolver Configuration below.
- `egg_resolver_timeout`: (Optional) Scope-level timeout in seconds for egg resolver execution (number or null). Must be positive if specified.

**Hive Fields**:
- `path`: Absolute path to hive directory
- `display_name`: User-friendly display name
- `created_at`: ISO 8601 timestamp of hive creation
- `child_tiers`: (Optional) Hive-level child_tiers configuration (dict or null). See Child Tiers Configuration below.
- `egg_resolver`: (Optional) Hive-level egg resolver command (string or null). See Egg Resolver Configuration below.
- `egg_resolver_timeout`: (Optional) Hive-level timeout in seconds for egg resolver execution (number or null). Must be positive if specified.

**Note**: Ticket IDs are globally unique across all hives. Dependencies can reference tickets in any hive, with same-tier restriction (bee→bee, t1→t1, etc.).

**Implementation**: See `src/config.py` for BeesConfig, HiveConfig dataclasses, scope matching, and load/save functions.

## Scope Pattern Matching

Scope keys are directory paths supporting glob wildcards:

- **Exact path**: `/Users/dev/projects/myrepo` matches only that directory
- **`*`**: Matches within a single path segment. `/Users/dev/projects/bees*` matches `bees`, `bees_other`, `bees123` but not `bees/worktree`
- **`**`**: Matches recursively through subdirectories. `/Users/dev/projects/bees/**` matches `bees`, `bees/worktree`, `bees/deep/path`

**Resolution**: First matching scope wins (evaluated in declaration order). More specific patterns should be listed before general ones.

**Implementation**: `match_scope_pattern()` converts patterns to regex (`**` → `(/.*)?`, `*` → `[^/]*`) and uses `re.fullmatch()`. Results are cached per pattern.

**Functions**:
- `match_scope_pattern(repo_root, pattern) -> bool`: Check if repo_root matches a scope pattern
- `find_matching_scope(repo_root, global_config) -> str | None`: Find first matching scope pattern
- `get_scoped_config(repo_root) -> BeesConfig | None`: Load global config, match scope, return BeesConfig

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

**Hive Level** (within a hive entry):
```json
{
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "normalized_name": {
          "path": "/absolute/path/to/hive",
          "child_tiers": {
            "t1": ["Task", "Tasks"],
            "t2": ["Subtask", "Subtasks"]
          }
        }
      }
    }
  }
}
```

### Resolution Order

The `resolve_child_tiers_for_hive()` function determines which child_tiers to use via fallback chain:

1. **Hive level**: Check hive's `child_tiers`
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
  "created_at": "2026-02-03T10:30:45.123456"
}
```

**Operations**:
- `colonize_hive(name, path, child_tiers=None)`: Register new hive, create identity marker, write to global config. Creates exact-path scope if no scope matches. Optional `child_tiers` parameter allows setting per-hive tier configuration at creation time (see Hive Colonization section below).
- `abandon_hive(name)`: Remove from scope's hive registry, leave filesystem intact
- `rename_hive(old_name, new_name)`: Update scope registry and identity marker. Ticket IDs are globally unique and NOT rewritten during rename.

**Functions**:
- `get_scope_key_for_hive(normalized_hive_name, global_config) -> str`: Returns the scope key a hive is registered under. Raises ValueError if not found.

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
- `validate_unique_hive_name()` checks for duplicate normalized names before registration
- Display names are preserved in `HiveConfig.display_name` for UI/reports

## Config API

The config module provides a type-safe dataclass API for all config operations.

**Global Config (low-level)**:
- `load_global_config() -> dict`: Read entire `~/.bees/config.json` as raw dict
- `save_global_config(global_config: dict)`: Atomically write entire global config

**Scoped Config (high-level)**:
- `load_bees_config() -> BeesConfig | None`: Load config for current repo_root from context
- `save_bees_config(config: BeesConfig)`: Save config to matching scope. Raises ValueError if no scope matches.
- `parse_scope_to_bees_config(scope_data: dict) -> BeesConfig`: Parse a scope dict into BeesConfig
- `serialize_bees_config_to_scope(config: BeesConfig) -> dict`: Serialize BeesConfig to scope dict

**Context Management**: `repo_root` flows through Python's `contextvars.ContextVar` (see `src/repo_context.py`), eliminating the need to thread it through function parameters. MCP entry points set the context via `repo_root_context(resolved_root)`.

## Egg Resolver Configuration

The egg resolver system enables custom resolution of egg field values from bee tickets into lists of resource strings. Resolution is configured at three levels with fallback behavior.

### Configuration Levels

Egg resolver settings can be configured at three levels:

**Global Level** (top-level in `~/.bees/config.json`):
```json
{
  "egg_resolver": "custom-resolver-command",
  "egg_resolver_timeout": 30,
  "scopes": { ... }
}
```

**Scope Level** (within a scope in `~/.bees/config.json`):
```json
{
  "scopes": {
    "/path/to/repo": {
      "egg_resolver": "scope-specific-command",
      "egg_resolver_timeout": 60,
      "hives": { ... }
    }
  }
}
```

**Hive Level** (within a hive entry):
```json
{
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "normalized_name": {
          "path": "/absolute/path/to/hive",
          "egg_resolver": "hive-specific-command",
          "egg_resolver_timeout": 45
        }
      }
    }
  }
}
```

### Resolution Order

The `resolve_eggs` MCP tool determines which resolver to use via fallback chain:

1. **Hive level**: Check hive's `egg_resolver` and `egg_resolver_timeout`
2. **Scope level**: Check scope's `egg_resolver` and `egg_resolver_timeout`
3. **Global level**: Check top-level `egg_resolver` and `egg_resolver_timeout`
4. **Default**: Use built-in default resolver (null → null, string → [string], other → [json.dumps(value)])

Each level's `egg_resolver` and `egg_resolver_timeout` are resolved independently using the same fallback order.

### Special Values

**egg_resolver**:
- `null` or omitted: Continue fallback chain to next level
- `"default"`: Stop fallback chain and use built-in default resolver (same as null at default level)
- `"command string"`: Use custom resolver command (subprocess invocation)

**egg_resolver_timeout**:
- `null` or omitted: Continue fallback chain to next level
- `number` (positive): Timeout in seconds for resolver execution

### Custom Resolver Interface

Custom resolvers are invoked as subprocesses with two arguments:
- `--repo-root {path}`: Absolute path to repository root
- `--egg-value {shlex.quote(json.dumps(egg_value))}`: JSON-serialized egg field value (shell-quoted)

**Output Requirements**:
- Must print valid JSON to stdout
- JSON must be array of strings or null
- Exit code must be 0 for success
- Non-zero exit code treated as error

**Timeout Handling**:
- Process killed if execution exceeds configured timeout
- Timeout error raised to caller

### Validation Rules

**egg_resolver**:
- Must be string or null
- Global validation: `load_global_config()` checks global-level field
- Scope validation: `parse_scope_to_bees_config()` checks scope-level field
- Hive validation: `_parse_hives_data()` checks hive-level field

**egg_resolver_timeout**:
- Must be number (int or float) or null
- Must be positive if specified
- Same validation points as egg_resolver

### Implementation

**Functions**:
- `resolve_egg_resolver(normalized_hive, config) -> str | None`: Resolve egg_resolver using 3-level fallback. Handles "default" special value.
- `resolve_egg_resolver_timeout(normalized_hive, config) -> int | float | None`: Resolve timeout using 3-level fallback.

**Integration**: The `resolve_eggs` MCP tool in `src/mcp_egg_ops.py` calls these resolution functions to determine resolver and timeout, then invokes default or custom resolver accordingly.

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

**Hive Level** (within a hive entry):
```json
{
  "scopes": {
    "/path/to/repo": {
      "hives": {
        "normalized_name": {
          "path": "/absolute/path/to/hive",
          "status_values": ["open", "closed"]
        }
      }
    }
  }
}
```

### Resolution Order

Status values are resolved using a 3-level fallback chain with a default:

1. **Hive level**: Check hive's `status_values`
2. **Scope level**: Check scope's `status_values`
3. **Global level**: Check top-level `status_values`
4. **Default**: Return `None` (freeform - any string accepted)

### Fallback Semantics

**null or omitted**: Fall through to next level in the chain
**[] (empty list)**: Fall through to next level (treated as absent)
**Non-empty list**: Stop fallback chain and use this exact configuration

### No Merging

Each level completely replaces the status_values configuration — there is NO merging of status values between levels. When a level provides a non-empty status_values list, that exact configuration is used and the fallback chain stops.

### Validation Rules

**status_values**:
- Must be list of strings or null
- Empty list `[]` is treated as absent (falls through to next level)
- Global validation: `load_global_config()` checks global-level field
- Scope validation: `parse_scope_to_bees_config()` checks scope-level field
- Hive validation: `_parse_hives_data()` checks hive-level field

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

The `queries` key is a dictionary mapping query name strings to stage lists. Each stage list is a list of lists of strings, matching the output of `QueryParser.parse_and_validate()`.

**Global Level** (top-level in `~/.bees/config.json`):
```json
{
  "queries": {
    "open_bees": [["type=bee", "status=open"]],
    "bees_with_children": [["type=bee"], ["children"]]
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
        "open_tasks": [["type=t1", "status=open"]],
        "finished_epics": [["type=t1", "status=finished"]]
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

Queries are validated at registration time via `QueryParser.parse_and_validate()`. Only structurally valid query pipelines can be stored. The validated stage lists (list of lists of strings) are persisted directly — the original YAML string is not retained.

### Implementation

**Functions**:
- `resolve_named_query(name, repo_root, global_config) -> dict`: Resolve a query name using 2-level fallback with out-of-scope detection. In `src/config.py`.
- `check_query_name_conflict(name, scope, repo_root, global_config) -> dict | None`: Check for name conflicts before saving. In `src/config.py`.
- `_add_named_query(name, query_yaml, scope, resolved_root) -> dict`: Register a new named query in config-backed storage. In `src/mcp_query_ops.py`.
- `_delete_named_query(name, scope, resolved_root) -> dict`: Remove a named query from config-backed storage with empty-dict cleanup. In `src/mcp_query_ops.py`.
- `_list_named_queries(show_all, resolved_root) -> dict`: List queries accessible from the caller's context, or all queries system-wide. In `src/mcp_query_ops.py`.

## Hive Colonization

The `colonize_hive` MCP tool creates and registers new hives with optional per-hive child_tiers configuration.

### colonize_hive Parameters

```python
colonize_hive(
    name: str,
    path: str,
    child_tiers: dict[str, list] | None = None
)
```

**Required Parameters**:
- `name`: Display name for the hive (e.g., "Back End", "Frontend")
- `path`: Absolute path to the directory where the hive should be created

**Optional Parameter**:
- `child_tiers`: Per-hive child tiers configuration (dict or None)

### child_tiers Parameter Semantics

The `child_tiers` parameter supports three semantic states that control how the hive resolves its tier configuration:

**1. `None` (default, parameter omitted)**:
- Hive does NOT store a child_tiers key in config
- Enables fallback chain: hive → scope → global → default
- Hive inherits tier configuration from parent scope or global level
- Use when hive should follow standard project tier configuration

**2. `{}` (empty dictionary)**:
- Hive stores `"child_tiers": {}` in config (empty dict persisted)
- Stops fallback chain immediately
- Hive operates in bees-only mode (no child tiers allowed)
- Use for project hub hives that only track top-level bees

**3. Populated dictionary (e.g., `{"t1": ["Task", "Tasks"]}`)**:
- Hive stores exact tier configuration in config
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
          "created_at": "2026-02-16T12:00:00",
          "child_tiers": {
            "t1": ["Task", "Tasks"],
            "t2": ["Subtask", "Subtasks"]
          }
        },
        "hub": {
          "path": "/path/to/repo/tickets/hub",
          "display_name": "Project Hub",
          "created_at": "2026-02-16T12:00:00",
          "child_tiers": {}
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

In this example:
- `backend` hive has custom tiers (t1, t2) → Uses own configuration
- `hub` hive has empty child_tiers → Bees-only mode
- `frontend` hive has no child_tiers key → Inherits from scope/global

**Note**: The `.hive/identity.json` marker does NOT store child_tiers. This field is only stored in `~/.bees/config.json`.

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

1. If hive has `child_tiers` key in config (empty or populated), use that value
2. If hive has no `child_tiers` key, fall back to scope level
3. If scope has no `child_tiers`, fall back to global level
4. If global has no `child_tiers`, default to `{}` (bees-only)

The distinction between "key absent" (None) and "key present with empty dict" ({}) is critical for correct fallback behavior.

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
