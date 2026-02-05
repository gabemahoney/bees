---
id: features.bees-u97
type: subtask
title: Migrate test_pipeline.py to use conftest.py fixtures
description: 'Remove local fixture definitions from tests/test_pipeline.py and update
  test signatures to use shared fixtures from conftest.py. Replace any local setup/teardown
  with appropriate shared fixtures. Verify tests pass after migration.


  **Context**: Part of Epic features.bees-74p to eliminate 500+ lines of duplicate
  fixture code.


  **Files**: tests/test_pipeline.py, tests/conftest.py


  **Acceptance**: tests/test_pipeline.py has no local fixture definitions, all tests
  use conftest.py fixtures, pytest tests/test_pipeline.py passes.'
parent: features.bees-4vi
created_at: '2026-02-05T12:05:38.275966'
updated_at: '2026-02-05T12:34:52.975385'
status: completed
bees_version: '1.1'
---

Remove local fixture definitions from tests/test_pipeline.py and update test signatures to use shared fixtures from conftest.py. Replace any local setup/teardown with appropriate shared fixtures. Verify tests pass after migration.

**Context**: Part of Epic features.bees-74p to eliminate 500+ lines of duplicate fixture code.

**Files**: tests/test_pipeline.py, tests/conftest.py

**Acceptance**: tests/test_pipeline.py has no local fixture definitions, all tests use conftest.py fixtures, pytest tests/test_pipeline.py passes.
