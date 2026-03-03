"""
Help documentation and MCP tool reference for Bees ticket management system.

This module contains the help function that provides comprehensive documentation
for all available MCP tools, their parameters, and core system concepts.
"""

from typing import Any


def _help() -> dict[str, Any]:
    """
    Display available MCP tools and their parameters.

    Returns comprehensive list of all available Bees MCP commands with their
    parameters, types, and brief descriptions—similar to --help output.

    CRITICAL: NEVER modify tickets or directory structure directly via file operations.
    ALWAYS use the MCP server tools (create_ticket, update_ticket, delete_ticket, etc.).
    Direct file modifications bypass validation, relationship sync, and can corrupt the ticket database.

    HIVES
    - Isolated ticket directories within repo, tracked in ~/.bees/config.json
    - Identity marker: .hive/identity.json contains normalized_name, display_name, created_at
    - Tickets stored flat at hive root
    - Naming: Display name normalized (lowercase, spaces→underscores, special chars removed)
    - Config keys and ticket ID prefixes use normalized names
    - Discovery: Primary lookup in config.json, fallback scan_for_hive() for .hive markers

    TICKET TYPES
    - Dynamic tier system: Ticket types are configured in ~/.bees/config.json under child_tiers
    - t0 (Bee): Top-level tier, always present, optional children array, no parent field allowed
    - Child tiers (t1, t2, t3...): Configured dynamically via child_tiers config
    - Each child tier requires a parent from the tier above (t1 parent is t0, t2 parent is t1, etc.)
    - Tier names are configurable with optional singular/plural friendly names
    - ID format: <type>.<id> where type=b (bee), t1, t2, etc. (e.g., b.Amx, t1.X4F2, t2.nQ3xA)
    - Schema: Markdown with YAML frontmatter, schema_version field marks valid tickets

    CHILD_TIERS CONFIGURATION
    - Three-level resolution: hive-level → scope-level → global-level → bees-only default
    - Resolution: For a given hive, check hive child_tiers first, then scope, then global. First defined level wins.
    - Absent semantics: None or missing child_tiers at a level = fall through to next level
    - Present semantics: child_tiers present at a level (even empty {}) = stops the chain
    - Empty {} stops the chain and means bees-only for that hive (no child tiers)
    - Structure: {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}
    - Tier keys must follow pattern t[0-9]+ (t1, t2, t3, etc.), sequential starting at t1
    - Friendly names [singular, plural] are optional (use [] for unnamed tiers)
    - Hive-level override example: A hive with child_tiers: {"t1": ["Epic", "Epics"]} uses Epics
      even if scope defines Tasks/Subtasks. Another hive with child_tiers: {} is bees-only.
      A hive with no child_tiers key inherits from scope or global.
    - Use get_types with optional hive_name parameter to see resolved tiers for a specific hive
    - Use set_types to set or unset child_tiers at any scope (global, repo_scope, or hive)
    - Controls which ticket types are valid when creating tickets
    - Determines tier hierarchy for parent-child relationships

    STATUS_VALUES
    - Three-level resolution: hive-level → scope-level → global-level → freeform default
    - Resolution: For a given hive, check hive status_values first, then scope, then global. First defined level wins.
    - Absent semantics: None or missing status_values at a level = fall through to next level
    - Present semantics: Non-empty status_values list at a level = stops the chain
    - Empty list [] treated as absent (falls through to next level)
    - Each level completely overrides lower levels (no merging between levels)
    - When no level defines status_values: freeform mode (any string value accepted)
    - Structure: status_values: ["open", "in_progress", "completed"]

    PARENT/CHILD RELATIONSHIPS
    - Valid pairs: Follow tier hierarchy (t0→t1, t1→t2, t2→t3, etc.)
    - Hierarchy determined by child_tiers configuration in ~/.bees/config.json
    - Bidirectional sync: Setting A.parent=B auto-updates B.children to include A
    - Bidirectional sync: Setting A.children=[C] auto-updates C.parent=A
    - Update behavior: Removing A from B.children nullifies A.parent (except child tiers)
    - Delete cascade: Two-phase bottom-up algorithm deletes entire child subtree (fail-fast on read errors)
    - Delete behavior: Parent's children array is updated to remove the deleted ticket;
      other relationship fields in surviving tickets are not modified; dangling refs detected by linter
    - Child tier constraint: All child tiers (t1, t2, t3...) require parent field

    DEPENDENCIES
    - up_dependencies: Tickets this one depends on (blockers)
    - down_dependencies: Tickets depending on this one (blocked items)
    - Bidirectional sync: Setting A.up_dependencies=[B] auto-updates B.down_dependencies=[A]
    - Same-type restriction: Bees→Bees, Tasks→Tasks, Subtasks→Subtasks only
    - Circular detection: Validates no direct or transitive cycles
    - Delete behavior: By default, surviving tickets are not modified (dependency arrays may contain stale
      refs). Set delete_with_dependencies: true in global config to remove the deleted subtree from
      external tickets' dependency arrays before deletion.

    QUERIES
    - Multi-stage pipeline: Each stage filters or traverses previous result set
    - Search terms (AND logic): type=, id=, status=, title~regex, tag~regex, hive=, hive~regex
    - Graph terms (traversal): parent, children, up_dependencies, down_dependencies
    - Stage purity: Each stage is ONLY search OR ONLY graph, never mixed
    - Named queries: Stored in ~/.bees/config.json under named_queries, validated on save

    Returns:
        dict: Contains 'commands' list with command details and 'concepts' with technical reference
    """
    commands = [
        {"name": "health_check", "description": "Check MCP server health status", "parameters": []},
        {
            "name": "create_ticket",
            "description": "Create a new ticket (bee, task, or subtask)",
            "parameters": [
                {
                    "name": "ticket_type",
                    "type": "str",
                    "required": True,
                    "description": (
                        "Type: bee (t0) or child tier (t1, t2, t3...). Valid types depend on "
                        "child_tiers configuration in ~/.bees/config.json. Bee (t0) is always valid."
                    ),
                },
                {"name": "title", "type": "str", "required": True, "description": "Ticket title"},
                {"name": "hive_name", "type": "str", "required": True, "description": "Hive name for ticket"},
                {"name": "description", "type": "str", "required": False, "description": "Detailed description"},
                {"name": "parent", "type": "str", "required": False, "description": "Parent ticket ID"},
                {"name": "children", "type": "list[str]", "required": False, "description": "Child ticket IDs"},
                {
                    "name": "up_dependencies",
                    "type": "list[str]",
                    "required": False,
                    "description": "Blocking ticket IDs",
                },
                {
                    "name": "down_dependencies",
                    "type": "list[str]",
                    "required": False,
                    "description": "Blocked ticket IDs",
                },
                {"name": "tags", "type": "list[str]", "required": False, "description": "Tag strings"},
                {"name": "status", "type": "str", "required": False, "description": "Status"},
                {
                    "name": "egg",
                    "type": "any (JSON-serializable)",
                    "required": False,
                    "description": "Egg field for resource association",
                },
            ],
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
                {"name": "tags", "type": "list[str]", "required": False, "description": "New tags"},
                {"name": "status", "type": "str", "required": False, "description": "New status"},
            ],
        },
        {
            "name": "delete_ticket",
            "description": "Delete a ticket and cascade to children",
            "parameters": [
                {"name": "ticket_id", "type": "str", "required": True, "description": "Ticket ID to delete"},
            ],
        },
        {
            "name": "show_ticket",
            "description": "Retrieve and return ticket data by ticket ID",
            "parameters": [
                {"name": "ticket_id", "type": "str", "required": True, "description": "Ticket ID to retrieve"}
            ],
        },
        {
            "name": "get_types",
            "description": "Get valid ticket types, resolved for a specific hive or scope default",
            "parameters": [
                {
                    "name": "hive_name", "type": "str", "required": False,
                    "description": "Hive name to resolve tiers for (uses scope default if omitted)",
                },
            ],
        },
        {
            "name": "set_types",
            "description": "Set or unset child_tiers configuration at the global, repo_scope, or hive level",
            "parameters": [
                {
                    "name": "scope", "type": "str", "required": True,
                    "description": "Target scope: 'global', 'repo_scope', or 'hive'",
                },
                {
                    "name": "hive_name", "type": "str", "required": False,
                    "description": "Hive name (required when scope='hive')",
                },
                {
                    "name": "child_tiers", "type": "dict", "required": False,
                    "description": (
                        "Dict mapping tier keys to [singular, plural] arrays."
                        " {} for bees-only. Required unless unset=True."
                    ),
                },
                {
                    "name": "unset", "type": "bool", "required": False,
                    "description": "If True, remove child_tiers from the target level (idempotent)",
                },
                {
                    "name": "repo_root", "type": "str", "required": False,
                    "description": "Optional explicit repo root path (fallback for non-Roots clients)",
                },
            ],
        },
        {
            "name": "add_named_query",
            "description": "Register a named query for reuse",
            "parameters": [
                {"name": "name", "type": "str", "required": True, "description": "Query name"},
                {"name": "query_yaml", "type": "str", "required": True, "description": "YAML query structure"},
            ],
        },
        {
            "name": "execute_named_query",
            "description": "Execute a named query",
            "parameters": [
                {"name": "query_name", "type": "str", "required": True, "description": "Name of saved query"},
            ],
        },
        {
            "name": "execute_freeform_query",
            "description": "Execute a query from YAML string",
            "parameters": [
                {"name": "query_yaml", "type": "str", "required": True, "description": "YAML query pipeline"},
            ],
        },
        {
            "name": "generate_index",
            "description": "Generate markdown index of tickets",
            "parameters": [
                {"name": "hive_name", "type": "str", "required": False, "description": "Hive to index"},
            ],
        },
        {
            "name": "colonize_hive",
            "description": "Create and register a new hive",
            "parameters": [
                {"name": "name", "type": "str", "required": True, "description": "Display name for hive"},
                {"name": "path", "type": "str", "required": True, "description": "Absolute path to hive directory"},
            ],
        },
        {"name": "list_hives", "description": "List all registered hives with ticket counts", "parameters": []},
        {
            "name": "abandon_hive",
            "description": "Unregister a hive (files unchanged)",
            "parameters": [{"name": "hive_name", "type": "str", "required": True, "description": "Hive to abandon"}],
        },
        {
            "name": "rename_hive",
            "description": "Rename hive and update all ticket IDs",
            "parameters": [
                {"name": "old_name", "type": "str", "required": True, "description": "Current hive name"},
                {"name": "new_name", "type": "str", "required": True, "description": "New hive name"},
            ],
        },
        {
            "name": "sanitize_hive",
            "description": "Validate and auto-fix malformed tickets in hive",
            "parameters": [{"name": "hive_name", "type": "str", "required": True, "description": "Hive to sanitize"}],
        },
        {
            "name": "move_bee",
            "description": "Move bee tickets to a different hive within the same scope",
            "parameters": [
                {
                    "name": "bee_ids",
                    "type": "list[str]",
                    "required": True,
                    "description": "Bee ticket IDs to move (e.g., ['b.Amx', 'b.X4F'])",
                },
                {
                    "name": "destination_hive",
                    "type": "str",
                    "required": True,
                    "description": "Normalized name of the destination hive",
                },
                {
                    "name": "repo_root",
                    "type": "str",
                    "required": False,
                    "description": "Optional explicit repo root path",
                },
            ],
            "returns": (
                "On success: {status, moved: list, skipped: list, not_found: list, failed: list[{id, reason}]}. "
                "On error: {status: 'error', message, error_type}."
            ),
        },
    ]

    concepts = """
CRITICAL: NEVER modify tickets or directory structure directly via file operations.
ALWAYS use the MCP server tools (create_ticket, update_ticket, delete_ticket, etc.).
Direct file modifications bypass validation, relationship sync, and can corrupt the ticket database.

HIVES
- Isolated ticket directories within repo, tracked in ~/.bees/config.json
- Identity marker: .hive/identity.json contains normalized_name, display_name, created_at
- Tickets stored flat at hive root
- Naming: Display name normalized (lowercase, spaces→underscores, special chars removed)
- Config keys and ticket ID prefixes use normalized names
- Discovery: Primary lookup in config.json, fallback scan_for_hive() for .hive markers

TICKET TYPES
- Dynamic tier system: Ticket types are configured in ~/.bees/config.json under child_tiers
- t0 (Bee): Top-level tier, always present, optional children array, no parent field allowed
- Child tiers (t1, t2, t3...): Configured dynamically via child_tiers config
- Each child tier requires a parent from the tier above (t1 parent is t0, t2 parent is t1, etc.)
- Tier names are configurable with optional singular/plural friendly names
- ID format: <type>.<id> where type=b (bee), t1, t2, etc. (e.g., b.Amx, t1.X4F2, t2.nQ3xA)
- Schema: Markdown with YAML frontmatter, schema_version field marks valid tickets

CHILD_TIERS CONFIGURATION
- Three-level resolution: hive-level → scope-level → global-level → bees-only default
- Resolution: For a given hive, check hive child_tiers first, then scope, then global. First defined level wins.
- Absent semantics: None or missing child_tiers at a level = fall through to next level
- Present semantics: child_tiers present at a level (even empty {}) = stops the chain
- Empty {} stops the chain and means bees-only for that hive (no child tiers)
- Structure: {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}
- Tier keys must follow pattern t[0-9]+ (t1, t2, t3, etc.), sequential starting at t1
- Friendly names [singular, plural] are optional (use [] for unnamed tiers)
- Hive-level override example: A hive with child_tiers: {"t1": ["Epic", "Epics"]} uses Epics
  even if scope defines Tasks/Subtasks. Another hive with child_tiers: {} is bees-only.
  A hive with no child_tiers key inherits from scope or global.
- Use get_types with optional hive_name parameter to see resolved tiers for a specific hive
- Use set_types to set or unset child_tiers at any scope (global, repo_scope, or hive)
- Controls which ticket types are valid when creating tickets
- Determines tier hierarchy for parent-child relationships

STATUS_VALUES
- Three-level resolution: hive-level → scope-level → global-level → freeform default
- Resolution: For a given hive, check hive status_values first, then scope, then global. First defined level wins.
- Absent semantics: None or missing status_values at a level = fall through to next level
- Present semantics: Non-empty status_values list at a level = stops the chain
- Empty list [] treated as absent (falls through to next level)
- Each level completely overrides lower levels (no merging between levels)
- When no level defines status_values: freeform mode (any string value accepted)
- Structure: status_values: ["open", "in_progress", "completed"]

PARENT/CHILD RELATIONSHIPS
- Valid pairs: Follow tier hierarchy (t0→t1, t1→t2, t2→t3, etc.)
- Hierarchy determined by child_tiers configuration in ~/.bees/config.json
- Bidirectional sync: Setting A.parent=B auto-updates B.children to include A
- Bidirectional sync: Setting A.children=[C] auto-updates C.parent=A
- Update behavior: Removing A from B.children nullifies A.parent (except child tiers)
- Delete cascade: Two-phase bottom-up algorithm deletes entire child subtree (fail-fast on read errors)
- Delete behavior: Parent's children array is updated to remove the deleted ticket;
  other relationship fields in surviving tickets are not modified; dangling refs detected by linter
- Child tier constraint: All child tiers (t1, t2, t3...) require parent field

DEPENDENCIES
- up_dependencies: Tickets this one depends on (blockers)
- down_dependencies: Tickets depending on this one (blocked items)
- Bidirectional sync: Setting A.up_dependencies=[B] auto-updates B.down_dependencies=[A]
- Same-type restriction: Bees→Bees, Tasks→Tasks, Subtasks→Subtasks only
- Circular detection: Validates no direct or transitive cycles
- Delete behavior: By default, surviving tickets are not modified (dependency arrays may contain stale
  refs). Set delete_with_dependencies: true in global config to remove the deleted subtree from
  external tickets' dependency arrays before deletion.

QUERIES
- Multi-stage pipeline: Each stage filters or traverses previous result set
- Search terms (AND logic): type=, id=, status=, title~regex, tag~regex, hive=, hive~regex
- Graph terms (traversal): parent, children, up_dependencies, down_dependencies
- Stage purity: Each stage is ONLY search OR ONLY graph, never mixed
- Named queries: Stored in ~/.bees/config.json under named_queries, validated on save
"""

    return {"status": "success", "commands": commands, "concepts": concepts}
