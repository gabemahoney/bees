---
id: features.bees-7gj
type: subtask
title: Update mcp_server.py to import and use mcp_query_ops functions
description: "Context: After extracting query operations to mcp_query_ops.py, update\
  \ the main server file to use the extracted functions.\n\nImplementation Steps:\n\
  1. Add import statement at top of src/mcp_server.py:\n   ```python\n   from mcp_query_ops\
  \ import _add_named_query, _execute_query, _execute_freeform_query\n   ```\n2. Remove\
  \ the function implementations (lines 1760-1999)\n3. Keep the @mcp.tool() decorators\
  \ as thin wrappers that call the imported functions\n4. Verify no duplicate function\
  \ definitions remain\n5. Ensure all tool registrations still work correctly\n\n\
  Files Affected:\n- src/mcp_server.py\n\nAcceptance Criteria:\n- Import statement\
  \ added correctly\n- Function implementations removed (keep only decorators)\n-\
  \ Tool decorators call imported functions\n- No duplicate definitions\n- Server\
  \ still initializes correctly\n\nParent Task: features.bees-txe"
down_dependencies:
- features.bees-uxv
parent: features.bees-txe
created_at: '2026-02-03T17:03:17.640403'
updated_at: '2026-02-03T17:03:40.745942'
status: closed
bees_version: '1.1'
---

Context: After extracting query operations to mcp_query_ops.py, update the main server file to use the extracted functions.

Implementation Steps:
1. Add import statement at top of src/mcp_server.py:
   ```python
   from mcp_query_ops import _add_named_query, _execute_query, _execute_freeform_query
   ```
2. Remove the function implementations (lines 1760-1999)
3. Keep the @mcp.tool() decorators as thin wrappers that call the imported functions
4. Verify no duplicate function definitions remain
5. Ensure all tool registrations still work correctly

Files Affected:
- src/mcp_server.py

Acceptance Criteria:
- Import statement added correctly
- Function implementations removed (keep only decorators)
- Tool decorators call imported functions
- No duplicate definitions
- Server still initializes correctly

Parent Task: features.bees-txe
