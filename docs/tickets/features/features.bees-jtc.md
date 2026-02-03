---
id: features.bees-jtc
type: subtask
title: Fix test_list_hives_uses_context to pass string repo_root
description: '**Context**: The test test_list_hives_uses_context (line 105) currently
  passes a Mock context object to _list_hives(), but the function expects repo_root
  parameter to be a string path, not a Mock object.


  **Requirements**:

  - Update line 122 in tests/test_mcp_roots.py

  - Change from: `result = await _list_hives(ctx)`

  - Change to: `result = await _list_hives(ctx, repo_root=str(test_repo))`

  - This ensures the function receives a proper string path instead of Mock propagation


  **File**: tests/test_mcp_roots.py


  **Acceptance**: Test passes Mock context but explicit string repo_root parameter'
down_dependencies:
- features.bees-3sy
parent: features.bees-4ju
created_at: '2026-02-03T12:35:57.789028'
updated_at: '2026-02-03T12:45:04.778183'
status: completed
bees_version: '1.1'
---

**Context**: The test test_list_hives_uses_context (line 105) currently passes a Mock context object to _list_hives(), but the function expects repo_root parameter to be a string path, not a Mock object.

**Requirements**:
- Update line 122 in tests/test_mcp_roots.py
- Change from: `result = await _list_hives(ctx)`
- Change to: `result = await _list_hives(ctx, repo_root=str(test_repo))`
- This ensures the function receives a proper string path instead of Mock propagation

**File**: tests/test_mcp_roots.py

**Acceptance**: Test passes Mock context but explicit string repo_root parameter
