"""
Reference Materials Resolution Operations for Bees MCP Server

This module implements resolution of reference_materials entries from bee tickets
using configured resolvers (default file-path resolver or registered custom commands).
"""

import asyncio
import json
import logging
import os
import shlex
import signal
import sys
from pathlib import Path
from typing import Any

from .builtin_resolvers import resolve_bee, resolve_github
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

# Process groups are POSIX-only. Where they exist, each custom resolver runs in
# its own session (and so its own process group) so that a timeout kills every
# process the resolver started, not just the resolver itself.
_KILL_PROCESS_GROUP = os.name == "posix" and hasattr(os, "killpg")

# After killing a timed-out resolver, how long to wait for its pipes to reach
# EOF before closing them ourselves.
_POST_KILL_DRAIN_TIMEOUT = 1.0


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

        if resolver_name in ("default", "file-path"):
            resolved = resolve_file_path(value, repo_root)
        elif resolver_name == "github":
            resolved = await asyncio.to_thread(resolve_github, value)
        elif resolver_name == "bees":
            resolved = resolve_bee(value)
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


def _kill_resolver(proc: asyncio.subprocess.Process) -> None:
    """
    Kill a custom resolver and, on POSIX, every process in its process group.

    Killing only the resolver would leave its children running, still holding
    the resolver's stdout/stderr pipes open.

    Args:
        proc: The resolver process, started with ``start_new_session=True``
            when ``_KILL_PROCESS_GROUP`` is set
    """
    if _KILL_PROCESS_GROUP:
        try:
            # The resolver leads its own session, so its PID is its group ID.
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            # The group has no live members left. Some platforms (macOS)
            # report EPERM rather than ESRCH when only unreaped zombies remain.
            pass
        return

    try:
        proc.kill()
    except (ProcessLookupError, PermissionError):
        pass  # The resolver has already exited


async def _reap_killed_resolver(proc: asyncio.subprocess.Process) -> None:
    """
    Wait, for a bounded time, for a killed resolver to exit and its pipes to close.

    Draining stdout/stderr to EOF lets the pipe transports close cleanly.
    Without it, asyncio logs "Future exception was never retrieved" tracebacks
    to stderr when the event loop cleans up the still-active pipe transports.
    The wait is bounded because a process outside the killed group (one that
    started its own session, or any child on platforms without process groups)
    can hold the pipes open indefinitely. When the bound expires, the pipe
    transports are closed instead, so the readers see EOF and nothing is left
    for the event loop to clean up.

    Args:
        proc: The resolver process, already killed via ``_kill_resolver()``
    """

    async def _drain(stream: asyncio.StreamReader | None) -> None:
        if stream:
            try:
                await stream.read()
            except Exception:
                pass

    try:
        await asyncio.wait_for(
            asyncio.gather(_drain(proc.stdout), _drain(proc.stderr), proc.wait()),
            timeout=_POST_KILL_DRAIN_TIMEOUT,
        )
    except asyncio.TimeoutError:
        # asyncio.subprocess.Process has no public close(); closing its
        # transport closes both pipe transports while the event loop still runs.
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            transport.close()


async def _invoke_custom_resolver(
    command: str,
    value: Any,
    repo_root: Path,
    timeout: int | float | None,
) -> Any:
    """
    Invoke a custom resolver as a subprocess.

    Command format: {interpreter_tokens} + [command, "--repo-root", repo_root, "--value", value]
    where value is a raw string for str types, or json.dumps(value) for other types.

    String values are passed as raw strings. Non-string, non-None values (dict,
    list, int, etc.) are JSON-encoded before being passed to the resolver. None
    values never reach this function — the caller short-circuits and returns None
    directly.

    Args:
        command: The resolver command to invoke
        value: The reference_materials entry value to pass to the resolver
        repo_root: The repository root path
        timeout: Timeout in seconds (None for no timeout). On timeout the
            resolver's whole process group is killed (POSIX; elsewhere only
            the resolver itself).

    Returns:
        Any: Parsed JSON output from resolver (any JSON-compatible value or null)

    Raises:
        RuntimeError: If resolver execution fails, times out, or returns invalid JSON
    """
    # Short-circuit: null values are not passed to resolvers
    if value is None:
        return None

    # Build args list — no shell quoting needed with create_subprocess_exec.
    # Pass strings raw; JSON-encode non-string types.
    if isinstance(value, str):
        raw_value = value
    else:
        raw_value = json.dumps(value)
    # Detect interpreter so scripts don't need the executable bit set.
    # 1. By file extension: .py → use the current Python interpreter.
    # 2. Fallback: read shebang from first line of the script file.
    # 3. No interpreter found: invoke directly (legacy behaviour).
    interpreter_tokens: list[str] = []
    if command.endswith(".py"):
        interpreter_tokens = [sys.executable]
    else:
        try:
            with open(command, encoding="utf-8", errors="replace") as _f:
                first_line = _f.readline()
            if first_line.startswith("#!"):
                interpreter_tokens = shlex.split(first_line[2:].strip())
        except OSError:
            pass  # Can't read file — fall back to direct invocation

    args = interpreter_tokens + [command, "--repo-root", str(repo_root), "--value", raw_value]

    logger.info(f"Invoking custom resolver: {args}")

    # Run the resolver in its own session where supported, so a timeout can
    # kill its whole process group (see _KILL_PROCESS_GROUP).
    spawn_kwargs: dict[str, Any] = {"start_new_session": True} if _KILL_PROCESS_GROUP else {}

    try:
        # Invoke subprocess with timeout
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **spawn_kwargs,
        )

        # Wait for completion with timeout
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            # Kill the resolver's whole process group, not just the resolver:
            # a surviving child keeps the pipes open, and the call would then
            # block until that child exits. Then reap with a bounded wait.
            _kill_resolver(proc)
            await _reap_killed_resolver(proc)
            timeout_msg = f"Resolver timed out after {timeout} seconds"
            logger.error(timeout_msg)
            raise RuntimeError(timeout_msg) from None
        except asyncio.CancelledError:
            # In its own session, the resolver no longer receives the
            # terminal's Ctrl-C, so kill its group when the caller gives up.
            # Reap it too: an unreaped subprocess transport is left for the
            # event loop's teardown, which then warns that the loop is closed.
            _kill_resolver(proc)
            await _reap_killed_resolver(proc)
            raise

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
