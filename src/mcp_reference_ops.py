"""
Reference Materials Resolution Operations for Bees MCP Server

This module implements resolution of reference_materials entries from bee tickets
using configured resolvers (default file-path resolver or registered custom commands).
"""

import asyncio
import json
import logging
import shlex
from pathlib import Path
from typing import Any

from .config import load_resolver_registry

# Logger
logger = logging.getLogger(__name__)


DEFAULT_RESOLVER_CONVENTION = (
    "Accepts a string file path (absolute or relative). "
    "Absolute paths are normalized with Path.resolve() and checked for existence. "
    "Relative paths require repo_root and are resolved against it before existence check. "
    'Returns {"status": "success", "resolved_path": str} on success, '
    'or {"status": "error", "raw_value": value, "error": str} on failure.'
)


def resolve_file_path(value: Any, repo_root: Path | None = None) -> dict:
    """
    Resolve a file path value to an absolute, existing path.

    Args:
        value: The value to resolve (must be a string file path)
        repo_root: Repository root for resolving relative paths (required for relative paths)

    Returns:
        dict: Resolution result:
            On success: {"status": "success", "resolved_path": str}
            On error: {"status": "error", "raw_value": value, "error": str}
    """
    if not isinstance(value, str):
        return {"status": "error", "raw_value": value, "error": "value must be a string file path"}

    path = Path(value)

    if path.is_absolute():
        resolved = path.resolve()
        if resolved.exists():
            return {"status": "success", "resolved_path": str(resolved)}
        return {"status": "error", "raw_value": value, "error": f"path does not exist: {value}"}

    # Relative path — repo_root is required
    if repo_root is None:
        return {
            "status": "error",
            "raw_value": value,
            "error": "repo_root is required to resolve relative paths",
        }

    resolved = (repo_root / path).resolve()
    if resolved.exists():
        return {"status": "success", "resolved_path": str(resolved)}
    return {"status": "error", "raw_value": value, "error": f"path does not exist: {value}"}


async def _resolve_references(
    reference_materials: list[dict[str, Any]] | None,
    repo_root: Path | None = None,
) -> list[dict[str, Any]] | None:
    """
    Resolve all entries in a reference_materials list.

    For each entry in reference_materials:
    - Reads the ``resolver`` key (defaults to ``"default"`` if absent)
    - If ``"default"``: resolves via ``resolve_file_path()``
    - If the name is registered in the resolver registry: invokes via
      ``_invoke_custom_resolver()`` using the entry's path and timeout
    - If unregistered: fails gracefully for that entry, returning the raw
      value with an error

    Each entry is resolved independently; a failure on one does not affect others.

    Args:
        reference_materials: The reference_materials list from a bee ticket.
            Each entry is a dict with at least a ``"value"`` key and an optional
            ``"resolver"`` key.
        repo_root: Repository root for resolving relative file paths.

    Returns:
        None if reference_materials is None.
        Otherwise a list of dicts — one per input entry — where each dict
        contains the original entry fields plus a ``"resolved"`` key holding
        the resolution result.
    """
    if reference_materials is None:
        return None

    registry = load_resolver_registry()
    results: list[dict[str, Any]] = []

    for entry in reference_materials:
        value = entry.get("value")
        resolver_name = entry.get("resolver", "default")

        if resolver_name == "default":
            resolved = resolve_file_path(value, repo_root)
        elif resolver_name in registry:
            resolver_entry = registry[resolver_name]
            try:
                resolved = await _invoke_custom_resolver(
                    command=resolver_entry.path,
                    value=value,
                    repo_root=repo_root or Path("."),
                    timeout=resolver_entry.timeout,
                )
            except RuntimeError as e:
                resolved = {"status": "error", "raw_value": value, "error": str(e)}
        else:
            resolved = {
                "status": "error",
                "raw_value": value,
                "error": f"unregistered resolver: {resolver_name!r}",
            }

        result_entry = dict(entry)
        result_entry["resolved"] = resolved
        results.append(result_entry)

    return results


async def _invoke_custom_resolver(
    command: str,
    value: Any,
    repo_root: Path,
    timeout: int | float | None,
) -> Any:
    """
    Invoke a custom resolver as a subprocess.

    Command format: {command} --repo-root {shlex.quote(path)} --value {value}
    where value is shlex.quote(value) for strings, shlex.quote(json.dumps(value))
    for other types.

    String values are passed as raw strings. Non-string, non-None values (dict,
    list, int, etc.) are JSON-encoded before being passed to the resolver. None
    values never reach this function — the caller short-circuits and returns None
    directly.

    Args:
        command: The resolver command to invoke
        value: The reference_materials entry value to pass to the resolver
        repo_root: The repository root path
        timeout: Timeout in seconds (None for no timeout)

    Returns:
        Any: Parsed JSON output from resolver (any JSON-compatible value or null)

    Raises:
        RuntimeError: If resolver execution fails, times out, or returns invalid JSON
    """
    # Short-circuit: null values are not passed to resolvers
    if value is None:
        return None

    # Build command with args
    # Pass strings raw; JSON-encode non-string types.
    if isinstance(value, str):
        value_arg = shlex.quote(value)
    else:
        value_arg = shlex.quote(json.dumps(value))
    full_command = f"{command} --repo-root {shlex.quote(str(repo_root))} --value {value_arg}"

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
            # Kill process on timeout; close transport while loop is running to
            # avoid "Event loop is closed" GC traceback on loop teardown.
            proc.kill()
            await proc.wait()
            if hasattr(proc, "_transport") and proc._transport is not None:
                proc._transport.close()
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
