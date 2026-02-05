---
id: features.bees-abt
type: subtask
title: Update existing tests to use repo_root_ctx fixture
description: |
  Context: Existing tests that directly call functions need to use context fixture.

  What to Change:
  - Scan all test files for tests that call functions requiring repo_root
  - Update test signatures to include `repo_root_ctx` fixture parameter
  - Remove any manual context setup in tests (use fixture instead)
  - Remove any explicit repo_root parameters from function calls (context provides it)

  Files: tests/*.py (all test files)

  Success Criteria:
  - Tests use repo_root_ctx fixture consistently
  - No tests manually set up context
  - No tests pass repo_root to functions
  - All tests still pass
parent: features.bees-aa7
status: completed
created_at: '2026-02-04T19:15:28.000000'
updated_at: '2026-02-04T19:15:28.000000'
bees_version: '1.1'
---

Context: Existing tests that directly call functions need to use context fixture.

What to Change:
- Scan all test files for tests that call functions requiring repo_root
- Update test signatures to include `repo_root_ctx` fixture parameter
- Remove any manual context setup in tests (use fixture instead)
- Remove any explicit repo_root parameters from function calls (context provides it)

Files: tests/*.py (all test files)

Success Criteria:
- Tests use repo_root_ctx fixture consistently
- No tests manually set up context
- No tests pass repo_root to functions
- All tests still pass
