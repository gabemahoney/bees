---
id: features.bees-4ib
type: subtask
title: Run unit tests and fix failures
description: 'Context: Validate that index generation extraction doesn''t break existing
  functionality.


  What to Run:

  - Execute full test suite: poetry run pytest

  - Focus on index-related tests

  - Focus on mcp_server integration tests

  - Check for import errors or missing modules


  What to Fix:

  - Any test failures related to index generation

  - Import errors from module extraction

  - Mock/patch updates needed for new module structure

  - Integration issues between mcp_server and mcp_index_ops


  Files: All test files, src/mcp_index_ops.py, src/mcp_server.py


  Acceptance:

  - All tests pass (100% pass rate)

  - No import errors

  - No regression in existing index functionality

  - Index generation works for per-hive and all-hive modes'
parent: features.bees-zy7
up_dependencies:
- features.bees-fe7
status: completed
created_at: '2026-02-03T17:03:45.443570'
updated_at: '2026-02-03T17:03:45.443573'
bees_version: '1.1'
---

Context: Validate that index generation extraction doesn't break existing functionality.

What to Run:
- Execute full test suite: poetry run pytest
- Focus on index-related tests
- Focus on mcp_server integration tests
- Check for import errors or missing modules

What to Fix:
- Any test failures related to index generation
- Import errors from module extraction
- Mock/patch updates needed for new module structure
- Integration issues between mcp_server and mcp_index_ops

Files: All test files, src/mcp_index_ops.py, src/mcp_server.py

Acceptance:
- All tests pass (100% pass rate)
- No import errors
- No regression in existing index functionality
- Index generation works for per-hive and all-hive modes
