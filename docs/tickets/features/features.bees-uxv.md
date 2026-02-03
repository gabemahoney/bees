---
id: features.bees-uxv
type: subtask
title: Run unit tests and fix failures
description: "Context: Execute the full test suite to verify the query operations\
  \ extraction didn't break any functionality.\n\nImplementation Steps:\n1. Run the\
  \ complete test suite: `poetry run pytest`\n2. Pay special attention to:\n   - Query-related\
  \ tests (test_query_tools.py, test_multi_hive_query.py)\n   - MCP server tests (test_mcp_server.py)\n\
  \   - Any tests that use query operations\n3. Fix any failures, even if they appear\
  \ pre-existing\n4. Ensure 100% test pass rate\n5. Check for import errors or circular\
  \ dependencies\n\nFiles Affected:\n- Any test files that fail\n- Source files if\
  \ bugs are discovered\n\nAcceptance Criteria:\n- All tests pass (100% success rate)\n\
  - No import errors or circular dependencies\n- Query operations work identically\
  \ to before refactoring\n- Test coverage maintained or improved\n\nParent Task:\
  \ features.bees-txe"
parent: features.bees-txe
up_dependencies:
- features.bees-7gj
status: open
created_at: '2026-02-03T17:03:40.739370'
updated_at: '2026-02-03T17:03:40.739376'
bees_version: '1.1'
---

Context: Execute the full test suite to verify the query operations extraction didn't break any functionality.

Implementation Steps:
1. Run the complete test suite: `poetry run pytest`
2. Pay special attention to:
   - Query-related tests (test_query_tools.py, test_multi_hive_query.py)
   - MCP server tests (test_mcp_server.py)
   - Any tests that use query operations
3. Fix any failures, even if they appear pre-existing
4. Ensure 100% test pass rate
5. Check for import errors or circular dependencies

Files Affected:
- Any test files that fail
- Source files if bugs are discovered

Acceptance Criteria:
- All tests pass (100% success rate)
- No import errors or circular dependencies
- Query operations work identically to before refactoring
- Test coverage maintained or improved

Parent Task: features.bees-txe
