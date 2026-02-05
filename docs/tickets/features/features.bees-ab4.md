---
id: features.bees-ab4
type: subtask
title: Create resolve_repo_root helper in mcp_repo_utils.py
description: |
  Context: MCP entry points need a helper that tries Roots protocol first, then falls back to explicit repo_root parameter.

  What to Implement:
  - Add to src/mcp_repo_utils.py
  - Function signature: `async def resolve_repo_root(ctx: Context, explicit_root: str | None) -> Path`
  - Logic:
    1. Try client_root = await get_client_repo_root(ctx)
    2. If client_root, verify it's a git repo and return it
    3. If explicit_root provided, convert to Path and return
    4. Otherwise raise error: "Your MCP client does not support the roots protocol. Please provide repo_root parameter."
  - Add type hints and docstring

  Files: src/mcp_repo_utils.py

  Success Criteria:
  - Function implemented with proper error handling
  - Tries Roots first, then explicit param
  - Returns Path object
  - Clear error message when neither available
parent: features.bees-aa2
status: completed
created_at: '2026-02-04T19:15:03.000000'
updated_at: '2026-02-04T19:15:03.000000'
bees_version: '1.1'
---

Context: MCP entry points need a helper that tries Roots protocol first, then falls back to explicit repo_root parameter.

What to Implement:
- Add to src/mcp_repo_utils.py
- Function signature: `async def resolve_repo_root(ctx: Context, explicit_root: str | None) -> Path`
- Logic:
  1. Try client_root = await get_client_repo_root(ctx)
  2. If client_root, verify it's a git repo and return it
  3. If explicit_root provided, convert to Path and return
  4. Otherwise raise error: "Your MCP client does not support the roots protocol. Please provide repo_root parameter."
- Add type hints and docstring

Files: src/mcp_repo_utils.py

Success Criteria:
- Function implemented with proper error handling
- Tries Roots first, then explicit param
- Returns Path object
- Clear error message when neither available
