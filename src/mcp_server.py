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
from .mcp_index_ops import _generate_index
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
from .mcp_help import _help

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


# Register the generate_index tool with FastMCP
generate_index_tool = mcp.tool(name="generate_index")(_generate_index)


# Register the help tool with FastMCP
help = mcp.tool(name="help")(_help)


if __name__ == "__main__":
    logger.info("Running Bees MCP Server directly")
    start_server()
    mcp.run()
