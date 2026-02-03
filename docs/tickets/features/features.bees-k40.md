---
id: features.bees-k40
type: subtask
title: Add unit tests for get_client_repo_root None return behavior
description: "**Context:**\nAfter fixing test_get_client_repo_root_raises_on_empty_roots,\
  \ ensure comprehensive test coverage for the None return behavior of get_client_repo_root().\n\
  \n**Task:**\nReview test coverage in tests/test_mcp_roots.py for get_client_repo_root():\n\
  1. Verify existing tests cover:\n   - Valid roots returns Path (test_get_client_repo_root_with_valid_context\
  \ exists)\n   - Empty roots returns None (test_get_client_repo_root_returns_none_on_empty_roots\
  \ fixed)\n   - None roots returns None (may need to add)\n2. Add any missing edge\
  \ cases:\n   - Context with list_roots() returning None (not just empty list)\n\
  \   - Context with invalid/malformed root URIs\n\n**Acceptance:**\n- All None return\
  \ paths are tested\n- Edge cases covered\n- Tests pass"
up_dependencies:
- features.bees-8u7
down_dependencies:
- features.bees-mq4
parent: features.bees-o0l
created_at: '2026-02-03T12:36:25.006170'
updated_at: '2026-02-03T12:37:39.720684'
status: completed
bees_version: '1.1'
---

**Context:**
After fixing test_get_client_repo_root_raises_on_empty_roots, ensure comprehensive test coverage for the None return behavior of get_client_repo_root().

**Task:**
Review test coverage in tests/test_mcp_roots.py for get_client_repo_root():
1. Verify existing tests cover:
   - Valid roots returns Path (test_get_client_repo_root_with_valid_context exists)
   - Empty roots returns None (test_get_client_repo_root_returns_none_on_empty_roots fixed)
   - None roots returns None (may need to add)
2. Add any missing edge cases:
   - Context with list_roots() returning None (not just empty list)
   - Context with invalid/malformed root URIs

**Acceptance:**
- All None return paths are tested
- Edge cases covered
- Tests pass
