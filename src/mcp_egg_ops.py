"""
Egg Resolution Operations for Bees MCP Server

This module implements the resolve_eggs MCP tool that resolves egg field values
from bee tickets using configured egg resolvers (default or custom commands).
"""

import asyncio
import json
import logging
import shlex
from pathlib import Path
from typing import Any

from .config import load_bees_config, resolve_egg_resolver, resolve_egg_resolver_timeout
from .mcp_ticket_ops import find_hive_for_ticket
from .paths import get_ticket_path, infer_ticket_type_from_id
from .reader import read_ticket

# Logger
logger = logging.getLogger(__name__)


async def _resolve_eggs(
    ticket_id: str,
    resolved_root: Path | None = None,
) -> dict[str, Any]:
    """
    Resolve egg field from a bee ticket using configured egg resolver.

    Execution flow:
    1. Fetch ticket and validate it's a bee
    2. Extract egg field
    3. Determine resolver via config resolution order (hive → scope → global → default)
    4. If default (None): return value unchanged (identity function)
    5. If command string: invoke subprocess with --repo-root and --egg-value args
    6. Parse JSON output and validate (array of strings or null)
    7. Return result dict with status and resources

    Args:
        ticket_id: ID of the bee ticket to resolve eggs for
        resolved_root: Pre-resolved repo root path (injected by adapter)

    Returns:
        dict: Resolution result with structure:
            On success: {"status": "success", "ticket_id": str, "resources": list[str] | None}
            On error: {"status": "error", "error_type": str, "message": str}

    Raises:
        RuntimeError: If resolver execution fails or times out

    Example:
        >>> await _resolve_eggs("b.Amx")
        {"status": "success", "ticket_id": "b.Amx", "resources": ["file1.txt", "file2.txt"]}
    """
    # Validate ticket_id is not empty
    if not ticket_id or not ticket_id.strip():
        error_msg = "ticket_id cannot be empty"
        logger.error(error_msg)
        return {"status": "error", "error_type": "invalid_ticket_id", "message": error_msg}

    # Find hive for ticket (O(n) scan across all hives)
    resolved_hive = find_hive_for_ticket(ticket_id)
    if not resolved_hive:
        error_msg = f"Ticket not found in any configured hive: {ticket_id}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "ticket_not_found", "message": error_msg}

    # Infer ticket type from ID
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        error_msg = f"Ticket does not exist: {ticket_id}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "ticket_not_found", "message": error_msg}

    # Validate ticket is a bee
    if ticket_type != "bee":
        error_msg = f"resolve_eggs only works on bee tickets, got type: {ticket_type}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "invalid_ticket_type", "message": error_msg}

    # Get ticket path and read ticket
    ticket_path = get_ticket_path(ticket_id, ticket_type, resolved_hive)
    try:
        ticket = read_ticket(ticket_id, file_path=ticket_path)
    except FileNotFoundError:
        error_msg = f"Ticket file not found: {ticket_id}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "ticket_not_found", "message": error_msg}
    except Exception as e:
        error_msg = f"Failed to read ticket {ticket_id}: {e}"
        logger.error(error_msg)
        return {"status": "error", "error_type": "read_error", "message": error_msg}

    egg_value = ticket.egg

    # Determine resolver via config resolution (hive → scope → global → default)
    config = load_bees_config()
    egg_resolver = resolve_egg_resolver(resolved_hive, config)
    timeout = resolve_egg_resolver_timeout(resolved_hive, config)

    logger.info(f"Resolving eggs for {ticket_id} with resolver: {egg_resolver or 'default'}")

    # Handle default resolver (inline, no subprocess)
    if egg_resolver is None:
        resources = _default_resolver(egg_value)
        logger.info(f"Default resolver returned: {resources}")
        return {"status": "success", "ticket_id": ticket_id, "resources": resources}

    # Handle custom resolver (subprocess invocation)
    if resolved_root is None:
        error_msg = "resolved_root is required when a custom egg resolver is configured"
        logger.error(error_msg)
        return {"status": "error", "error_type": "missing_config", "message": error_msg}
    resources = await _invoke_custom_resolver(egg_resolver, egg_value, resolved_root, timeout)
    logger.info(f"Custom resolver returned: {resources}")
    return {"status": "success", "ticket_id": ticket_id, "resources": resources}


def _default_resolver(egg_value: Any) -> Any:
    """
    Default egg resolver — identity function.

    Returns the egg value unchanged. Custom resolvers can transform
    egg values via subprocess; the default resolver is a no-op.
    """
    return egg_value


async def _invoke_custom_resolver(
    command: str,
    egg_value: Any,
    repo_root: Path,
    timeout: int | float | None,
) -> Any:
    """
    Invoke custom egg resolver as subprocess.

    Command format: {command} --repo-root {shlex.quote(path)} --egg-value {value}
    where value is shlex.quote(egg_value) for strings, shlex.quote(json.dumps(egg_value)) for other types.

    String egg values are passed as raw strings. Non-string, non-None values (dict, list,
    int, etc.) are JSON-encoded before being passed to the resolver. None egg values never
    reach this function — the caller short-circuits and returns None directly.

    Args:
        command: The resolver command to invoke
        egg_value: The egg field value to pass to the resolver
        repo_root: The repository root path
        timeout: Timeout in seconds (None for no timeout)

    Returns:
        Any: Parsed JSON output from resolver (any JSON-compatible value or null)

    Raises:
        RuntimeError: If resolver execution fails, times out, or returns invalid JSON
    """
    # Short-circuit: null eggs are not passed to resolvers
    if egg_value is None:
        return None

    # Build command with args
    # Pass strings raw; JSON-encode non-string types.
    if isinstance(egg_value, str):
        egg_arg = shlex.quote(egg_value)
    else:
        egg_arg = shlex.quote(json.dumps(egg_value))
    full_command = f"{command} --repo-root {shlex.quote(str(repo_root))} --egg-value {egg_arg}"

    logger.info(f"Invoking custom resolver: {full_command}")

    try:
        # Invoke subprocess with timeout
        proc = await asyncio.create_subprocess_shell(
            full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for completion with timeout
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            # Kill process on timeout
            proc.kill()
            await proc.wait()
            timeout_msg = f"Resolver timed out after {timeout} seconds"
            logger.error(timeout_msg)
            raise RuntimeError(timeout_msg) from None

        # Check exit code
        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace")
            error_msg = f"Resolver exited with code {proc.returncode}. Stderr: {stderr_text}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Parse JSON output
        stdout_text = stdout.decode("utf-8", errors="replace")
        try:
            result = json.loads(stdout_text)
        except json.JSONDecodeError as e:
            error_msg = f"Resolver returned invalid JSON: {e}. Output: {stdout_text}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

        return result

    except Exception as e:
        # Re-raise RuntimeError as-is, wrap other exceptions
        if isinstance(e, RuntimeError):
            raise
        error_msg = f"Failed to invoke resolver: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
