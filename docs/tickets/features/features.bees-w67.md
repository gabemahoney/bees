---
id: features.bees-w67
type: subtask
title: Add repo_root parameter to _execute_query, _execute_freeform_query, _show_ticket
  functions
description: '**Context**: Part of Epic features.bees-h0a to support clients without
  roots protocol. These 3 query functions need repo_root fallback.


  **Requirements**:

  - Add optional repo_root: str | None = None parameter to _execute_query, _execute_freeform_query,
  _show_ticket in src/mcp_server.py

  - Pass repo_root to get_repo_root(ctx, repo_root=repo_root) calls

  - Update function docstrings to document the repo_root parameter and when to use
  it


  **Files**: src/mcp_server.py


  **Acceptance**: All 3 functions accept repo_root parameter and pass it through to
  get_repo_root()'
parent: features.bees-lmo
status: open
created_at: '2026-02-03T06:41:28.819199'
updated_at: '2026-02-03T06:41:28.819201'
bees_version: '1.1'
---

**Context**: Part of Epic features.bees-h0a to support clients without roots protocol. These 3 query functions need repo_root fallback.

**Requirements**:
- Add optional repo_root: str | None = None parameter to _execute_query, _execute_freeform_query, _show_ticket in src/mcp_server.py
- Pass repo_root to get_repo_root(ctx, repo_root=repo_root) calls
- Update function docstrings to document the repo_root parameter and when to use it

**Files**: src/mcp_server.py

**Acceptance**: All 3 functions accept repo_root parameter and pass it through to get_repo_root()
