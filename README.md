## Overview

Bees is an MCP server that implements a markdown-based ticket management system.

## Installation

```bash
git clone https://github.com/gabemahoney/bees.git
cd bees
```

**Suggested:** Poetry for dependency management

## Quick Start

### Configure Claude Code

Add the following to your `~/.claude.json` under the `mcpServers` section:
```json
{
  "mcpServers": {
    "bees": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Verify Connection

```bash
claude mcp list
```

You should see `bees - ✓ Connected`.

## Usage

Manage tickets through Claude Code using the MCP tools. You can create epics, tasks, and subtasks, query tickets by status or type, update ticket properties, and generate markdown reports.

**IMPORTANT:** All ticket creation requires a `hive_name` parameter. You must specify which hive the ticket belongs to.

Use natural language with the LLM to:
- create, update and delete tickets (hive_name REQUIRED for creation)
- add named queries the LLM can then later use
- run named queries to find tickets that match them

Each hive maintains its own auto-generated index at `{hive_path}/index.md`. Use the `generate_index` MCP tool to regenerate indexes on demand.

### Hive Configuration

Bees supports multiple "hives" - separate ticket collections within your repository. Configuration is stored in `.bees/config.json` and created automatically on first use.

**Hive Structure:**

Each hive contains:
- **Ticket files** (root directory) - All tickets (epics, tasks, subtasks) stored as `.md` files in hive root with flat storage
- `/eggs` - Reserved for future features (e.g., ticket templates, pre-configured workflows)
- `/evicted` - Archived/completed tickets for historical reference
- `/.hive/identity.json` - Identity marker file containing hive metadata for automatic recovery if the hive is moved

**Flat Storage Architecture:**

Bees version 1.1 uses flat storage architecture:
- All ticket types (epics, tasks, subtasks) are stored directly in the hive root directory
- No type-specific subdirectories (`/epics`, `/tasks`, `/subtasks`)
- Ticket type is determined from the `type` field in YAML frontmatter
- Each ticket file is named `{ticket_id}.md` (e.g., `backend.bees-abc1.md`)
- The `bees_version: 1.1` field in YAML frontmatter identifies files as tickets

**Index Link Format:**

The auto-generated `index.md` file uses relative paths that work with the flat storage structure:
- Links use the format `[ticket-id: title](ticket-id.md)` (relative path from index location)
- Example: `[backend.bees-abc1: Add login API](backend.bees-abc1.md)`
- Links work from `{hive_name}/index.md` to `{hive_name}/{ticket_id}.md`
- No type subdirectories in links (e.g., `tickets/tasks/` is NOT used)

**Test Coverage:**

The test suite has been migrated to support flat storage architecture:
- All test fixtures now use config-based hive setup via `.bees/config.json`
- Test directories are created per-test using temporary directories with proper hive configuration
- Tests validate ticket YAML frontmatter includes `bees_version: 1.1` field
- Flat storage tests confirm all ticket types are stored in hive root (not in type subdirectories)
- Tests updated: `test_mcp_create_ticket_hive.py`, `test_create_ticket.py`, `test_delete_ticket.py`, `test_mcp_hive_inference.py`, `test_paths.py`
- Tests requiring refactoring: `test_relationship_sync.py`, `test_writer.py` (marked as skipped with TODO)
- The `test_generate_demo_tickets.py` test suite validates the flat storage architecture:
  - Verifies all ticket types (epics, tasks, subtasks) are stored in hive root directory (`default/`)
  - Confirms tickets are NOT in old type-specific subdirectories (`default/epics/`, `default/tasks/`, `default/subtasks/`)
  - Tests edge cases like missing ticket files and validates graceful error handling
  - Validates demo ticket generation produces correct relationships, dependencies, and metadata
  - Reference Task bees-kr4km and Epic bees-yuql for implementation details

The `.hive/identity.json` file contains:
- `normalized_name` - The normalized hive identifier
- `display_name` - The original display name
- `created_at` - ISO 8601 timestamp of when the hive was created
- `version` - Hive format version (currently "1.0.0")

**Configuration:**

Hives are registered with a display name and path. Names are normalized automatically using `normalize_hive_name()` from `id_utils.py`. Normalization rules:

1. **Converted to lowercase** - All uppercase letters become lowercase
2. **Spaces and hyphens become underscores** - Whitespace and `-` characters are replaced with `_`
3. **Special characters removed** - Only `a-z`, `0-9`, and `_` are allowed; all other characters are stripped
4. **Must start with letter or underscore** - If name starts with a digit after normalization, `_` is prepended

Examples:
- `'Back End'` → `'back_end'`
- `'front-end'` → `'front_end'`
- `'BackEnd'` → `'backend'`
- `'123project'` → `'_123project'`

Paths must be absolute and within the repository root.

**Hive Path Requirements:**

When creating tickets, the system validates that hive paths are accessible and writable:

- **Path must exist** - The hive directory must exist on the filesystem before tickets can be created
- **Must be a directory** - The path cannot be a regular file; it must be a directory
- **Must be writable** - The directory must have write permissions so tickets can be created
- **Symlinks supported** - Hive paths can be symlinks, but they must point to valid, writable directories

**Common Error Messages:**

If path validation fails, you'll see descriptive error messages:

- `"Hive path does not exist: '/path/to/hive'. Please create the directory before creating tickets."` - The directory doesn't exist; create it with `mkdir -p /path/to/hive`
- `"Hive path is not a directory: '/path/to/hive'. Path must be a directory, not a file."` - A file exists at the path; remove it or use a different path
- `"Hive directory is not writable: '/path/to/hive'. Please check directory permissions."` - Fix permissions with `chmod u+w /path/to/hive`
- `"Failed to resolve hive path '/path/to/hive': [error details]"` - Usually indicates a broken symlink or permission issue

**Troubleshooting:**

If you encounter hive path errors:

1. **Missing directory:** Create the hive directory: `mkdir -p /path/to/hive`
2. **Permission errors:** Ensure write permissions: `chmod u+w /path/to/hive`
3. **Broken symlink:** Check symlink target exists: `ls -la /path/to/hive`
4. **File instead of directory:** Remove file and create directory: `rm /path/to/hive && mkdir /path/to/hive`

**Duplicate Name Detection:**

The system rejects duplicate normalized names to prevent configuration conflicts. Since names are normalized before registration, different display names that normalize to the same value will be rejected:

- ✅ First registration: `colonize_hive("Back End", "/path/backend")` → Creates hive with normalized name `back_end`
- ❌ Duplicate attempt: `colonize_hive("back end", "/path/other")` → **REJECTED** (normalizes to `back_end`, which already exists)
- ❌ Duplicate attempt: `colonize_hive("back_end", "/path/third")` → **REJECTED** (normalizes to `back_end`, which already exists)

Error message format: `"A hive with normalized name 'back_end' already exists. Display name: 'Back End'"`

This ensures each hive has a unique identifier while allowing users to choose their preferred display names (spaces, capitalization, etc.).

**Hive Name Validation:**

Hive names must contain at least one alphanumeric character (a-z, A-Z, 0-9). The system validates hive names before creating tickets and rejects invalid names:

- **Valid:** `"backend"`, `"Back End"` (normalizes to `back_end`), `"front-end"` (normalizes to `front_end`)
- **Invalid:** `"   "` (whitespace only), `"@#$%"` (special characters only), `"---"` (no alphanumeric), `""` (empty string)

**Configuration File Structure:**

The `.bees/config.json` file stores hive registrations and settings:

```json
{
  "hives": {
    "backend": {
      "path": "/path/to/backend",
      "display_name": "Backend",
      "created_at": "2026-02-01T12:00:00.000000"
    }
  },
  "allow_cross_hive_dependencies": false,
  "schema_version": "1.0"
}
```

**HiveConfig Data Structure:**

The `HiveConfig` dataclass in `src/config.py` defines the schema for each hive entry:

- `path` (str): Absolute path to the hive directory
- `display_name` (str): Original display name as provided during colonization
- `created_at` (str): ISO 8601 timestamp of when the hive was created (e.g., `"2026-02-01T12:00:00.000000"`)

This dataclass matches the structure stored in `config.json` and is used when loading/saving hive configuration through `load_bees_config()` and `save_bees_config()`.

**Config Management:**

The config file is managed automatically by the system:
- **Automatic creation**: Created on first hive registration if it doesn't exist
- **Atomic writes**: Uses temporary file + rename to prevent corruption
- **Timestamps**: Each hive entry includes creation timestamp in ISO 8601 format
- **Error handling**: All config write operations handle permissions errors, disk full, and other I/O issues gracefully

**Error Handling:**

Config loading functions provide different error handling strategies:
- **`load_hive_config_dict()` (Dict API)**: Returns default structure on all errors
  - Returns defaults on malformed JSON or I/O errors
  - Logs warning message: `"Malformed JSON in {config_path}: {error}. Returning default structure."`
  - Default structure returned: `{'hives': {}, 'allow_cross_hive_dependencies': False, 'schema_version': '1.0'}`
  - Missing config files return default structure without warnings (expected behavior on first run)
  - Prevents application crashes while making errors visible through logs
- **`load_bees_config()` (Dataclass API)**: Mixed error handling for validation
  - Returns None if file doesn't exist (expected on first run)
  - Returns default BeesConfig on malformed JSON (with warning log)
  - Raises ValueError on schema validation errors (invalid schema_version type, invalid hive data type)
  - Provides strict validation for type-safe operations
- **Config write errors**: During hive colonization, write failures return descriptive error responses:
  - `config_write_error`: Failed to write config file (disk full, permissions)
  - `config_error`: Unexpected error during config registration

Example write error response:
```json
{
  "status": "error",
  "error_type": "config_write_error",
  "message": "Failed to write config file: Permission denied",
  "validation_details": {
    "operation": "write_config",
    "reason": "Permission denied"
  }
}
```

**Config Loading Consolidation:**

All config loading functions are consolidated in `src/config.py` for consistent behavior:
- `load_hive_config_dict()`: Loads `.bees/config.json` and returns dict with hive configuration (graceful degradation)
- `load_bees_config()`: Loads `.bees/config.json` and returns typed `BeesConfig` object (strict validation)
- Different error handling strategies: dict API returns defaults on all errors; dataclass API validates and may raise ValueError
- Located in `src/config.py` module, imported by `mcp_server.py` and other components

**Dict Wrapper Functions:**

The `src/config.py` module provides dict-based wrapper functions for config management:

- **`load_hive_config_dict() -> dict`**
  - Loads `.bees/config.json` and returns configuration as a dictionary
  - Returns default structure if file doesn't exist or contains malformed JSON
  - Preserves all fields including `created_at` timestamps
  - Example:
    ```python
    config = load_hive_config_dict()
    # Returns: {'hives': {...}, 'allow_cross_hive_dependencies': False, 'schema_version': '1.0'}
    backend_config = config['hives']['backend']
    # Returns: {'path': '/path/to/backend', 'display_name': 'Backend', 'created_at': '2026-02-01T...'}
    ```

- **`write_hive_config_dict(config: dict) -> None`**
  - Writes configuration dictionary to `.bees/config.json`
  - Preserves all fields including `created_at` timestamps
  - Automatically sets `schema_version` to '1.0' if not present
  - Raises `IOError` on write failures (permissions, disk space)
  - Example:
    ```python
    config = load_hive_config_dict()
    config['hives']['backend'] = {'path': '/path', 'display_name': 'Backend', 'created_at': '2026-02-01T12:00:00'}
    write_hive_config_dict(config)
    ```

- **`register_hive_dict(normalized_name: str, display_name: str, path: str, timestamp: datetime) -> dict`**
  - Loads current config, adds new hive entry, and returns updated dictionary
  - Does NOT write to disk - caller must call `write_hive_config_dict()` to persist
  - Automatically converts timestamp to ISO 8601 format for `created_at` field
  - Example:
    ```python
    from datetime import datetime
    config = register_hive_dict('backend', 'Backend', '/path/to/hive', datetime.now())
    write_hive_config_dict(config)  # Persist to disk
    ```

**Note:** All tickets are stored in hive-specific directories.

### Ticket ID Format

All tickets use the hive-prefixed format: `hive_name.bees-abc1`

- The hive name is normalized and prefixed to the ID
- Example: `backend.bees-abc1`, `front_end.bees-xyz9`
- **REQUIRED:** The `hive_name` parameter is mandatory for all `create_ticket()` calls
- Omitting `hive_name` will result in a `ValueError`

### Schema Versioning

All tickets include a `bees_version` field in their YAML frontmatter for schema versioning:

- **Purpose:** Tracks the schema version at ticket creation time, enabling schema evolution and backward compatibility
- **Current Version:** 1.1
- **Location:** YAML frontmatter (automatically set on ticket creation)
- **Automatic:** The field is automatically added when creating tickets via `create_epic()`, `create_task()`, or `create_subtask()`
- **Required:** All ticket markdown files MUST include the `bees_version` field. Files without this field will be rejected as invalid Bees tickets.

Example ticket frontmatter:
```yaml
---
id: backend.bees-abc1
type: task
title: Example Task
bees_version: '1.1'
---
```

**Validation:** The `read_ticket()` function validates that markdown files contain the `bees_version` field in frontmatter. Files without this field will raise a `ValidationError` with a clear message indicating the file is not a valid Bees ticket. This validation ensures proper ticket identification in the flat storage architecture.

**ID Parsing:**

The `parse_ticket_id()` utility function splits ticket IDs to extract the hive name and base ID:

```python
# Hive-prefixed ID format
parse_ticket_id("backend.bees-abc1")  # Returns: ("backend", "bees-abc1")

