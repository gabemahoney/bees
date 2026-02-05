---
id: features.bees-ab9
type: subtask
title: Add unit tests for MCP entry points context usage
description: |
  Context: Verify MCP entry points correctly set up context and handle both Roots and explicit param.

  What to Test:
  - Test entry point with Roots-supporting client (mock ctx.list_roots)
  - Test entry point with explicit repo_root param
  - Test entry point with neither (should raise error)
  - Test context is properly set for downstream calls
  - Test context cleanup after function completes

  Files: tests/test_mcp_entry_points.py (new or update existing)

  Success Criteria:
  - Tests cover both Roots and explicit param paths
  - Tests verify error when neither available
  - All tests pass
parent: features.bees-aa2
status: completed
created_at: '2026-02-04T19:15:08.000000'
updated_at: '2026-02-04T19:15:08.000000'
bees_version: '1.1'
---

Context: Verify MCP entry points correctly set up context and handle both Roots and explicit param.

What to Test:
- Test entry point with Roots-supporting client (mock ctx.list_roots)
- Test entry point with explicit repo_root param
- Test entry point with neither (should raise error)
- Test context is properly set for downstream calls
- Test context cleanup after function completes

Files: tests/test_mcp_entry_points.py (new or update existing)

Success Criteria:
- Tests cover both Roots and explicit param paths
- Tests verify error when neither available
- All tests pass
