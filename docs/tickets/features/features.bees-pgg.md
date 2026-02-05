---
id: features.bees-pgg
type: task
title: Fix MCP roots protocol error handling for non-supporting clients
description: |
  Fix get_client_repo_root() to properly handle clients that don't support roots protocol.
  
  **Problem:**
  When ctx.list_roots() is called on clients that don't support the roots protocol,
  it raises McpError (from mcp.shared.exceptions), but the code only catches
  NotFoundError (from fastmcp.exceptions). This causes the error to bubble up
  instead of gracefully falling back to the explicit repo_root parameter.
  
  **Evidence from logs:**
  ```
  src.mcp_repo_utils - ERROR - Unexpected error in get_client_repo_root: McpError: Method not found
  src.mcp_hive_ops - ERROR - Failed to list hives: Method not found
  ```
  
  **Root cause:**
  - Line 100 in src/mcp_repo_utils.py only catches NotFoundError
  - McpError is NOT caught, so it goes to line 105's generic Exception handler
  - Line 108 re-raises the exception instead of returning None
  - This prevents the fallback to explicit repo_root parameter
  
  **The fix:**
  1. Import McpError from mcp.shared.exceptions (in addition to NotFoundError)
  2. Catch both exception types at line 100:
     ```python
     except (NotFoundError, McpError) as e:
     ```
  3. Return None to signal roots protocol is unavailable
  4. This allows resolve_repo_root() to use the explicit repo_root parameter fallback
  
  **Success criteria:**
  - Clients without roots protocol support can use explicit repo_root parameter
  - list_hives and other MCP tools work on clients without roots support
  - Error message is logged at INFO level, not ERROR
  - No exception is raised, graceful fallback occurs
  
  **Files to modify:**
  - src/mcp_repo_utils.py (line 12: add import, line 100: catch both exceptions)
parent: features.bees-nho
status: closed
priority: 1
labels: ["bug", "mcp"]
created_at: '2026-02-05T06:50:00.000000'
updated_at: '2026-02-05T08:00:00.000000'
bees_version: '1.1'
---

Fix exception handling for clients that don't support MCP roots protocol.
