# Bees

A markdown-based ticket management system designed for LLMs.

## Overview

Bees is a ticket tracking system that stores tickets as individual markdown files with YAML frontmatter.
It supports three ticket types: Epic, Task, and Subtask, with rich relationship management including
parent-child hierarchies and dependency tracking.

## Features

- **Markdown Storage**: All tickets stored as `.md` files with YAML frontmatter
- **Three Ticket Types**: Epics, Tasks, and Subtasks with hierarchical relationships
- **Bidirectional Relationships**: Parent-child and dependency relationships maintained automatically
- **Flexible Labeling**: Freeform labels instead of hard-coded status enums
- **MCP Server**: Write operations through MCP ensure data consistency
- **Query System**: Multi-stage pipeline queries with regex support
- **Linter**: Validates schema compliance and relationship consistency
- **Auto-Generated Index**: Dynamically generated markdown index for browsing all tickets

## Installation

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest
```

## Demo Ticket Dataset

For testing and development, Bees includes a demo ticket generation script that creates a
representative set of sample tickets with diverse statuses, priorities, labels, and
relationships.

### What's Generated

The demo script creates:
- **5 Epics**: Various statuses (open, in progress, completed) with different priorities
- **8 Tasks**: Linked to epics with parent relationships and blocking dependencies
- **15 Subtasks**: Distributed across tasks with various statuses (open, in progress,
  completed)

All tickets include:
- Realistic titles and descriptions
- Multiple labels (backend, frontend, security, etc.)
- Parent-child relationships (tasks → epics, subtasks → tasks)
- Dependency chains (some tasks block other tasks)
- Various statuses and priority levels (0-4)
- Owner assignments

### Usage

To generate the demo ticket dataset:

```bash
poetry run python scripts/generate_demo_tickets.py
```

This will populate your `tickets/` directory with sample epics, tasks, and subtasks. The
generated tickets have valid YAML frontmatter and proper bidirectional relationships.

### Regenerating Demo Data

You can regenerate the demo dataset at any time:

```bash
# Clear existing demo tickets (if needed)
rm -rf tickets/epics/bees-* tickets/tasks/bees-* tickets/subtasks/bees-*

# Generate fresh demo data
poetry run python scripts/generate_demo_tickets.py
```

The script uses the same ticket factory functions as the MCP server, ensuring demo tickets
have the same structure as real tickets created through the API.

### Use Cases

Demo tickets are useful for:
- Testing index generation functionality
- Demonstrating the query system with realistic data
- Validating linter functionality with complex relationship graphs
- Exploring the ticket structure without creating tickets manually
- Development and debugging of new features

## Project Structure

```
/bees                    # This repository (library code)
  /src                   # Source code
  /tests                 # Test suite
  /docs                  # Documentation
```

## Setting Up Your Project for Bees

To use bees in your project, create the following directory structure in your project root:

```
/your-project
  /tickets              # Ticket storage directory
    /epics              # Epic tickets go here
    /tasks              # Task tickets go here
    /subtasks           # Subtask tickets go here
```

The bees library expects this `/tickets` directory structure to exist in your current working directory
and will use it for all ticket read/write operations.

## Index Generation

The Bees system provides an auto-generated markdown index for browsing and navigating all tickets
across the system. The index is dynamically created by scanning the `tickets/` directory and
organizing tickets by type.

### Features

- **Automatic Scanning**: Recursively scans `tickets/epics/`, `tickets/tasks/`, and
  `tickets/subtasks/` directories to discover all ticket files
- **Organized by Type**: Groups tickets into separate sections for Epics, Tasks, and Subtasks
- **Hierarchy Display**: Shows ticket ID, title, status, and parent relationships (for subtasks)
- **Sorted Output**: Tickets are sorted alphabetically by ID within each section for consistent
  ordering

### Index Format

The generated index follows this markdown structure:

```markdown
# Ticket Index

## Epics
- [bees-abc] Epic Title (open)
- [bees-xyz] Another Epic (closed)

## Tasks
- [bees-def] Task Title (in_progress)

## Subtasks
- [bees-ghi] Subtask Title (open) (parent: bees-def)
```

### Usage

The index generation functionality is available through both a Python API and an MCP tool.
**For LLM agents, the MCP tool is the recommended approach** as it ensures data consistency
and follows the Model Context Protocol standard.

**Python API** (implemented in `src/index_generator.py`):

- `scan_tickets()`: Scans the tickets directory and returns grouped ticket data
- `format_index_markdown()`: Formats ticket data into structured markdown with clickable links
- `generate_index()`: High-level API that orchestrates scanning and formatting

**MCP Tool**: See the [MCP Server](#mcp-server) section below for details on the `generate_index`
tool, which provides the same functionality through the Model Context Protocol interface.

The generated index includes clickable markdown links to individual ticket files using relative
paths. Each ticket entry is formatted as:

```markdown
- [ticket-id: title](tickets/{type}s/ticket-id.md) (status)
```

**Example index output:**

```markdown
# Ticket Index

## Epics
- [bees-abc: Authentication System](tickets/epics/bees-abc.md) (open)
- [bees-def: Data Export Feature](tickets/epics/bees-def.md) (in_progress)

## Tasks
- [bees-123: Build Login API](tickets/tasks/bees-123.md) (open) (parent: bees-abc)
- [bees-456: Create Export Endpoint](tickets/tasks/bees-456.md) (completed) (parent: bees-def)

## Subtasks
- [bees-xyz: Write API tests](tickets/subtasks/bees-xyz.md) (open) (parent: bees-123)
```

**Navigation:**
- Clicking on any ticket link opens the corresponding ticket file in your markdown viewer
- Relative paths ensure links work regardless of where the repository is located
- Links are formatted as `tickets/{type}s/{ticket-id}.md` (e.g., `tickets/epics/bees-abc.md`)
  matching the actual directory structure (tickets/epics/, tickets/tasks/, tickets/subtasks/)
- This ensures clickable links work correctly in markdown viewers (Task: bees-3fh9)

## MCP Server

The Bees MCP (Model Context Protocol) server provides write operations for creating, updating, and deleting tickets while maintaining bidirectional consistency of all relationships. This ensures that when you create a parent-child relationship or add a dependency, both tickets are automatically updated.

### Starting the MCP Server

The recommended way to start the MCP server is using the provided CLI command:

```bash
poetry run start-mcp
```

This command loads configuration from `config.yaml` and starts the server with proper
initialization and graceful shutdown handling.

**Alternative methods:**

Start programmatically:
```python
from src.mcp_server import start_server, mcp

# Start the server
start_server()

# Run the MCP server
mcp.run()
```

Or run the module directly:
```bash
poetry run python -m src.mcp_server
```

### Server Configuration

The MCP server is configured via `config.yaml` in the project root. Create this file with the
following settings:

```yaml
# Server host address (default: localhost)
host: localhost

# Server port (default: 8000)
port: 8000

# Ticket directory path (default: ./tickets)
ticket_directory: ./tickets
```

**Configuration Options:**

- **host**: Server bind address. Use `localhost` for local access only, or `0.0.0.0` to allow
  external connections
- **port**: Port number for the server. Choose a port not in use by other services
- **ticket_directory**: Path to the directory containing ticket files. Can be absolute or relative
  to working directory

The server will create the ticket directory automatically if it doesn't exist.

### Stopping the Server

To gracefully stop the MCP server, press `Ctrl+C` or send a `SIGTERM` signal. The server handles
shutdown gracefully, ensuring all operations complete before exiting.

### Troubleshooting

**Port already in use:**
If you see an error about the port being in use, either:
- Stop the service using that port
- Change the `port` setting in `config.yaml` to an available port

**Permission errors:**
Ensure you have read/write permissions for the `ticket_directory` path specified in the
configuration.

**Configuration file not found:**
If the server can't find `config.yaml`, make sure you're running the command from the project
root directory where the config file is located.

### Server Information

- **Name**: Bees Ticket Management Server
- **Version**: 0.1.0
- **Transport**: Standard I/O (stdio) by default

### Available MCP Tools

The server exposes the following tools for ticket management:

#### health_check

Check the health status of the MCP server.

**Returns:**
```json
{
  "status": "healthy",
  "server_running": true,
  "ready": true,
  "name": "Bees Ticket Management Server",
  "version": "0.1.0"
}
```

#### create_ticket

Create a new ticket (epic, task, or subtask) with automatic bidirectional relationship management. When creating a ticket with relationships (parent, children, dependencies), all related tickets are automatically updated to maintain bidirectional consistency.

**Parameters:**
- `ticket_type` (required): "epic", "task", or "subtask"
- `title` (required): Ticket title (cannot be empty)
- `description`: Detailed description
- `parent`: Parent ticket ID (required for subtasks, optional for tasks, not allowed for epics)
- `children`: List of child ticket IDs to link
- `up_dependencies`: List of ticket IDs that this ticket depends on (blocking tickets)
- `down_dependencies`: List of ticket IDs that depend on this ticket (blocked tickets)
- `labels`: List of label strings
- `owner`: Owner/assignee email or username
- `priority`: Priority level (0-4, lower is higher priority)
- `status`: Status string (default: "open")

**Returns:**
```json
{
  "status": "success",
  "ticket_id": "bees-abc",
  "ticket_type": "epic",
  "title": "Implement Authentication"
}
```

**Examples:**

Create an epic without parent:
```python
result = create_ticket(
    ticket_type="epic",
    title="Implement Authentication System",
    description="Build OAuth authentication system",
    labels=["security", "backend"],
    priority=0
)
# Returns: {"status": "success", "ticket_id": "bees-abc", ...}
```

Create a task with parent:
```python
result = create_ticket(
    ticket_type="task",
    title="Build Login API",
    description="Implement POST /api/login endpoint",
    parent="bees-abc",  # Links to epic
    labels=["backend", "api"],
    priority=1
)
# Parent epic (bees-abc) is automatically updated with this task in its children array
```

Create a subtask with required parent:
```python
result = create_ticket(
    ticket_type="subtask",
    title="Write login endpoint tests",
    parent="bees-xyz",  # Required for subtasks
    labels=["testing"]
)
```

Create ticket with dependencies:
```python
result = create_ticket(
    ticket_type="task",
    title="Frontend Login UI",
    up_dependencies=["bees-api"],  # Depends on API task
    down_dependencies=["bees-test"]  # Blocks testing task
)
# Blocking ticket (bees-api) automatically gets this ticket in its down_dependencies
# Blocked ticket (bees-test) automatically gets this ticket in its up_dependencies
```

**Bidirectional Relationship Updates:**

When creating a ticket with relationships, the following automatic updates occur:

1. **Parent relationship**: If `parent` is set, the parent ticket's `children` array is automatically updated to include the new ticket ID
2. **Children relationship**: If `children` are specified, each child ticket's `parent` field is set to the new ticket ID
3. **Up dependencies**: If `up_dependencies` are set, each blocking ticket's `down_dependencies` array is updated to include the new ticket
4. **Down dependencies**: If `down_dependencies` are set, each blocked ticket's `up_dependencies` array is updated to include the new ticket

All updates are atomic - either all related tickets are updated or the operation fails.

**Validation Rules:**
- Title cannot be empty
- Ticket type must be one of: epic, task, subtask
- Epics cannot have a parent
- Subtasks must have a parent
- Parent ticket must exist
- All referenced dependency tickets must exist
- All referenced child tickets must exist
- Cannot have circular dependencies (a ticket in both up_dependencies and down_dependencies)

**Error Handling:**

The tool raises `ValueError` for validation failures:

```python
# Error: Empty title
create_ticket(ticket_type="epic", title="")
# ValueError: Ticket title cannot be empty

# Error: Epic with parent
create_ticket(ticket_type="epic", title="Test", parent="bees-abc")
# ValueError: Epics cannot have a parent

# Error: Subtask without parent
create_ticket(ticket_type="subtask", title="Test")
# ValueError: Subtasks must have a parent

# Error: Non-existent parent
create_ticket(ticket_type="task", title="Test", parent="bees-nonexistent")
# ValueError: Parent ticket does not exist: bees-nonexistent

# Error: Non-existent dependency
create_ticket(ticket_type="task", title="Test", up_dependencies=["bees-fake"])
# ValueError: Dependency ticket does not exist: bees-fake

