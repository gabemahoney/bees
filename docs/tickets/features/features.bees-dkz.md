---
id: features.bees-dkz
type: subtask
title: Run unit tests and fix failures
description: "Context: After extracting hive operations to mcp_hive_ops.py, need to\
  \ ensure entire test suite passes.\n\nWhat to Do:\n- Run full test suite: poetry\
  \ run pytest\n- Fix any import errors or test failures\n- Ensure all hive operation\
  \ tests pass:\n  - test_colonize_hive.py\n  - test_mcp_rename_hive.py\n  - test_sanitize_hive.py\n\
  \  - test_mcp_hive_inference.py (if affected)\n  - Any other tests that use hive\
  \ operations\n- Fix any issues introduced by the module extraction\n- Ensure 100%\
  \ pass rate, even if you believe issues were pre-existing\n\nFiles: All test files,\
  \ particularly hive-related tests\n\nReference: Parent Task features.bees-2hp\n\n\
  Acceptance Criteria:\n- poetry run pytest passes with 0 failures\n- All hive operation\
  \ tests work correctly\n- No regressions from module extraction\n- Test suite is\
  \ green and stable"
parent: features.bees-2hp
up_dependencies:
- features.bees-ggr
status: open
created_at: '2026-02-03T17:03:35.212400'
updated_at: '2026-02-03T17:03:35.212403'
bees_version: '1.1'
---

Context: After extracting hive operations to mcp_hive_ops.py, need to ensure entire test suite passes.

What to Do:
- Run full test suite: poetry run pytest
- Fix any import errors or test failures
- Ensure all hive operation tests pass:
  - test_colonize_hive.py
  - test_mcp_rename_hive.py
  - test_sanitize_hive.py
  - test_mcp_hive_inference.py (if affected)
  - Any other tests that use hive operations
- Fix any issues introduced by the module extraction
- Ensure 100% pass rate, even if you believe issues were pre-existing

Files: All test files, particularly hive-related tests

Reference: Parent Task features.bees-2hp

Acceptance Criteria:
- poetry run pytest passes with 0 failures
- All hive operation tests work correctly
- No regressions from module extraction
- Test suite is green and stable
