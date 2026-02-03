## Overview

Bees is an MCP server that implements a markdown-based ticket management system.

## Installation

```bash
git clone https://github.com/gabemahoney/bees.git
```

## Requirements

### MCP Client Requirements

The bees MCP server requires clients to support the **MCP Roots Protocol**. This protocol allows the server to know which repository the client is working in, ensuring all operations target the correct repository.

**Supported Clients:**
- ✅ Claude Desktop (official MCP client)
- ✅ OpenCode
- ❌ Basic MCP clients without roots support

If you see an error like "Unable to determine repository location", ensure your MCP client supports and is configured to send roots.

## Quick Start

### Configure Claude Code

Add the following to your `~/.claude.json`:
```json
{
  "mcpServers": {
    "🐝": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Verify connection:
```bash
claude mcp list
```

### Configure OpenCode

Add the following to your `opencode.json` (project root) or `~/.config/opencode/opencode.json` (global):
```json
{
  "mcp": {
    "🐝": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Verify connection:
```bash
opencode mcp list
```

## Usage

Use natural language with the LLM to:
- create, update and delete tickets
- add named queries the LLM can then later use
- run named queries to find tickets that match them

Tickets are stored as simple markdown files with yaml front-matter for metadata.
Suggested usage is for LLMs to create tickets (to keep metadata integrity).
Humans can modify the markdown. Humans can modify the yaml metadata as well.
The MCP Server has a linter which will verify metadata integrity and warn.

## Hives

Bees supports grouping tickets into Hives which are simply simply folders in your repo where a group of related tickets are stored.
Active Hives are stored in `.bees/config.json` (which the MCP server will auto-create).
When you create new tickets you should tell the LLM which Hive to create them in.
Modifying or deleting tickets does not require you to specify the Hive

## Index

Each Hive has an auto-generated `index.md` file which a human can use to navigate and view that Hive's tickets 

## Ticket Relationships

Tickets come in three types: Epic, Task and Subtask
Epics can have Tasks as children. Tasks can have Subtasks as Children.

Tickets can depend on other tickets. Epics can only depend on Epics, Tasks can only depend on Tasks and Subtasks can only depend on Subtasks.

Note: By default tickets cannot depend on tickets in other hives. You can remove this restriction by modifying your `.bees/config.json` to include
`"allow_cross_hive_dependencies": true`

```json
{
  "hives": {
    "backend": {
      "path": "/path/to/backend",
      "display_name": "Backend",
      "created_at": "2026-02-01T12:00:00.000000"
    }
  },
  "allow_cross_hive_dependencies": true,
  "schema_version": "1.0"
}
```

## Ticket ID Format

All tickets use the format: `hive_name.bees-abc1`:
- hive_name: User-defined hive name normalized
- bees-abc1: 4 character id to identify the beed

## MCP Commands

Human users do not need to interact with the MCP server. These commands are provided only for informational purposes.

For a complete list of available commands with parameters and technical reference, use:
```
help()
```

- **list_hives** - No parameters
  - Lists all registered hives in the repository
- **colonize_hive** - `name, path`
  - Creates a new hive with validation and registration
  - **Parameters:**
    - `name` (required): Display name for the hive (e.g., 'Back End')
    - `path` (required): Absolute path to hive directory (must exist and be within repository)
- **abandon_hive** - `hive_name`
  - Stops tracking a hive without deleting ticket files
  - **Parameters:**
    - `hive_name` (required): Display name or normalized name of hive to abandon
- **rename_hive** - `old_name, new_name`
  - Renames a hive by updating config, ticket IDs, filenames, and all references
  - **Parameters:**
    - `old_name` (required): Current hive name (display or normalized)
    - `new_name` (required): Desired new hive name
- **create_ticket** - `ticket_type, title, description, parent, children, up_dependencies, down_dependencies, labels, owner, priority, status, hive_name`
  - Creates a new ticket with the sent parameters
- **show_ticket** - `ticket_id`
  - Retrieves and returns all data for a specific ticket
- **update_ticket** - `ticket_id, title, description, parent, children, up_dependencies, down_dependencies, labels, owner, priority, status`
  - Modifies an existing ticket based on the sent parameters
- **delete_ticket** - `ticket_id`
  - Deletes ticket and all child and grandchild tickets
- **add_named_query** - `name, query_yaml`
  - Registers reusable queries that can be executed later by `name`
  - All queries are validated at registration time to ensure immediate feedback on errors
- **execute_query** - `query_name, hive_names`
  - Executes a registered named query
  - `hive_names` is optional; when provided, filters results to only tickets from specified hives
  - Default behavior: all hives included when `hive_names` is omitted
  - Validates that all specified hives exist; returns error if any hive not found
- **execute_freeform_query** - `query_yaml, hive_names`
  - Executes a YAML query pipeline directly without persisting it to the registry
  - Enables one-step ad-hoc query execution without cluttering the named query registry
  - **Parameters:**
    - `query_yaml` (required): YAML string representing the query pipeline
    - `hive_names` (optional): List of hive names to filter results
  - **Returns:** `{status, result_count, ticket_ids, stages_executed}`
  - Use for exploratory queries; use `add_named_query` + `execute_query` for reusable queries
- **generate_index** - `status, type, hive_name`
  - `hive_name` is optional; when provided, generates index only for that specific hive
  - When omitted, regenerates indexes for all registered hives
  - Each hive's index is written to `{hive_path}/index.md`
- **health_check** - No parameters

### Examples

```python
# List all registered hives
list_hives()
# Returns: {'status': 'success', 'hives': [{'display_name': 'Back End', 'normalized_name': 'back_end', 'path': '...'}, ...]}

# List hives when none configured
# Returns: {'status': 'success', 'hives': [], 'message': 'No hives configured'}

# Colonize a new hive
colonize_hive(name="Back End", path="/Users/user/projects/myrepo/tickets/backend")
# Returns: {'status': 'success', 'normalized_name': 'back_end', 'display_name': 'Back End', 'path': '...'}

# Colonize with validation error (invalid path)
colonize_hive(name="Frontend", path="relative/path")
# Returns: {'status': 'error', 'error_type': 'path_validation_error', 'message': '...'}

# Abandon a hive (stop tracking without deleting files)
abandon_hive(hive_name="Back End")
# Returns: {'status': 'success', 'message': 'Hive "Back End" abandoned successfully', 'display_name': 'Back End', 'normalized_name': 'back_end', 'path': '/Users/user/projects/myrepo/tickets/backend'}

# Rename a hive (updates config, IDs, filenames, and cross-references)
rename_hive(old_name="backend", new_name="api_layer")
# Returns: {'status': 'success', 'message': 'Hive renamed successfully from backend to api_layer', 'old_name': 'backend', 'new_name': 'api_layer', 'tickets_updated': 15, 'cross_references_updated': 8, 'path': '/Users/user/projects/myrepo/tickets/backend'}

# Create an epic (hive_name is required)
create_ticket(ticket_type="epic", title="Add user authentication", description="Implement login/logout", hive_name="backend")

# Create a task under an epic
create_ticket(ticket_type="task", title="Build login API", parent="backend.epic-001", hive_name="backend")

# Create a ticket with hive prefix (generates ID like "backend.bees-abc")
create_ticket(ticket_type="epic", title="Backend API", hive_name="backend")

# Show ticket details
show_ticket(ticket_id="backend.bees-abc1")
# Returns: {'status': 'success', 'ticket_id': 'backend.bees-abc1', 'ticket_type': 'epic', 'title': '...', ...}

# Create a ticket in a multi-word hive (generates ID like "my_hive.bees-123")
create_ticket(ticket_type="task", title="Setup database", hive_name="My Hive")

# Update ticket status
update_ticket(ticket_id="task-001", status="in_progress")

# Add labels to a ticket
update_ticket(ticket_id="task-001", labels=["backend", "security"])

# Add a dependency (task-002 depends on task-001)
update_ticket(ticket_id="task-002", up_dependencies=["task-001"])

# Delete ticket with children (automatically routes to backend hive, always cascades)
delete_ticket(ticket_id="backend.bees-abc1")

# Register a static query (validated at registration)
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

# Execute ad-hoc query without persisting (one-step)
execute_freeform_query(query_yaml="- [type=epic]\n- [children]")
# Returns: {'status': 'success', 'result_count': 42, 'ticket_ids': ['backend.bees-abc1', ...], 'stages_executed': 2}

# Execute ad-hoc query with hive filter
execute_freeform_query(query_yaml="- [type=task, status=open]", hive_names=["backend"])

# Find all tasks with a specific parent
execute_freeform_query(query_yaml="- [parent=features.bees-d3s]")

# Combine parent= with other search terms
execute_freeform_query(query_yaml="- [type=task, parent=features.bees-d3s]")

# Compare to named query approach (two-step)
add_named_query(name="epic_children", query_yaml="- [type=epic]\n- [children]")
execute_query(query_name="epic_children")
# Same results, but query is persisted for reuse

# Generate index for all hives
generate_index()

# Generate index filtered by status and type
generate_index(status="open", type="task")

# Generate index for specific hive only
generate_index(hive_name="backend")

# Generate index for specific hive with filters
generate_index(hive_name="backend", status="open")
```

