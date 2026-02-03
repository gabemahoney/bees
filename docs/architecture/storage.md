# Storage Architecture

## Overview

Bees uses a flat storage architecture where all tickets are stored in hive root directories. This document covers hive directory structure, identity markers, ticket schema, and storage design decisions.

## Hive Directory Structure

Each hive has a specific directory layout:

```
hive_root/
├── .hive/
│   └── identity.json       # Hive metadata and identity marker
├── eggs/                   # Reserved for future use
├── evicted/                # Reserved for future use
├── {ticket_id}.md          # Ticket files (flat storage)
└── {ticket_id}.md          # All tickets at root level
```

### Directory Components

**`.hive/identity.json`**: Identity marker file containing hive metadata
- `normalized_name`: Internal hive identifier (lowercase, underscores)
- `display_name`: Original display name preserving case
- `created_at`: Timestamp of hive creation
- `bees_version`: Schema version at creation time

**`eggs/`**: Reserved directory for future features (currently unused)

**`evicted/`**: Reserved directory for future features (currently unused)

**Ticket files**: All tickets stored directly at hive root (`{hive_root}/{ticket_id}.md`)

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
  "bees_version": "1.1"
}
```

**Creation**: Automatically created during hive colonization (`colonize_hive()`)

**Updates**: Updated during hive rename operations to reflect new names

**Recovery**: If missing, can be recreated during rename operations (recovery scenario)

## Hive ID System

### Purpose

Namespace ticket IDs by hive to prevent collisions and enable multi-hive support within a single repository.

### ID Format

- **Without hive**: `bees-abc` (3 alphanumeric characters)
- **With hive**: `{normalized_hive}.bees-abc` (hive prefix + dot + base ID)
- **Examples**: `backend.bees-abc`, `my_hive.bees-123`, `bees-xyz`

### ID Pattern Validation

- **Regex**: `^([a-z_][a-z0-9_]*\.)?bees-[a-z0-9]{3}$`
- Supports both formats: with and without hive prefix
- Hive prefix must start with lowercase letter or underscore
- Base ID always follows `bees-` prefix with 3 alphanumeric chars

### Normalization

Hive names are normalized to lowercase with underscores replacing spaces and special characters. See `docs/architecture/configuration.md` for detailed normalization rules.

## Ticket Schema Versioning

### Purpose

Add schema versioning to ticket YAML frontmatter for future-proof ticket identification and schema evolution support in flat storage architecture.

### Version Field in Frontmatter

- **Field name**: `bees_version`
- **Current version**: `1.1` (corresponds to flat storage schema)
- **Location**: YAML frontmatter
- **Requirement**: Mandatory for all tickets
- **Set at**: Ticket creation time (automatically by factory functions)

### Schema Version Constant

Single source of truth: `BEES_SCHEMA_VERSION = '1.1'` in `src/constants.py`

### Example Ticket Frontmatter

```yaml
---
id: backend.bees-abc1
type: task
title: Example Task
bees_version: '1.1'
status: open
created_at: 2026-02-01T12:00:00
---
```

### Validation

The `read_ticket()` function validates `bees_version` field presence in frontmatter:

- Validation occurs immediately after parsing frontmatter
- Raises `ValidationError` if field is missing
- Error message: "Markdown file is not a valid Bees ticket: missing 'bees_version' field in frontmatter"
- Critical for flat storage: distinguishes ticket files from other markdown files in hive root

### Design Rationale

- **String version** (not int) allows flexibility for minor versions or branches (e.g., "1.1.1", "2.0-beta")
- **Stored in frontmatter** (not body) for efficient scanning without parsing full markdown
- **Set at creation time** (not dynamically) creates immutable audit trail of when ticket was created
- **Enables future schema evolution**: queries can filter by version

## Flat Storage Architecture

### Design Decision

Bees version 1.1 migrated from hierarchical storage (type-specific subdirectories) to flat storage where all tickets are stored in hive root directory.

### Rationale

- **Simplifies path resolution**: No type-to-directory mapping needed
- **Reduces directory nesting**: One less level of hierarchy
- **Single source of truth**: Type information comes from YAML frontmatter, not directory location
- **Uniform treatment**: All ticket types treated uniformly by filesystem
- **Easier refactoring**: Type changes don't require file moves

### Implementation

**Path Format**: `{hive_root}/{ticket_id}.md`

Examples:
```
# Flat storage (bees_version 1.1)
backend/backend.bees-abc1.md
backend/backend.bees-xyz9.md
frontend/frontend.bees-250.md

# Legacy hierarchical (bees_version 1.0) - no longer supported
backend/epics/backend.bees-abc1.md
backend/tasks/backend.bees-xyz9.md
```

### Key Functions

**`get_ticket_path()`** (`src/paths.py`):
- Returns: `{hive_root}/{ticket_id}.md`
- Type parameter kept for API compatibility but no longer affects path
- No subdirectories: all tickets in same directory

**`list_tickets()`** (`src/paths.py`):
- Scans hive root directory directly: `{hive_root}/*.md`
- No subdirectory traversal
- Validates `bees_version` field presence
- Only returns files with valid `bees_version` field
- Ignores non-ticket markdown files

**`infer_ticket_type_from_id()`** (`src/paths.py`):
- Reads ticket file from hive root
- Parses YAML frontmatter to extract `type` field
- Validates `bees_version` field presence
- Returns type from frontmatter, not directory location
- Returns None if file doesn't exist or isn't a valid ticket

**`_load_tickets()`** (`src/pipeline.py`):
- Scans hive root directory only: `{hive_root}/*.md`
- No recursive subdirectory scanning
- Filters files by `bees_version` field presence
- Explicitly skips subdirectories like `/eggs` and `/evicted`
- Performance: O(n) where n = number of .md files in hive root

### Integration with Schema Versioning

- Flat storage scans YAML `type` field AND `bees_version` to identify tickets
- Schema version enables queries to distinguish ticket markdown files from other markdown files in hive root
- Future queries can filter by schema version (e.g., "find all v1.0 tickets for migration")
- Validation requirement enforces architectural decision: all ticket files must be identifiable via `bees_version` field

## Hive Colonization

### Directory Creation

When creating a new hive via `colonize_hive()`:

1. **Name Normalization**: Converts display name to normalized identifier
2. **Path Validation**: Ensures path is absolute, exists, and within repository
3. **Uniqueness Check**: Verifies normalized name doesn't exist in registry
4. **Directory Structure**: Creates `/eggs`, `/evicted`, and `/.hive` directories
5. **Identity Marker**: Writes `.hive/identity.json` with hive metadata
6. **Config Registration**: Registers hive in `.bees/config.json`

### Creation is Idempotent

Uses `Path.mkdir(parents=True, exist_ok=True)` for safe directory creation without errors if directories already exist.

## Storage Best Practices

### Ticket Identification

Always validate `bees_version` field when scanning for tickets to distinguish ticket files from other markdown content.

### Path Resolution

Use `get_ticket_path()` for consistent path resolution across the codebase. Never construct ticket paths manually.

### Type Information

Read ticket type from YAML frontmatter, not from filesystem location. The filesystem location is uniform for all ticket types.

### Hive Recovery

Config-based lookup is primary method. The `.hive/identity.json` marker enables recovery via `scan_for_hive()` when config entries are stale, but write operations should fail fast without automatic recovery.
