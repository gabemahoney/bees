---
id: features.bees-ycr
type: task
title: Force reimport of dependent modules
description: 'Context: Python caches imported modules, so mocks applied after initial
  imports may not take effect. This causes intermittent test failures depending on
  import order.


  What Needs to Change:

  - Add module reload logic to conftest.py fixture/autouse fixture

  - Force reimport of modules that use `get_repo_root_from_path` after mock is established

  - Identify all modules that import this function and ensure they reload


  Why: Forcing reimports ensures the mocked version is used consistently across all
  tests regardless of import order.


  Success Criteria:

  - conftest.py contains module reload logic that runs before tests

  - Tests that import `get_repo_root_from_path` in new modules automatically use mocked
  version

  - No import order dependency issues in test suite


  Files: conftest.py

  Epic: features.bees-w0c'
down_dependencies:
- features.bees-tv7
parent: features.bees-w0c
children:
- features.bees-02n
- features.bees-wza
- features.bees-40m
- features.bees-r9t
- features.bees-47c
- features.bees-a2g
created_at: '2026-02-05T12:44:30.690635'
updated_at: '2026-02-05T12:45:47.964556'
priority: 0
status: open
bees_version: '1.1'
---

Context: Python caches imported modules, so mocks applied after initial imports may not take effect. This causes intermittent test failures depending on import order.

What Needs to Change:
- Add module reload logic to conftest.py fixture/autouse fixture
- Force reimport of modules that use `get_repo_root_from_path` after mock is established
- Identify all modules that import this function and ensure they reload

Why: Forcing reimports ensures the mocked version is used consistently across all tests regardless of import order.

Success Criteria:
- conftest.py contains module reload logic that runs before tests
- Tests that import `get_repo_root_from_path` in new modules automatically use mocked version
- No import order dependency issues in test suite

Files: conftest.py
Epic: features.bees-w0c
