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

**`.hive/identity.json`**: Identity marker file containing hive metadata and hive-level configuration
- `normalized_name`: Internal hive identifier (lowercase, underscores)
- `display_name`: Original display name preserving case
- `created_at`: Timestamp of hive creation
- `version`: Schema version at creation time
- `child_tiers`: (optional) Per-hive tier configuration override
- `status_values`: (optional) Per-hive status values override — can be a list (override active), `null` (explicit override — use no labels), or absent (inherit from scope/global)

**`/cemetery`**: Archive directory for retired tickets managed by the undertaker. Files use the naming convention `{tier}.{guid}.md`. Excluded from all active operations (queries, linting, indexing, path resolution). Not auto-created during colonization.

**`evicted/`**: Reserved directory for completed/archived tickets (not auto-created during colonization)

**Ticket directories**: Each ticket is a directory named with its ticket ID, containing the ticket markdown file
- Directory name matches ticket ID exactly (e.g., `b.amx/` contains `b.amx.md`)
- Child tickets are subdirectories of their parent's directory
- Bees (top-level tickets) are directories at hive root level

### Identity Marker

The `.hive/identity.json` file serves as the authoritative marker that identifies a directory as a Bees hive. This marker enables:

- **Hive recovery**: `scan_for_hive()` can locate hives that have been moved or whose config entries are stale
- **Hive identification**: Verifies directory is a valid hive before operations
- **Hive boundary**: A `.hive/` directory below another hive's root starts a nested hive, and walks of the enclosing hive stop there (see [Nested Hives](#nested-hives))
- **Metadata storage**: Preserves display name and creation timestamp

**Format**:
```json
{
  "normalized_name": "backend",
  "display_name": "Back End",
  "created_at": "2026-02-01T12:00:00",
  "version": "1.0.0",
  "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
  "status_values": ["open", "in_progress", "done"]
}
```

Configuration fields are optional. Only fields with hive-level overrides are present.

**Creation**: Automatically created during hive colonization (`colonize_hive()`)

**Updates**: Updated during hive rename operations to reflect new names

**Recovery**: If missing, can be recreated during rename operations (recovery scenario)

**Dual purpose**: The identity marker serves both hive discovery and hive-level configuration storage. Configuration fields (`child_tiers`, `status_values`) use presence-based semantics: field present = hive-level override active; field absent = fall through to scope/global configuration via the resolution chain.

## Cemetery Directory

### Purpose

The cemetery is an archive for tickets that have been retired by the undertaker. When a ticket reaches the end of its lifecycle, it is moved to the cemetery rather than deleted, preserving a historical record while removing the ticket from all active operations.

### Location and File Naming

The cemetery lives at `{hive_root}/cemetery/`. Archived ticket files use a flat naming convention: `{tier}.{guid}.md` (e.g., `t1.abc123def.md`). This differs from the normal hierarchical `{ticket_id}/{ticket_id}.md` pattern — cemetery files are stored flat, not in per-ticket directories.

### Exclusion from Active Operations

The cemetery is excluded from all active operations: queries, linting, indexing, and path resolution. Strict traversal excludes it without a blocklist, as a natural consequence of the positive-match approach described in the Directory Traversal section below. The linter's deep traversal, which also enters non-ticket directories, skips `cemetery/` by name.

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
reference_materials: null
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

All ticket parsing flows through `read_ticket()`, which is backed by an in-memory cache validated against each file's stat signature. This includes single-ticket reads and bulk operations like `list_tickets()` and `infer_ticket_type_from_id()`. See [caching.md](caching.md) for the full cache design.

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

