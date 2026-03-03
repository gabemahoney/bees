"""Bees sting command — emits CLI reference in non-MCP sessions.

When invoked:
  1. Detect if CWD is in a bees-managed scope. No match → silent exit 0.
  2. Scan known Claude config locations for a bees MCP server entry.
     Match in global or current-project scope → MCP mode → silent exit 0.
  3. Otherwise print the plain-text CLI reference and exit 0.
"""

import json
import logging
import re
import sys
from pathlib import Path

from .config import find_matching_scope, load_global_config
from .repo_utils import get_repo_root_from_path

logger = logging.getLogger(__name__)

# Matches "bees", "bees-mcp", "my_bees", but NOT "frisbees"
_BEES_PATTERN = re.compile(r"(?i)(?:^|[-_])bees(?:$|[-_])")

_CLI_REFERENCE = """\
You are in a bees-managed project; bees is a ticket management system.
Tickets are called bees. They are stored in directories called hives.
Bees support a tier hierarchy: bees are top-level tickets; child tiers (t1, t2, etc.)
are sub-tickets nested under a parent.
Use the bees CLI for all ticket operations.
All commands output JSON to stdout, including errors. Exit 0 on success, exit 1 on error.
Run bees <command> -h for full usage on any command.

  create-ticket           Create a bee or child-tier ticket
  show-ticket             Retrieve one or more tickets by ID
  update-ticket           Update ticket fields; supports batch mode for status/tags
  delete-ticket           Delete tickets and their child subtrees (cascading)
  execute-freeform-query  Run an ad-hoc YAML query pipeline
  execute-named-query     Run a saved named query
  add-named-query         Save a query for reuse
  list-named-queries      List all saved queries
  delete-named-query      Delete a saved query by name
  colonize-hive           Create and register a new hive
  list-hives              List all registered hives
  abandon-hive            Unregister a hive (files kept on disk)
  rename-hive             Rename a hive and optionally its folder on disk
  sanitize-hive           Validate and auto-fix malformed tickets in a hive
  get-types               Show allowed ticket types for all hives
  set-types               Configure tier hierarchy at global, repo, or hive scope
  get-status-values       Show configured status values at all scope levels
  set-status-values       Configure allowed statuses at global, repo, or hive scope
  generate-index          Generate index.md files for hives
  undertaker              Archive bee tickets to /cemetery
  move-bee                Move bee tickets to a different hive"""


def _key_matches_bees(key: str) -> bool:
    """Return True if the MCP server key matches the bees pattern."""
    return bool(_BEES_PATTERN.search(key))


def _has_bees_in_mcp_servers(mcp_servers: object) -> bool:
    """Return True if any key in mcp_servers dict matches the bees pattern."""
    if not isinstance(mcp_servers, dict):
        return False
    return any(_key_matches_bees(k) for k in mcp_servers)


def _detect_mcp(repo_root: Path) -> bool:
    """Scan the three Claude config locations for a bees MCP server entry.

    Returns True if bees MCP is configured for the global scope or for the
    current repo_root project scope.  A match scoped to a *different* project
    does NOT count.
    """
    home = Path.home()

    # --- Location 1 & 2: ~/.claude.json ---
    claude_json = home / ".claude.json"
    try:
        raw = claude_json.read_text(encoding="utf-8")
        data = json.loads(raw)

        # 1. Top-level mcpServers (global scope)
        if _has_bees_in_mcp_servers(data.get("mcpServers")):
            return True

        # 2. Per-project entry matching current repo root
        projects = data.get("projects")
        if isinstance(projects, dict):
            repo_root_str = str(repo_root)
            project_data = projects.get(repo_root_str)
            if isinstance(project_data, dict):
                if _has_bees_in_mcp_servers(project_data.get("mcpServers")):
                    return True
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError):
        pass  # malformed or unreadable — skip silently

    # --- Location 3: <repo_root>/.mcp.json ---
    dot_mcp = repo_root / ".mcp.json"
    try:
        raw = dot_mcp.read_text(encoding="utf-8")
        data = json.loads(raw)
        if _has_bees_in_mcp_servers(data.get("mcpServers")):
            return True
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError):
        pass

    # --- Location 4: ~/.claude/settings.json ---
    settings_json = home / ".claude" / "settings.json"
    try:
        raw = settings_json.read_text(encoding="utf-8")
        data = json.loads(raw)
        if _has_bees_in_mcp_servers(data.get("mcpServers")):
            return True
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError):
        pass

    # --- Location 5: <repo_root>/.claude/settings.local.json ---
    settings_local = repo_root / ".claude" / "settings.local.json"
    try:
        raw = settings_local.read_text(encoding="utf-8")
        data = json.loads(raw)
        if _has_bees_in_mcp_servers(data.get("mcpServers")):
            return True
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError):
        pass

    return False


def handle_sting(args):
    """Handle the `bees sting` command."""
    # Step 1 — Scope detection
    repo_root = get_repo_root_from_path(Path.cwd())
    global_config = load_global_config()
    matching_scope = find_matching_scope(repo_root, global_config)
    if matching_scope is None:
        sys.exit(0)

    # Step 2 — MCP detection
    if _detect_mcp(repo_root):
        sys.exit(0)

    # Step 3 — Output CLI reference
    print(_CLI_REFERENCE)
    sys.exit(0)
