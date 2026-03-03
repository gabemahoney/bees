# Storage Architecture

## Overview

Bees uses a hierarchical storage architecture where each ticket is stored in its own directory, with child tickets nested as subdirectories within their parent's directory. This document covers hive directory structure, identity markers, ticket schema, and storage design decisions.

## Hive Directory Structure

Each hive uses a hierarchical directory layout where ticket ownership relationships are reflected in the filesystem structure:

```
hive_root/
├── .hive/
│   └── identity.json       # Hive metadata and identity marker
├── cemetery/               # Archive for retired tickets (undertaker)
├── eggs/                   # Optional: created by egg resolver when configured
├── b.amx/                      # Bee directory
│   ├── b.amx.md                # Bee ticket file
│   ├── t1.amx.1j/              # Child task directory
│   │   ├── t1.amx.1j.md        # Task ticket file
│   │   └── t2.amx.1j.4p/       # Grandchild subtask directory
│   │       └── t2.amx.1j.4p.md # Subtask ticket file
│   └── t1.amx.3k/              # Another child task
│       └── t1.amx.3k.md
└── b.xyz/                      # Another bee
    └── b.xyz.md
```

### Directory Components

**`.hive/identity.json`**: Identity marker file containing hive metadata
- `normalized_name`: Internal hive identifier (lowercase, underscores)
- `display_name`: Original display name preserving case
- `created_at`: Timestamp of hive creation
- `version`: Schema version at creation time

**`/cemetery`**: Archive directory for retired tickets managed by the undertaker. Files use the naming convention `{tier}.{guid}.md`. Excluded from all active operations (queries, linting, indexing, path resolution). Not auto-created during colonization.

**`evicted/`**: Reserved directory for completed/archived tickets (not auto-created during colonization)

**`eggs/`**: Optional directory for egg resolver data (not auto-created, only used when resolver is configured)

**Ticket directories**: Each ticket is a directory named with its ticket ID, containing the ticket markdown file
- Directory name matches ticket ID exactly (e.g., `b.amx/` contains `b.amx.md`)
- Child tickets are subdirectories of their parent's directory
- Bees (top-level tickets) are directories at hive root level

### Identity Marker

The `.hive/identity.json` file serves as the authoritative marker that identifies a directory as a Bees hive. This marker enables:

- **Hive recovery**: `scan_for_hive()` can locate hives that have been moved or whose config entries are stale
- **Hive identification**: Verifies directory is a valid hive before operations
- **Metadata storage**: Preserves display name and creation timestamp

**Format**:
```json
{
  "normalized_name": "backend",
  "display_name": "Back End",
  "created_at": "2026-02-01T12:00:00",
  "version": "1.0.0"
}
```

**Creation**: Automatically created during hive colonization (`colonize_hive()`)

**Updates**: Updated during hive rename operations to reflect new names

**Recovery**: If missing, can be recreated during rename operations (recovery scenario)

**Note**: The identity marker does NOT store per-hive configuration like `child_tiers`. These fields are only stored in `~/.bees/config.json`. The identity marker serves solely for hive discovery and basic metadata.

## Cemetery Directory

### Purpose

The cemetery is an archive for tickets that have been retired by the undertaker. When a ticket reaches the end of its lifecycle, it is moved to the cemetery rather than deleted, preserving a historical record while removing the ticket from all active operations.

### Location and File Naming

The cemetery lives at `{hive_root}/cemetery/`. Archived ticket files use a flat naming convention: `{tier}.{guid}.md` (e.g., `t1.abc123def.md`). This differs from the normal hierarchical `{ticket_id}/{ticket_id}.md` pattern — cemetery files are stored flat, not in per-ticket directories.

### Exclusion from Active Operations

The cemetery is excluded from all active operations: queries, linting, indexing, and path resolution. This exclusion is not achieved through a hardcoded directory blocklist — instead, it is a natural consequence of the positive-match traversal approach described in the Directory Traversal section below.

## Ticket ID System

### Purpose

