---
id: features.bees-p9b
type: subtask
title: Run unit tests and fix failures
description: 'Context: After refactoring mcp_server.py, need to ensure all existing
  tests still pass.


  What to Do:

  - Run the full test suite with pytest

  - Fix any test failures caused by the refactoring

  - Verify no tests were broken by moving functions to new modules

  - Ensure 100% of tests pass, even if issues appear pre-existing

  - Check that test imports are updated if they directly imported from mcp_server.py


  Files: tests/, src/mcp_server.py, all extracted modules


  Acceptance: All unit tests pass. Any failures caused by refactoring are fixed.'
parent: features.bees-4u5
up_dependencies:
- features.bees-svd
status: open
created_at: '2026-02-03T17:03:50.902014'
updated_at: '2026-02-03T17:03:50.902018'
bees_version: '1.1'
---

Context: After refactoring mcp_server.py, need to ensure all existing tests still pass.

What to Do:
- Run the full test suite with pytest
- Fix any test failures caused by the refactoring
- Verify no tests were broken by moving functions to new modules
- Ensure 100% of tests pass, even if issues appear pre-existing
- Check that test imports are updated if they directly imported from mcp_server.py

Files: tests/, src/mcp_server.py, all extracted modules

Acceptance: All unit tests pass. Any failures caused by refactoring are fixed.