# Error: Circular dependency
create_ticket(
    ticket_type="task",
    title="Test",
    up_dependencies=["bees-x"],
    down_dependencies=["bees-x"]
)
# ValueError: Circular dependency detected: ticket cannot both depend on and be
# depended on by the same tickets: {'bees-x'}
```

All validation errors are logged for debugging purposes.

#### update_ticket

Update an existing ticket with automatic bidirectional relationship synchronization. When updating relationships (parent, children, dependencies), all related tickets are automatically updated to maintain consistency.

**Parameters:**
- `ticket_id` (required): ID of the ticket to update
- `title`: New title (optional)
- `description`: New description (optional)
- `parent`: New parent ticket ID, or None/empty string to remove parent (optional)
- `children`: New list of child ticket IDs (optional)
- `up_dependencies`: New list of blocking dependency ticket IDs (optional)
- `down_dependencies`: New list of dependent ticket IDs (optional)
- `labels`: New list of labels (optional)
- `owner`: New owner/assignee (optional)
- `priority`: New priority level (optional)
- `status`: New status (optional)

**Returns:**
```json
{
  "status": "success",
  "ticket_id": "bees-abc",
  "ticket_type": "task",
  "title": "Updated Title"
}
```

**Examples:**

Update basic fields:
```python
result = update_ticket(
    ticket_id="bees-abc",
    title="Updated Title",
    status="in_progress",
    priority=1
)
# Only specified fields are updated, others remain unchanged
```

Add parent relationship:
```python
result = update_ticket(
    ticket_id="bees-tk1",
    parent="bees-ep1"
)
# Parent epic (bees-ep1) automatically gets bees-tk1 added to its children array
```

Remove parent relationship:
```python
result = update_ticket(
    ticket_id="bees-tk1",
    parent=None  # or empty string ""
)
# Parent's children array is automatically updated to remove bees-tk1
# Task's parent field is set to None
```

Add children:
```python
result = update_ticket(
    ticket_id="bees-ep1",
    children=["bees-tk1", "bees-tk2", "bees-tk3"]
)
# All three tasks automatically get their parent field set to bees-ep1
```

Remove children:
```python
result = update_ticket(
    ticket_id="bees-ep1",
    children=[]  # Empty list removes all children
)
# All former children have their parent field cleared (set to None)
```

Update dependencies:
```python
result = update_ticket(
    ticket_id="bees-tk1",
    up_dependencies=["bees-tk2", "bees-tk3"],  # This task depends on tk2 and tk3
    down_dependencies=["bees-tk4"]             # This task blocks tk4
)
# Blocking tickets (tk2, tk3) automatically get tk1 added to their down_dependencies
# Blocked ticket (tk4) automatically gets tk1 added to its up_dependencies
```

**Bidirectional Relationship Updates:**

The update_ticket tool calculates the difference between old and new relationship values and synchronizes changes across all affected tickets:

1. **Parent Changes**:
   - If parent changed: Remove ticket from old parent's children, add to new parent's children
   - If parent removed (None): Remove ticket from old parent's children, clear parent field
   - If parent added: Add ticket to new parent's children, set parent field

2. **Children Changes**:
   - Added children: Set parent field on each new child
   - Removed children: Clear parent field on each removed child

3. **Dependency Changes**:
   - Added up_dependencies: Add ticket to each blocking ticket's down_dependencies
   - Removed up_dependencies: Remove ticket from each formerly blocking ticket's down_dependencies
   - Added down_dependencies: Add ticket to each blocked ticket's up_dependencies
   - Removed down_dependencies: Remove ticket from each formerly blocked ticket's up_dependencies

**Validation Rules:**
- Ticket ID must exist
- Title cannot be empty (if provided)
- All referenced relationship IDs must exist (parent, children, dependencies)
- Cannot create circular dependencies (ticket in both up and down dependencies)
- Relationship changes maintain type hierarchy (Epic→Task→Subtask)

**Error Handling:**

The tool raises `ValueError` for validation failures:

```python
# Error: Non-existent ticket
update_ticket(ticket_id="bees-nonexistent", title="Test")
# ValueError: Ticket does not exist: bees-nonexistent

# Error: Empty title
update_ticket(ticket_id="bees-abc", title="")
# ValueError: Ticket title cannot be empty

# Error: Non-existent parent
update_ticket(ticket_id="bees-tk1", parent="bees-nonexistent")
# ValueError: Parent ticket does not exist: bees-nonexistent

# Error: Non-existent child
update_ticket(ticket_id="bees-ep1", children=["bees-nonexistent"])
# ValueError: Child ticket does not exist: bees-nonexistent

# Error: Non-existent dependency
update_ticket(ticket_id="bees-tk1", up_dependencies=["bees-nonexistent"])
# ValueError: Dependency ticket does not exist: bees-nonexistent

# Error: Circular dependency
update_ticket(
    ticket_id="bees-tk1",
    up_dependencies=["bees-tk2"],
    down_dependencies=["bees-tk2"]
)
# ValueError: Circular dependency detected: {'bees-tk2'}
```

**Edge Cases Handled:**

1. **Partial Updates**: Only specified fields are modified; unspecified fields retain their current values
2. **Removing Relationships**: Setting parent to None or empty string removes the relationship
3. **Empty Arrays**: Setting children, up_dependencies, or down_dependencies to [] removes all relationships
4. **Idempotency**: Setting a relationship that already exists is safe (no duplicates created)
5. **Concurrent Modifications**: File locking prevents data corruption from simultaneous updates

All validation errors are logged for debugging purposes.

#### add_named_query

Register a new named query for later execution. Named queries can be parameterized with
placeholders that are substituted at execution time, allowing reusable query templates.

**Parameters:**
- `name` (required): Name for the query (used to execute it later)
- `query_yaml` (required): YAML string representing the query structure
- `validate` (optional): Whether to validate query structure (default: true, set false for parameterized queries)

**Returns:**
```json
{
  "status": "success",
  "query_name": "beta_tasks",
  "message": "Query 'beta_tasks' registered successfully"
}
```

**Examples:**

Register a simple query:
```python
query_yaml = """
- - type=task
  - label~beta
- - parent
"""
result = add_named_query("beta_task_parents", query_yaml)
# Returns: {"status": "success", "query_name": "beta_task_parents", ...}
```

Register a parameterized query:
```python
# Use placeholders like {param_name} for dynamic values
query_yaml = """
- - type={ticket_type}
  - label~{label}
"""
# Skip validation for parameterized queries (placeholders won't validate)
result = add_named_query("typed_label_filter", query_yaml, validate=False)
# Returns: {"status": "success", ...}
```

**Query Storage:**

Named queries are persisted to `.bees/queries.yaml` and survive server restarts.
You can list all registered queries using the query storage module.

**Validation:**

When `validate=True` (default), the query structure is validated before storage:
- Query must be valid YAML list of stages
- Each stage must be list of search or graph terms
- Search terms validated: type=, id=, title~, label~
- Graph terms validated: parent, children, up_dependencies, down_dependencies
- No mixing of search and graph terms in same stage
- Regex patterns must be compilable

**Error Handling:**
```python
# Error: Empty query name
add_named_query("", query_yaml)
# ValueError: Query name cannot be empty

# Error: Invalid query structure (malformed YAML)
add_named_query("bad_query", "not: valid: yaml: structure")
# ValueError: Invalid query structure: ...

# Error: Invalid search term
add_named_query("bad_query", "- [type=invalid_type]")
# ValueError: Invalid query structure: Stage 0: Invalid type 'invalid_type'. Valid types: epic, task, subtask
```

**Use Cases:**
- **Reusable queries**: Define common queries once, execute them by name
- **Parameterized queries**: Create query templates with placeholders for dynamic execution
- **Team workflows**: Share queries across team members via version control
- **Complex filters**: Store complex regex patterns and multi-stage pipelines with memorable names

#### execute_query

Execute a named query that was previously registered with `add_named_query`. Supports
parameter substitution for parameterized queries.

**Parameters:**
- `query_name` (required): Name of the registered query to execute
- `params` (optional): JSON string of parameters for variable substitution

**Returns:**
```json
{
  "status": "success",
  "query_name": "beta_tasks",
  "result_count": 5,
  "ticket_ids": ["bees-tk1", "bees-tk2", "bees-tk3", "bees-tk4", "bees-tk5"]
}
```

**Examples:**

Execute a simple query:
```python
result = execute_query("beta_task_parents")
# Returns: {"status": "success", "result_count": 3, "ticket_ids": [...]}
```

Execute a parameterized query:
```python
# Query was registered with placeholders: type={ticket_type}, label~{label}
params_json = '{"ticket_type": "task", "label": "beta"}'
result = execute_query("typed_label_filter", params=params_json)
# Substitutes: type=task, label~beta
# Returns: {"status": "success", "result_count": 5, "ticket_ids": [...]}
```

Execute with multiple parameters:
```python
# Query: [["type={type}", "label~{label}"], ["parent"]]
params_json = '{"type": "task", "label": "open"}'
result = execute_query("my_query", params=params_json)
```

**Parameter Substitution:**

Parameters are substituted using placeholder syntax `{param_name}`:
- Placeholders in query: `type={ticket_type}`, `label~{label}`, `title~{pattern}`
- Parameters JSON: `{"ticket_type": "task", "label": "beta", "pattern": ".*API.*"}`
- Result: `type=task`, `label~beta`, `title~.*API.*`

**Query Execution:**

The execute_query tool:
1. Loads the named query from storage (`.bees/queries.yaml`)
2. Performs parameter substitution if params provided
3. Executes query using PipelineEvaluator (loads tickets from `tickets/` directory)
4. Returns sorted list of matching ticket IDs

**Error Handling:**
```python
# Error: Query not found
execute_query("nonexistent_query")
# ValueError: Query not found: nonexistent_query. Available queries: beta_tasks, open_items

# Error: Missing required parameter
execute_query("typed_filter", params='{}')
# ValueError: Missing required parameter: ticket_type. Provided: (none)

# Error: Invalid JSON in params
execute_query("my_query", params="not valid json")
# ValueError: Invalid JSON in params: ...

# Error: Query execution failure (e.g., tickets/ directory not found)
execute_query("beta_tasks")
# ValueError: Failed to execute query 'beta_tasks': Tickets directory not found
```

**Listing Available Queries:**

You can list all registered queries programmatically:
```python
from src.query_storage import list_queries

available = list_queries()
print(f"Available queries: {', '.join(available)}")
```

**Performance:**

- Query loading: O(1) lookup in queries.yaml
- Parameter substitution: O(n) where n = number of terms in query
- Query execution: Depends on query complexity and ticket count
  - Loads all tickets once: O(t) where t = total tickets
  - Executes stages: O(s * m) where s = stages, m = tickets per stage

**Common Query Patterns:**

Find open work items:
```yaml
open_work_items:
  - - type={type}
    - label~(?i)(open|in progress)
```

Find blocked tasks:
```yaml
blocked_tasks:
  - - type=task
  - - up_dependencies
```

Find epic children:
```yaml
epic_children:
  - - id={epic_id}
  - - children
```

#### delete_ticket

Delete a ticket and automatically clean up all relationships in related tickets.
When a ticket is deleted, all references to it are removed from parent, children,
and dependency arrays across all related tickets.

**Parameters:**
- `ticket_id` (required): ID of the ticket to delete
- `cascade` (optional): If true, recursively delete all child tickets (default: false)

**Returns:**
```json
{
  "status": "success",
  "ticket_id": "bees-abc",
  "ticket_type": "task",
  "message": "Successfully deleted ticket bees-abc"
}
```

**Examples:**

Delete a ticket without children:
```python
result = delete_ticket(ticket_id="bees-tk1")
# Returns: {"status": "success", "ticket_id": "bees-tk1", ...}
# Parent's children array automatically cleaned up
# All dependency arrays in related tickets automatically cleaned up
```

Delete a ticket with cascade (removes children):
```python
result = delete_ticket(ticket_id="bees-ep1", cascade=True)
# Recursively deletes bees-ep1 and ALL its children (tasks and subtasks)
# All relationships cleaned up for every deleted ticket
```

Delete a ticket without cascade (unlinks children):
```python
result = delete_ticket(ticket_id="bees-ep1", cascade=False)
# Deletes bees-ep1 but leaves children intact
# Children (tasks) have their parent field set to None
# Children (subtasks) remain pointing to deleted parent (validation requirement)
```

**Automatic Cleanup Behavior:**

When a ticket is deleted, the following cleanup occurs automatically:

1. **Parent Cleanup**: If the ticket has a parent, it's removed from the parent's
   `children` array
2. **Dependency Cleanup**: The ticket ID is removed from:
   - `down_dependencies` array in all blocking tickets (tickets in up_dependencies)
   - `up_dependencies` array in all blocked tickets (tickets in down_dependencies)
3. **Children Handling** (based on cascade parameter):
   - If `cascade=true`: All child tickets are recursively deleted with the same
     cleanup logic
   - If `cascade=false`:
     - Task and Epic children: Parent field set to None (unlinked)
     - Subtask children: Parent field unchanged (subtasks require a parent, so they
       remain orphaned pointing to deleted parent)

**Validation Rules:**
- Ticket ID must exist
- Cannot delete non-existent tickets

**Error Handling:**

The tool raises `ValueError` for validation failures:

```python
# Error: Non-existent ticket
delete_ticket(ticket_id="bees-nonexistent")
# ValueError: Ticket does not exist: bees-nonexistent

# Error: File access issues
delete_ticket(ticket_id="bees-tk1")
# ValueError: Failed to delete ticket file ... (if filesystem error occurs)
```

**Cascade Delete Example:**

```python
# Given hierarchy:
#   Epic bees-ep1
#     Task bees-tk1
#       Subtask bees-st1
#       Subtask bees-st2
#     Task bees-tk2

# Cascade delete the epic
delete_ticket(ticket_id="bees-ep1", cascade=True)

# Result: All 5 tickets deleted (ep1, tk1, tk2, st1, st2)
# All relationships cleaned up for each deleted ticket
# Parent epic's parent (if any) has bees-ep1 removed from children
# Any tickets depending on any of these 5 tickets have dependencies cleaned up
```

**Important Notes:**
- Deletion is immediate and permanent - there is no undo
- All relationship cleanup is atomic - either all related tickets update or the
  operation fails
- Cascade delete processes children depth-first (deletes deepest descendants first)
- Subtasks cannot be unlinked from deleted parents due to validation requirements,
  so they remain as orphaned records if cascade=false

#### generate_index

Generate a markdown index of all tickets with optional filtering by status and type.
The index provides a consolidated view of all tickets grouped by type (Epics, Tasks,
Subtasks) with clickable ticket IDs, titles, and status information.

**Parameters:**
- `status` (optional): Filter tickets by status (e.g., "open", "completed", "in_progress")
- `type` (optional): Filter tickets by type (e.g., "epic", "task", "subtask")

**Returns:**
```json
{
  "status": "success",
  "markdown": "# Ticket Index\n\n## Epics\n- [bees-abc] Epic Title (open)\n..."
}
```

**Examples:**

Generate index of all tickets:
```python
result = generate_index()
# Returns: {"status": "success", "markdown": "# Ticket Index\n\n## Epics\n..."}
# Includes all epics, tasks, and subtasks regardless of status
```

Filter by status (open tickets only):
```python
result = generate_index(status="open")
# Returns only tickets with status="open"
# Shows open epics, tasks, and subtasks
```

Filter by type (epics only):
```python
result = generate_index(type="epic")
# Returns only epic tickets
# Includes all statuses (open, completed, etc.)
```

Combine both filters (open tasks):
```python
result = generate_index(status="open", type="task")
# Returns only tasks with status="open"
# Excludes epics and subtasks
# Excludes completed/closed tasks
```

**Generated Index Format:**

The markdown index is structured with sections for each ticket type:

```markdown
# Ticket Index

