---
id: features.bees-92k
type: subtask
title: Migrate test_paths.py to use conftest.py fixtures
description: 'Remove local fixture definitions from tests/test_paths.py and update
  test signatures to use shared fixtures from conftest.py. Replace any local setup/teardown
  with appropriate shared fixtures (mock_repo_root, hive_fixture, etc.). Verify tests
  pass after migration.


  **Context**: Part of Epic features.bees-74p to eliminate 500+ lines of duplicate
  fixture code.


  **Files**: tests/test_paths.py, tests/conftest.py


  **Acceptance**: tests/test_paths.py has no local fixture definitions, all tests
  use conftest.py fixtures, pytest tests/test_paths.py passes.'
down_dependencies:
- features.bees-f6z
- features.bees-037
- features.bees-2ws
parent: features.bees-4vi
created_at: '2026-02-05T12:05:33.748482'
updated_at: '2026-02-05T12:32:24.251489'
status: completed
bees_version: '1.1'
---

Remove local fixture definitions from tests/test_paths.py and update test signatures to use shared fixtures from conftest.py. Replace any local setup/teardown with appropriate shared fixtures (mock_repo_root, hive_fixture, etc.). Verify tests pass after migration.

**Context**: Part of Epic features.bees-74p to eliminate 500+ lines of duplicate fixture code.

**Files**: tests/test_paths.py, tests/conftest.py

**Acceptance**: tests/test_paths.py has no local fixture definitions, all tests use conftest.py fixtures, pytest tests/test_paths.py passes.
