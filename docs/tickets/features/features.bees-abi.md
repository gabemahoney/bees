---
id: features.bees-abi
type: subtask
title: Add unit tests for ticket_factory.py refactor
description: |
  Context: Verify ticket creation functions work correctly with context.

  What to Test:
  - Test create_epic creates tickets correctly
  - Test create_task creates tickets correctly
  - Test create_subtask creates tickets correctly
  - Test functions raise error when context not set
  - Test created tickets have correct IDs and paths
  - Test ticket files written to correct locations

  Files: tests/test_ticket_factory.py (update existing)

  Success Criteria:
  - Tests verify context requirement
  - Tests verify ticket creation works correctly
  - All tests pass
parent: features.bees-aa5
status: completed
created_at: '2026-02-04T19:15:17.000000'
updated_at: '2026-02-04T19:15:17.000000'
bees_version: '1.1'
---

Context: Verify ticket creation functions work correctly with context.

What to Test:
- Test create_epic creates tickets correctly
- Test create_task creates tickets correctly
- Test create_subtask creates tickets correctly
- Test functions raise error when context not set
- Test created tickets have correct IDs and paths
- Test ticket files written to correct locations

Files: tests/test_ticket_factory.py (update existing)

Success Criteria:
- Tests verify context requirement
- Tests verify ticket creation works correctly
- All tests pass