## Epics
- [bees-abc] Authentication System (open)
- [bees-def] Payment Integration (completed)

## Tasks
- [bees-ghi] Build Login API (in_progress)
- [bees-jkl] Implement OAuth (open)

## Subtasks
- [bees-mno] Write API tests (open) (parent: bees-ghi)
- [bees-pqr] Add rate limiting (completed) (parent: bees-ghi)
```

**Key Features:**
- **Grouped by Type**: Separate sections for Epics, Tasks, and Subtasks
- **Sorted by ID**: Tickets within each section sorted alphabetically by ID
- **Status Display**: Current status shown inline for quick reference
- **Parent Context**: Subtasks include parent ticket ID for hierarchy
- **Empty Sections**: Shows "*No tickets found*" when section is empty

**Use Cases:**

Browse all tickets:
```python
# Get overview of entire ticket database
index = generate_index()
print(index["markdown"])
```

View work in progress:
```python
# See all open work items
open_work = generate_index(status="open")
```

Review completed epics:
```python
# Check which epics are done
done_epics = generate_index(status="completed", type="epic")
```

Check subtask status:
```python
# See all subtasks and their parents
all_subtasks = generate_index(type="subtask")
```

**Performance Notes:**
- Index is generated on-demand (not cached)
- Scans all ticket files from filesystem
- Typical generation time: 50-100ms for 500 tickets
- Filters are applied during scanning to reduce memory usage

**Filter Matching:**
- Status filter is case-sensitive: use exact status values from tickets
- Type filter accepts: "epic", "task", or "subtask"
- Invalid filter values result in empty sections (no error)
- Null/missing parameters mean no filtering (include all)

**Error Handling:**

The tool handles errors gracefully:

```python
# Corrupted ticket files are skipped with warning
# Missing tickets directory returns empty sections
# Filesystem errors logged and raised as ValueError

try:
    result = generate_index()
    print(result["markdown"])
except ValueError as e:
    print(f"Index generation failed: {e}")
```

### Server Lifecycle Management

**Starting the server:**
```python
from src.mcp_server import start_server

result = start_server()
# Returns: {"status": "running", "name": "Bees Ticket Management Server", "version": "0.1.0"}
```

**Stopping the server:**
```python
from src.mcp_server import stop_server

result = stop_server()
# Returns: {"status": "stopped", "name": "Bees Ticket Management Server"}
```

**Checking server health:**
```python
from src.mcp_server import _health_check

result = _health_check()
# Returns health status with server_running and ready flags
```

### Troubleshooting MCP Server

**Server won't start:**
- Ensure fastmcp is installed: `poetry install`
- Check that Python version is 3.10 or higher
- Verify no port conflicts if using network transport

**Tool calls failing:**
- Check server is running with health_check tool
- Verify ticket_id exists for update/delete operations
- Ensure ticket_type is valid for create operations

**Relationship sync issues:**
- Verify related ticket IDs exist before creating relationships
- Check that parent/child hierarchy is valid (Epic→Task→Subtask)
- Use health_check to confirm server is in ready state

## Linter

The Bees linter validates ticket files for schema compliance and relationship consistency.
It provides structured error reporting to help identify and fix issues in your ticket database.

### Running the Linter

**Command Line Interface:**

The recommended way to run the linter is via the CLI command:

```bash
# Run linter on default tickets directory
poetry run python -m src.cli

# Run linter on custom directory
poetry run python -m src.cli --tickets-dir /path/to/tickets

# Output results as JSON
poetry run python -m src.cli --json

# Enable verbose logging
poetry run python -m src.cli -v
```

The CLI automatically updates the corruption state based on validation results. If errors are found, the database is marked as corrupt and the MCP server will refuse to start.

**Programmatic Usage:**

To validate all tickets programmatically:

```python
from src.linter import Linter

# Create linter instance
linter = Linter("tickets")

# Run validation checks (automatically updates corruption state)
report = linter.run()

# Check if database is corrupt
if report.is_corrupt():
    print("Database has validation errors!")
    print(report.to_markdown())
else:
    print("Database is clean - no errors found")
```

### Validation Checks

The linter performs the following validation checks:

**ID Format Validation**
- Ensures all ticket IDs match the required pattern: `bees-[a-z0-9]{3}`
- Example valid IDs: `bees-abc`, `bees-250`, `bees-9pw`
- Example invalid IDs: `bees-ABC` (uppercase), `bees-1234` (too long), `INVALID-ID` (wrong format)

**ID Uniqueness Validation**
- Detects duplicate ticket IDs across all ticket types (epics, tasks, subtasks)
- Each ticket must have a globally unique ID

**Bidirectional Relationship Validation**

The linter enforces bidirectional consistency for two types of relationships:

*Parent/Children Relationships:*
- When a ticket lists another ticket in its `parent` field, the parent must list it
  in its `children` field
- When a ticket lists children in its `children` field, each child must list it as
  their `parent`
- Detects orphaned child references (child lists parent, but parent doesn't list child)
- Detects orphaned parent references (parent lists child, but child doesn't list parent)

*Dependency Relationships:*
- When ticket A lists ticket B in `up_dependencies`, ticket B must list ticket A in
  `down_dependencies`
- When ticket A lists ticket B in `down_dependencies`, ticket B must list ticket A in
  `up_dependencies`
- Detects orphaned dependencies (missing backlinks in dependency chains)
- Detects missing backlinks (one-way dependency references)

**Cyclical Dependency Detection**

The linter detects cycles in both blocking dependencies and hierarchical relationships to prevent invalid dependency configurations:

*Blocking Dependency Cycles:*
- Detects circular dependencies in `up_dependencies` and `down_dependencies` chains
- Example: Ticket A depends on B, B depends on C, C depends on A (forms a cycle)
- Also detects self-cycles where a ticket depends on itself
- Error type: `dependency_cycle`

*Hierarchical Relationship Cycles:*
- Detects circular parent-child relationships in `parent` and `children` fields
- Example: Ticket A is parent of B, B is parent of C, C is parent of A (forms a cycle)
- Also detects self-cycles where a ticket is its own parent
- Error type: `hierarchy_cycle`

The cycle detector uses depth-first search (DFS) with path tracking to identify cycles and reports the exact cycle path in error messages (e.g., "bees-aa1 -> bees-bb1 -> bees-cc1 -> bees-aa1").

**Example Validation Errors:**

```markdown
# Orphaned Child Example
ERROR: Ticket 'bees-xyz' lists 'bees-abc' as parent, but 'bees-abc' does not list
'bees-xyz' in its children

# Missing Backlink Example
ERROR: Ticket 'bees-aaa' lists 'bees-bbb' in down_dependencies, but 'bees-bbb' does
not list 'bees-aaa' in its up_dependencies

# Blocking Dependency Cycle Example
ERROR: Cycle detected in blocking dependencies: bees-aa1 -> bees-bb1 -> bees-cc1 -> bees-aa1

# Hierarchical Cycle Example
ERROR: Cycle detected in parent/child hierarchy: bees-ep1 -> bees-tk1 -> bees-st1 -> bees-ep1
```

**Interpreting Cycle Error Messages:**

When a cycle is detected, the error message shows the complete cycle path using arrow notation:
- `bees-aa1 -> bees-bb1 -> bees-cc1 -> bees-aa1` indicates ticket aa1 depends on bb1, bb1 depends on cc1, and cc1 depends back on aa1
- The first ticket ID in the path is where the cycle was detected
- For self-cycles (ticket depends on itself), the path will be: `bees-abc -> bees-abc`

**Fixing Validation Errors:**

To fix relationship errors, ensure all relationships are properly synchronized:
- Add the missing backlink to the referenced ticket
- Remove the orphaned reference if it's incorrect
- Use the relationship sync tools to maintain consistency

To fix cycle errors:
- Break the cycle by removing one or more dependency/parent links
- Reorganize dependencies to create an acyclic structure
- For blocking dependencies: Ensure work items have a clear order without circular dependencies
- For hierarchical relationships: Ensure parent-child structure forms a proper tree/DAG

After fixing validation errors, run the linter again to clear the corruption state:
```bash
poetry run python -m src.cli
```

### Corruption State Management

The linter automatically manages the database corruption state based on validation results:

**Corruption State File:**
- Location: `.bees/corruption_report.json`
- Contains: validation errors, error count, timestamp
- Created automatically when linter finds errors
- Cleared automatically when linter finds no errors

**Checking Corruption State:**

```python
from src.corruption_state import is_corrupt, get_report

# Check if database is corrupt
if is_corrupt():
    print("Database is corrupt!")

    # Get corruption report
    report = get_report()
    if report:
        print(f"Error count: {report['error_count']}")
        print(f"Timestamp: {report['timestamp']}")
```

**Manually Clearing Corruption State:**

```python
from src.corruption_state import clear

# Clear corruption state (use after manually fixing issues)
clear()
```

**MCP Server Startup Check:**

The MCP server checks corruption state on startup and refuses to start if the database is corrupt:

```bash
$ poetry run start-mcp
ERROR: DATABASE CORRUPTION DETECTED
The ticket database is corrupt. MCP server cannot start.
Run the linter to see validation errors:
  python -m src.cli --tickets-dir tickets

Found 3 validation error(s)

Sample errors:
  - [id_format] Ticket ID 'INVALID-ID' does not match required format: bees-[a-z0-9]{3}
  - [duplicate_id] Duplicate ticket ID 'bees-abc' found (also in epic)
  - [dependency_cycle] Cycle detected in blocking dependencies: bees-aa1 -> bees-bb1 -> bees-aa1

Fix the validation errors and run the linter again to clear the corruption state.
```

This ensures data integrity by preventing the MCP server from modifying a corrupt database.

### Error Reporting

The linter provides structured error reporting with severity levels:

**Error Severity Levels:**
- `error`: Critical issues that mark the database as corrupt
- `warning`: Minor issues that don't prevent operation

**Report Formats:**

JSON format for programmatic processing:
```python
# Get JSON report
json_str = report.to_json()

# Or get dictionary
report_dict = report.to_dict()
```

Markdown format for human-readable output:
```python
# Generate markdown report
markdown = report.to_markdown()
print(markdown)
```

**Example Markdown Output:**
```markdown
# Linter Report

## Summary

- **Status**: ❌ CORRUPT
- **Total Errors**: 2
- **Total Warnings**: 0
- **Affected Tickets**: 2

## Validation Errors by Type

### Id Format
*1 errors, 0 warnings*

- ❌ **INVALID-ID**: Ticket ID 'INVALID-ID' does not match required format: bees-[a-z0-9]{3}

### Duplicate Id
*1 errors, 0 warnings*

- ❌ **bees-abc**: Duplicate ticket ID 'bees-abc' found (also in epic)
```

### Querying Validation Errors

Filter errors by various criteria:

```python
# Get all errors
all_errors = report.get_errors()

# Filter by ticket ID
ticket_errors = report.get_errors(ticket_id="bees-abc")

# Filter by error type
format_errors = report.get_errors(error_type="id_format")
duplicate_errors = report.get_errors(error_type="duplicate_id")
cycle_errors = report.get_errors(error_type="dependency_cycle")
hierarchy_errors = report.get_errors(error_type="hierarchy_cycle")

# Filter by severity
errors = report.get_errors(severity="error")
warnings = report.get_errors(severity="warning")

# Combine filters
critical = report.get_errors(ticket_id="bees-abc", severity="error")
```

### Summary Statistics

Get summary statistics about validation errors:

```python
summary = report.get_summary()

# Access summary data
print(f"Total errors: {summary['total_errors']}")
print(f"Total warnings: {summary['total_warnings']}")
print(f"Affected tickets: {summary['affected_tickets']}")

# Errors by type
for error_type, counts in summary['by_type'].items():
    print(f"{error_type}: {counts['errors']} errors, {counts['warnings']} warnings")
```

### Programmatic API

**Linter Class**
- `Linter(tickets_dir: str)`: Initialize linter with tickets directory
- `run() -> LinterReport`: Scan all tickets and return validation report

**LinterReport Class**
- `add_error(ticket_id, error_type, message, severity)`: Add validation error
- `get_errors(ticket_id, error_type, severity)`: Query errors by criteria
- `is_corrupt() -> bool`: Check if database has critical errors
- `to_json() -> str`: Generate JSON report
- `to_markdown() -> str`: Generate markdown report
- `get_summary() -> dict`: Get summary statistics

**ValidationError Dataclass**
- `ticket_id`: ID of the ticket with the error
- `error_type`: Category of error (e.g., 'id_format', 'duplicate_id')
- `message`: Human-readable error description
- `severity`: Error severity ('error' or 'warning')

## API Usage

### Creating Tickets

Use the factory functions to create new tickets:

```python
from src.ticket_factory import create_epic, create_task, create_subtask

# Create an epic
epic_id = create_epic(
    title="Implement Authentication System",
    description="Build user authentication with OAuth support",
    labels=["security", "backend"],
    priority=0,
    owner="user@example.com"
)
print(f"Created epic: {epic_id}")  # e.g., "bees-abc"

# Create a task linked to the epic
task_id = create_task(
    title="Build login API endpoint",
    description="Implement POST /api/login endpoint",
    parent=epic_id,
    labels=["backend", "api"],
    priority=1
)
print(f"Created task: {task_id}")  # e.g., "bees-xyz"