**`walk_hive()`** (`src/paths.py`):
- The one directory walker for hives: walks top-down like `os.walk`, yielding sorted subdirectory lists
- Takes an optional `enter` predicate on subdirectory names; only accepted subdirectories are entered
- Never enters another hive nested below the walk root (see [Nested Hives](#nested-hives)); the walk root itself is always walked, so it may be a hive root or a ticket directory
- Used by the ticket walkers below and directly by empty-directory cleanup, delete's subtree collection, and the undertaker's archive renames

**`find_enclosing_hive_root()`** (`src/paths.py`):
- Returns the root of another hive nested below a hive root that a given path lies in, or `None`
- Used by the linter's directory enforcement to refuse a move out of a nested hive, or into or onto one

**`find_nested_hive_root()`** (`src/paths.py`):
- Returns the first root of another hive found anywhere below a directory, or `None`
- Walks every directory below it, including hidden ones, `evicted/` and `cemetery/`, unlike the pruned walks
- Used by the linter's directory enforcement to refuse a move that would carry a nested hive along with the ticket's directory, or go into an existing target directory that holds one

**`iter_ticket_files()`** (`src/paths.py`):
- Primary traversal function for well-structured hives
- Uses positive-match traversal: only enters directories whose names match the ticket ID pattern
- Yields paths matching the `{ticket_id}/{ticket_id}.md` convention
- Never enters a nested hive
- Used by `list_tickets()`, query operations, index generation, and the subtree scans of move-bee, clone-bee and delete (cache eviction)

**`iter_ticket_files_deep()`** (`src/paths.py`):
- Broader traversal for the linter
- Enters all directories except hidden ones, `evicted/` and `cemetery/`, and never enters a nested hive
- Finds tickets even in wrong locations or with non-standard directory names
- Used when scanning for misplaced or invalid tickets that need correction

**`find_ticket_file()`** (`src/paths.py`):
- Locates a specific ticket's file by ID using selective traversal
- Supports both strict mode (default, ticket-ID directories only) and deep mode (for finding misplaced tickets)
- Never enters a nested hive, in either mode
- Used by the linter's directory enforcement (deep mode, to find a misplaced ticket and its parent), and by move-bee, clone-bee and the undertaker to locate a ticket (strict mode)

**`get_ticket_path()`** (`src/paths.py`):
- Builds the path with `compute_ticket_path()`, with no directory walk
- Returns the path only if the file exists there
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
- Reads the ticket with `read_ticket()` (via `get_ticket_type()`), which locates it with `compute_ticket_path()`, with no directory walk
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

- **Strict** (`iter_ticket_files`): Only enters ticket-ID directories. Used for all normal operations — queries, indexing, path resolution. Naturally excludes `/cemetery`, `.hive/`, `evicted/`, and any other non-ticket directory.
- **Deep** (`iter_ticket_files_deep`): Enters all non-hidden directories except `evicted/` and `cemetery/` (hidden ones include `.hive/`). Used by the linter to find misplaced tickets that may have ended up in unexpected locations. This broader scan is necessary because a misplaced ticket's parent directory won't match the ticket ID pattern, so strict traversal would miss it.

Both modes run on `walk_hive()`, so neither enters a nested hive.

### Nested Hives

**Design Decision**: A hive may sit inside another hive's directory (e.g. hive `plans` at `Ideas/Plans/` inside hive `ideas` at `Ideas/`). The nested hive's tickets belong to it alone: no walk of the enclosing hive enters its directory.

**Boundary**: A directory below the walk root belongs to another hive when it holds its own `.hive/` directory or is the root of a hive registered in any scope of the global config. Either is enough, so an unregistered directory with a `.hive/` and a registered hive root without one both count. Registered roots are matched also when the walk root is a symlink to the hive's directory.

**Pruning**: `walk_hive()` neither yields such a directory nor visits anything under it. The walks over a hive's tree all go through it: the linter scan, `find_ticket_file()`, directory enforcement, empty-directory cleanup, `list_tickets()`, queries, index generation, and the subtree scans of move-bee, clone-bee, delete and the undertaker. Only `find_nested_hive_root()` walks without pruning, since it is looking for such a directory. The `.hive/` check reads the listing `os.walk` already made, and the global config is loaded once per walk, so pruning adds no per-directory I/O.

**Rationale**:
- **Own configuration**: The nested hive has its own tiers, status values and layout. Linting its tickets against the enclosing hive's config would flag their tiers `unknown_tier` and move its bees to the enclosing hive's root, out of their own hive.
- **One owner per ticket**: Each ticket is scanned, fixed and moved only by the hive it lives in.

**Limits**:
- Pruning applies to walks. Moving or deleting a whole ticket directory (move-bee, the undertaker's move to `/cemetery`, delete) still takes everything in it, including a hive nested inside that ticket directory. Renaming a hive's folder (`rename_hive` with folder rename) likewise moves every hive nested in it and does not update their registered paths.
- The linter's directory enforcement is the exception: it never carries a nested hive along with a ticket's directory, nor moves a ticket's directory into an existing target directory that holds one (see [Linter Enforcement](#linter-enforcement)).
- An unregistered nested hive (one marked only by `.hive/`) is walked by no registered hive, so its tickets are not in `sanitize_hive`'s cross-hive ticket map (see [validation.md](validation.md#nested-hives)).

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
- Checks tickets parents first (by ancestor count through `parent` links), so a parent misplaced inside its child's directory moves out first and the child follows in the same run
- Never deletes anything: an existing target directory is merged into, including one that holds the misplaced ticket itself (e.g. a bee at `b.abc/misc/b.abc/`, moved through a temporary `b.abc.moving-XXXX/` directory beside the target). A move that would overwrite an entry of the target, or nest the target inside the ticket's own directory, is refused with `move_target_conflict` and nothing is moved. Each entry name is checked again just before it moves, so a name taken during the merge is never overwritten either (see [validation.md](validation.md#validation-rules), Directory Structure Enforcement)
- A move that fails partway is reported as `directory_enforcement_failed`; afterwards only emptied directories (the temporary one and those left on the way) are removed. A ticket left behind is found as misplaced later in the same run or on the next; a non-ticket file left behind stays until moved by hand
- Never makes a move that crosses a nested hive's boundary: out of a nested hive, into or onto one, carrying one along with the ticket's directory, or into an existing target directory that holds one. It reports `cross_hive_move_blocked` and moves nothing (see [validation.md](validation.md#nested-hives))

**Auto-correction flow**:
1. User accidentally moves `t1.amx.12/` directory to wrong location via file manager
2. `sanitize_hive` runs the linter (the watcher in `src/watcher.py` would also trigger it, but nothing in the CLI or MCP server starts the watcher)
3. Linter reads `parent` field from `t1.amx.12.md` frontmatter
4. Linter verifies `t1.amx.12/` directory is under parent's directory
5. If misplaced, linter moves `t1.amx.12/` directory to correct location under parent
6. `generate_index` brings `index.md` up to date

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
6. **Identity Marker**: Writes `.hive/identity.json` with hive metadata and optional hive-level config overrides
7. **Config Registration**: Registers hive in `~/.bees/config.json`

**Note**: Only the `.hive/` directory is created during colonization. Ticket directories are created when tickets are written.

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

**Important**: After the v3→v4 migration, hive-level `child_tiers` and `status_values` are stored in `.hive/identity.json` (the source of truth for hive-level overrides). Scope-level and global-level values remain in `~/.bees/config.json` as fallback levels in the resolution chain.

For complete details on child_tiers resolution and fallback behavior, see `docs/architecture/configuration.md`.

### Creation is Idempotent

Directory creation is safe to repeat — existing directories are not modified.

If `.hive/identity.json` already exists when `colonize_hive` runs, the existing `created_at` value is preserved. Only `normalized_name`, `display_name`, and `version` are updated. This ensures `created_at` always reflects the original hive creation time, even if the hive is re-registered (e.g., after `abandon_hive` and `colonize_hive` on the same directory).

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
- Linter will auto-detect on next run (`sanitize_hive`; the watcher is not started by the CLI or MCP server)
- Linter will move ticket directory (and all children) to correct location
- Run `generate_index` afterwards to refresh `index.md`

### Hive Recovery

Config-based lookup is primary method. The `.hive/identity.json` marker enables recovery via `scan_for_hive()` when config entries are stale, but write operations should fail fast without automatic recovery.
