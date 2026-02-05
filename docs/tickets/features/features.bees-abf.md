---
id: features.bees-abf
type: subtask
title: Add unit tests for paths.py refactor
description: |
  Context: Verify paths.py functions work correctly with context.

  What to Test:
  - Test get_ticket_path resolves paths correctly
  - Test infer_ticket_type_from_id identifies types correctly
  - Test list_tickets finds all tickets
  - Test functions raise error when context not set
  - Test functions work when context is set

  Files: tests/test_paths.py (update existing)

  Success Criteria:
  - Tests verify context requirement
  - Tests verify path operations work correctly
  - All tests pass
parent: features.bees-aa4
status: completed
created_at: '2026-02-04T19:15:14.000000'
updated_at: '2026-02-04T19:15:14.000000'
bees_version: '1.1'
---

Context: Verify paths.py functions work correctly with context.

What to Test:
- Test get_ticket_path resolves paths correctly
- Test infer_ticket_type_from_id identifies types correctly
- Test list_tickets finds all tickets
- Test functions raise error when context not set
- Test functions work when context is set

Files: tests/test_paths.py (update existing)

Success Criteria:
- Tests verify context requirement
- Tests verify path operations work correctly
- All tests pass
