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
- `/eggs` - Reserved for future features
- `/evicted` - Archived/completed tickets
- `/.hive` - Identity marker for automatic recovery if the hive is moved

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

**Hive Name Validation:**

Hive names must contain at least one alphanumeric character (a-z, A-Z, 0-9). The system validates hive names before creating tickets and rejects invalid names:

- **Valid:** `"backend"`, `"Back End"` (normalizes to `back_end`), `"front-end"` (normalizes to `front_end`)
- **Invalid:** `"   "` (whitespace only), `"@#$%"` (special characters only), `"---"` (no alphanumeric), `""` (empty string)

Example configuration:
```json
{
  "hives": {
    "backend": {
      "path": "/path/to/backend",
      "display_name": "Backend"
    }
  },
  "allow_cross_hive_dependencies": false,
  "schema_version": "1.0"
}
```

**Note:** All tickets are stored in hive-specific directories.

### Ticket ID Format

All tickets use the hive-prefixed format: `hive_name.bees-abc1`

- The hive name is normalized and prefixed to the ID
- Example: `backend.bees-abc1`, `front_end.bees-xyz9`
- **REQUIRED:** The `hive_name` parameter is mandatory for all `create_ticket()` calls
- Omitting `hive_name` will result in a `ValueError`

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

All path resolution requires hive-prefixed IDs:
- Format: `/path/to/{hive_name}/epics/{hive_name}.bees-abc1.md`
- Unprefixed IDs (e.g., `bees-abc1`) are not supported and will raise `ValueError`
- All ticket IDs must include the hive prefix separated by a dot (e.g., `backend.bees-abc1`)

## MCP Commands

- **create_ticket** - `ticket_type, title, description, parent, children, up_dependencies, down_dependencies, labels, owner, priority, status, hive_name`
  - **`hive_name` parameter is REQUIRED for all ticket creation**
  - All new tickets must specify a hive; generates hive-prefixed IDs (e.g., `backend.bees-abc1`)
  - Attempting to create a ticket without `hive_name` will raise a `ValueError`
- **update_ticket** - `ticket_id, title, description, parent, children, up_dependencies, down_dependencies, labels, owner, priority, status`
  - Automatically infers hive from `ticket_id` (no hive_name parameter needed)
- **delete_ticket** - `ticket_id, cascade`
  - Automatically infers hive from `ticket_id` (no hive_name parameter needed)
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

# Delete ticket with children
delete_ticket(ticket_id="epic-001", cascade=True)

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

