## Overview

Bees is an MCP server that implements a markdown-based ticket management system.

## Installation

```bash
git clone https://github.com/gabemahoney/bees.git
cd bees
poetry install
```

## Start the Server

```bash
poetry run python -m src.main > /tmp/bees_server.log 2>&1 &
```

Verify it's running:
```bash
curl http://127.0.0.1:8000/health
```

## Quick Start

### Configure Claude Code

Add the MCP server to your project configuration in `~/.claude.json`:
```json
{
  "projects": {
    "/path/to/your/project": {
      "mcpServers": {
        "🐝": {
          "type": "http",
          "url": "http://127.0.0.1:8000/mcp"
        }
      }
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