# Create a subtask linked to the task
subtask_id = create_subtask(
    title="Write unit tests for login endpoint",
    description="Test success and failure cases",
    parent=task_id,
    labels=["testing"]
)
print(f"Created subtask: {subtask_id}")  # e.g., "bees-9pw"
```

#### Ticket Creation Parameters

**create_epic(title, description="", labels=None, up_dependencies=None, down_dependencies=None,
owner=None, priority=None, status="open", ticket_id=None)**
- `title` (required): Epic title
- `description`: Description text (also used as markdown body)
- `labels`: List of label strings for categorization
- `up_dependencies`: List of ticket IDs that block this epic
- `down_dependencies`: List of ticket IDs that this epic blocks
- `owner`: Owner email or username
- `priority`: Priority level (0-4, lower is higher priority)
- `status`: Status string (default: "open")
- `ticket_id`: Optional custom ID (auto-generated if not provided)

**create_task(title, description="", parent=None, labels=None, up_dependencies=None,
down_dependencies=None, owner=None, priority=None, status="open", ticket_id=None)**
- Same parameters as create_epic
- `parent`: Optional parent epic ID

**create_subtask(title, parent, description="", labels=None, up_dependencies=None,
down_dependencies=None, owner=None, priority=None, status="open", ticket_id=None)**
- Same parameters as create_task
- `parent` (required): Parent task ID - subtasks must have a parent

#### Ticket ID Format

Ticket IDs are automatically generated in the format: `bees-<3 alphanumeric chars>`

Examples: `bees-250`, `bees-abc`, `bees-9pw`, `bees-xyz`

IDs are randomly generated with collision detection to ensure uniqueness.

#### YAML Frontmatter Structure

Created tickets have this structure:

```markdown
---
id: bees-250
type: epic
title: Implement Authentication System
description: Build user authentication with OAuth support
labels:
- security
- backend
status: open
priority: 0
owner: user@example.com
created_at: '2026-01-30T10:00:00.123456'
updated_at: '2026-01-30T10:00:00.123456'
---

Build user authentication with OAuth support
```

### Reading Tickets

Use the `read_ticket()` function to load and parse ticket files:

```python
from src.reader import read_ticket
from src.models import Epic, Task, Subtask

# Read an epic ticket
epic = read_ticket("tickets/epics/bees-250.md")
print(f"Epic: {epic.title}")
print(f"Children: {epic.children}")

# Read a task ticket
task = read_ticket("tickets/tasks/bees-jty.md")
print(f"Task: {task.title}")
print(f"Parent: {task.parent}")

# Read a subtask ticket
subtask = read_ticket("tickets/subtasks/bees-xyz.md")
print(f"Subtask: {subtask.title}")
print(f"Parent: {subtask.parent}")
```

### Ticket Data Classes

The reader returns typed objects based on the ticket type:

- **Epic**: For tickets with `type: epic`
- **Task**: For tickets with `type: task`
- **Subtask**: For tickets with `type: subtask`

All ticket types include these fields:
- `id`: Ticket identifier (e.g., "bees-250")
- `type`: Ticket type ("epic", "task", or "subtask")
- `title`: Ticket title
- `description`: Ticket description (from markdown body)
- `labels`: List of label strings
- `up_dependencies`: List of ticket IDs this ticket depends on
- `down_dependencies`: List of ticket IDs that depend on this ticket
- `parent`: Parent ticket ID (for Tasks and Subtasks)
- `children`: List of child ticket IDs (for Epics and Tasks)
- `created_at`, `updated_at`: Optional datetime fields
- `owner`, `created_by`, `priority`, `status`: Optional metadata fields

### Error Handling

The reader raises specific exceptions for different error conditions:

```python
from src.reader import read_ticket
from src.parser import ParseError
from src.validator import ValidationError

try:
    ticket = read_ticket("tickets/epics/bees-250.md")
except FileNotFoundError:
    print("Ticket file not found")
except ParseError as e:
    print(f"Failed to parse ticket file: {e}")
except ValidationError as e:
    print(f"Ticket validation failed: {e}")
```

Factory functions also raise ValueError for invalid inputs:

```python
from src.ticket_factory import create_epic

try:
    epic_id = create_epic(title="", description="test")
except ValueError as e:
    print(f"Invalid input: {e}")  # "Epic title is required"
```

## Troubleshooting

### Common Creation Errors

**ValueError: title is required**
- All tickets must have a non-empty title
- Solution: Provide a title parameter when calling create functions

**ValueError: parent is required**
- Subtasks must have a parent task ID
- Solution: Provide the parent parameter when calling create_subtask()

**FileNotFoundError or OSError during creation**
- The tickets directory structure may not exist
- Solution: Ensure /tickets/epics, /tickets/tasks, and /tickets/subtasks directories exist
- The factory functions will attempt to create directories automatically

**ID collision warnings**
- Very rare: Random ID generation created a duplicate
- Solution: The system automatically retries with a new ID
- If this persists, check your tickets directory for corruption

## Sample Tickets

The repository includes sample tickets demonstrating all features of the ticket
system. These samples are located in `/tickets` and can be used as templates or
for testing.

### Sample File Locations

- **Epic**: `tickets/epics/sample-epic.md` (ID: bees-ep1)
- **Task**: `tickets/tasks/sample-task.md` (ID: bees-tk1)
- **Subtask**: `tickets/subtasks/sample-subtask.md` (ID: bees-sb1)

### Sample Epic (bees-ep1)

Demonstrates Epic-specific fields:

```yaml
id: bees-ep1
type: epic
title: Sample Epic - E-commerce Platform
description: Implement a complete e-commerce platform with product catalog,
shopping cart, and checkout functionality
labels:
  - feature
  - backend
  - frontend
up_dependencies: []
down_dependencies: []
children: []
status: open
priority: 2
owner: engineering-team
created_at: 2026-01-30T15:00:00Z
updated_at: 2026-01-30T15:00:00Z
```

### Sample Task (bees-tk1)

Demonstrates Task-specific fields with parent reference to epic:

```yaml
id: bees-tk1
type: task
title: Sample Task - Implement Product Catalog API
description: Build RESTful API endpoints for product catalog with search and
filtering
parent: bees-ep1  # Links to sample epic
labels:
  - backend
  - api
  - database
up_dependencies: []
down_dependencies:
  - bees-dp1  # This task blocks another task
children: []
status: in progress
priority: 1
owner: backend-team
```

### Sample Subtask (bees-sb1)

Demonstrates Subtask-specific fields with parent reference to task:

```yaml
id: bees-sb1
type: subtask
title: Sample Subtask - Create database schema for products table
description: Design and implement the products table schema with indexes
parent: bees-tk1  # Links to sample task (REQUIRED for subtasks)
labels:
  - database
  - migration
up_dependencies: []
down_dependencies: []
status: open
priority: 0
owner: alice@example.com
```

### Relationship Linking Examples

The sample tickets demonstrate the three-tier hierarchy:

1. **Parent-Child Relationships**:
   - Epic `bees-ep1` has child Task `bees-tk1` (via `parent` field in task)
   - Task `bees-tk1` has child Subtask `bees-sb1` (via `parent` field in
subtask)

2. **Dependency Relationships**:
   - Task `bees-tk1` has a `down_dependency` on `bees-dp1`, meaning it blocks
that task
   - When bidirectional consistency is enforced, `bees-dp1` would have
`bees-tk1` in its `up_dependencies`

3. **Field Types**:
   - `parent`: Single string or null (one parent per ticket)
   - `children`: List of strings (can have multiple children)
   - `up_dependencies`: List of strings (tickets that block this one)
   - `down_dependencies`: List of strings (tickets blocked by this one)

### Reading Sample Tickets

Use the sample tickets to test the reader module:

```python
from src.reader import read_ticket

# Read and parse sample tickets
epic = read_ticket('tickets/epics/sample-epic.md')
task = read_ticket('tickets/tasks/sample-task.md')
subtask = read_ticket('tickets/subtasks/sample-subtask.md')

# Verify YAML frontmatter parsing
print(f"Epic ID: {epic.id}, Type: {epic.type}")
print(f"Task Parent: {task.parent}")
print(f"Subtask Parent: {subtask.parent}")

# Check relationships
print(f"Task Down Dependencies: {task.down_dependencies}")
```

## Relationship Synchronization

The relationship synchronization module (`src/relationship_sync.py`) maintains bidirectional consistency of all ticket relationships. When you add a child to a parent or create a dependency, both tickets are automatically updated to reflect the relationship in both directions.

### Overview

**Bidirectional Consistency**: The sync module ensures that:
- When a child is added to a parent, the parent's `children` array is updated AND the child's `parent` field is set
- When a dependency is created, both `up_dependencies` (on dependent) and `down_dependencies` (on blocker) are updated
- All relationship operations are validated before being applied
- Changes are atomic - either all related tickets update or none do

### Core Helper Functions

#### add_child_to_parent(parent_id, child_id)

Adds a child to a parent ticket with bidirectional updates.

```python
from src.relationship_sync import add_child_to_parent

# Add a task as child of an epic
add_child_to_parent("bees-ep1", "bees-tk1")

# Now:
# - bees-ep1.children includes "bees-tk1"
# - bees-tk1.parent is "bees-ep1"
```

**Features**:
- Validates both tickets exist
- Validates type hierarchy (Epic→Task, Task→Subtask)
- Idempotent: safe to call multiple times
- Atomic: updates both tickets or fails cleanly

#### remove_child_from_parent(parent_id, child_id)

Removes a child from a parent ticket with bidirectional cleanup.

```python
from src.relationship_sync import remove_child_from_parent

# Remove a task from its parent epic
remove_child_from_parent("bees-ep1", "bees-tk1")

# Now:
# - bees-ep1.children no longer includes "bees-tk1"
# - bees-tk1.parent is None
```

**Features**:
- Safe to call even if relationship doesn't exist
- Clears parent field on child
- Removes child from parent's children array

#### add_dependency(dependent_id, blocking_id)

Creates a dependency relationship between two tickets.

```python
from src.relationship_sync import add_dependency

# Make bees-ta1 depend on bees-ta2 (ta2 blocks ta1)
add_dependency("bees-ta1", "bees-ta2")

# Now:
# - bees-ta1.up_dependencies includes "bees-ta2" (what blocks me)
# - bees-ta2.down_dependencies includes "bees-ta1" (what I block)
```

**Features**:
- Validates both tickets exist
- Prevents circular dependencies (direct and transitive)
- Prevents self-dependencies
- Idempotent: safe to call multiple times

#### remove_dependency(dependent_id, blocking_id)

Removes a dependency relationship with bidirectional cleanup.

```python
from src.relationship_sync import remove_dependency

# Remove dependency between two tasks
remove_dependency("bees-ta1", "bees-ta2")

# Now:
# - bees-ta1.up_dependencies no longer includes "bees-ta2"
# - bees-ta2.down_dependencies no longer includes "bees-ta1"
```

### Validation Functions

The sync module includes validation functions to prevent invalid relationships:

#### validate_ticket_exists(ticket_id)

Checks if a ticket file exists before modifying relationships.

```python
from src.relationship_sync import validate_ticket_exists

try:
    validate_ticket_exists("bees-xyz")
    print("Ticket exists")
except FileNotFoundError as e:
    print(f"Ticket not found: {e}")
```

#### validate_parent_child_relationship(parent_id, child_id)

Ensures type hierarchy is valid:
- Epic can parent Task
- Task can parent Subtask
- Epic cannot parent Subtask directly

**Performance optimization**: This function uses lightweight type inference to validate the
hierarchy without loading full ticket objects. It checks ticket file locations to determine
types, avoiding the overhead of parsing entire ticket markdown files. This makes validation
significantly faster, especially during bulk relationship operations.

```python
from src.relationship_sync import validate_parent_child_relationship

try:
    # This is valid
    validate_parent_child_relationship("bees-ep1", "bees-tk1")

    # This raises ValueError (Epic cannot parent Subtask)
    validate_parent_child_relationship("bees-ep1", "bees-st1")
except ValueError as e:
    print(f"Invalid hierarchy: {e}")
except FileNotFoundError as e:
    print(f"Ticket not found: {e}")
```

**How it works**:
```python
# Instead of loading full tickets:
# parent = read_ticket(...)  # Slow: parses YAML + markdown
# child = read_ticket(...)

# Uses lightweight file location check:
parent_type = infer_ticket_type_from_id("bees-ep1")  # Fast: only checks file exists
child_type = infer_ticket_type_from_id("bees-tk1")
# Then validates: (parent_type, child_type) in valid_combinations
```

#### check_for_circular_dependency(ticket_id, new_dependency_id)

Prevents dependency cycles by checking both direct and transitive dependencies.

```python
from src.relationship_sync import check_for_circular_dependency

try:
    # This is safe
    check_for_circular_dependency("bees-ta1", "bees-ta2")

    # If bees-ta2 already depends on bees-ta1, this raises ValueError
    check_for_circular_dependency("bees-ta2", "bees-ta1")
except ValueError as e:
    print(f"Circular dependency detected: {e}")
```

### Batch Operations

For efficiency when multiple relationships need updating (e.g., during ticket deletion), use batch operations:

#### sync_relationships_batch(updates)

Applies multiple relationship updates in a single operation with atomicity guarantees.

```python
from src.relationship_sync import sync_relationships_batch

# Update format: (ticket_id, field_name, operation, value)
updates = [
    ("bees-ep1", "children", "add", "bees-tk1"),
    ("bees-ep1", "children", "add", "bees-tk2"),
    ("bees-tk1", "parent", "add", "bees-ep1"),
    ("bees-tk2", "parent", "add", "bees-ep1"),
]

