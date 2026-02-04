---
id: features.bees-ucu
type: subtask
title: Run unit tests and fix failures
description: "Context: Execute full test suite to verify mcp_repo_utils extraction\
  \ doesn't break existing functionality.\n\nWhat to Do:\n- Run: poetry run pytest\n\
  - Verify all tests pass (especially MCP-related tests)\n- If failures occur, debug\
  \ and fix them\n- Pay special attention to:\n  - tests/test_mcp_server.py (uses\
  \ repo root functions)\n  - tests/test_mcp_*.py files\n  - Any tests using repository\
  \ detection\n- Ensure 100% pass rate\n\nRequirements:\n- All existing tests must\
  \ pass\n- New mcp_repo_utils tests must pass\n- No regressions from extraction\n\
  - Fix any import errors or broken references\n\nParent Task: features.bees-alr\n\
  Blocked By: features.bees-at0 (add unit tests)\n\nSuccess Criteria:\n- pytest exits\
  \ with 0 (all tests pass)\n- No import errors\n- No broken MCP tool functionality\n\
  - Test output shows 100% pass rate"
up_dependencies:
- features.bees-at0
parent: features.bees-alr
created_at: '2026-02-03T17:03:33.899781'
updated_at: '2026-02-03T19:23:37.189153'
status: completed
bees_version: '1.1'
---

Context: Execute full test suite to verify mcp_repo_utils extraction doesn't break existing functionality.

What to Do:
- Run: poetry run pytest
- Verify all tests pass (especially MCP-related tests)
- If failures occur, debug and fix them
- Pay special attention to:
  - tests/test_mcp_server.py (uses repo root functions)
  - tests/test_mcp_*.py files
  - Any tests using repository detection
- Ensure 100% pass rate

Requirements:
- All existing tests must pass
- New mcp_repo_utils tests must pass
- No regressions from extraction
- Fix any import errors or broken references

Parent Task: features.bees-alr
Blocked By: features.bees-at0 (add unit tests)

Success Criteria:
- pytest exits with 0 (all tests pass)
- No import errors
- No broken MCP tool functionality
- Test output shows 100% pass rate
