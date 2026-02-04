"""
Help documentation and MCP tool reference for Bees ticket management system.

This module contains the help function that provides comprehensive documentation
for all available MCP tools, their parameters, and core system concepts.
"""

from typing import Dict, Any


def _help() -> Dict[str, Any]:
    """
    Display available MCP tools and their parameters.

    Returns comprehensive list of all available Bees MCP commands with their
    parameters, types, and brief descriptions—similar to --help output.

    CRITICAL: NEVER modify tickets or directory structure directly via file operations.
    ALWAYS use the MCP server tools (create_ticket, update_ticket, delete_ticket, etc.).
    Direct file modifications bypass validation, relationship sync, and can corrupt the ticket database.

    HIVES
    - Isolated ticket directories within repo, tracked in .bees/config.json
    - Identity marker: .hive/identity.json contains normalized_name, display_name, created_at
    - Tickets stored flat at hive root
    - Naming: Display name normalized (lowercase, spaces→underscores, special chars removed)
    - Config keys and ticket ID prefixes use normalized names
    - Discovery: Primary lookup in config.json, fallback scan_for_hive() for .hive markers

    TICKET TYPES
    - Epic: Top-level, optional children array, no parent field allowed
    - Task: Mid-level, required parent (Epic), optional children (Subtasks)
    - Subtask: Leaf-level, required parent (Task), children always empty
    - ID format: {hive_normalized}.bees-{3char} (e.g., backend.bees-abc)
    - Schema: Markdown with YAML frontmatter, bees_version field marks valid tickets

    PARENT/CHILD RELATIONSHIPS
    - Valid pairs: Epic↔Task, Task↔Subtask
    - Bidirectional sync: Setting A.parent=B auto-updates B.children to include A
    - Bidirectional sync: Setting A.children=[C] auto-updates C.parent=A
    - Update behavior: Removing A from B.children nullifies A.parent (except subtasks)
    - Delete cascade: Deleting parent recursively deletes entire child subtree
    - Delete cleanup: Removes deleted ticket from parent's children array
    - Subtask constraint: parent field cannot be nullified (required)

    DEPENDENCIES
    - up_dependencies: Tickets this one depends on (blockers)
    - down_dependencies: Tickets depending on this one (blocked items)
    - Bidirectional sync: Setting A.up_dependencies=[B] auto-updates B.down_dependencies=[A]
    - Same-type restriction: Epics→Epics, Tasks→Tasks, Subtasks→Subtasks only
    - Circular detection: Validates no direct or transitive cycles
    - Delete cleanup: Removes deleted ticket from all related dependency arrays

    QUERIES
    - Multi-stage pipeline: Each stage filters or traverses previous result set
    - Search terms (AND logic): type=, id=, title~regex, label~regex
    - Graph terms (traversal): parent, children, up_dependencies, down_dependencies
    - Stage purity: Each stage is ONLY search OR ONLY graph, never mixed
    - Named queries: Stored as YAML in .bees/queries/, validated on save

    Returns:
        dict: Contains 'commands' list with command details and 'concepts' with technical reference
    """
    commands = [
        {
            "name": "health_check",
            "description": "Check MCP server health status",
            "parameters": []
        },
        {
            "name": "create_ticket",
            "description": "Create a new ticket (epic, task, or subtask)",
            "parameters": [
                {"name": "ticket_type", "type": "str", "required": True, "description": "Type: epic, task, or subtask"},
                {"name": "title", "type": "str", "required": True, "description": "Ticket title"},
                {"name": "hive_name", "type": "str", "required": True, "description": "Hive name for ticket"},
                {"name": "description", "type": "str", "required": False, "description": "Detailed description"},
                {"name": "parent", "type": "str", "required": False, "description": "Parent ticket ID"},
                {"name": "children", "type": "list[str]", "required": False, "description": "Child ticket IDs"},
                {"name": "up_dependencies", "type": "list[str]", "required": False, "description": "Blocking ticket IDs"},
                {"name": "down_dependencies", "type": "list[str]", "required": False, "description": "Blocked ticket IDs"},
                {"name": "labels", "type": "list[str]", "required": False, "description": "Label strings"},
                {"name": "owner", "type": "str", "required": False, "description": "Owner/assignee"},
                {"name": "priority", "type": "int", "required": False, "description": "Priority level"},
                {"name": "status", "type": "str", "required": False, "description": "Status"}
            ]
        },
        {
            "name": "update_ticket",
            "description": "Update an existing ticket",
            "parameters": [
                {"name": "ticket_id", "type": "str", "required": True, "description": "Ticket ID to update"},
                {"name": "title", "type": "str", "required": False, "description": "New title"},
                {"name": "description", "type": "str", "required": False, "description": "New description"},
                {"name": "parent", "type": "str", "required": False, "description": "New parent ID"},
                {"name": "children", "type": "list[str]", "required": False, "description": "New children IDs"},
                {"name": "up_dependencies", "type": "list[str]", "required": False, "description": "New blocking IDs"},
                {"name": "down_dependencies", "type": "list[str]", "required": False, "description": "New blocked IDs"},
                {"name": "labels", "type": "list[str]", "required": False, "description": "New labels"},
                {"name": "owner", "type": "str", "required": False, "description": "New owner"},
                {"name": "priority", "type": "int", "required": False, "description": "New priority"},
                {"name": "status", "type": "str", "required": False, "description": "New status"}
            ]
        },
        {
            "name": "delete_ticket",
            "description": "Delete a ticket and cascade to children",
            "parameters": [
                {"name": "ticket_id", "type": "str", "required": True, "description": "Ticket ID to delete"}
            ]
        },
        {
            "name": "show_ticket",
            "description": "Retrieve and return ticket data by ticket ID",
            "parameters": [
                {"name": "ticket_id", "type": "str", "required": True, "description": "Ticket ID to retrieve"}
            ]
        },
        {
            "name": "add_named_query",
            "description": "Register a named query for reuse",
            "parameters": [
                {"name": "name", "type": "str", "required": True, "description": "Query name"},
                {"name": "query_yaml", "type": "str", "required": True, "description": "YAML query structure"}
            ]
        },
        {
            "name": "execute_query",
            "description": "Execute a named query",
            "parameters": [
                {"name": "query_name", "type": "str", "required": True, "description": "Name of saved query"},
                {"name": "hive_names", "type": "list[str]", "required": False, "description": "Hives to search"}
            ]
        },
        {
            "name": "execute_freeform_query",
            "description": "Execute a query from YAML string",
            "parameters": [
                {"name": "query_yaml", "type": "str", "required": True, "description": "YAML query pipeline"},
                {"name": "hive_names", "type": "list[str]", "required": False, "description": "Hives to search"}
            ]
        },
        {
            "name": "generate_index",
            "description": "Generate markdown index of tickets",
            "parameters": [
                {"name": "status", "type": "str", "required": False, "description": "Status filter"},
                {"name": "type", "type": "str", "required": False, "description": "Type filter"},
                {"name": "hive_name", "type": "str", "required": False, "description": "Hive to index"}
            ]
        },
        {
            "name": "colonize_hive",
            "description": "Create and register a new hive",
            "parameters": [
                {"name": "name", "type": "str", "required": True, "description": "Display name for hive"},
                {"name": "path", "type": "str", "required": True, "description": "Absolute path to hive directory"}
            ]
        },
        {
            "name": "list_hives",
            "description": "List all registered hives with ticket counts",
            "parameters": []
        },
        {
            "name": "abandon_hive",
            "description": "Unregister a hive (files unchanged)",
            "parameters": [
                {"name": "hive_name", "type": "str", "required": True, "description": "Hive to abandon"}
            ]
        },
        {
            "name": "rename_hive",
            "description": "Rename hive and update all ticket IDs",
            "parameters": [
                {"name": "old_name", "type": "str", "required": True, "description": "Current hive name"},
                {"name": "new_name", "type": "str", "required": True, "description": "New hive name"}
            ]
        },
        {
            "name": "sanitize_hive",
            "description": "Validate and auto-fix malformed tickets in hive",
            "parameters": [
                {"name": "hive_name", "type": "str", "required": True, "description": "Hive to sanitize"}
            ]
        }
    ]

    concepts = """
CRITICAL: NEVER modify tickets or directory structure directly via file operations.
ALWAYS use the MCP server tools (create_ticket, update_ticket, delete_ticket, etc.).
Direct file modifications bypass validation, relationship sync, and can corrupt the ticket database.

HIVES
- Isolated ticket directories within repo, tracked in .bees/config.json
- Identity marker: .hive/identity.json contains normalized_name, display_name, created_at
- Tickets stored flat at hive root
- Naming: Display name normalized (lowercase, spaces→underscores, special chars removed)
- Config keys and ticket ID prefixes use normalized names
- Discovery: Primary lookup in config.json, fallback scan_for_hive() for .hive markers

TICKET TYPES
- Epic: Top-level, optional children array, no parent field allowed
- Task: Mid-level, required parent (Epic), optional children (Subtasks)
- Subtask: Leaf-level, required parent (Task), children always empty
- ID format: {hive_normalized}.bees-{3char} (e.g., backend.bees-abc)
- Schema: Markdown with YAML frontmatter, bees_version field marks valid tickets

PARENT/CHILD RELATIONSHIPS
- Valid pairs: Epic↔Task, Task↔Subtask
- Bidirectional sync: Setting A.parent=B auto-updates B.children to include A
- Bidirectional sync: Setting A.children=[C] auto-updates C.parent=A
- Update behavior: Removing A from B.children nullifies A.parent (except subtasks)
- Delete cascade: Deleting parent recursively deletes entire child subtree
- Delete cleanup: Removes deleted ticket from parent's children array
- Subtask constraint: parent field cannot be nullified (required)

DEPENDENCIES
- up_dependencies: Tickets this one depends on (blockers)
- down_dependencies: Tickets depending on this one (blocked items)
- Bidirectional sync: Setting A.up_dependencies=[B] auto-updates B.down_dependencies=[A]
- Same-type restriction: Epics→Epics, Tasks→Tasks, Subtasks→Subtasks only
- Circular detection: Validates no direct or transitive cycles
- Delete cleanup: Removes deleted ticket from all related dependency arrays

QUERIES
- Multi-stage pipeline: Each stage filters or traverses previous result set
- Search terms (AND logic): type=, id=, title~regex, label~regex
- Graph terms (traversal): parent, children, up_dependencies, down_dependencies
- Stage purity: Each stage is ONLY search OR ONLY graph, never mixed
- Named queries: Stored as YAML in .bees/queries/, validated on save
"""

    return {
        "status": "success",
        "commands": commands,
        "concepts": concepts
    }
