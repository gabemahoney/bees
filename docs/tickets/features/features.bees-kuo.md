---
id: features.bees-kuo
type: subtask
title: Fix test_create_ticket_uses_context to pass string repo_root
description: '**Context**: The test test_create_ticket_uses_context (line 129) currently
  passes a Mock context object to _create_ticket(), but the function expects repo_root
  parameter to be a string path, not a Mock object.


  **Requirements**:

  - Update line 147-152 in tests/test_mcp_roots.py

  - Add `repo_root=str(test_repo)` parameter to the _create_ticket() call

  - This ensures the function receives a proper string path instead of Mock propagation


  **File**: tests/test_mcp_roots.py


  **Acceptance**: Test passes Mock context but explicit string repo_root parameter'
down_dependencies:
- features.bees-3sy
parent: features.bees-4ju
created_at: '2026-02-03T12:36:02.183266'
updated_at: '2026-02-03T12:45:12.505085'
status: completed
bees_version: '1.1'
---

**Context**: The test test_create_ticket_uses_context (line 129) currently passes a Mock context object to _create_ticket(), but the function expects repo_root parameter to be a string path, not a Mock object.

**Requirements**:
- Update line 147-152 in tests/test_mcp_roots.py
- Add `repo_root=str(test_repo)` parameter to the _create_ticket() call
- This ensures the function receives a proper string path instead of Mock propagation

**File**: tests/test_mcp_roots.py

**Acceptance**: Test passes Mock context but explicit string repo_root parameter
