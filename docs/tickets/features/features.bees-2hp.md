---
id: features.bees-2hp
type: task
title: Extract hive lifecycle operations to mcp_hive_ops.py
description: 'Context: Hive operations (colonize, list, abandon, rename, sanitize)
  are complex lifecycle management functions that should be isolated.


  What Needs to Change:

  - Create new file src/mcp_hive_ops.py

  - Move `colonize_hive_core()` function (lines 429-687)

  - Move `_colonize_hive()` MCP wrapper (lines 2175-2260)

  - Move `_list_hives()` function (lines 2262-2349)

  - Move `_abandon_hive()` function (lines 2351-2436)

  - Move `_rename_hive()` function (lines 2438-2840)

  - Move `_sanitize_hive()` function (lines 2842-2990)

  - Import mcp_hive_utils for path validation and scanning

  - Import mcp_repo_utils for repo root detection

  - Update imports in src/mcp_server.py


  Why: Hive lifecycle is a major subsystem that''s easier to understand when isolated.
  These operations are complex and need their own focused module.


  Files: src/mcp_hive_ops.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_hive_ops.py exists with all 6 functions

  - All hive operations work correctly

  - Config registration/updates still work

  - All existing hive operation tests pass

  - Module is ~700-800 lines


  Epic: features.bees-d6o'
up_dependencies:
- features.bees-pt9
- features.bees-alr
- features.bees-wvm
down_dependencies:
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-8jm
- features.bees-ggr
- features.bees-lhh
- features.bees-zxe
- features.bees-o5g
- features.bees-dkz
created_at: '2026-02-03T17:02:04.054871'
updated_at: '2026-02-03T17:03:35.215225'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Hive operations (colonize, list, abandon, rename, sanitize) are complex lifecycle management functions that should be isolated.

What Needs to Change:
- Create new file src/mcp_hive_ops.py
- Move `colonize_hive_core()` function (lines 429-687)
- Move `_colonize_hive()` MCP wrapper (lines 2175-2260)
- Move `_list_hives()` function (lines 2262-2349)
- Move `_abandon_hive()` function (lines 2351-2436)
- Move `_rename_hive()` function (lines 2438-2840)
- Move `_sanitize_hive()` function (lines 2842-2990)
- Import mcp_hive_utils for path validation and scanning
- Import mcp_repo_utils for repo root detection
- Update imports in src/mcp_server.py

Why: Hive lifecycle is a major subsystem that's easier to understand when isolated. These operations are complex and need their own focused module.

Files: src/mcp_hive_ops.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_hive_ops.py exists with all 6 functions
- All hive operations work correctly
- Config registration/updates still work
- All existing hive operation tests pass
- Module is ~700-800 lines

Epic: features.bees-d6o
