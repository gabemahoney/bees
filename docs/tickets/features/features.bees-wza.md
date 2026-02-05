---
id: features.bees-wza
type: subtask
title: Add module reload logic to conftest.py
description: 'Context: After mocking `get_repo_root_from_path`, need to force reimport
  of dependent modules so they use the mocked version.


  Requirements:

  - Add autouse fixture or modify existing fixture in conftest.py

  - Use importlib.reload() to force reimport of modules that use `get_repo_root_from_path`

  - Ensure reload runs after mock is established but before tests execute

  - Handle ImportError gracefully if modules not yet loaded


  Files: tests/conftest.py


  Acceptance:

  - conftest.py contains module reload logic

  - Reload happens after mock patching

  - Tests run without import order issues


  Reference: Task features.bees-ycr'
parent: features.bees-ycr
created_at: '2026-02-05T12:45:28.344918'
updated_at: '2026-02-05T15:45:44.182896'
status: cancelled
bees_version: '1.1'
---

Context: After mocking `get_repo_root_from_path`, need to force reimport of dependent modules so they use the mocked version.

Requirements:
- Add autouse fixture or modify existing fixture in conftest.py
- Use importlib.reload() to force reimport of modules that use `get_repo_root_from_path`
- Ensure reload runs after mock is established but before tests execute
- Handle ImportError gracefully if modules not yet loaded

Files: tests/conftest.py

Acceptance:
- conftest.py contains module reload logic
- Reload happens after mock patching
- Tests run without import order issues

Reference: Task features.bees-ycr
