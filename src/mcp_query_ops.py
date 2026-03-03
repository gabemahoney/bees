"""
MCP Query Operations Module

Provides query operation functions for the Bees ticket management MCP server.
Handles named query registration and execution (both named and freeform queries).

This module is part of the modular refactoring of mcp_server.py to improve
maintainability and separation of concerns.
"""

import logging
from pathlib import Path
from typing import Any

from .config import (
    check_query_name_conflict,
    find_matching_scope,
    load_global_config,
    resolve_named_query,
    save_global_config,
)
from .pipeline import PipelineEvaluator
from .query_parser import QueryParser, QueryValidationError
from .repo_utils import get_repo_root_from_path  # noqa: F401 - kept for monkeypatching in tests

logger = logging.getLogger(__name__)


def _add_named_query(name: str, query_yaml: str, scope: str, resolved_root: Path) -> dict[str, Any]:
    """
    Register a new named query in config-backed storage.

    Queries are validated at registration time. The query is stored in the
    global config (``~/.bees/config.json``) under either the top-level
    ``queries`` dict (scope="global") or the matched repo scope's ``queries``
    dict (scope="repo").

    Args:
        name: Name for the query (used to execute it later)
        query_yaml: YAML string representing the query structure
        scope: Where to store the query ("global" or "repo")
        resolved_root: Pre-resolved repo root path

    Returns:
        dict: Success or error status with query information
    """
    # Validate name is not empty
    if not name or not name.strip():
        error_msg = "Query name cannot be empty"
        logger.error(error_msg)
        return {"status": "error", "error_type": "invalid_query", "message": error_msg}

    name = name.strip()

    # Validate scope
    if scope not in ("global", "repo"):
        return {
            "status": "error",
            "error_type": "invalid_scope",
            "message": f"Invalid scope '{scope}'. Must be 'global' or 'repo'.",
        }

    global_config = load_global_config()

    # For scope="repo": verify resolved_root matches a registered scope
    matched_pattern = find_matching_scope(resolved_root, global_config) if scope == "repo" else None
    if scope == "repo" and matched_pattern is None:
        return {
            "status": "error",
            "error_type": "scope_not_found",
            "message": f"No registered scope matches repo root '{resolved_root}'.",
        }

    # Check for name conflicts BEFORE writing
    conflict = check_query_name_conflict(name, scope, resolved_root, global_config)
    if conflict is not None:
        return {
            "status": "error",
            "error_type": "query_name_conflict",
            "message": f"Query '{name}' already exists at {conflict['level']} level ({conflict['location']}).",
            "conflict_level": conflict["level"],
            "conflict_location": conflict["location"],
        }

    # Parse and validate query structure
    try:
        parser = QueryParser()
        stages = parser.parse_and_validate(query_yaml)
    except QueryValidationError as e:
        error_msg = f"Invalid query structure: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "parse_error", "message": error_msg}

    # Write parsed stages to the appropriate queries dict in global config
    if scope == "global":
        if "queries" not in global_config:
            global_config["queries"] = {}
        global_config["queries"][name] = stages
    else:  # scope == "repo"
        scope_data = global_config["scopes"][matched_pattern]
        if "queries" not in scope_data:
            scope_data["queries"] = {}
        scope_data["queries"][name] = stages

    save_global_config(global_config)

    logger.info(f"Successfully registered named query: {name} (scope={scope})")
    return {
        "status": "success",
        "query_name": name,
        "scope": scope,
        "message": f"Query '{name}' registered successfully",
    }


def _delete_named_query(name: str, resolved_root: Path) -> dict[str, Any]:
    """
    Delete a named query from config-backed storage.

    Searches for the query by name — first in global queries, then across all
    repo scopes. If the last query at a scope level is removed, the ``queries``
    key is cleaned up entirely.

    Args:
        name: Name of the query to delete
        resolved_root: Pre-resolved repo root path (used for context only)

    Returns:
        dict: Success or error status with query information
    """
    global_config = load_global_config()

    # Search global queries first
    global_queries = global_config.get("queries", {})
    if name in global_queries:
        del global_queries[name]
        if not global_queries:
            global_config.pop("queries", None)
        else:
            global_config["queries"] = global_queries
        save_global_config(global_config)
        logger.info(f"Successfully deleted named query: {name} (scope=global)")
        return {
            "status": "success",
            "query_name": name,
            "message": f"Query '{name}' deleted successfully.",
        }

    # Search only the caller's matched repo scope
    matched_pattern = find_matching_scope(resolved_root, global_config)
    if matched_pattern is not None:
        scope_data = global_config["scopes"][matched_pattern]
        scope_queries = scope_data.get("queries", {})
        if name in scope_queries:
            del scope_queries[name]
            if not scope_queries:
                scope_data.pop("queries", None)
            else:
                scope_data["queries"] = scope_queries
            save_global_config(global_config)
            logger.info(f"Successfully deleted named query: {name} (scope={matched_pattern})")
            return {
                "status": "success",
                "query_name": name,
                "message": f"Query '{name}' deleted successfully.",
            }

    return {
        "status": "error",
        "error_type": "query_not_found",
        "message": f"Query '{name}' not found.",
    }


