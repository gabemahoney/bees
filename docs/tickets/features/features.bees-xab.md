---
id: features.bees-xab
type: task
title: Remove extracted tests from test_mcp_server.py
description: 'Context: After creating new test files, remove duplicated tests from
  the original file.


  What Needs to Change:

  - Remove lifecycle tests (now in test_mcp_server_lifecycle.py)

  - Remove scan/validate tests (now in test_mcp_scan_validate.py)

  - Keep remaining tool tests (~1,600 lines)

  - Verify no orphaned imports or helper functions


  Why: Completes the file split and prevents duplicate test execution.


  Success Criteria:

  - test_mcp_server.py contains only remaining tool tests

  - `pytest tests/test_mcp_server.py` passes all tests

  - File size approximately 1,600 lines or less


  Files: tests/test_mcp_server.py. Epic: features.bees-5y8'
up_dependencies:
- features.bees-xhi
- features.bees-82b
down_dependencies:
- features.bees-se5
parent: features.bees-5y8
children:
- features.bees-g99
- features.bees-zkk
- features.bees-nj5
- features.bees-xz7
- features.bees-11n
created_at: '2026-02-05T16:12:54.061930'
updated_at: '2026-02-05T16:46:53.887821'
priority: 0
status: completed
bees_version: '1.1'
---

Context: After creating new test files, remove duplicated tests from the original file.

What Needs to Change:
- Remove lifecycle tests (now in test_mcp_server_lifecycle.py)
- Remove scan/validate tests (now in test_mcp_scan_validate.py)
- Keep remaining tool tests (~1,600 lines)
- Verify no orphaned imports or helper functions

Why: Completes the file split and prevents duplicate test execution.

Success Criteria:
- test_mcp_server.py contains only remaining tool tests
- `pytest tests/test_mcp_server.py` passes all tests
- File size approximately 1,600 lines or less

Files: tests/test_mcp_server.py. Epic: features.bees-5y8
