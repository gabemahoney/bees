---
id: features.bees-jop
type: subtask
title: Extract lifecycle tests from test_mcp_server.py
description: 'Context: Move server startup, shutdown, and tool registration tests
  from monolithic file to new lifecycle file


  What to Extract:

  - Identify all lifecycle-related tests in tests/test_mcp_server.py (server startup,
  shutdown, tool registration)

  - Move ~400 lines of lifecycle tests to test_mcp_server_lifecycle.py

  - Remove extracted tests from test_mcp_server.py

  - Preserve all test logic, fixtures, and assertions


  Files: tests/test_mcp_server_lifecycle.py, tests/test_mcp_server.py


  Acceptance: Lifecycle tests moved to new file, removed from old file, target ~400
  lines in new file'
parent: features.bees-xhi
up_dependencies:
- features.bees-vw7
status: open
created_at: '2026-02-05T16:13:46.597872'
updated_at: '2026-02-05T16:13:46.597876'
bees_version: '1.1'
---

Context: Move server startup, shutdown, and tool registration tests from monolithic file to new lifecycle file

What to Extract:
- Identify all lifecycle-related tests in tests/test_mcp_server.py (server startup, shutdown, tool registration)
- Move ~400 lines of lifecycle tests to test_mcp_server_lifecycle.py
- Remove extracted tests from test_mcp_server.py
- Preserve all test logic, fixtures, and assertions

Files: tests/test_mcp_server_lifecycle.py, tests/test_mcp_server.py

Acceptance: Lifecycle tests moved to new file, removed from old file, target ~400 lines in new file
