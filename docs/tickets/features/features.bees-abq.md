---
id: features.bees-abq
type: subtask
title: Add unit tests for utility files refactor
description: |
  Context: Verify all refactored utility files work correctly with context.

  What to Test:
  - Test writer.py write_ticket_file works correctly
  - Test id_utils.py extract_existing_ids_from_all_hives works correctly
  - Test index_generator.py functions work correctly
  - Test hive_utils.py functions work correctly
  - Test watcher.py start_watcher works correctly
  - Test mcp_hive_utils.py validate_hive_path works correctly
  - Test all functions raise error when context not set

  Files: tests/test_writer.py, tests/test_id_utils.py, tests/test_index_generator.py, tests/test_hive_utils.py, tests/test_watcher.py, tests/test_mcp_hive_utils.py (update existing or create new)

  Success Criteria:
  - Tests verify context requirement
  - Tests verify all operations work correctly
  - All tests pass
parent: features.bees-aa6
status: completed
created_at: '2026-02-04T19:15:25.000000'
updated_at: '2026-02-05T00:00:00.000000'
bees_version: '1.1'
---

Context: Verify all refactored utility files work correctly with context.

What to Test:
- Test writer.py write_ticket_file works correctly
- Test id_utils.py extract_existing_ids_from_all_hives works correctly
- Test index_generator.py functions work correctly
- Test hive_utils.py functions work correctly
- Test watcher.py start_watcher works correctly
- Test mcp_hive_utils.py validate_hive_path works correctly
- Test all functions raise error when context not set

Files: tests/test_writer.py, tests/test_id_utils.py, tests/test_index_generator.py, tests/test_hive_utils.py, tests/test_watcher.py, tests/test_mcp_hive_utils.py (update existing or create new)

Success Criteria:
- Tests verify context requirement
- Tests verify all operations work correctly
- All tests pass
