---
id: features.bees-aa7
type: task
title: Update test suite for context usage
description: |
  Context: Tests call functions directly and need repo_root context set up. Need to verify the refactor works and that concurrent requests with different repos work correctly.

  What Needs to Change:
  - Wrap test function calls in `with repo_root_context(test_path):` blocks
  - Or create pytest fixtures that automatically set up context
  - Add test for concurrent requests with different repos:
    - Create multiple async tasks
    - Each task uses different repo_root via context
    - Verify contexts don't interfere with each other
  - Update any tests that explicitly pass repo_root parameter to functions

  Why: Ensure tests work with new context-based approach. Verify thread-safety and that concurrent requests work correctly. This is critical for production use.

  Files: tests/ (all test files)

  Note: See parent Epic features.bees-nho for detailed implementation patterns and code examples.

  Success Criteria:
  - All existing tests pass
  - New concurrent context test added and passing
  - Test fixtures or context wrappers properly set repo_root
  - No test failures due to missing context
  - Concurrent requests with different repos work correctly
parent: features.bees-nho
children: ["features.bees-abs", "features.bees-abt", "features.bees-abu", "features.bees-abv"]
status: completed
priority: 0
up_dependencies: ["features.bees-aa3", "features.bees-aa4", "features.bees-aa5", "features.bees-aa6"]
created_at: '2026-02-04T19:00:06.000000'
updated_at: '2026-02-04T19:00:06.000000'
bees_version: '1.1'
---

Context: Tests call functions directly and need repo_root context set up. Need to verify the refactor works and that concurrent requests with different repos work correctly.

What Needs to Change:
- Wrap test function calls in `with repo_root_context(test_path):` blocks
- Or create pytest fixtures that automatically set up context
- Add test for concurrent requests with different repos:
  - Create multiple async tasks
  - Each task uses different repo_root via context
  - Verify contexts don't interfere with each other
- Update any tests that explicitly pass repo_root parameter to functions

Why: Ensure tests work with new context-based approach. Verify thread-safety and that concurrent requests work correctly. This is critical for production use.

Files: tests/ (all test files)

Success Criteria:
- All existing tests pass
- New concurrent context test added and passing
- Test fixtures or context wrappers properly set repo_root
- No test failures due to missing context
- Concurrent requests with different repos work correctly
