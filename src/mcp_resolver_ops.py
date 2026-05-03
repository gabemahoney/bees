"""
MCP Resolver Operations Module

Provides resolver registry management for the Bees ticket management system.
Handles registering, updating, and removing named resolver scripts.
"""

import logging
import re
from pathlib import Path

from .config import ResolverEntry, load_global_config, load_resolver_registry, save_resolver_registry

logger = logging.getLogger(__name__)


def _extract_convention(script_path: str) -> str | None:
    """Extract the RESOLVER CONVENTION section from a resolver script's module docstring.

    Reads the file, finds ``## RESOLVER CONVENTION`` in the module docstring,
    and extracts the text from that heading until the next ``##`` heading or
    end of docstring.

    Args:
        script_path: Path to the resolver script file.

    Returns:
        Stripped convention text, or None if the section is not found.
    """
    try:
        content = Path(script_path).read_text(encoding="utf-8")
    except OSError:
        return None

    # Extract the module docstring — the first triple-quoted string in the file,
    # which may be preceded by a shebang or encoding comment.
    docstring_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
    if not docstring_match:
        docstring_match = re.search(r"'''(.*?)'''", content, re.DOTALL)
    if not docstring_match:
        return None

    docstring = docstring_match.group(1)

    # Find the ## RESOLVER CONVENTION heading
    convention_match = re.search(r"##\s*RESOLVER CONVENTION\s*\n(.*?)(?=##|\Z)", docstring, re.DOTALL)
    if not convention_match:
        return None

    return convention_match.group(1).strip() or None


def _get_resolvers() -> dict:
    """Return all registered resolvers plus the built-in resolvers.

    Built-ins listed:
      - ``file-path``: resolves string file paths (canonical name for ``default``)
      - ``github``: fetches GitHub issue/PR metadata via gh CLI
      - ``bees``: identity resolver for Bee ID links

    Returns:
        dict with "status": "success" and "resolvers": list of resolver dicts.
        Each entry has: name, path, timeout, convention, built_in.
    """
    from .builtin_resolvers import (  # avoid circular at module level
        BEES_RESOLVER_CONVENTION,
        GITHUB_RESOLVER_CONVENTION,
    )
    from .mcp_reference_ops import DEFAULT_RESOLVER_CONVENTION  # avoid circular at module level

    registry = load_resolver_registry()
    resolvers = [
        {
            "name": "file-path",
            "path": None,
            "timeout": None,
            "convention": DEFAULT_RESOLVER_CONVENTION,
            "built_in": True,
        },
        {
            "name": "github",
            "path": None,
            "timeout": None,
            "convention": GITHUB_RESOLVER_CONVENTION,
            "built_in": True,
        },
        {
            "name": "bees",
            "path": None,
            "timeout": None,
            "convention": BEES_RESOLVER_CONVENTION,
            "built_in": True,
        },
    ]
    for name, entry in registry.items():
        resolvers.append(
            {
                "name": name,
                "path": entry.path,
                "timeout": entry.timeout,
                "convention": entry.convention,
                "built_in": False,
            }
        )
    return {"status": "success", "resolvers": resolvers}


def _set_resolver(
    name: str,
    path: str | None = None,
    timeout: int | float | None = None,
    unset: bool = False,
) -> dict:
    """Register, update, or remove a named resolver in the global registry.

    Args:
        name: Resolver name. "default" is reserved and cannot be used.
        path: Absolute path to the resolver script (required for register/update).
        timeout: Optional timeout in seconds for the resolver.
        unset: If True, remove the resolver from the registry instead of adding/updating.

    Returns:
        Success or error dict.
    """
    _RESERVED_NAMES = {"default", "file-path", "github", "bees"}
    if name in _RESERVED_NAMES:
        return {
            "status": "error",
            "error_type": "reserved_name",
            "message": f"{name} is a reserved resolver name",
        }

    if unset:
        registry = load_resolver_registry()
        if name not in registry:
            return {
                "status": "error",
                "error_type": "not_found",
                "message": f"Resolver '{name}' not found in registry",
            }

        # Check no hive in any scope references this resolver in allowed_resolvers
        global_config = load_global_config()
        for scope_pattern, scope_data in global_config.get("scopes", {}).items():
            for hive_name, hive_data in scope_data.get("hives", {}).items():
                allowed = hive_data.get("allowed_resolvers")
                if allowed and name in allowed:
                    return {
                        "status": "error",
                        "error_type": "resolver_in_use",
                        "message": (
                            f"Resolver '{name}' is referenced by hive '{hive_name}' "
                            f"in scope '{scope_pattern}' (allowed_resolvers). "
                            "Remove it from that hive first."
                        ),
                    }

        del registry[name]
        save_resolver_registry(registry)
        return {
            "status": "success",
            "action": "unset",
            "name": name,
        }

    # Register / update mode
    if not path:
        return {
            "status": "error",
            "error_type": "missing_path",
            "message": "path is required when registering or updating a resolver",
        }

    if not Path(path).exists():
        return {
            "status": "error",
            "error_type": "file_not_found",
            "message": f"Resolver script not found: {path}",
        }

    convention = _extract_convention(path)
    registry = load_resolver_registry()
    registry[name] = ResolverEntry(path=path, timeout=timeout, convention=convention)
    save_resolver_registry(registry)

    result: dict = {
        "status": "success",
        "action": "set",
        "name": name,
        "path": path,
    }
    if timeout is not None:
        result["timeout"] = timeout
    if convention is not None:
        result["convention"] = convention
    return result