# All updates applied atomically
sync_relationships_batch(updates)
```

**Features**:
- Loads all tickets once (efficient)
- Validates all tickets exist before making changes
- **Automatic deduplication**: Removes duplicate operations before execution to optimize I/O
- **Atomicity guarantee**: all updates succeed or all fail with no partial state
- Implements write-ahead logging (WAL) for rollback capability
- Reduces file I/O overhead for bulk operations

**Atomicity Implementation**:

The batch function provides transaction-like semantics using write-ahead logging:

1. **Phase 1 - Validation**: Verify all referenced tickets exist
2. **Phase 2 - Loading**: Load all affected tickets into memory
3. **Phase 3 - Deduplication**: Remove duplicate operations to prevent redundant I/O
4. **Phase 4 - Backup (WAL)**: Create backup copies of original ticket state
5. **Phase 5 - Apply Changes**: Modify tickets in memory
6. **Phase 6 - Write with Rollback**: Write all tickets to disk
   - If any write fails, restore all tickets from backups
   - Log error details for debugging
   - Raise RuntimeError with original failure cause
7. **Phase 7 - Cleanup**: Clear backup references (in finally block)

**Error Handling**:

```python
from src.relationship_sync import sync_relationships_batch

try:
    updates = [
        ("bees-ep1", "children", "add", "bees-tk1"),
        ("bees-tk1", "parent", "add", "bees-ep1"),
    ]
    sync_relationships_batch(updates)
except ValueError as e:
    # Validation error (invalid operation or field name)
    print(f"Invalid update: {e}")
except FileNotFoundError as e:
    # Referenced ticket doesn't exist
    print(f"Ticket not found: {e}")
except RuntimeError as e:
    # Write failure with rollback attempted
    print(f"Batch operation failed: {e}")
    # All tickets restored to original state
```

**Rollback Behavior**:

If a write operation fails partway through Phase 5:
- All tickets are restored from WAL backups
- No partial state persists
- Original error is wrapped in RuntimeError
- Rollback failures are logged but don't prevent error propagation

Example failure scenario:
```python
# Given tickets: bees-ep1 (children=[]), bees-tk1 (parent=None), bees-tk2
(parent=None)
updates = [
    ("bees-ep1", "children", "add", "bees-tk1"),
    ("bees-ep1", "children", "add", "bees-tk2"),
    ("bees-tk1", "parent", "add", "bees-ep1"),
    ("bees-tk2", "parent", "add", "bees-ep1"),
]

# If write fails after updating bees-ep1 but before bees-tk1:
# - Rollback restores bees-ep1.children to []
# - All tickets remain in original state
# - RuntimeError raised with details
```

**Deduplication Example**:
```python
# If you pass the same operation multiple times, it's automatically deduplicated
updates = [
    ("bees-ep1", "children", "add", "bees-tk1"),
    ("bees-ep1", "children", "add", "bees-tk1"),  # Duplicate - will be removed
    ("bees-tk1", "parent", "add", "bees-ep1"),
]
# Only 2 unique operations are executed: add child once, set parent once
sync_relationships_batch(updates)
```

**Supported operations**:
- `operation`: "add" or "remove"
- `field_name`: "children", "parent", "up_dependencies", "down_dependencies"

### Usage Examples

#### Creating Parent-Child Relationship

```python
from src.ticket_factory import create_epic, create_task
from src.relationship_sync import add_child_to_parent

# Create tickets
epic_id = create_epic(title="Build Authentication")
task_id = create_task(title="Implement OAuth")

# Link them bidirectionally
add_child_to_parent(epic_id, task_id)

# Verify relationship
from src.reader import read_ticket
epic = read_ticket(f"tickets/epics/{epic_id}.md")
task = read_ticket(f"tickets/tasks/{task_id}.md")

print(f"Epic children: {epic.children}")  # ['bees-tk1']
print(f"Task parent: {task.parent}")      # 'bees-ep1'
```

#### Creating Dependencies

```python
from src.ticket_factory import create_task
from src.relationship_sync import add_dependency

# Create tasks
backend_task = create_task(title="Build API")
frontend_task = create_task(title="Build UI")

# Make frontend depend on backend (backend blocks frontend)
add_dependency(frontend_task, backend_task)

# Verify relationship
from src.reader import read_ticket
frontend = read_ticket(f"tickets/tasks/{frontend_task}.md")
backend = read_ticket(f"tickets/tasks/{backend_task}.md")

print(f"Frontend up_dependencies: {frontend.up_dependencies}")    # ['bees-tk2']
print(f"Backend down_dependencies: {backend.down_dependencies}")  # ['bees-tk1']
```

#### Error Handling

```python
from src.relationship_sync import (
    add_child_to_parent,
    add_dependency,
    validate_parent_child_relationship,
    check_for_circular_dependency
)

try:
    # Attempt to add invalid parent-child relationship
    add_child_to_parent("bees-ep1", "bees-st1")
except ValueError as e:
    print(f"Validation failed: {e}")
    # "Invalid parent-child relationship: epic cannot parent subtask"

try:
    # Attempt to create circular dependency
    add_dependency("bees-ta1", "bees-ta2")
    add_dependency("bees-ta2", "bees-ta1")  # This will fail
except ValueError as e:
    print(f"Circular dependency: {e}")
    # "Circular dependency detected: bees-ta2 already depends on bees-ta1"

try:
    # Attempt to reference nonexistent ticket
    add_child_to_parent("bees-ep1", "bees-nonexistent")
except FileNotFoundError as e:
    print(f"Ticket not found: {e}")
    # "Ticket bees-nonexistent not found. Cannot modify relationships."
```

### Integration with MCP Server

The MCP server tools (create_ticket, update_ticket, delete_ticket) use the relationship sync module internally to ensure all relationship changes are bidirectional:

- **create_ticket**: Calls `add_child_to_parent()` and `add_dependency()` for specified relationships
- **update_ticket**: Compares old and new values, adds/removes relationships as needed
- **delete_ticket**: Uses `sync_relationships_batch()` to clean up all relationships efficiently

This ensures that whether you use the MCP server or call the sync functions directly, relationships are always maintained consistently across all tickets.

### File Locking for Concurrent Modifications

The relationship sync module implements file locking to prevent concurrent modification issues when multiple processes access the same ticket files simultaneously.

**How it works**:
- Uses OS-level file locking: `fcntl.flock()` on Unix/macOS, `msvcrt.locking()` on Windows
- Exclusive locks are acquired before writing ticket files
- Locks are automatically released when file operations complete

**Retry behavior**:
- If a lock cannot be acquired immediately, the system retries with exponential backoff
- Retry delays: 0.1s, 0.2s, 0.4s (3 attempts total)
- Each retry attempt is logged for debugging
- After max retries, a `RuntimeError` is raised with a clear error message

**Error handling**:
- `RuntimeError`: Raised when file lock cannot be acquired after all retries
  - Message indicates another process may be modifying the ticket
  - Recommended action: Wait briefly and retry the operation
- Lock acquisition failures are logged at WARNING level
- Successful operations are logged at DEBUG level

**Performance implications**:
- File locking adds minimal overhead for single-process operations
- In concurrent scenarios, processes may experience brief delays during lock contention
- Exponential backoff prevents resource exhaustion during high contention
- Maximum total wait time: ~0.7 seconds before failure

**Usage notes**:
- All relationship sync operations (`add_child_to_parent`, `add_dependency`, etc.) automatically use file locking
- No code changes needed to benefit from concurrent access protection
- For batch operations, locks are acquired per-ticket during the write phase
- Cross-platform compatible: works on Unix, macOS, and Windows systems

### Performance Optimizations

#### Ticket Lookup Early Return

The internal `_load_ticket_by_id()` function uses an early return optimization to minimize filesystem access when loading tickets:

**How it works**:
- Searches ticket directories in order: epic → task → subtask
- Returns immediately upon finding the ticket in any directory
- Avoids unnecessary checks of remaining directories

**Performance impact**:
- Epics: Only 1 directory check (optimal case)
- Tasks: Maximum 2 directory checks (epic fails, task succeeds)
- Subtasks: Maximum 3 directory checks (all directories searched)
- Reduces average lookup time by ~33% compared to always checking all directories

**Implementation**:
```python
# Old behavior: checked all 3 directories even after finding ticket
# New behavior: returns immediately when ticket found
for ticket_type in ["epic", "task", "subtask"]:
    try:
        path = get_ticket_path(ticket_id, ticket_type)
        ticket = read_ticket(path)
        return ticket  # Early return - no more directory checks
    except Exception:
        continue
```

This optimization is especially beneficial for operations that load many tickets, such as dependency validation and batch relationship updates.

## Query Parser

The Query Parser validates YAML query structures for the multi-stage query pipeline system.
Queries are used to filter and traverse ticket relationships with support for both search
and graph terms.

### Query Structure

A query is a list of stages evaluated sequentially as a pipeline:

```yaml
- ['type=epic', 'label~beta']     # Stage 1: Search stage
- ['children']                    # Stage 2: Graph stage
- ['label~open']                  # Stage 3: Search stage
```

**Key Concepts**:
- **Stages**: List of stages evaluated in order, results passed to next stage
- **Terms**: Each stage contains terms that are ANDed together
- **Stage Types**: Each stage is either a Search stage OR a Graph stage (never mixed)
- **Deduplication**: Results deduplicated after each stage
- **Short-circuit**: Empty result set terminates pipeline early

### Search Terms

Search terms filter tickets by attributes:

- **type=** - Filter by ticket type (epic, task, subtask)
  - Example: `type=task`
- **id=** - Filter by ticket ID
  - Example: `id=bees-250`
- **title~** - Filter by title using regex pattern
  - Example: `title~(?i)authentication`
- **label~** - Filter by labels using regex pattern
  - Example: `label~beta|alpha`

Multiple search terms in a stage are ANDed together. OR logic is expressed using
regex alternation (|). Negation uses regex negative lookahead.

### Graph Terms

Graph terms traverse ticket relationships:

- **children** - Get child tickets
- **parent** - Get parent ticket
- **up_dependencies** - Get tickets this ticket depends on (blockers)
- **down_dependencies** - Get tickets that depend on this ticket (blocked)

Graph terms have no parameters - they simply traverse the relationship graph.

### Stage Purity Rules

**Critical**: Each stage must contain ONLY search terms OR ONLY graph terms, never both.
This maintains clear semantics for pipeline execution.

**Valid stages**:
```yaml
['type=epic', 'label~beta']          # Pure search
['children']                         # Pure graph
['type=task', 'title~API', 'label~open']  # Pure search
```

**Invalid stages**:
```yaml
['type=epic', 'children']            # Mixed - INVALID
['label~open', 'parent']             # Mixed - INVALID
```

### Regex Pattern Syntax

Search terms with ~ support full Python regex syntax:

**Case-insensitive matching**:
```yaml
label~(?i)beta              # Matches: beta, Beta, BETA
```

**OR patterns (alternation)**:
```yaml
label~beta|alpha|preview    # Matches any of: beta, alpha, preview
```

**Negation (negative lookahead)**:
```yaml
label~^(?!.*closed).*       # Matches anything NOT containing "closed"
label~^(?!.*preview).*      # Matches anything NOT containing "preview"
```

**Complex patterns**:
```yaml
title~^(Task|Epic):         # Starts with "Task:" or "Epic:"
label~p[0-4]               # Matches priority labels p0-p4
```

### Example Queries

**Find open beta work items**:
```yaml
open_beta_work_items:
  - ['type=epic', 'label~(?i)(beta|preview)']  # Epics with beta/preview labels
  - ['children']                                # Get their children
  - ['label~(?i)(open|in progress)']           # Filter to open items
```

**Find non-beta items**:
```yaml
non_beta_items:
  - ['label~^(?!.*beta).*']                    # Items without "beta" label
```

**Find open non-preview tasks**:
```yaml
open_non_preview_tasks:
  - ['type=task', 'label~^(?!.*preview).*', 'label~(?i)(open|in progress)']
```

### Using QueryParser

```python
from src.query_parser import QueryParser, QueryValidationError

# Create parser instance
parser = QueryParser()

# Parse and validate query
query_yaml = """
- ['type=epic', 'label~beta']
- ['children']
- ['label~open']
"""

try:
    stages = parser.parse_and_validate(query_yaml)
    print(f"Valid query with {len(stages)} stages")
except QueryValidationError as e:
    print(f"Invalid query: {e}")
```

**Parse only** (without validation):
```python
stages = parser.parse(query_yaml)
```

**Validate parsed stages**:
```python
stages = parser.parse(query_yaml)
parser.validate(stages)
```

### Error Handling

The parser provides clear error messages for validation failures:

**Structure errors**:
- Query must be a list
- Each stage must be a list of strings
- Stages cannot be empty

**Term validation errors**:
- Invalid search term values (e.g., `type=invalid`)
- Invalid regex patterns in title~/label~
- Unknown term names

**Stage purity errors**:
- Cannot mix search and graph terms in same stage
- Error message shows which stage and what types were mixed

**Example error messages**:
```python
# Stage mixing error
QueryValidationError: Stage 0: Cannot mix search and graph terms in same stage.
Found both: search, graph

# Invalid type error
QueryValidationError: Stage 0: Invalid type 'invalid'.
Valid types: epic, task, subtask

# Invalid regex error
QueryValidationError: Stage 0: Invalid regex pattern in label~ term: ...
```

### Validation Rules

The parser enforces these validation rules:

1. **YAML Structure**: Query must be valid YAML list of lists
2. **Search Terms**:
   - type= must be one of: epic, task, subtask
   - id= must have a value
   - title~/label~ must have valid regex patterns
3. **Graph Terms**:
   - Must be one of: children, parent, up_dependencies, down_dependencies
   - No parameters allowed (term is exact match)
4. **Stage Purity**: No mixing search and graph terms
5. **Regex Compilation**: All regex patterns must compile successfully

## Search Executor

The Search Executor (`src/search_executor.py`) implements filtering of in-memory ticket
data using search terms. It supports exact match and regex-based filtering with AND logic
across all search terms in a stage.

### Supported Search Terms

The SearchExecutor supports four types of search terms:

**1. type= (Exact Match)**

Filters tickets by exact match on the `issue_type` field.

```python
from src.search_executor import SearchExecutor