# Multiple dots (splits on first dot only)
parse_ticket_id("multi.dot.bees-xyz")  # Returns: ("multi", "dot.bees-xyz")
```

The parser handles edge cases:
- Splits on the first dot only, preserving dots in base ID
- Raises `ValueError` for `None` or empty string inputs

**Path Resolution:**

All path resolution requires hive-prefixed IDs and validates tickets using YAML frontmatter:
- Format: `/path/to/{hive_name}/{hive_name}.bees-abc1.md` (flat storage in hive root)
- Unprefixed IDs (e.g., `bees-abc1`) are not supported and will raise `ValueError`
- All ticket IDs must include the hive prefix separated by a dot (e.g., `backend.bees-abc1`)
- Ticket type is inferred from YAML frontmatter `type` field, not from directory structure
- The `bees_version` field in YAML frontmatter is required to identify valid tickets
- Files without `bees_version` are treated as non-ticket markdown files and ignored
- `infer_ticket_type_from_id()` scans hive root and reads YAML to determine ticket type
- `list_tickets()` scans hive root and filters by `bees_version` presence and optional `type` field

## MCP Commands

- **colonize_hive** - `name, path`
  - Creates a new hive with validation and registration
  - **Parameters:**
    - `name` (required): Display name for the hive (e.g., 'Back End')
    - `path` (required): Absolute path to hive directory (must exist and be within repository)
  - **Returns:**
    - On success: `{'status': 'success', 'normalized_name': str, 'display_name': str, 'path': str, 'message': str}`
    - On error: `{'status': 'error', 'message': str, 'error_type': str, 'validation_details': dict}`
  - **Validation:**
    - Path must be absolute (not relative)
    - Path must exist and be within git repository root
    - Normalized hive name must be unique across all hives
    - Name must contain at least one alphanumeric character
  - **Hive Structure Created:**
    - `/eggs` - Directory for future features
    - `/evicted` - Directory for archived tickets
    - `/.hive/identity.json` - Identity marker with hive metadata
  - **Registration:**
    - Automatically registers hive in `.bees/config.json`
    - Creates config file if it doesn't exist
  - **Linter Integration (Stubbed):**
    - Placeholder for future linter validation during hive colonization
    - Intended behavior: Validate no conflicting tickets exist across hives
    - Implementation deferred to future Epic
  - **Error Cases:**
    - `validation_error`: Name normalizes to empty string
    - `path_validation_error`: Path is relative, doesn't exist, or outside repository
    - `duplicate_name_error`: Normalized name already registered
    - `filesystem_error`: Directory creation failed (permissions, disk full)
    - `config_error`: Failed to update config.json

- **create_ticket** - `ticket_type, title, description, parent, children, up_dependencies, down_dependencies, labels, owner, priority, status, hive_name`
  - **`hive_name` parameter is REQUIRED for all ticket creation**
  - All new tickets must specify a hive; generates hive-prefixed IDs (e.g., `backend.bees-abc1`)
  - **Validation:** Hive must exist in `.bees/config.json` before creating tickets
  - The `hive_name` is normalized and checked against registered hives in config
  - Attempting to create a ticket without `hive_name` will raise a `ValueError`
  - Attempting to create a ticket for a non-existent hive will raise a `ValueError` with message: "Hive '{hive_name}' (normalized: '{normalized}') does not exist in config. Please create the hive first using colonize_hive. If the hive directory exists but isn't registered, you may need to run colonize_hive to register it."
  - **Design:** create_ticket uses strict validation and does NOT attempt automatic hive recovery. This ensures write operations are explicit and consistent with update_ticket/delete_ticket behavior.
  - Ticket is stored in the hive directory specified in config (flat storage at hive root)
- **update_ticket** - `ticket_id, title, description, parent, children, up_dependencies, down_dependencies, labels, owner, priority, status`
  - Automatically infers hive from `ticket_id` (no hive_name parameter needed)
  - **Ticket ID Format:** `{hive}.bees-{random}` (e.g., `backend.bees-abc1`)
  - The hive prefix is extracted from the ticket_id and used to route the update to the correct hive
  - **Example:** Updating `backend.bees-abc1` automatically routes to the `backend` hive
  - **Error Cases:**
    - Malformed IDs (no dot separator): Returns error "Malformed ticket ID: Expected format: hive_name.bees-xxxx"
    - Unknown hives: Returns error "Unknown hive: '{hive}' not found in config"
- **delete_ticket** - `ticket_id, cascade`
  - Automatically infers hive from `ticket_id` (no hive_name parameter needed)
  - **Ticket ID Format:** `{hive}.bees-{random}` (e.g., `backend.bees-abc1`)
  - The hive prefix is extracted from the ticket_id and used to route the deletion to the correct hive
  - **Example:** Deleting `backend.bees-abc1` automatically routes to the `backend` hive
  - **Cascade Parameter:** When `cascade=True`, recursively deletes all child tickets
  - **Error Cases:**
    - Malformed IDs (no dot separator): Returns error "Malformed ticket ID: Expected format: hive_name.bees-xxxx"
    - Unknown hives: Returns error "Hive '{hive_prefix}' not found in configuration"
- **add_named_query** - `name, query_yaml, validate`
- **execute_query** - `query_name, params, hive_names`
  - `hive_names` is optional; when provided, filters results to only tickets from specified hives
  - Default behavior: all hives included when `hive_names` is omitted
  - Validates that all specified hives exist; returns error if any hive not found
- **generate_index** - `status, type, hive_name`
  - `hive_name` is optional; when provided, generates index only for that specific hive
  - When omitted, regenerates indexes for all registered hives
  - Each hive's index is written to `{hive_path}/index.md`
- **health_check** - No parameters

### Examples

```python
# Colonize a new hive
colonize_hive(name="Back End", path="/Users/user/projects/myrepo/tickets/backend")
# Returns: {'status': 'success', 'normalized_name': 'back_end', 'display_name': 'Back End', 'path': '...'}

