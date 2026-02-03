---
id: features.bees-4u5
type: task
title: Refactor mcp_server.py to use extracted modules
description: 'Context: With all functions extracted, mcp_server.py needs to be refactored
  to import and use the new modules. The file should shrink from 3,222 lines to ~300-500
  lines.


  What Needs to Change:

  - Add imports for all 9 new modules at top of src/mcp_server.py

  - Remove all extracted function implementations

  - Keep only: FastMCP initialization, logging setup, server state, `start_server()`,
  `stop_server()`, `_health_check()`

  - Keep all `@mcp.tool()` decorators as thin wrappers that call functions from extracted
  modules

  - Verify no functions are left that should have been extracted

  - Verify all tool registrations still work


  Why: This completes the refactoring by making mcp_server.py a thin orchestration
  layer that registers tools and delegates to specialized modules.


  Files: src/mcp_server.py


  Success Criteria:

  - src/mcp_server.py is ~300-500 lines (down from 3,222)

  - All imports reference new modules

  - All @mcp.tool decorators still present

  - Server starts successfully

  - All tools are registered and callable

  - No circular import errors


  Epic: features.bees-d6o'
up_dependencies:
- features.bees-pt9
- features.bees-alr
- features.bees-wvm
- features.bees-t9t
- features.bees-jzd
- features.bees-2hp
- features.bees-txe
- features.bees-zy7
- features.bees-jlu
down_dependencies:
- features.bees-dkp
parent: features.bees-d6o
children:
- features.bees-b1s
- features.bees-5ob
- features.bees-1uj
- features.bees-ydt
- features.bees-svd
- features.bees-s5q
- features.bees-ruz
- features.bees-vx5
- features.bees-p9b
created_at: '2026-02-03T17:02:22.649132'
updated_at: '2026-02-03T17:03:50.905238'
priority: 0
status: open
bees_version: '1.1'
---

Context: With all functions extracted, mcp_server.py needs to be refactored to import and use the new modules. The file should shrink from 3,222 lines to ~300-500 lines.

What Needs to Change:
- Add imports for all 9 new modules at top of src/mcp_server.py
- Remove all extracted function implementations
- Keep only: FastMCP initialization, logging setup, server state, `start_server()`, `stop_server()`, `_health_check()`
- Keep all `@mcp.tool()` decorators as thin wrappers that call functions from extracted modules
- Verify no functions are left that should have been extracted
- Verify all tool registrations still work

Why: This completes the refactoring by making mcp_server.py a thin orchestration layer that registers tools and delegates to specialized modules.

Files: src/mcp_server.py

Success Criteria:
- src/mcp_server.py is ~300-500 lines (down from 3,222)
- All imports reference new modules
- All @mcp.tool decorators still present
- Server starts successfully
- All tools are registered and callable
- No circular import errors

Epic: features.bees-d6o