executor = SearchExecutor()
tickets = {
    'bees-ep1': {'issue_type': 'epic', 'title': 'My Epic'},
    'bees-tk1': {'issue_type': 'task', 'title': 'My Task'},
}

result = executor.filter_by_type(tickets, 'epic')
# Returns: {'bees-ep1'}
```

**2. id= (Exact Match)**

Filters tickets by exact match on ticket ID.

```python
result = executor.filter_by_id(tickets, 'bees-tk1')
# Returns: {'bees-tk1'} if exists, empty set otherwise
```

**3. title~ (Regex Match)**

Filters tickets by regex pattern matching on the `title` field. Case-insensitive by default.

```python
tickets = {
    'bees-tk1': {'title': 'Build Authentication System'},
    'bees-tk2': {'title': 'Create User Profile'},
}

result = executor.filter_by_title_regex(tickets, 'Authentication')
# Returns: {'bees-tk1'}

# Using regex patterns
result = executor.filter_by_title_regex(tickets, 'Build.*System')
# Returns: {'bees-tk1'}
```

**4. label~ (Regex Match)**

Filters tickets by regex pattern matching on ANY label in the `labels` array.
Case-insensitive by default.

```python
tickets = {
    'bees-ep1': {'labels': ['backend', 'security', 'beta']},
    'bees-tk1': {'labels': ['frontend', 'ui']},
}

result = executor.filter_by_label_regex(tickets, 'beta')
# Returns: {'bees-ep1'}

# OR pattern using regex alternation
result = executor.filter_by_label_regex(tickets, 'beta|frontend')
# Returns: {'bees-ep1', 'bees-tk1'}
```

### AND Logic Semantics

The `execute()` method applies AND logic across all search terms. Tickets must match
ALL terms to be included in the result set.

```python
executor = SearchExecutor()

tickets = {
    'bees-ep1': {'issue_type': 'epic', 'title': 'Build Auth', 'labels': ['beta']},
    'bees-tk1': {'issue_type': 'task', 'title': 'Build API', 'labels': ['beta']},
    'bees-tk2': {'issue_type': 'task', 'title': 'Create UI', 'labels': ['alpha']},
}

# Type=task AND label~beta
result = executor.execute(tickets, ['type=task', 'label~beta'])
# Returns: {'bees-tk1'} (only ticket matching both conditions)
```

**Short-circuit optimization**: If any filter returns an empty set, execution stops
immediately without evaluating remaining filters.

### Regex Pattern Examples

**Case-insensitive matching** (default behavior):
```python
executor.filter_by_title_regex(tickets, 'authentication')
# Matches: "Authentication", "AUTHENTICATION", "authentication"
```

**OR patterns** (using regex alternation):
```python
executor.filter_by_label_regex(tickets, 'beta|alpha|preview')
# Matches tickets with ANY of these labels
```

**Negation** (using negative lookahead):
```python
executor.filter_by_label_regex(tickets, r'^(?!.*closed).*')
# Matches tickets that DON'T have "closed" in any label
```

**Complex patterns**:
```python
executor.filter_by_title_regex(tickets, r'^Task:.*API$')
# Matches titles starting with "Task:" and ending with "API"

executor.filter_by_label_regex(tickets, r'p[0-4]')
# Matches priority labels p0, p1, p2, p3, p4
```

### Usage Example

```python
from src.search_executor import SearchExecutor

# Create executor
executor = SearchExecutor()

# Prepare ticket data (typically loaded by PipelineEvaluator)
tickets = {
    'bees-ep1': {
        'id': 'bees-ep1',
        'issue_type': 'epic',
        'title': 'Build Authentication System',
        'labels': ['backend', 'security', 'beta'],
    },
    'bees-tk1': {
        'id': 'bees-tk1',
        'issue_type': 'task',
        'title': 'Implement OAuth Login',
        'labels': ['backend', 'api', 'beta'],
    },
}

# Execute search with multiple terms (AND logic)
search_terms = ['type=task', 'label~beta', 'title~OAuth']
result_ids = executor.execute(tickets, search_terms)
# Returns: {'bees-tk1'}

# Individual filter methods
epic_ids = executor.filter_by_type(tickets, 'epic')
beta_ids = executor.filter_by_label_regex(tickets, 'beta')
auth_ids = executor.filter_by_title_regex(tickets, 'Auth')
```

### Error Handling

The SearchExecutor raises exceptions for invalid inputs:

```python
import re
from src.search_executor import SearchExecutor

executor = SearchExecutor()

# Invalid regex pattern
try:
    executor.filter_by_title_regex(tickets, '[invalid(')
except re.error as e:
    print(f"Regex error: {e}")

# Invalid search term format
try:
    executor.execute(tickets, ['invalid_term'])
except ValueError as e:
    print(f"Invalid term: {e}")

# Unknown term name
try:
    executor.execute(tickets, ['unknown=value'])
except ValueError as e:
    print(f"Unknown term: {e}")
```

### Integration with Query Pipeline

The SearchExecutor is used by the PipelineEvaluator (when implemented) to execute
search stages in multi-stage query pipelines. The pipeline:

1. Loads all tickets into memory once
2. Identifies search stages (containing type=, id=, title~, label~ terms)
3. Routes search stages to SearchExecutor
4. Passes result set to next stage
5. Deduplicates and short-circuits on empty results

## Graph Executor

The Graph Executor (`src/graph_executor.py`) implements graph-based traversal of ticket relationships using in-memory data structures. It enables pipeline stages to navigate parent-child hierarchies and dependency graphs without disk I/O.

### Supported Relationship Types

The GraphExecutor supports four relationship traversal operations:

**1. parent** - Get parent ticket

Traverses from child to parent in the hierarchy (Task→Epic, Subtask→Task).

```python
from src.graph_executor import GraphExecutor

executor = GraphExecutor()
tickets = {
    'bees-ep1': {'parent': None, 'children': ['bees-tk1']},
    'bees-tk1': {'parent': 'bees-ep1', 'children': ['bees-st1']},
    'bees-st1': {'parent': 'bees-tk1', 'children': []},
}

result = executor.traverse(tickets, {'bees-tk1'}, 'parent')
# Returns: {'bees-ep1'}

# Multiple tickets can have same parent
result = executor.traverse(tickets, {'bees-tk1', 'bees-st1'}, 'parent')
# Returns: {'bees-ep1', 'bees-tk1'}
```

**2. children** - Get child tickets

Traverses from parent to children in the hierarchy (Epic→Tasks, Task→Subtasks).

```python
tickets = {
    'bees-ep1': {'children': ['bees-tk1', 'bees-tk2']},
    'bees-tk1': {'children': ['bees-st1', 'bees-st2']},
}

result = executor.traverse(tickets, {'bees-ep1'}, 'children')
# Returns: {'bees-tk1', 'bees-tk2'}

# Multiple input tickets aggregate their children
result = executor.traverse(tickets, {'bees-ep1', 'bees-tk1'}, 'children')
# Returns: {'bees-tk1', 'bees-tk2', 'bees-st1', 'bees-st2'}
```

**3. up_dependencies** - Get blocking tickets

Traverses to tickets that the input tickets depend on (blockers).

```python
tickets = {
    'bees-tk1': {'up_dependencies': ['bees-tk2', 'bees-tk3']},
    'bees-tk2': {'up_dependencies': []},
    'bees-tk3': {'up_dependencies': ['bees-tk4']},
}

result = executor.traverse(tickets, {'bees-tk1'}, 'up_dependencies')
# Returns: {'bees-tk2', 'bees-tk3'}

# Can traverse multiple hops
result2 = executor.traverse(tickets, result, 'up_dependencies')
# Returns: {'bees-tk4'}
```

**4. down_dependencies** - Get blocked tickets

Traverses to tickets that depend on the input tickets (what this ticket blocks).

```python
tickets = {
    'bees-tk1': {'down_dependencies': ['bees-tk2']},
    'bees-tk2': {'down_dependencies': ['bees-tk3', 'bees-tk4']},
}

result = executor.traverse(tickets, {'bees-tk1'}, 'down_dependencies')
# Returns: {'bees-tk2'}

# Can chain to find all transitively blocked tickets
result2 = executor.traverse(tickets, result, 'down_dependencies')
# Returns: {'bees-tk3', 'bees-tk4'}
```

### In-Memory Data Structure

The GraphExecutor operates on an in-memory dictionary mapping ticket IDs to ticket metadata:

```python
tickets = {
    'ticket_id': {
        'id': 'ticket_id',
        'issue_type': 'epic|task|subtask',
        'title': 'Ticket Title',
        'parent': 'parent_id' or None,
        'children': ['child_id1', 'child_id2'],
        'up_dependencies': ['blocking_id1', 'blocking_id2'],
        'down_dependencies': ['blocked_id1', 'blocked_id2'],
        # ... other fields
    }
}
```

This structure is typically populated by the PipelineEvaluator when loading tickets from disk at the start of query execution.

### Edge Cases and Error Handling

The GraphExecutor handles edge cases gracefully without crashing:

**Missing ticket IDs**:
```python
# Ticket not in data structure - logs warning and skips
result = executor.traverse(tickets, {'bees-xxx'}, 'parent')
# Returns: set() (empty)
# Logs: "Ticket bees-xxx not found in ticket data, skipping"
```

**None/empty values in input set**:
```python
# None or empty string in input - logs warning and skips
result = executor.traverse(tickets, {None, 'bees-tk1'}, 'parent')
# Returns: {'bees-ep1'} (processes valid IDs only)
# Logs: "Encountered None or empty ticket ID in input set, skipping"
```

**Missing relationship fields**:
```python
# Ticket missing 'parent' field - returns empty set
tickets = {'bees-tk1': {'id': 'bees-tk1'}}
result = executor.traverse(tickets, {'bees-tk1'}, 'parent')
# Returns: set() (no error)
```

**Empty relationship lists**:
```python
# Empty children array - returns empty set
tickets = {'bees-ep1': {'children': []}}
result = executor.traverse(tickets, {'bees-ep1'}, 'children')
# Returns: set()
```

**Invalid graph terms**:
```python
# Invalid relationship type - logs warning and returns empty set
result = executor.traverse(tickets, {'bees-tk1'}, 'invalid_term')
# Returns: set()
# Logs: "Invalid graph term 'invalid_term', returning empty set"
```

### Usage Example

```python
from src.graph_executor import GraphExecutor

# Create executor
executor = GraphExecutor()

# Prepare ticket data (typically loaded by PipelineEvaluator)
tickets = {
    'bees-ep1': {
        'id': 'bees-ep1',
        'issue_type': 'epic',
        'title': 'Build Authentication',
        'parent': None,
        'children': ['bees-tk1', 'bees-tk2'],
        'up_dependencies': [],
        'down_dependencies': ['bees-ep2'],
    },
    'bees-tk1': {
        'id': 'bees-tk1',
        'issue_type': 'task',
        'title': 'OAuth Login',
        'parent': 'bees-ep1',
        'children': ['bees-st1'],
        'up_dependencies': [],
        'down_dependencies': ['bees-tk2'],
    },
}

# Traverse relationships
parent = executor.traverse(tickets, {'bees-tk1'}, 'parent')
# Returns: {'bees-ep1'}

children = executor.traverse(tickets, {'bees-ep1'}, 'children')
# Returns: {'bees-tk1', 'bees-tk2'}

# Chain traversals for multi-hop navigation
grandchildren = executor.traverse(tickets, children, 'children')
# Returns: {'bees-st1'}
```

### Integration with Query Pipeline

The GraphExecutor is used by the PipelineEvaluator to execute graph stages in multi-stage query pipelines. The pipeline:

1. Loads all tickets into memory once
2. Identifies graph stages (containing parent, children, up_dependencies, down_dependencies terms)
3. Routes graph stages to GraphExecutor
4. Passes result set (ticket IDs) from stage to stage
5. Deduplicates ticket IDs after each stage
6. Short-circuits on empty results

**Example query using graph traversal**:
```yaml
# Find all children of beta epics that are open
- ['type=epic', 'label~beta']    # Search stage: find beta epics
- ['children']                    # Graph stage: get their children
- ['label~open']                  # Search stage: filter to open items
```

### Performance Characteristics

- **Time Complexity**: O(n) where n is the number of input ticket IDs
  - Each input ticket is looked up once in the dictionary (O(1) per lookup)
  - Relationship traversal is direct field access (O(1) per field)
- **Space Complexity**: O(m) where m is the number of related ticket IDs found
- **No Disk I/O**: All operations use in-memory data structure
- **Deduplication**: Results are stored in a set, automatically deduplicating related IDs

### Design Decisions

**Separation from SearchExecutor**: Graph and search executors are separate classes to maintain clear separation of concerns. Search operates on ticket attributes (type, title, labels), while graph operates on relationships (parent, children, dependencies).

**In-memory only**: The executor assumes all ticket data has been pre-loaded into memory by the pipeline. This eliminates disk I/O during traversal, making multi-stage queries efficient.

**Graceful degradation**: Missing relationships and invalid inputs return empty sets rather than raising exceptions. This allows pipelines to continue executing even when some tickets have incomplete data.

## Pipeline Evaluator

The Pipeline Evaluator (`src/pipeline.py`) is the main orchestrator for executing multi-stage
query pipelines. It loads all tickets into memory once from the `tickets/` directory (markdown
files with YAML frontmatter), then executes query stages sequentially against the in-memory
data structure.

### Overview

**Key Features**:
- **Single disk load**: All tickets loaded into memory once during initialization
- **Sequential stage execution**: Stages execute in order, results pass from stage to stage
- **Automatic deduplication**: Ticket IDs deduplicated after each stage
- **Short-circuit optimization**: Pipeline terminates early if any stage returns empty set
- **Stage type detection**: Automatically routes search vs graph stages to appropriate executors
- **Batch query support**: Execute multiple queries using same in-memory data

### Architecture

The PipelineEvaluator coordinates three main components:

1. **Ticket Loader**: Reads markdown files from `tickets/epics/`, `tickets/tasks/`, `tickets/subtasks/`
   subdirectories, parses YAML frontmatter, and normalizes ticket data for executors
2. **SearchExecutor**: Handles search stages (type=, id=, title~, label~)
3. **GraphExecutor**: Handles graph stages (parent, children, up_dependencies, down_dependencies)

### Loading Tickets

Tickets are loaded from markdown files with YAML frontmatter on initialization:

```python
from src.pipeline import PipelineEvaluator