# Colonize with validation error (invalid path)
colonize_hive(name="Frontend", path="relative/path")
# Returns: {'status': 'error', 'error_type': 'path_validation_error', 'message': '...'}

# Create an epic (hive_name is required)
create_ticket(ticket_type="epic", title="Add user authentication", description="Implement login/logout", hive_name="backend")

# Create a task under an epic
create_ticket(ticket_type="task", title="Build login API", parent="backend.epic-001", hive_name="backend")

# Create a ticket with hive prefix (generates ID like "backend.bees-abc")
create_ticket(ticket_type="epic", title="Backend API", hive_name="backend")

# Create a ticket in a multi-word hive (generates ID like "my_hive.bees-123")
create_ticket(ticket_type="task", title="Setup database", hive_name="My Hive")

# Update ticket status
update_ticket(ticket_id="task-001", status="in_progress")

# Add labels to a ticket
update_ticket(ticket_id="task-001", labels=["backend", "security"])

# Add a dependency (task-002 depends on task-001)
update_ticket(ticket_id="task-002", up_dependencies=["task-001"])

# Delete ticket with children (automatically routes to backend hive)
delete_ticket(ticket_id="backend.bees-abc1", cascade=True)

# Register query
add_named_query(name="open_tasks", query_yaml="- - type=task\n  - status=open")

# Execute query (all hives)
execute_query(query_name="open_tasks")

# Execute query filtered to single hive
execute_query(query_name="open_tasks", hive_names=["backend"])

# Execute query filtered to multiple hives
execute_query(query_name="open_tasks", hive_names=["backend", "frontend"])

# Error handling: nonexistent hive
# execute_query(query_name="open_tasks", hive_names=["nonexistent"])
# Returns: ValueError: Hive not found: nonexistent. Available hives: backend, frontend

# Generate index for all hives
generate_index()

# Generate index filtered by status and type
generate_index(status="open", type="task")

# Generate index for specific hive only
generate_index(hive_name="backend")

# Generate index for specific hive with filters
generate_index(hive_name="backend", status="open")
```

