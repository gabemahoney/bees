---
id: features.bees-xhi
type: task
title: Create test_mcp_server_lifecycle.py with server lifecycle tests
description: 'Context: Lifecycle tests cover server startup, shutdown, and tool registration
  - foundational functionality that should be isolated.


  What Needs to Change:

  - Create tests/test_mcp_server_lifecycle.py

  - Extract identified lifecycle tests from test_mcp_server.py

  - Ensure imports reference conftest.py fixtures (dependency Epic completed)

  - Target ~400 lines


  Why: Separates foundational server behavior from business logic tests.


  Success Criteria:

  - File exists with lifecycle tests only

  - `pytest tests/test_mcp_server_lifecycle.py` passes all tests

  - File size approximately 400 lines


  Files: tests/test_mcp_server_lifecycle.py, tests/test_mcp_server.py. Epic: features.bees-5y8'
up_dependencies:
- features.bees-4i1
down_dependencies:
- features.bees-xab
- features.bees-3jb
parent: features.bees-5y8
children:
- features.bees-vw7
- features.bees-jop
- features.bees-uxt
- features.bees-vii
- features.bees-q20
- features.bees-rfd
created_at: '2026-02-05T16:12:48.841335'
updated_at: '2026-02-05T16:30:29.836895'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Lifecycle tests cover server startup, shutdown, and tool registration - foundational functionality that should be isolated.

What Needs to Change:
- Create tests/test_mcp_server_lifecycle.py
- Extract identified lifecycle tests from test_mcp_server.py
- Ensure imports reference conftest.py fixtures (dependency Epic completed)
- Target ~400 lines

Why: Separates foundational server behavior from business logic tests.

Success Criteria:
- File exists with lifecycle tests only
- `pytest tests/test_mcp_server_lifecycle.py` passes all tests
- File size approximately 400 lines

Files: tests/test_mcp_server_lifecycle.py, tests/test_mcp_server.py. Epic: features.bees-5y8