# Initialize pipeline - loads all tickets into memory
pipeline = PipelineEvaluator(tickets_dir="tickets")

# Access loaded tickets
print(f"Loaded {len(pipeline.tickets)} tickets")
```

**Directory Structure**:
```
tickets/
├── epics/       # Epic tickets (user-testable features)
├── tasks/       # Task tickets (implementation work)
└── subtasks/    # Subtask tickets (atomic actions)
```

**Markdown File Format**:
Each ticket is a markdown file with YAML frontmatter:
```markdown
---
id: bees-tk1
type: task
title: Build Authentication
description: Implement OAuth login with JWT tokens
parent: bees-ep1
labels:
  - backend
  - security
up_dependencies: []
down_dependencies: []
status: open
priority: 1
---

# Build Authentication

Implementation details go here...
```

**Ticket data structure** (normalized for executors):
```python
{
    'bees-tk1': {
        'id': 'bees-tk1',
        'title': 'Build Authentication',
        'issue_type': 'task',
        'status': 'open',
        'labels': ['backend', 'security'],
        'parent': 'bees-ep1',
        'children': ['bees-st1', 'bees-st2'],
        'up_dependencies': ['bees-tk2'],  # Tickets this one depends on
        'down_dependencies': ['bees-tk3'],  # Tickets that depend on this one
    }
}
```

### Normalization and Relationship Building

The loader performs two passes over ticket data:

**Pass 1 - Normalization**: Converts YAML frontmatter to executor format
- Maps `type` field to `issue_type` for backward compatibility
- Extracts relationship fields: `parent`, `children`, `up_dependencies`, `down_dependencies`
- Extracts labels, status, and other metadata

**Pass 2 - Reverse relationships**: Builds bidirectional relationships
- If ticket A has parent B → add A to B's children list
- If ticket A has up_dependency on B → add A to B's down_dependencies list
- Ensures graph traversal works in both directions

### Executing Queries

Execute a parsed query (from QueryParser) using the pipeline:

```python
from src.query_parser import QueryParser
from src.pipeline import PipelineEvaluator

# Parse query
parser = QueryParser()
stages = parser.parse_and_validate("""
- ['type=epic', 'label~beta']
- ['children']
- ['label~open']
""")

# Execute query
pipeline = PipelineEvaluator()
result_ids = pipeline.execute_query(stages)

print(f"Found {len(result_ids)} matching tickets: {result_ids}")
```

### Stage Execution Flow

The pipeline executes stages sequentially with this logic:

1. **Start with all tickets**: First stage processes complete ticket set
2. **Determine stage type**: Inspect terms to classify as search or graph
3. **Route to executor**:
   - Search stages → SearchExecutor.execute()
   - Graph stages → GraphExecutor.traverse() for each term
4. **Pass results**: Stage N output becomes stage N+1 input
5. **Deduplicate**: Remove duplicate ticket IDs (set operations)
6. **Short-circuit**: Stop if any stage returns empty set
7. **Return final set**: Ticket IDs that passed through all stages

**Example execution trace**:
```python
stages = [
    ['type=epic', 'label~beta'],  # Search stage
    ['children'],                  # Graph stage
    ['label~open'],                # Search stage
]

# Stage 0: Search all tickets for epics with beta label
# Input: {all ticket IDs}
# Output: {'bees-ep1', 'bees-ep2'}

# Stage 1: Traverse to children of those epics
# Input: {'bees-ep1', 'bees-ep2'}
# Output: {'bees-tk1', 'bees-tk2', 'bees-tk3'}

# Stage 2: Filter children to only open items
# Input: {'bees-tk1', 'bees-tk2', 'bees-tk3'}
# Output: {'bees-tk1', 'bees-tk3'}

# Final result: {'bees-tk1', 'bees-tk3'}
```

### Stage Type Detection

The pipeline automatically detects stage type by inspecting term patterns:

```python
# Search stage detection
['type=epic']                # Has search term → search stage
['label~beta']              # Has search term → search stage
['type=task', 'title~API']  # All search terms → search stage

# Graph stage detection
['children']                # Has graph term → graph stage
['parent']                  # Has graph term → graph stage
['up_dependencies']         # Has graph term → graph stage

# Invalid - raises ValueError
['type=epic', 'children']   # Mixed search and graph → ERROR
```

**Implementation**:
```python
stage_type = pipeline.get_stage_type(stage)
# Returns: 'search' or 'graph'
# Raises: ValueError if mixed or unrecognized
```

### Deduplication

Ticket IDs are deduplicated after each stage using set operations:

```python
# Example: Multiple tasks have same parent epic
# Stage 1: Get all tasks
# Result: {'bees-tk1', 'bees-tk2'}

# Stage 2: Get parent of each task
# Raw results: ['bees-ep1', 'bees-ep1']  # Duplicates!
# Deduplicated: {'bees-ep1'}  # Set operation removes dupes
```

This prevents duplicate ticket IDs in pipeline results.

### Short-Circuit Optimization

If any stage returns an empty result set, pipeline execution stops immediately:

```python
stages = [
    ['type=epic'],       # Returns: {'bees-ep1', 'bees-ep2'}
    ['label~beta'],      # Returns: {'bees-ep1'}
    ['children'],        # Returns: {'bees-tk1'}
    ['label~closed'],    # Returns: {} (empty!)
    ['parent'],          # NOT EXECUTED - pipeline short-circuited
]

result = pipeline.execute_query(stages)
# Returns: set() (empty)
```

This optimization avoids unnecessary stage execution when results are already empty.

### Batch Query Execution

Execute multiple queries sequentially using the same cached ticket data:

```python
pipeline = PipelineEvaluator()

queries = [
    [['type=epic', 'label~beta']],           # Query 1
    [['type=task'], ['parent']],             # Query 2
    [['label~open'], ['up_dependencies']],   # Query 3
]

results = pipeline.execute_batch(queries)
# Returns: [set(), set(), set()] (one result per query)

# Tickets loaded once, reused for all 3 queries
print(f"Executed {len(queries)} queries")
```

**Use case**: Named query commands that execute multiple related queries in sequence.

### Error Handling

The pipeline provides clear error messages for common issues:

**Missing tickets directory**:
```python
pipeline = PipelineEvaluator(tickets_dir="/invalid/path")
# Raises: FileNotFoundError: Tickets directory not found: /invalid/path
```

**Invalid YAML frontmatter**:
```python
# If a markdown file has malformed YAML
# Raises: ValueError: Invalid YAML in tickets/tasks/broken.md: ...
```

**Mixed stage types**:
```python
stage = ['type=epic', 'children']  # Mixed search and graph
pipeline.get_stage_type(stage)
# Raises: ValueError: Stage has mixed search and graph terms: ...
```

**Empty stage**:
```python
pipeline.get_stage_type([])
# Raises: ValueError: Cannot determine type of empty stage
```

**Unrecognized terms**:
```python
pipeline.get_stage_type(['unknown_term'])
# Raises: ValueError: Stage has no recognized search or graph terms: ...
```

### Integration with Other Components

The Pipeline Evaluator integrates with:

**QueryParser** - Provides parsed and validated stages:
```python
parser = QueryParser()
stages = parser.parse_and_validate(query_yaml)
results = pipeline.execute_query(stages)
```

**SearchExecutor** - Executes search stages:
- Receives in-memory ticket dict and search terms
- Returns set of matching ticket IDs
- Handles type=, id=, title~, label~ filtering

**GraphExecutor** - Executes graph stages:
- Receives in-memory ticket dict and input ticket IDs
- Traverses relationships based on graph term
- Returns set of related ticket IDs

### Performance Characteristics

**Initialization**:
- Time: O(n) where n = total markdown files in tickets/ directory
- Memory: O(n) - all tickets loaded into memory
- One-time cost per pipeline instance

**Query execution**:
- Time: O(s * m) where s = number of stages, m = avg tickets per stage
- Memory: O(m) - result sets stored between stages
- No disk I/O during execution (all data in memory)

**Batch execution**:
- Time: O(q * s * m) where q = number of queries
- Memory: O(m) - tickets loaded once, reused for all queries
- Significant savings vs loading tickets per query

### Example Usage

**Single query execution**:
```python
from src.query_parser import QueryParser
from src.pipeline import PipelineEvaluator

# Parse and execute query
parser = QueryParser()
pipeline = PipelineEvaluator()

query_yaml = """
- ['type=epic', 'label~beta']
- ['children']
- ['type=task']
"""

stages = parser.parse_and_validate(query_yaml)
result_ids = pipeline.execute_query(stages)

print(f"Matching tickets: {result_ids}")
```

**Batch query execution**:
```python
# Define multiple queries
queries = {
    'open_beta_items': [
        ['type=epic', 'label~beta'],
        ['children'],
        ['label~open'],
    ],
    'non_preview_tasks': [
        ['type=task', 'label~^(?!.*preview).*'],
    ],
}

# Execute all queries
pipeline = PipelineEvaluator()
for name, stages in queries.items():
    results = pipeline.execute_query(stages)
    print(f"{name}: {len(results)} tickets")
```

**Accessing ticket data after query**:
```python
result_ids = pipeline.execute_query(stages)

# Get full ticket data for results
for ticket_id in result_ids:
    ticket = pipeline.tickets[ticket_id]
    print(f"{ticket['id']}: {ticket['title']} ({ticket['issue_type']})")
```

## Query System

The Bees query system provides a powerful multi-stage pipeline for filtering and
traversing ticket relationships. Queries combine search terms (filtering by
attributes) and graph terms (traversing relationships) in sequential stages.

### Query Structure

A query is a YAML list of stages evaluated sequentially as a pipeline:

```yaml
- ['type=epic', 'label~beta']    # Stage 1: Search stage (AND logic)
- ['children']                     # Stage 2: Graph stage (traverse relationships)
- ['label~open']                   # Stage 3: Search stage (filter results)
```

**Key Concepts**:

- **Stages**: Each stage is a list of terms evaluated together
- **Pipeline Flow**: Results from stage N become input to stage N+1
- **Deduplication**: Results are automatically deduplicated after each stage
- **Short-circuit**: Empty result set terminates pipeline early
- **Stage Purity**: Each stage must be ONLY search terms OR ONLY graph terms (never
  mixed)

### Search Terms

Search terms filter tickets by attributes using AND logic within a stage:

- **type=VALUE** - Filter by ticket type (epic, task, subtask)
  ```yaml
  ['type=task']
  ```

- **id=VALUE** - Filter by exact ticket ID
  ```yaml
  ['id=bees-250']
  ```

- **title~REGEX** - Filter by title using regex pattern (case-insensitive)
  ```yaml
  ['title~(?i)authentication']
  ```

- **label~REGEX** - Filter by labels using regex pattern (case-insensitive)
  ```yaml
  ['label~beta']
  ```

Multiple search terms in the same stage are ANDed together:
```yaml
['type=task', 'label~beta', 'title~API']  # Must match ALL three conditions
```

### Graph Terms

Graph terms traverse ticket relationships from the current result set:

- **children** - Get child tickets (Epic→Tasks, Task→Subtasks)
- **parent** - Get parent ticket (Task→Epic, Subtask→Task)
- **up_dependencies** - Get tickets that block this one (dependencies)
- **down_dependencies** - Get tickets blocked by this one (dependents)

Graph stages take the input ticket IDs and return related ticket IDs:
```yaml
['children']           # Get children of tickets from previous stage
['up_dependencies']    # Get blockers of tickets from previous stage
```

### AND/OR Semantics

**AND Logic** - Within a stage, all terms must match:
```yaml
['type=task', 'label~beta', 'label~open']  # type AND label AND label
```

**OR Logic** - Use regex alternation (|) within a term:
```yaml
['label~(beta|alpha|preview)']  # Matches ANY of these labels
['type=task', 'label~(open|in progress)']  # type=task AND (open OR in progress)
```

### Sequential Stage Evaluation

Stages execute in order, passing results between stages:

1. **Stage 1 Input**: All tickets in the system
2. **Stage 1 Output**: Filtered/traversed ticket IDs → becomes Stage 2 input
3. **Stage 2 Output**: Further filtered/traversed IDs → becomes Stage 3 input
4. And so on...

**Example execution flow**:
```yaml
# Query: Find open tasks that are children of beta epics
- ['type=epic', 'label~beta']      # Stage 1: Returns {bees-ep1, bees-ep2}
- ['children']                       # Stage 2: Returns {bees-tk1, bees-tk2, bees-tk3}
- ['type=task', 'label~open']       # Stage 3: Returns {bees-tk1, bees-tk3}
```

### Stage Separation Rules

**CRITICAL**: Search and graph terms cannot be mixed in the same stage.

**Valid stages**:
```yaml
['type=epic', 'label~beta']              # Pure search ✓
['children']                              # Pure graph ✓
['type=task', 'title~API', 'label~open'] # Pure search ✓
['parent']                                # Pure graph ✓
```

**Invalid stages**:
```yaml
['type=epic', 'children']                # Mixed search and graph ✗
['label~open', 'parent']                 # Mixed search and graph ✗
```

This separation maintains clear semantics: search stages filter tickets by
attributes, graph stages traverse relationships.

### Example Queries

These examples demonstrate common query patterns from the system requirements.

#### Example 1: Open Beta Work Items

Find all open or in-progress children of beta/preview epics:

```yaml
open_beta_work_items:
  - ['type=epic', 'label~(?i)(beta|preview)']   # Find beta/preview epics
  - ['children']                                 # Get their children (tasks)
  - ['label~(?i)(open|in progress)']            # Filter to open items
