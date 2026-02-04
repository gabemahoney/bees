"""
MCP Server for Bees Ticket Management System

Provides FastMCP server infrastructure with tool registration for ticket operations.
"""

import json
import logging
import os
import re
import yaml
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal
from fastmcp import FastMCP, Context
from .paths import infer_ticket_type_from_id, get_ticket_path
from .index_generator import generate_index
from .config import (
    validate_unique_hive_name, load_bees_config, save_bees_config,
    HiveConfig, BeesConfig, init_bees_config_if_needed,
    load_hive_config_dict, write_hive_config_dict, register_hive_dict
)
from .id_utils import normalize_hive_name
from .mcp_id_utils import parse_ticket_id, parse_hive_from_ticket_id
from .mcp_repo_utils import get_repo_root_from_path, get_client_repo_root, get_repo_root
from .mcp_hive_utils import validate_hive_path, scan_for_hive
from .mcp_relationships import (
    _update_bidirectional_relationships,
    _add_child_to_parent,
    _remove_child_from_parent,
    _set_parent_on_child,
    _remove_parent_from_child,
    _add_to_down_dependencies,
    _remove_from_down_dependencies,
    _add_to_up_dependencies,
    _remove_from_up_dependencies
)
from .mcp_ticket_ops import (
    _create_ticket,
    _update_ticket,
    _delete_ticket,
    _show_ticket
)
from .mcp_hive_ops import (
    colonize_hive_core,
    _colonize_hive,
    _list_hives,
    _abandon_hive,
    _rename_hive,
    _sanitize_hive
)
from .mcp_query_ops import (
    _add_named_query,
    _execute_query,
    _execute_freeform_query
)

# Ensure log directory exists
log_dir = Path.home() / '.bees'
log_dir.mkdir(exist_ok=True)

# Configure logging to file for MCP stdio compatibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=log_dir / 'mcp.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Bees Ticket Management Server")

# Server state
_server_running = False




def start_server() -> Dict[str, Any]:
    """
    Start the MCP server.

    Returns:
        dict: Server status information
    """
    global _server_running

    try:
        logger.info("Starting Bees MCP Server...")
        _server_running = True
        logger.info("Bees MCP Server started successfully")

        return {
            "status": "running",
            "name": "Bees Ticket Management Server",
            "version": "0.1.0"
        }
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        _server_running = False
        raise


def stop_server() -> Dict[str, Any]:
    """
    Stop the MCP server.

    Returns:
        dict: Server status information
    """
    global _server_running

    try:
        logger.info("Stopping Bees MCP Server...")
        _server_running = False
        logger.info("Bees MCP Server stopped successfully")

        return {
            "status": "stopped",
            "name": "Bees Ticket Management Server"
        }
    except Exception as e:
        logger.error(f"Failed to stop server: {e}")
        raise


def _health_check() -> Dict[str, Any]:
    """
    Check the health status of the MCP server.

    Returns:
        dict: Health status including server state and readiness
    """
    return {
        "status": "healthy" if _server_running else "stopped",
        "server_running": _server_running,
        "name": "Bees Ticket Management Server",
        "version": "0.1.0",
        "ready": _server_running
    }


# Register the health_check tool with FastMCP
health_check = mcp.tool(name="health_check")(_health_check)


# Register the create_ticket tool with FastMCP (implementation in mcp_ticket_ops.py)
create_ticket = mcp.tool(name="create_ticket")(_create_ticket)


# Register the update_ticket tool with FastMCP (implementation in mcp_ticket_ops.py)
update_ticket = mcp.tool(name="update_ticket")(_update_ticket)


# Register the delete_ticket tool with FastMCP (implementation in mcp_ticket_ops.py)
delete_ticket = mcp.tool(name="delete_ticket")(_delete_ticket)


# Register hive lifecycle operation tools with FastMCP (implementation in mcp_hive_ops.py)
colonize_hive = mcp.tool(name="colonize_hive")(_colonize_hive)
list_hives = mcp.tool(name="list_hives")(_list_hives)
abandon_hive = mcp.tool(name="abandon_hive")(_abandon_hive)
rename_hive = mcp.tool(name="rename_hive")(_rename_hive)
sanitize_hive = mcp.tool(name="sanitize_hive")(_sanitize_hive)


# Register the add_named_query tool with FastMCP (implementation in mcp_query_ops.py)
add_named_query = mcp.tool(name="add_named_query")(_add_named_query)


# Register the execute_query tool with FastMCP (implementation in mcp_query_ops.py)
execute_query = mcp.tool(name="execute_query")(_execute_query)


# Register the execute_freeform_query tool with FastMCP (implementation in mcp_query_ops.py)
execute_freeform_query = mcp.tool(name="execute_freeform_query")(_execute_freeform_query)


# Register the show_ticket tool with FastMCP (implementation in mcp_ticket_ops.py)
show_ticket = mcp.tool(name="show_ticket")(_show_ticket)


def _generate_index(
    status: str | None = None,
    type: str | None = None,
    hive_name: str | None = None
) -> Dict[str, Any]:
    """
    Generate markdown index of all tickets with optional filters.

    Scans the tickets directory and creates a formatted markdown index.
    Optionally filters tickets by status and/or type. Can generate per-hive
    indexes or indexes for all hives.

    When hive_name is provided, generates and writes index only for that hive
    to {hive_path}/index.md.

    When hive_name is omitted, iterates all registered hives and generates
    separate index.md files for each hive at their respective hive roots.

    Args:
        status: Optional status filter (e.g., 'open', 'completed')
        type: Optional type filter (e.g., 'epic', 'task', 'subtask')
        hive_name: Optional hive name to generate index for specific hive only.
                   If provided, generates index only for that hive.
                   If omitted, generates indexes for all hives.

    Returns:
        dict: Response with status and generated markdown index

    Example:
        result = _generate_index()
        result = _generate_index(status='open')
        result = _generate_index(type='epic')
        result = _generate_index(status='open', type='task')
        result = _generate_index(hive_name='backend')
    """
    try:
        index_markdown = generate_index(
            status_filter=status,
            type_filter=type,
            hive_name=hive_name
        )
        logger.info(f"Successfully generated ticket index (status={status}, type={type}, hive_name={hive_name})")
        return {
            "status": "success",
            "markdown": index_markdown
        }
    except Exception as e:
        error_msg = f"Failed to generate index: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


# Register the generate_index tool with FastMCP
generate_index_tool = mcp.tool(name="generate_index")(_generate_index)


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


# Register the help tool with FastMCP
help = mcp.tool(name="help")(_help)


if __name__ == "__main__":
    logger.info("Running Bees MCP Server directly")
    start_server()
    mcp.run()
