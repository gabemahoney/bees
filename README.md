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

Use natural language with the LLM to:
- create, update and delete tickets
- add named queries the LLM can then later use
- run named queries to find tickets that match them

The auto-generated index is at `tickets/index.md` and updates automatically when tickets change.

### Hive Configuration

Bees stores hive configuration in `.bees/config.json` in the client repository root.

**Hive Colonization:**

When creating a new hive, use the `colonize_hive()` function to set up the directory structure:

```python
from src.mcp_server import colonize_hive

# Create a new hive with subdirectories
result = colonize_hive(name='Back End', path='/Users/username/projects/myrepo/tickets/backend')
```

This creates the following directory structure:
- `/eggs` - Reserved for future feature storage (currently stubbed)
- `/evicted` - Storage for completed and archived tickets
- `/.hive` - Hidden marker directory containing hive identity for recovery

The function automatically:
- Creates both subdirectories with `parents=True, exist_ok=True` for idempotent operations
- Creates a `.hive` marker containing hive identity (normalized name and display name)
- Normalizes the hive name (e.g., 'Back End' → 'back_end')
- Returns status information including the normalized name and hive path

**Hive Recovery:**

The `.hive` marker enables automatic hive recovery when paths change. If a hive is moved or renamed, Bees can scan for its `.hive` marker to locate it:

- Each hive contains a `/.hive/identity.json` file with its normalized name and display name
- When a hive cannot be found at its configured path, Bees recursively scans the repository for `.hive` markers
- If a matching marker is found, the config is automatically updated with the new path
- Orphaned `.hive` markers (not registered in config) trigger warning logs for cleanup

**Scan Security & Performance:**

The `scan_for_hive()` function includes security and performance optimizations:

- **Depth Limiting**: Scanning is limited to 10 directory levels from the repository root to prevent excessive filesystem traversal if the repo root is `/` or a high-level directory
- **Config Optimization**: Accepts an optional `config` parameter to avoid redundant disk reads when scanning multiple hives

Usage example with config parameter:
```python
from src.mcp_server import scan_for_hive
from src.config import load_bees_config

# Load config once for multiple scans
config_dict = load_bees_config().dict()

# Scan for multiple hives without reloading config
hive1_path = scan_for_hive('backend', config=config_dict)
hive2_path = scan_for_hive('frontend', config=config_dict)
```

**Configuration Schema:**

```json
{
  "hives": {
    "backend": {
      "path": "/Users/username/projects/myrepo/tickets/backend",
      "display_name": "Backend"
    },
    "frontend": {
      "path": "/Users/username/projects/myrepo/tickets/frontend",
      "display_name": "Frontend"
    }
  },
  "allow_cross_hive_dependencies": false,
  "schema_version": "1.0"
}
```

**Fields:**
- `hives`: Dictionary mapping normalized hive names to hive configurations
  - `path`: Absolute path to hive directory
  - `display_name`: Human-readable name for the hive
- `allow_cross_hive_dependencies`: Whether tickets in different hives can depend on each other
- `schema_version`: Configuration schema version (currently "1.0")

**Name Normalization:**

Hive names are automatically normalized for use as configuration keys:
- Spaces are converted to underscores
- Names are lowercased
- Normalized names must be unique

Examples:
- 'Back End' → 'back_end'
- 'UPPERCASE' → 'uppercase'
- 'Multi Word Name' → 'multi_word_name'

This prevents registration of hives with different display names that would collide when normalized (e.g., 'Back End' and 'back end' both normalize to 'back_end').

**Path Validation:**

Hive paths are validated during registration to ensure security and consistency:
- **Must be absolute paths** - Relative paths like `tickets/backend` are rejected
- **Must exist** - The directory must be created before registering the hive
- **Must be within repository root** - Paths outside the git repository are rejected for security
- **Trailing slashes normalized** - Paths like `/path/to/hive/` are normalized to `/path/to/hive`

Example validation errors:
```
ValueError: Hive path must be absolute, got relative path: tickets/backend
ValueError: Hive path does not exist: /Users/username/projects/myrepo/nonexistent
ValueError: Hive path must be within repository root. Path: /tmp/outside, Repo root: /Users/username/projects/myrepo
```

## MCP Commands

- **create_ticket** - `ticket_type, title, description, parent, children, up_dependencies, down_dependencies, labels, owner, priority, status`
- **update_ticket** - `ticket_id, title, description, parent, children, up_dependencies, down_dependencies, labels, owner, priority, status`
- **delete_ticket** - `ticket_id, cascade`
- **add_named_query** - `name, query_yaml, validate`
- **execute_query** - `query_name, params`
- **generate_index** - `status, type`
- **health_check** - No parameters

### Examples

```python
# Create an epic
create_ticket(ticket_type="epic", title="Add user authentication", description="Implement login/logout")

# Create a task under an epic
create_ticket(ticket_type="task", title="Build login API", parent="epic-001")

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

# Execute query
execute_query(query_name="open_tasks")

# Generate index
generate_index(status="open", type="task")
```