```

**How it works**:
1. Stage 1 finds epics with "beta" or "preview" labels (case-insensitive)
2. Stage 2 traverses to all child tickets of those epics
3. Stage 3 filters children to only those with "open" or "in progress" labels

**Expected results**: Task tickets that are children of beta epics and have open
status labels.

#### Example 2: Non-Beta Items

Find all tickets that don't have a "beta" label:

```yaml
non_beta_items:
  - ['label~^(?!.*beta).*']    # Negative lookahead: NOT containing "beta"
```

**How it works**:
1. Single stage uses regex negative lookahead to match tickets without "beta" in
   any label
2. The pattern `^(?!.*beta).*` means "from start, ensure 'beta' doesn't appear
   anywhere"

**Expected results**: All tickets (epics, tasks, subtasks) that don't have any
label containing "beta".

#### Example 3: Open Non-Preview Tasks

Find open tasks that don't have a "preview" label:

```yaml
open_non_preview_tasks:
  - ['type=task', 'label~^(?!.*preview).*', 'label~(?i)(open|in progress)']
```

**How it works**:
1. Single stage with three search terms (AND logic)
2. Must be type=task AND not contain "preview" AND have open/in-progress label
3. All conditions must be true for ticket to be included

**Expected results**: Task tickets with open status that aren't preview items.

### Regex Syntax for Advanced Filtering

Regex patterns in `title~` and `label~` terms support full Python regex syntax.

#### Case-Insensitive Matching

Use the `(?i)` flag for case-insensitive matching:

```yaml
['label~(?i)beta']           # Matches: beta, Beta, BETA, BeTa
['title~(?i)authentication'] # Matches any case variation
```

#### OR Patterns (Alternation)

Use the pipe operator `|` to match any of several patterns:

```yaml
['label~(beta|alpha|preview)']         # Matches ANY of these labels
['label~(open|in progress|blocked)']   # Status matching
['title~(API|REST|GraphQL)']           # Technology keywords
```

**Note**: Parentheses group the alternatives. Without them, `label~beta|alpha`
would match "beta" anywhere or "alpha" in the entire field.

#### Negation (Negative Lookahead)

Use negative lookahead `(?!...)` to exclude patterns:

```yaml
['label~^(?!.*closed).*']    # NOT containing "closed"
['label~^(?!.*preview).*']   # NOT containing "preview"
['title~^(?!.*deprecated).*'] # NOT containing "deprecated"
```

**Pattern breakdown**:
- `^` - Start of string
- `(?!.*preview)` - Negative lookahead: ensure "preview" doesn't appear anywhere
- `.*` - Match the rest of the string

#### Complex Patterns

Combine regex features for advanced filtering:

```yaml
# Starts with "Task:" or "Epic:"
['title~^(Task|Epic):']

# Priority labels p0 through p4
['label~p[0-4]']

# Matches "feature-*" or "bugfix-*" labels
['label~(feature|bugfix)-.*']

# Title contains "API" but not "deprecated"
['title~(?=.*API)(?!.*deprecated).*']
```

#### Common Pitfalls

**Forgetting case sensitivity**: Regex is case-sensitive by default. Use `(?i)`
flag for case-insensitive matching.

```yaml
['label~beta']      # Only matches lowercase "beta"
['label~(?i)beta']  # Matches any case variation ✓
```

**Incorrect negation**: Negation requires full lookahead pattern, not just `!`.

```yaml
['label~!closed']              # INVALID - ! is not regex negation ✗
['label~^(?!.*closed).*']      # CORRECT - negative lookahead ✓
```

**Alternation without grouping**: Alternation has low precedence.

```yaml
['label~beta|alpha']           # May not work as expected
['label~(beta|alpha)']         # CORRECT - explicitly grouped ✓
```

### Adding Named Queries via MCP

LLMs can programmatically add and execute named queries using MCP tools.

#### add_named_query Tool

Register a new named query that can be executed later:

**Parameters**:
- `name` (required): Query name for later execution
- `query_yaml` (required): YAML string defining the query stages
- `validate` (optional): Validate query structure (default: true)

**Example usage**:
```python
# Add a simple query
query_yaml = """
- ['type=task', 'label~beta']
- ['parent']
"""
result = add_named_query(
    name="beta_task_parents",
    query_yaml=query_yaml
)
# Returns: {"status": "success", "query_name": "beta_task_parents", ...}
```

**Parameterized queries** (with placeholders):
```python
# Use {param_name} for dynamic values
query_yaml = """
- ['type={ticket_type}', 'label~{label}']
"""
# Set validate=False for parameterized queries
result = add_named_query(
    name="typed_label_filter",
    query_yaml=query_yaml,
    validate=False  # Skip validation for placeholders
)
```

**Query storage**: Named queries are persisted to `.bees/queries.yaml` and
survive server restarts.

#### execute_query Tool

Execute a previously registered named query:

**Parameters**:
- `query_name` (required): Name of registered query
- `params` (optional): JSON string of parameter values

**Example usage**:
```python
# Execute simple query
result = execute_query("beta_task_parents")
# Returns: {"status": "success", "result_count": 5, "ticket_ids": [...]}

# Execute parameterized query with parameters
params = '{"ticket_type": "task", "label": "open"}'
result = execute_query("typed_label_filter", params=params)
# Returns: {"status": "success", "result_count": 3, "ticket_ids": [...]}
```

**Example conversation flow**:

```
LLM: I'll create a query to find all blocked tasks.

[Calls add_named_query with name="blocked_tasks" and query_yaml=...]

LLM: Query registered. Now executing it...

[Calls execute_query with query_name="blocked_tasks"]

LLM: Found 3 blocked tasks: bees-tk1, bees-tk2, bees-tk5
```

### Adding Named Queries Manually

Humans can manually edit `.bees/queries.yaml` to add custom queries.

#### File Location

The queries file is located at:
```
.bees/queries.yaml
```

Create this file if it doesn't exist. The MCP server will load queries from this
file on startup.

#### YAML Structure

Each named query is a key-value pair:
- **Key**: Query name (used with execute_query)
- **Value**: List of stages (same format as above examples)

**Example queries.yaml file**:
```yaml
# Named Queries for Bees Query System
---
open_beta_items:
  - ['type=epic', 'label~(?i)(beta|preview)']
  - ['children']
  - ['label~(?i)(open|in progress)']

high_priority_tasks:
  - ['type=task', 'label~p0|p1']

blocked_work:
  - ['up_dependencies']
  - ['label~(?i)open']
```

#### Adding a Custom Query

1. **Open the file**: Edit `.bees/queries.yaml` in your text editor
2. **Add your query**: Use YAML list syntax for stages
3. **Save the file**: Changes take effect on next MCP server restart
4. **Execute it**: Use execute_query MCP tool with your query name

**Example - Adding a new query**:
```yaml
# Add this to .bees/queries.yaml
my_custom_query:
  - ['type=task', 'label~backend']
  - ['up_dependencies']
```

Then execute it:
```python
result = execute_query("my_custom_query")
```

#### Validation Requirements

When manually editing, ensure:
- Valid YAML syntax (use a YAML linter)
- Each stage is a list of strings
- Search terms use correct format: `type=`, `id=`, `title~`, `label~`
- Graph terms are exact: `parent`, `children`, `up_dependencies`,
  `down_dependencies`
- No mixing of search and graph terms in same stage
- Regex patterns in `~` terms are valid Python regex

**Tip**: Test your query using execute_query after adding it. Validation errors
will show which stage and term are problematic.

### Troubleshooting Queries

Common issues and solutions when working with queries.

#### Query Validation Errors

**Error**: "Stage has mixed search and graph terms"

**Cause**: You mixed search (type=, label~) and graph (children, parent) terms in
the same stage.

**Solution**: Split into separate stages:
```yaml
# WRONG
- ['type=epic', 'children']

# CORRECT
- ['type=epic']
- ['children']
```

#### Regex Syntax Errors

**Error**: "Invalid regex pattern in label~ term"

**Cause**: Regex pattern has syntax error (unclosed bracket, invalid escape, etc.)

**Solution**: Test regex pattern separately, fix syntax:
```yaml
# WRONG
- ['label~[invalid(']

# CORRECT
- ['label~(beta|alpha)']
```

**Debugging tip**: Use a regex tester (like regex101.com) to validate patterns
before adding to queries.

#### Empty Results

**Issue**: Query returns empty result set when you expect matches.

**Possible causes and solutions**:

1. **Too restrictive filters**: Check if AND logic is too narrow
   ```yaml
   # This might be too restrictive
   - ['type=task', 'label~beta', 'label~alpha', 'label~preview']

   # Try OR logic instead
   - ['type=task', 'label~(beta|alpha|preview)']
   ```

2. **Case sensitivity**: Add `(?i)` flag for case-insensitive matching
   ```yaml
   # Might miss "Beta" or "BETA"
   - ['label~beta']

   # Matches any case
   - ['label~(?i)beta']
   ```

3. **No tickets match criteria**: Use simpler queries to verify tickets exist
   ```yaml
   # Start simple
   - ['type=task']

   # Add filters incrementally
   - ['type=task', 'label~beta']
   ```

4. **Earlier stage returned empty**: Pipeline short-circuits on empty results
   - Add logging/debugging to see which stage returns empty
   - Check each stage independently

#### Stage Type Validation Errors

**Error**: "Cannot determine type of empty stage"

**Cause**: Stage has no terms (empty list `[]`)

**Solution**: Remove empty stages or add terms:
```yaml
# WRONG
- ['type=epic']
- []
- ['children']

# CORRECT
- ['type=epic']
- ['children']
```

**Error**: "Stage has no recognized search or graph terms"

**Cause**: Stage contains unrecognized term names

**Solution**: Check term names against valid list:
- Search: `type=`, `id=`, `title~`, `label~`
- Graph: `parent`, `children`, `up_dependencies`, `down_dependencies`

```yaml
# WRONG
- ['status=open']  # 'status=' is not a valid term

# CORRECT
- ['label~open']   # Use label~ with regex
```

#### Invalid Relationship Traversals

**Issue**: Graph term returns no results when relationships should exist.

**Possible causes**:

1. **Tickets have no relationships**: Check ticket data for parent/children/
   dependencies fields
2. **Wrong graph term**: Verify you're using correct relationship direction
   - `parent` goes UP the hierarchy (Task→Epic)
   - `children` goes DOWN (Epic→Tasks)
   - `up_dependencies` finds blockers (what blocks me)
   - `down_dependencies` finds blocked (what I block)

#### Debugging Tips

1. **Test stages incrementally**: Execute each stage independently to isolate
   issues
2. **Check ticket data**: Verify tickets have expected labels, types, and
   relationships
3. **Simplify query**: Start with simple query and add complexity gradually
4. **Use execute_query response**: Check `result_count` to see how many tickets
   matched
5. **Validate YAML syntax**: Use YAML linter to catch structural issues

**Example debugging workflow**:
```python
# Step 1: Verify tickets exist
result = execute_query("all_tasks")  # Simple: [['type=task']]
print(f"Total tasks: {result['result_count']}")

# Step 2: Test filter
result = execute_query("beta_tasks")  # [['type=task', 'label~beta']]
print(f"Beta tasks: {result['result_count']}")

# Step 3: Test full query
result = execute_query("complex_query")  # Multi-stage query
print(f"Final results: {result['result_count']}")
```

## Testing

### Running Tests

Run the full test suite with pytest:

```bash
poetry run pytest
```

Run specific test files:

```bash
poetry run pytest tests/test_pipeline.py
poetry run pytest tests/test_search_executor.py
```

### Test Fixtures

The test suite uses dynamically generated markdown fixtures with YAML frontmatter that match
the production Bees ticket format. Test fixtures are created in temporary directories using
pytest's `tmp_path` fixture.

**Test Fixture Structure**:

```
temp_tickets_dir/
├── epics/
│   ├── bees-ep1.md
│   └── bees-ep2.md
├── tasks/
│   ├── bees-tk1.md
│   └── bees-tk2.md
└── subtasks/
    └── bees-st1.md
```

**Example Test Fixture Format**:

```markdown
---
id: bees-tk1
title: Implement OAuth Login
type: task
status: open
labels:
  - backend
  - api
parent: bees-ep1
children: []
up_dependencies: []
down_dependencies: []
---

# Implement OAuth Login

Test ticket content.
```

The `temp_tickets_dir` pytest fixture (in `tests/test_pipeline.py`) creates this structure
automatically for each test, ensuring isolation and repeatability.

### Path Structure Validation

Test assertions validate the hierarchical ticket path structure used by Bees:

- **Epics**: `tickets/epics/bees-XXX.md`
- **Tasks**: `tickets/tasks/bees-XXX.md`
- **Subtasks**: `tickets/subtasks/bees-XXX.md`

This hierarchical organization (instead of flat `tickets/bees-XXX.md` paths) provides
better organization and scalability as the ticket system grows. Tests in
`tests/test_index_generator.py` verify that generated index links use these correct
paths for all ticket types, ensuring consistency between the file system structure
and the navigation interface.

## Documentation

- [Schema Definition](docs/schema.md) - Complete ticket schema documentation
- [Product Requirements](docs/plans/PRD.md) - Project requirements and design
- [Query System Guide](docs/queries.md) - Comprehensive query syntax reference

## Development Status

This project is in active development. Current focus: Core schema and file
storage implementation.
