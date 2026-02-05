---
id: features.bees-90j
type: subtask
title: Fix tests that depend on import order to work with module reloading
description: 'Context: Module reloading in conftest.py may cause tests that rely on
  specific import order to fail.


  Requirements:

  - Identify tests that break due to module reload logic

  - Refactor tests to be order-independent (use explicit imports, avoid global state)

  - Ensure tests work correctly after conftest.py forces module reimport

  - Document any import order assumptions that were removed


  Reference: Task features.bees-tv7

  Files: tests/**/*.py


  Acceptance:

  - No tests depend on import order

  - All tests work correctly with module reloading in conftest.py

  - Test code is more robust and maintainable'
down_dependencies:
- features.bees-o3k
parent: features.bees-tv7
created_at: '2026-02-05T12:46:11.936075'
updated_at: '2026-02-05T12:46:16.504459'
status: open
bees_version: '1.1'
---

Context: Module reloading in conftest.py may cause tests that rely on specific import order to fail.

Requirements:
- Identify tests that break due to module reload logic
- Refactor tests to be order-independent (use explicit imports, avoid global state)
- Ensure tests work correctly after conftest.py forces module reimport
- Document any import order assumptions that were removed

Reference: Task features.bees-tv7
Files: tests/**/*.py

Acceptance:
- No tests depend on import order
- All tests work correctly with module reloading in conftest.py
- Test code is more robust and maintainable
