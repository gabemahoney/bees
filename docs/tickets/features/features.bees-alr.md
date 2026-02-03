---
id: features.bees-alr
type: task
title: Extract repository root detection to mcp_repo_utils.py
description: 'Context: Repository root detection logic (finding git repos, MCP context
  handling) is currently embedded in mcp_server.py. This needs to be its own module
  as it''s used by most MCP operations.


  What Needs to Change:

  - Create new file src/mcp_repo_utils.py

  - Move `get_repo_root_from_path()` function (lines 124-159)

  - Move `get_client_repo_root()` function (lines 161-209) with all error handling
  and logging

  - Move `get_repo_root()` wrapper function (lines 211-253) with fallback logic

  - Update imports in src/mcp_server.py

  - Ensure logging configuration is available in new module


  Why: Repo root detection is fundamental to all MCP operations and should be isolated
  before extracting operation functions.


  Files: src/mcp_repo_utils.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_repo_utils.py exists with all three functions

  - Logging works correctly in extracted module

  - All MCP tools can still detect repo root

  - All existing tests pass

  - Module is ~150-200 lines


  Epic: features.bees-d6o'
down_dependencies:
- features.bees-t9t
- features.bees-jzd
- features.bees-2hp
- features.bees-txe
- features.bees-zy7
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-420
- features.bees-00q
- features.bees-x3x
- features.bees-sas
- features.bees-at0
- features.bees-ucu
created_at: '2026-02-03T17:00:59.340639'
updated_at: '2026-02-03T17:03:33.903354'
priority: 0
status: open
bees_version: '1.1'
---

Context: Repository root detection logic (finding git repos, MCP context handling) is currently embedded in mcp_server.py. This needs to be its own module as it's used by most MCP operations.

What Needs to Change:
- Create new file src/mcp_repo_utils.py
- Move `get_repo_root_from_path()` function (lines 124-159)
- Move `get_client_repo_root()` function (lines 161-209) with all error handling and logging
- Move `get_repo_root()` wrapper function (lines 211-253) with fallback logic
- Update imports in src/mcp_server.py
- Ensure logging configuration is available in new module

Why: Repo root detection is fundamental to all MCP operations and should be isolated before extracting operation functions.

Files: src/mcp_repo_utils.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_repo_utils.py exists with all three functions
- Logging works correctly in extracted module
- All MCP tools can still detect repo root
- All existing tests pass
- Module is ~150-200 lines

Epic: features.bees-d6o
