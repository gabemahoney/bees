---
id: features.bees-ab2
type: subtask
title: Add unit tests for repo_context module
description: |
  Context: Verify repo_context.py works correctly with async code and proper error handling.

  What to Test:
  - Test get_repo_root() raises RuntimeError when context not set
  - Test set_repo_root() stores value correctly
  - Test get_repo_root() returns correct value after set
  - Test reset_repo_root() clears context
  - Test repo_root_context() manager sets and cleans up
  - Test repo_root_context() cleans up even if exception raised inside
  - Test concurrent async tasks with different repo_roots don't interfere

  Files: tests/test_repo_context.py (new)

  Success Criteria:
  - All test cases implemented
  - Tests verify error messages
  - Concurrent test proves async-safety
  - All tests pass
parent: features.bees-aa1
status: completed
created_at: '2026-02-04T19:15:01.000000'
updated_at: '2026-02-04T19:15:01.000000'
bees_version: '1.1'
---

Context: Verify repo_context.py works correctly with async code and proper error handling.

What to Test:
- Test get_repo_root() raises RuntimeError when context not set
- Test set_repo_root() stores value correctly
- Test get_repo_root() returns correct value after set
- Test reset_repo_root() clears context
- Test repo_root_context() manager sets and cleans up
- Test repo_root_context() cleans up even if exception raised inside
- Test concurrent async tasks with different repo_roots don't interfere

Files: tests/test_repo_context.py (new)

Success Criteria:
- All test cases implemented
- Tests verify error messages
- Concurrent test proves async-safety
- All tests pass
