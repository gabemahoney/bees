---
id: features.bees-0i0
type: subtask
title: Add unit tests for repo_root parameter fallback
description: '**Context**: Need to test the repo_root parameter fallback logic across
  all 11 MCP tool functions.


  **Requirements**:

  - Test get_repo_root() with repo_root provided (should return it)

  - Test get_repo_root() without repo_root but with roots support (should use roots)

  - Test get_repo_root() with both None (should raise ValueError with helpful message)

  - Test at least 2-3 representative MCP tools (_create_ticket, _colonize_hive, _execute_query)
  passing repo_root through

  - Test error handling when both fallbacks fail


  **Files**: tests/test_mcp_server.py (or appropriate test file)


  **Acceptance**: Tests cover all three fallback scenarios and verify proper error
  messages'
parent: features.bees-lmo
up_dependencies:
- features.bees-jsp
status: open
created_at: '2026-02-03T06:41:47.298529'
updated_at: '2026-02-03T06:41:47.298537'
bees_version: '1.1'
---

**Context**: Need to test the repo_root parameter fallback logic across all 11 MCP tool functions.

**Requirements**:
- Test get_repo_root() with repo_root provided (should return it)
- Test get_repo_root() without repo_root but with roots support (should use roots)
- Test get_repo_root() with both None (should raise ValueError with helpful message)
- Test at least 2-3 representative MCP tools (_create_ticket, _colonize_hive, _execute_query) passing repo_root through
- Test error handling when both fallbacks fail

**Files**: tests/test_mcp_server.py (or appropriate test file)

**Acceptance**: Tests cover all three fallback scenarios and verify proper error messages
