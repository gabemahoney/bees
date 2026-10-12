"""Startup self-check for the optional ``[serve]`` extra (fastmcp and mcp).

``bees serve`` needs fastmcp and mcp.  A venv can end up with them missing, half-installed
(a ``fastmcp/`` folder with no ``__init__.py``, which Python imports as a namespace package), or
at a version outside the supported range.  ``check_serve_dependencies`` probes for all of these and
returns a short, actionable message, or None when everything is usable.

Kept dependency-free (stdlib only) and importable without fastmcp or mcp, so the CLI can run it
before pulling in ``mcp_server``.
"""

import importlib
import importlib.metadata
import re
import shlex
import sys

# Keep in sync with the `serve` extra in pyproject.toml.
SUPPORTED_RANGES: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "fastmcp": ((3, 0, 2), (4,)),  # >=3.0.2,<4
    "mcp": ((1, 24, 0), (2,)),  # >=1.24.0,<2
}

# Distributions whose installed version is shown in the message (fastmcp >=3.3 keeps its files in fastmcp-slim).
REPORTED_DISTRIBUTIONS = ("fastmcp", "fastmcp-slim", "mcp")

# (module, names that src/ imports from it) -- see mcp_server.py, mcp_roots.py, mcp_repo_utils.py.
REQUIRED_NAMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fastmcp", ("Context", "FastMCP")),
    ("fastmcp.exceptions", ("NotFoundError",)),
    ("fastmcp.tools", ("FunctionTool",)),
    ("mcp.shared.exceptions", ("McpError",)),
)

PIPX_FIX = "pipx uninstall bees-md && pipx install 'bees-md[serve]'"


def pip_fix_command() -> str:
    """Clean-reinstall command for a pip-installed bees, built from the interpreter running bees.

    Uses ``sys.executable`` (shell-quoted) because a bare ``python`` may not exist (Ubuntu 22.04) or
    may be a different interpreter.  Uninstalling fastmcp, fastmcp-slim and mcp along with bees-md
    clears the half-written package files that an in-place upgrade across the fastmcp /
    fastmcp-slim split can leave behind; pip skips (with a warning) any that are not installed.
    """
    python = shlex.quote(sys.executable or "python3")
    return (
        f"{python} -m pip uninstall -y bees-md fastmcp fastmcp-slim mcp && "
        f"{python} -m pip install 'bees-md[serve]'"
    )


def parse_version(text: str) -> tuple[int, ...]:
    """Parse the leading dotted-integer part of a version string ("3.4.8rc1" -> (3, 4, 8))."""
    match = re.match(r"\d+(?:\.\d+)*", text.strip())
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def installed_version(distribution: str) -> str | None:
    """Installed version of a distribution, or None if it is not installed or its metadata is unreadable."""
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - broken metadata must not stop the check
        return None


def _describe_versions() -> str:
    parts = [f"{dist} {installed_version(dist) or 'not installed'}" for dist in REPORTED_DISTRIBUTIONS]
    return ", ".join(parts)


def _describe_ranges() -> str:
    parts = []
    for name, (low, high) in SUPPORTED_RANGES.items():
        parts.append(f"{name}>={'.'.join(map(str, low))},<{'.'.join(map(str, high))}")
    return ", ".join(parts)


def _probe_imports() -> str | None:
    """Return a description of the first import problem, or None if everything imports."""
    for package in ("fastmcp", "mcp"):
        try:
            module = importlib.import_module(package)
        except ImportError as e:
            return f"{package} cannot be imported ({e})"
        except Exception as e:  # noqa: BLE001 - any failure while importing means serve cannot run
            return f"importing {package} failed ({type(e).__name__}: {e})"
        if getattr(module, "__file__", None) is None:
            return (
                f"{package} is installed incompletely (its folder has no package files, "
                f"so Python sees an empty namespace package)"
            )

    for module_name, names in REQUIRED_NAMES:
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            return f"cannot import {module_name} ({e})"
        except Exception as e:  # noqa: BLE001
            return f"importing {module_name} failed ({type(e).__name__}: {e})"
        for name in names:
            if not hasattr(module, name):
                where = getattr(module, "__file__", None) or "unknown location"
                return f"cannot import name '{name}' from '{module_name}' ({where})"
    return None


def _probe_versions() -> str | None:
    """Return a description of the first out-of-range installed version, or None."""
    for name, (low, high) in SUPPORTED_RANGES.items():
        found = installed_version(name)
        if found is None:
            continue  # no metadata (e.g. vendored or source checkout): rely on the import probe
        parsed = parse_version(found)
        if not parsed or not (low <= parsed < high):
            return f"installed {name} {found} is outside the supported range"
    return None


def format_serve_dependency_message(problem: str) -> str:
    """Build the multi-line stderr message for a serve dependency problem."""
    return (
        f"bees serve cannot start: {problem}.\n"
        f"Installed: {_describe_versions()}. Supported: {_describe_ranges()}.\n"
        f"Fix with a clean reinstall:\n"
        f"  pipx:  {PIPX_FIX}\n"
        f"  pip:   {pip_fix_command()}"
    )


def check_serve_dependencies() -> str | None:
    """Probe fastmcp and mcp; return a ready-to-print message if unusable, else None.

    Checks, in order: the installed versions are inside the supported range, both packages import
    and are real packages (not an empty namespace package), and every name src/ imports from them
    exists.  Never raises.
    """
    problem = _probe_versions() or _probe_imports()
    if problem is None:
        return None
    return format_serve_dependency_message(problem)
