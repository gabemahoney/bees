"""
MCP Query Operations Module

Provides query operation functions for the Bees ticket management MCP server.
Handles named query registration and execution (both named and freeform queries).

This module is part of the modular refactoring of mcp_server.py to improve
maintainability and separation of concerns.
"""

import logging
from pathlib import Path
from typing import Any, Dict
from fastmcp import Context
from .query_storage import save_query, load_query, list_queries
from .query_parser import QueryParser, QueryValidationError
from .pipeline import PipelineEvaluator
from .config import load_bees_config
from .mcp_repo_utils import get_repo_root_from_path, get_repo_root, resolve_repo_root
from .repo_context import repo_root_context

logger = logging.getLogger(__name__)


def _add_named_query(
    name: str,
    query_yaml: str
) -> Dict[str, Any]:
    """
    Register a new named query for reuse.

    All queries are validated when registered to ensure they have valid structure.

    Args:
        name: Name for the query (used to execute it later)
        query_yaml: YAML string representing the query structure

    Returns:
        dict: Success status and query information

    Raises:
        ValueError: If query structure is invalid or name is invalid

    Example:
        query_yaml = '''
        - - type=task
          - label~beta
        - - parent
        '''
    """
    # Validate name is not empty
    if not name or not name.strip():
        error_msg = "Query name cannot be empty"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate and save query
    try:
        # This will validate structure and raise QueryValidationError if invalid
        save_query(name.strip(), query_yaml)
        logger.info(f"Successfully registered named query: {name}")

        return {
            "status": "success",
            "query_name": name.strip(),
            "message": f"Query '{name}' registered successfully"
        }

    except QueryValidationError as e:
        error_msg = f"Invalid query structure: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to save query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)


async def _execute_query(
    query_name: str,
    hive_names: list[str] | None = None,
    ctx: Context | None = None,
    repo_root: str | None = None
) -> Dict[str, Any]:
    """
    Execute a named query.

    Args:
        query_name: Name of the registered query to execute
        hive_names: Optional list of hive names to filter results (default: None = all hives)
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Query results with list of matching ticket IDs and metadata

    Raises:
        ValueError: If query name not found, hive not found, or execution fails

    Example:
        execute_query("open_tasks")
        execute_query("open_tasks", ["backend", "frontend"])
    """
    # Load query by name
    try:
        stages = load_query(query_name)
    except KeyError:
        error_msg = f"Query not found: {query_name}"
        logger.error(error_msg)
        available = list_queries()
        if available:
            error_msg += f". Available queries: {', '.join(available)}"
        else:
            error_msg += ". No queries registered yet."
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to load query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Resolve repo root and set context for entire function
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    
    with repo_root_context(resolved_root):
        # Validate hive existence if hive_names provided
        if hive_names:
            config = load_bees_config()
            if config is None:
                error_msg = "No hives configured. Available hives: none"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Check each hive exists
            for hive_name in hive_names:
                if hive_name not in config.hives:
                    available_hives = sorted(config.hives.keys())
                    error_msg = f"Hive not found: {hive_name}. Available hives: {', '.join(available_hives) if available_hives else 'none'}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

        # Execute query using pipeline evaluator
        try:
            evaluator = PipelineEvaluator()
            result_ids = evaluator.execute_query(stages, hive_names=hive_names)

            logger.info(f"Query '{query_name}' returned {len(result_ids)} tickets")

            return {
                "status": "success",
                "query_name": query_name,
                "result_count": len(result_ids),
                "ticket_ids": sorted(result_ids)
            }

        except Exception as e:
            error_msg = f"Failed to execute query '{query_name}': {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)


async def _execute_freeform_query(
    query_yaml: str,
    hive_names: list[str] | None = None,
    ctx: Context | None = None,
    repo_root: str | None = None
) -> Dict[str, Any]:
    """
    Execute a YAML query pipeline directly without persisting it.

    This function enables one-step ad-hoc query execution without polluting
    the query registry. The query is validated and executed immediately without
    being saved to disk.

    Args:
        query_yaml: YAML string representing the query pipeline structure
        hive_names: Optional list of hive names to filter results (default: None = all hives)
        ctx: FastMCP Context (auto-injected, gets client's repo root)

    Returns:
        dict: Query results with list of matching ticket IDs and metadata
            {
                "status": "success",
                "result_count": int,
                "ticket_ids": list[str],
                "stages_executed": int
            }

    Raises:
        ValueError: If query structure is invalid, hive not found, or execution fails

    Example:
        execute_freeform_query("- ['type=epic']\\n- ['children']")
        execute_freeform_query("- ['type=task', 'status=open']", ["backend"])
    """
    # Parse and validate query structure
    try:
        parser = QueryParser()
        stages = parser.parse_and_validate(query_yaml)
        logger.info(f"Parsed and validated freeform query with {len(stages)} stages")
    except QueryValidationError as e:
        error_msg = f"Invalid query structure: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Failed to parse query: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Resolve repo root and set context for entire function
    if ctx:
        resolved_root = await resolve_repo_root(ctx, repo_root)
    else:
        resolved_root = get_repo_root_from_path(Path.cwd())
    
    with repo_root_context(resolved_root):
        # Validate hive existence if hive_names provided
        if hive_names:
            config = load_bees_config()
            if config is None:
                error_msg = "No hives configured. Available hives: none"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Check each hive exists
            for hive_name in hive_names:
                if hive_name not in config.hives:
                    available_hives = sorted(config.hives.keys())
                    error_msg = f"Hive not found: {hive_name}. Available hives: {', '.join(available_hives) if available_hives else 'none'}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

        # Execute query using pipeline evaluator
        try:
            evaluator = PipelineEvaluator()
            result_ids = evaluator.execute_query(stages, hive_names=hive_names)

            logger.info(f"Freeform query returned {len(result_ids)} tickets across {len(stages)} stages")

            return {
                "status": "success",
                "result_count": len(result_ids),
                "ticket_ids": sorted(result_ids),
                "stages_executed": len(stages)
            }

        except Exception as e:
            error_msg = f"Failed to execute freeform query: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