def _list_named_queries(resolved_root: Path | None = None) -> dict[str, Any]:
    """
    List named queries from config-backed storage.

    Returns queries accessible from the current repo scope (matched
    repo-scoped queries + global queries).

    Args:
        resolved_root: Pre-resolved repo root path (used for scope matching)

    Returns:
        dict: Success status with list of query entries
    """
    global_config = load_global_config()
    result_queries: list[dict[str, Any]] = []

    # Find matched scope for resolved_root
    matched_pattern = find_matching_scope(resolved_root, global_config) if resolved_root else None
    if matched_pattern is not None:
        scope_data = global_config.get("scopes", {}).get(matched_pattern, {})
        for qname, qdef in scope_data.get("queries", {}).items():
            result_queries.append({
                "name": qname,
                "definition": qdef,
                "scope": "repo",
                "repo_root": matched_pattern,
            })
    # Collect global queries
    for qname, qdef in global_config.get("queries", {}).items():
        result_queries.append({
            "name": qname,
            "definition": qdef,
            "scope": "global",
            "repo_root": None,
        })

    return {
        "status": "success",
        "queries": result_queries,
        "count": len(result_queries),
    }


async def _execute_named_query(
    query_name: str, resolved_root: Path | None = None
) -> dict[str, Any]:
    """
    Execute a named query.

    Args:
        query_name: Name of the registered query to execute
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Query results with list of matching ticket IDs and metadata

    Raises:
        ValueError: If query name not found or execution fails

    Example:
        execute_named_query("open_tasks")
    """
    # Resolve query from config-backed storage
    global_config = load_global_config()
    resolution = resolve_named_query(query_name, resolved_root, global_config)

    if resolution["status"] == "out_of_scope":
        return {
            "status": "error",
            "error_type": "query_out_of_scope",
            "message": f"Query '{query_name}' exists but is not accessible from the current scope.",
        }

    if resolution["status"] == "not_found":
        # Collect all accessible query names (repo scope + global)
        available: list[str] = []
        seen: set[str] = set()
        matched_pattern = find_matching_scope(resolved_root, global_config)
        if matched_pattern is not None:
            scope_data = global_config.get("scopes", {}).get(matched_pattern, {})
            for q in sorted(scope_data.get("queries", {}).keys()):
                if q not in seen:
                    seen.add(q)
                    available.append(q)
        for q in sorted(global_config.get("queries", {}).keys()):
            if q not in seen:
                seen.add(q)
                available.append(q)
        return {
            "status": "error",
            "error_type": "query_not_found",
            "message": f"Query not found: {query_name}",
            "available_queries": available,
        }

    stages = resolution["stages"]

    # Execute query using pipeline evaluator
    try:
        evaluator = PipelineEvaluator()
        result_ids = evaluator.execute_query(stages)

        logger.info(f"Query '{query_name}' returned {len(result_ids)} tickets")

        return {
            "status": "success",
            "query_name": query_name,
            "result_count": len(result_ids),
            "ticket_ids": sorted(result_ids),
        }

    except Exception as e:
        error_msg = f"Failed to execute query '{query_name}': {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "execution_error", "message": error_msg}


async def _execute_freeform_query(
    query_yaml: str, resolved_root: Path | None = None
) -> dict[str, Any]:
    """
    Execute a YAML query pipeline directly without persisting it.

    This function enables one-step ad-hoc query execution without polluting
    the query registry. The query is validated and executed immediately without
    being saved to disk.

    Args:
        query_yaml: YAML string representing the query pipeline structure
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Query results with list of matching ticket IDs and metadata
            {
                "status": "success",
                "result_count": int,
                "ticket_ids": list[str],
                "stages_executed": int
            }

    Raises:
        ValueError: If query structure is invalid or execution fails

    Example:
        execute_freeform_query("- ['type=bee']\\n- ['children']")
        execute_freeform_query("- ['type=t1', 'status=open', 'hive=backend']")
    """
    # Parse and validate query structure
    try:
        parser = QueryParser()
        stages = parser.parse_and_validate(query_yaml)
        logger.info(f"Parsed and validated freeform query with {len(stages)} stages")
    except QueryValidationError as e:
        error_msg = f"Invalid query structure: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "parse_error", "message": error_msg}
    except Exception as e:
        error_msg = f"Failed to parse query: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "parse_error", "message": error_msg}

    # Execute query using pipeline evaluator
    try:
        evaluator = PipelineEvaluator()
        result_ids = evaluator.execute_query(stages)

        logger.info(f"Freeform query returned {len(result_ids)} tickets across {len(stages)} stages")

        return {
            "status": "success",
            "result_count": len(result_ids),
            "ticket_ids": sorted(result_ids),
            "stages_executed": len(stages),
        }

    except Exception as e:
        error_msg = f"Failed to execute freeform query: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "execution_error", "message": error_msg}
