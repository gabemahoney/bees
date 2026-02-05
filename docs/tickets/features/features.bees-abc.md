---
id: features.bees-abc
type: subtask
title: Add unit tests for config.py refactor
description: |
  Context: Verify config.py functions work correctly with context instead of explicit params.

  What to Test:
  - Test each config function works when context is set
  - Test functions raise error when context not set
  - Test config functions can call each other without passing repo_root
  - Test config file read/write operations still work

  Files: tests/test_config.py (update existing)

  Success Criteria:
  - Tests verify context requirement
  - Tests verify functions work correctly
  - All tests pass
parent: features.bees-aa3
status: completed
created_at: '2026-02-04T19:15:11.000000'
updated_at: '2026-02-04T19:15:11.000000'
bees_version: '1.1'
---

Context: Verify config.py functions work correctly with context instead of explicit params.

What to Test:
- Test each config function works when context is set
- Test functions raise error when context not set
- Test config functions can call each other without passing repo_root
- Test config file read/write operations still work

Files: tests/test_config.py (update existing)

Success Criteria:
- Tests verify context requirement
- Tests verify functions work correctly
- All tests pass
