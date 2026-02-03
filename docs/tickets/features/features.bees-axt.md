---
id: features.bees-axt
type: subtask
title: Run unit tests and fix failures
description: 'Context: Verify extraction didn''t break existing functionality and
  new tests pass.


  What to Do:

  1. Run full test suite: poetry run pytest

  2. Verify all existing tests still pass (especially MCP server tests)

  3. Verify new mcp_hive_utils tests pass

  4. Fix any failures, even if they appear pre-existing

  5. Ensure 100% test pass rate


  Files: All test files


  Acceptance Criteria:

  - All tests pass

  - No regressions in existing functionality

  - New mcp_hive_utils tests all green

  - Test suite runs cleanly'
parent: features.bees-wvm
up_dependencies:
- features.bees-98n
status: open
created_at: '2026-02-03T17:03:44.744158'
updated_at: '2026-02-03T17:03:44.744161'
bees_version: '1.1'
---

Context: Verify extraction didn't break existing functionality and new tests pass.

What to Do:
1. Run full test suite: poetry run pytest
2. Verify all existing tests still pass (especially MCP server tests)
3. Verify new mcp_hive_utils tests pass
4. Fix any failures, even if they appear pre-existing
5. Ensure 100% test pass rate

Files: All test files

Acceptance Criteria:
- All tests pass
- No regressions in existing functionality
- New mcp_hive_utils tests all green
- Test suite runs cleanly
