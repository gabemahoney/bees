---
id: features.bees-g8v
type: task
title: Clients that support Roots are getting incorrect "repo_root required" error
description: 'Bug: Clients that DO support the Roots protocol (such as Claude Code)
  are incorrectly getting the error: "repo_root is required. Your MCP client does
  not support the roots protocol."


  **Expected behavior:**

  - If client supports Roots protocol, automatically fetch repo_root via ctx.list_roots()

  - Only show "repo_root required" error for clients that DON''T support Roots

  - Claude Code supports Roots, so it should work without errors


  **Actual behavior:**

  - Even with Roots-supporting clients like Claude Code, the error is thrown

  - get_repo_root(ctx) returns None even though client supports roots


  **Root cause hypothesis:**

  mcp_repo_utils.py:97-101 catches ALL exceptions with bare except and returns None.
  This silently swallows any error from ctx.list_roots(), making it appear that roots
  isn''t supported even when it is. Should only catch the specific "method not found"
  exception (-32601).


  **Files:**

  - src/mcp_repo_utils.py (get_client_repo_root function)

  - src/mcp_ticket_ops.py (error handling in _create_ticket)'
parent: features.bees-h0a
created_at: '2026-02-04T16:23:45.000000+00:00'
updated_at: '2026-02-04T16:23:45.000000+00:00'
status: completed
bees_version: '1.1'
---

Bug: Clients that DO support the Roots protocol (such as Claude Code) are incorrectly getting the error: "repo_root is required. Your MCP client does not support the roots protocol."

**Expected behavior:**
- If client supports Roots protocol, automatically fetch repo_root via ctx.list_roots()
- Only show "repo_root required" error for clients that DON'T support Roots
- Claude Code supports Roots, so it should work without errors

**Actual behavior:**
- Even with Roots-supporting clients like Claude Code, the error is thrown
- get_repo_root(ctx) returns None even though client supports roots

**Root cause hypothesis:**
mcp_repo_utils.py:97-101 catches ALL exceptions with bare except and returns None. This silently swallows any error from ctx.list_roots(), making it appear that roots isn't supported even when it is. Should only catch the specific "method not found" exception (-32601).

**Files:**
- src/mcp_repo_utils.py (get_client_repo_root function)
- src/mcp_ticket_ops.py (error handling in _create_ticket)