Provide type-prefixed ticket identifiers that encode parent hierarchy and avoid visual ambiguity on case-insensitive filesystems.

### ID Format

- **Type-prefixed format**: `{type_prefix}.{shortID}`
- **Bee (t0)**: `b.xxx` (3-char) — Examples: `b.amx`, `b.x4f`, `b.r8p`
- **Tier 1 (t1)**: `t1.xxx.yy` (3-char base + 2-char segment) — Examples: `t1.amx.12`, `t1.r8p.9c`
- **Tier 2 (t2)**: `t2.xxx.yy.zz` (3-char base + two 2-char segments) — Examples: `t2.amx.12.49`, `t2.r8p.9c.zk`
- **Tier N**: `t{N}.xxx(.yy){N}` — 3-char base + N period-separated 2-char segments
- **Maximum depth**: T9 (21-char shortID)

### Character Set

**Lowercase-only Modified Crockford Base32** (34 characters):
- **Allowed**: digits `1–9` and lowercase letters `a–k`, `m–z`
- **Excluded**: `0` (zero), uppercase `O`, uppercase `I`, lowercase `l`, and all uppercase letters

### Hierarchical Prefix

A child ticket's shortID is the parent's shortID plus 2 new random characters. The full parent chain is embedded in the ID — no filesystem lookup required to determine ancestry.

Example chain:
- Bee: `b.abc`
- T1 child: `t1.abc.12`
- T2 grandchild: `t2.abc.12.49`

### Uniqueness

IDs are unique within the scope of their parent context:
- **Bees**: Checked against all entries in the hive root directory
- **Child tiers**: Checked against all entries in the parent ticket's directory only

## Ticket Schema Versioning

### Purpose

Add schema versioning to ticket YAML frontmatter for future-proof ticket identification and schema evolution support.

### Version Field in Frontmatter

- **Field name**: `schema_version`
- **Current version**: `"1.0.0"` (corresponds to hierarchical storage schema)
- **Location**: YAML frontmatter
- **Requirement**: Mandatory for all tickets
- **Set at**: Ticket creation time (automatically by factory functions)

### Schema Version Constant

Single source of truth: `SCHEMA_VERSION = "1.0.0"` in `src/constants.py`

### Example Ticket Frontmatter

**Bee Ticket:**
```yaml
---
id: b.amx
type: bee
title: Example Bee
egg: null
schema_version: "1.0.0"
status: open
created_at: 2026-02-01T12:00:00
---
```

**Child Tier Ticket:**
```yaml
---
id: t1.amx.12
type: t1
title: Example Task
parent: b.amx
schema_version: "1.0.0"
status: open
created_at: 2026-02-01T12:00:00
---
```

