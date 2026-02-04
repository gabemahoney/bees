---
id: features.bees-xaa
type: subtask
title: Run unit tests and fix failures
description: '**Context**: After modifying conftest.py patches and adding new tests,
  ensure full test suite passes.


  **Requirements**:

  - Run the complete test suite: `poetry run pytest`

  - Fix any failures that occur, whether in existing tests or new tests

  - Ensure 100% pass rate across all test files

  - Pay special attention to tests that depend on git repo mocking behavior

  - If failures appear pre-existing, still fix them to achieve 100% pass rate


  **Files**: All test files, especially those using mock_git_repo_check fixture


  **Parent Task**: features.bees-l4c


  **Acceptance**: All tests pass with 100% success rate. No test failures or errors
  remain.'
up_dependencies:
- features.bees-41y
parent: features.bees-l4c
created_at: '2026-02-03T19:27:30.289715'
updated_at: '2026-02-03T19:32:27.170372'
status: completed
bees_version: '1.1'
---

**Context**: After modifying conftest.py patches and adding new tests, ensure full test suite passes.

**Requirements**:
- Run the complete test suite: `poetry run pytest`
- Fix any failures that occur, whether in existing tests or new tests
- Ensure 100% pass rate across all test files
- Pay special attention to tests that depend on git repo mocking behavior
- If failures appear pre-existing, still fix them to achieve 100% pass rate

**Files**: All test files, especially those using mock_git_repo_check fixture

**Parent Task**: features.bees-l4c

**Acceptance**: All tests pass with 100% success rate. No test failures or errors remain.
