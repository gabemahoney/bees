---
id: features.bees-wvm
type: task
title: Extract hive utilities to mcp_hive_utils.py
description: 'Context: Hive path validation and filesystem scanning logic is scattered
  in mcp_server.py. These utilities are needed by hive operations and should be extracted
  early.


  What Needs to Change:

  - Create new file src/mcp_hive_utils.py

  - Move `validate_hive_path()` function (lines 255-316) with all validation logic

  - Move `scan_for_hive()` function (lines 318-427) with filesystem traversal

  - Update imports in src/mcp_server.py

  - Import mcp_id_utils if needed for hive name parsing


  Why: Hive utilities are used by multiple hive operations and need to be available
  before extracting those operations.


  Files: src/mcp_hive_utils.py (new), src/mcp_server.py


  Success Criteria:

  - src/mcp_hive_utils.py exists with both functions

  - All hive path validation still works

  - Hive scanning from config fallback still works

  - All existing tests pass

  - Module is ~200-250 lines


  Epic: features.bees-d6o'
down_dependencies:
- features.bees-t9t
- features.bees-jzd
- features.bees-2hp
- features.bees-4u5
parent: features.bees-d6o
children:
- features.bees-hnv
- features.bees-b2i
- features.bees-4qm
- features.bees-2uq
- features.bees-98n
- features.bees-axt
created_at: '2026-02-03T17:01:02.328020'
updated_at: '2026-02-03T17:03:44.747324'
priority: 0
status: open
bees_version: '1.1'
---

Context: Hive path validation and filesystem scanning logic is scattered in mcp_server.py. These utilities are needed by hive operations and should be extracted early.

What Needs to Change:
- Create new file src/mcp_hive_utils.py
- Move `validate_hive_path()` function (lines 255-316) with all validation logic
- Move `scan_for_hive()` function (lines 318-427) with filesystem traversal
- Update imports in src/mcp_server.py
- Import mcp_id_utils if needed for hive name parsing

Why: Hive utilities are used by multiple hive operations and need to be available before extracting those operations.

Files: src/mcp_hive_utils.py (new), src/mcp_server.py

Success Criteria:
- src/mcp_hive_utils.py exists with both functions
- All hive path validation still works
- Hive scanning from config fallback still works
- All existing tests pass
- Module is ~200-250 lines

Epic: features.bees-d6o