**Deprecated Fields**: The following fields were removed in schema cleanup (SR-6.3) and are disallowed in ticket frontmatter: `owner`, `priority`, `description`, `created_by`, `updated_at`, `bees_version`. The linter detects these fields and generates validation errors. See [Disallowed Fields Detection](validation.md#disallowed-fields-detection) for details.

### Validation

The `read_ticket()` function validates `schema_version` field presence in frontmatter:

- Validation occurs immediately after parsing frontmatter
- Raises `ValidationError` if field is missing
- Error message: "Markdown file is not a valid Bees ticket: missing 'schema_version' field in frontmatter"
- Critical for hierarchical storage: distinguishes ticket files from other markdown files in directory tree

### Cache-Backed Reads

All ticket parsing flows through `read_ticket()`, which is backed by an in-memory mtime cache when `hive_name` is provided. This includes single-ticket reads and bulk operations like `list_tickets()` and `infer_ticket_type_from_id()`. See [caching.md](caching.md) for the full cache design.

### Design Rationale

- **String version** (not int) allows flexibility for minor versions or branches (e.g., "1.1.1", "2.0-beta")
- **Stored in frontmatter** (not body) for efficient scanning without parsing full markdown
- **Set at creation time** (not dynamically) creates immutable audit trail of when ticket was created
- **Enables future schema evolution**: queries can filter by version

## Ticket Type System

### Type Definition

**Location**: `src/types.py`

```python
TicketType = Union[Literal["bee"], str]
```

### Design Decision

The type system uses `Union[Literal["bee"], str]` instead of a hardcoded literal to support dynamic tier types configured in `~/.bees/config.json` under `child_tiers`.

**Rationale**:
- **Extensibility**: Supports arbitrary tier hierarchies (t1, t2, t3...) without code changes
- **Type Safety**: Preserves "bee" as explicit literal while allowing string-based tier types
- **Configuration-Driven**: Valid types determined by `~/.bees/config.json` `child_tiers` field

### Runtime Validation

The type system enforces validation at two levels:

**1. MCP Function Validation** (`src/mcp_ticket_ops.py`):
- Builds valid types set from `{"bee"}` + `child_tiers` config keys
- Called by `_create_ticket()` before any ticket creation operations
- Raises `ValueError` for unrecognized types

**2. Model Validation** (`src/models.py::Ticket.__post_init__`):
- Permissive — accepts any type value at instantiation
- Allows corrupt tickets to load for linter inspection

### Valid Type Examples

**Bees-only system** (`child_tiers: {}`):
- `"bee"` only

**Two-tier system** (`child_tiers: {"t1": ["Task", "Tasks"]}`):
- `"bee"`, `"t1"`

**Multi-tier system** (`child_tiers: {"t1": ..., "t2": ..., "t3": ...}`):
- `"bee"`, `"t1"`, `"t2"`, `"t3"`

## Hierarchical Storage Architecture

### Design Decision

Bees uses hierarchical storage where each ticket is a directory containing its markdown file, with child tickets nested as subdirectories within their parent's directory.

### Rationale

- **Human-navigable structure**: Parent-child relationships visible from filesystem itself
- **Natural organization**: Directory nesting mirrors ticket ownership hierarchy
- **Source of truth principle**: Frontmatter is authoritative for relationships; filesystem structure is derived
- **Auto-maintained structure**: Linter automatically enforces correct directory locations based on frontmatter
- **Accidental move recovery**: File manager accidents are auto-corrected on next linter run

### Implementation

**Path Format**: `{hive_root}/{ticket_id}/{ticket_id}.md` for bees, with recursive nesting for children

Examples:
```
# Hierarchical storage (schema_version 1.0.0)
backend/b.amx/b.amx.md
backend/b.amx/t1.amx.1j/t1.amx.1j.md
backend/b.amx/t1.amx.1j/t2.amx.1j.4p/t2.amx.1j.4p.md
frontend/b.r8p/b.r8p.md
```

### Directory Naming Convention

**Critical Constraint**: Directory name must exactly match ticket ID
- Pattern: `{ticket_id}/{ticket_id}.md`
- Example: Ticket `b.amx` lives in directory `b.amx/` as file `b.amx.md`
- Violation: File `b.amx.md` in directory `other_name/` is invalid and will be moved by linter

### Key Functions

**`iter_ticket_files()`** (`src/paths.py`):
- Primary traversal function for well-structured hives
- Uses positive-match traversal: only enters directories whose names match the ticket ID pattern
- Yields paths matching the `{ticket_id}/{ticket_id}.md` convention
- Used by `list_tickets()`, `get_ticket_path()`, and query operations

**`iter_ticket_files_deep()`** (`src/paths.py`):
- Broader traversal for the linter
- Enters all directories except hidden ones and `evicted/`
- Finds tickets even in wrong locations or with non-standard directory names
- Used when scanning for misplaced or invalid tickets that need correction

**`find_ticket_file()`** (`src/paths.py`):
- Locates a specific ticket's file by ID using selective traversal
- Supports both strict mode (default, ticket-ID directories only) and deep mode (for finding misplaced tickets)
- Used by `get_ticket_path()` and `infer_ticket_type_from_id()`

**`get_ticket_path()`** (`src/paths.py`):
- Delegates to `find_ticket_file()` for selective traversal
- Validates directory name matches file stem (hierarchical pattern enforcement)
- Returns path only if directory name equals ticket ID
- Raises `FileNotFoundError` if ticket doesn't exist

**`compute_ticket_directory()`** (`src/paths.py`):
- Computes target directory path for new ticket creation
- For bees (no parent): Returns `{hive_root}/{ticket_id}/`
- For children (with parent): Returns `{parent_dir}/{ticket_id}/`
- Used by ticket writer to determine where to create new ticket directory

**`list_tickets()`** (`src/paths.py`):
- Delegates to `iter_ticket_files()` for selective traversal
- Validates `schema_version` field presence in frontmatter
- Performance: O(n) where n = ticket directories in hive tree

**`infer_ticket_type_from_id()`** (`src/paths.py`):
- Delegates to `find_ticket_file()` for selective traversal
- Parses YAML frontmatter to extract `type` field
- Validates `schema_version` field presence
- Returns type from frontmatter (authoritative source)

### Directory Traversal

**Design Decision**: The system uses positive-match traversal to discover ticket directories. During traversal, only directories whose names match the ticket ID pattern are entered. This is the inverse of a blocklist approach — rather than listing directories to skip, the system only descends into directories it recognizes as ticket IDs.

**Rationale**:
- **No hardcoded exclusion lists**: Adding new special directories (like `/cemetery`) requires no code changes to traversal logic
- **Self-maintaining**: Any non-ticket directory at any level of the tree is automatically ignored
- **Forward-compatible**: Future special directories are excluded by default without updates

**Two traversal modes**:

- **Strict** (`iter_ticket_files`): Only enters ticket-ID directories. Used for all normal operations — queries, indexing, path resolution. Naturally excludes `/cemetery`, `eggs/`, `.hive/`, `evicted/`, and any other non-ticket directory.
- **Deep** (`iter_ticket_files_deep`): Enters all non-hidden directories (skips `.hive/` and `evicted/`). Used by the linter to find misplaced tickets that may have ended up in unexpected locations. This broader scan is necessary because a misplaced ticket's parent directory won't match the ticket ID pattern, so strict traversal would miss it.

### Integration with Schema Versioning

- Hierarchical storage scans YAML `type` field AND `schema_version` to identify tickets
- Schema version distinguishes ticket markdown files from other markdown files in directory tree
- Hierarchical pattern enforcement (directory name = file stem) provides additional validation layer
- Validation requirement: all ticket files must match both hierarchical pattern AND have `schema_version` field

## Source of Truth Principle

### Frontmatter is Authoritative

**Design Decision**: YAML frontmatter fields (`parent`, `children`) are the authoritative source for all ticket relationships. Filesystem structure is derived from frontmatter, not the reverse.

**Rationale**:
- **Single source of truth**: Prevents conflicts between frontmatter and filesystem location
- **Programmatic access**: Relationships can be queried without filesystem traversal
- **Validation simplicity**: Linter can detect and correct misplaced tickets automatically
- **Recovery from accidents**: Manual file moves are auto-corrected on next linter run

### Linter Enforcement

The linter's `enforce_directory_structure()` method ensures filesystem matches frontmatter:
- Reads `parent` field from ticket frontmatter (authoritative source)
- Verifies ticket directory is located under parent's directory
- If misplaced, automatically moves ticket directory (and all children) to correct location
- For bees (no parent), verifies directory is at hive root level

**Auto-correction flow**:
1. User accidentally moves `t1.amx.12/` directory to wrong location via file manager
2. Watcher detects file change and triggers linter
3. Linter reads `parent` field from `t1.amx.12.md` frontmatter
4. Linter verifies `t1.amx.12/` directory is under parent's directory
5. If misplaced, linter moves `t1.amx.12/` directory to correct location under parent
6. File move triggers new watch event, which regenerates index

## Immutable Parent Relationships

### Design Decision

Parent relationships cannot be changed after ticket creation. Once a ticket is created with a parent, that relationship is permanent.

### Rationale

- **Stable directory hierarchy**: Prevents filesystem churn from re-parenting operations
- **Simplifies validation**: No need to handle directory moves during update operations
- **Clearer ownership**: Tickets permanently belong to their original parent
- **Prevents structural instability**: Re-parenting can break deeply nested hierarchies

### Implementation

The `update_ticket()` function in `src/mcp_ticket_ops.py` rejects any attempt to modify `parent` or `children` fields:
- Parent is set at creation time and becomes immutable
- Children are managed indirectly through child ticket creation/deletion operations
- Attempting to update `parent` or `children` via `update_ticket()` raises `ValueError`

**Note**: `create_ticket()` manages parent/children relationships at creation time. `delete_ticket()` removes the ticket's directory subtree only — it does not edit relationship fields in surviving tickets. Only `update_ticket()` enforces immutability post-creation.

## Hive Colonization

### Directory Creation

When creating a new hive via `colonize_hive(name, path, child_tiers=None)`:

1. **Name Normalization**: Converts display name to normalized identifier
2. **Path Validation**: Ensures path is absolute, exists, and within repository
3. **Uniqueness Check**: Verifies normalized name doesn't exist in registry
4. **child_tiers Validation**: Validates optional per-hive tier configuration if provided (Step 4.5)
5. **Directory Structure**: Creates `/.hive` directory
6. **Identity Marker**: Writes `.hive/identity.json` with hive metadata (no child_tiers field)
7. **Config Registration**: Registers hive in `~/.bees/config.json` with optional child_tiers field

**Note**: The `/eggs` directory is not auto-created during colonization. It is optional and only created by an egg resolver when resolver functionality is configured and used.

### child_tiers Parameter

The optional `child_tiers` parameter allows setting per-hive tier configuration at hive creation time:

**Parameter Semantics**:
- `None` (default): Hive inherits tier configuration from scope/global via fallback chain
- `{}` (empty dict): Hive operates in bees-only mode (no child tiers)
- Populated dict: Hive uses custom tier hierarchy (e.g., `{"t1": ["Task", "Tasks"]}`)

**Config Storage Examples**:

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

**Explanation**:
- `backend`: Custom tiers stored → stops fallback, uses own configuration
- `hub`: Empty dict stored → bees-only mode, no child tiers allowed
- `frontend`: No child_tiers key → inherits from scope/global config

**Important**: The `child_tiers` field is ONLY stored in `~/.bees/config.json`, NOT in `.hive/identity.json`. The identity marker contains only basic hive identification metadata.

For complete details on child_tiers resolution and fallback behavior, see `docs/architecture/configuration.md`.

### Creation is Idempotent

Uses `Path.mkdir(parents=True, exist_ok=True)` for safe directory creation without errors if directories already exist.

## Storage Best Practices

### Ticket Identification

Always validate `schema_version` field when scanning for tickets to distinguish ticket files from other markdown content. Additionally, verify hierarchical pattern: directory name must match file stem.

### Path Resolution

**For existing tickets**: Use `get_ticket_path()` which scans recursively to find the ticket file

**For new tickets**: Use `compute_ticket_directory()` to determine where to create the ticket directory based on parent relationship

Never construct ticket paths manually. Always use provided path resolution functions.

### Directory Creation

When creating new tickets:
1. Use `compute_ticket_directory()` to determine target directory path
2. Create the ticket directory: `{ticket_id}/`
3. Write the markdown file inside: `{ticket_id}/{ticket_id}.md`
4. For child tickets, ensure parent directory exists first

### Type Information

Read ticket type from YAML frontmatter, not from filesystem location. Frontmatter is the authoritative source for all ticket metadata.

### Directory Structure Enforcement

Trust the linter to maintain correct directory structure. Do not manually move ticket directories. If a ticket is misplaced:
- Linter will auto-detect on next run (triggered by watcher or manual `sanitize_hive`)
- Linter will move ticket directory (and all children) to correct location
- Directory moves trigger new watch events, maintaining consistency

### Hive Recovery

Config-based lookup is primary method. The `.hive/identity.json` marker enables recovery via `scan_for_hive()` when config entries are stale, but write operations should fail fast without automatic recovery.
