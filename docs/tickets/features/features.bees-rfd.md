---
id: features.bees-rfd
type: subtask
title: Run unit tests and fix failures
description: 'Context: Ensure test extraction didn''t break anything and all tests
  pass


  What to Execute:

  - Run pytest tests/test_mcp_server_lifecycle.py

  - Run pytest tests/test_mcp_server.py (verify extraction didn''t break remaining
  tests)

  - Fix any test failures

  - Ensure 100% pass rate for all tests

  - Verify file size is approximately 400 lines


  Files: tests/test_mcp_server_lifecycle.py, tests/test_mcp_server.py


  Acceptance: All tests pass, no failures, lifecycle file is ~400 lines'
parent: features.bees-xhi
up_dependencies:
- features.bees-q20
status: open
created_at: '2026-02-05T16:14:08.142246'
updated_at: '2026-02-05T16:14:08.142256'
bees_version: '1.1'
---

Context: Ensure test extraction didn't break anything and all tests pass

What to Execute:
- Run pytest tests/test_mcp_server_lifecycle.py
- Run pytest tests/test_mcp_server.py (verify extraction didn't break remaining tests)
- Fix any test failures
- Ensure 100% pass rate for all tests
- Verify file size is approximately 400 lines

Files: tests/test_mcp_server_lifecycle.py, tests/test_mcp_server.py

Acceptance: All tests pass, no failures, lifecycle file is ~400 lines
