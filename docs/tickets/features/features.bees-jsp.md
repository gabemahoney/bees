---
id: features.bees-jsp
type: subtask
title: Add repo_root parameter to get_repo_root() helper function
description: '**Context**: Need to support MCP clients that don''t implement roots
  protocol by allowing direct repo_root parameter.


  **Requirements**:

  - Update get_repo_root() function in src/mcp_server.py to accept optional repo_root:
  str | None = None parameter

  - Logic: if repo_root is provided, return it; otherwise try ctx.roots protocol;
  if both fail, raise ValueError

  - Update docstring to explain the fallback pattern for clients without roots support

  - Error message should be helpful: "repo_root parameter required for clients that
  don''t support roots protocol"


  **Files**: src/mcp_server.py


  **Acceptance**: get_repo_root() accepts repo_root parameter and implements proper
  fallback logic with clear error handling'
down_dependencies:
- features.bees-h1s
- features.bees-cmd
- features.bees-0i0
parent: features.bees-lmo
created_at: '2026-02-03T06:41:22.882623'
updated_at: '2026-02-03T12:30:47.974554'
status: completed
bees_version: '1.1'
---

**Context**: Need to support MCP clients that don't implement roots protocol by allowing direct repo_root parameter.

**Requirements**:
- Update get_repo_root() function in src/mcp_server.py to accept optional repo_root: str | None = None parameter
- Logic: if repo_root is provided, return it; otherwise try ctx.roots protocol; if both fail, raise ValueError
- Update docstring to explain the fallback pattern for clients without roots support
- Error message should be helpful: "repo_root parameter required for clients that don't support roots protocol"

**Files**: src/mcp_server.py

**Acceptance**: get_repo_root() accepts repo_root parameter and implements proper fallback logic with clear error handling
