---
id: features.bees-g99
type: subtask
title: Remove lifecycle tests from test_mcp_server.py
description: 'Context: Lifecycle tests have been moved to test_mcp_server_lifecycle.py
  and should be removed from the original file.


  What to Remove:

  - Identify all test functions related to server startup, shutdown, and tool registration

  - Remove these test functions and their helpers

  - Remove any imports used only by these tests


  Files: tests/test_mcp_server.py


  Acceptance: No lifecycle-related tests remain in test_mcp_server.py'
down_dependencies:
- features.bees-xz7
parent: features.bees-xab
created_at: '2026-02-05T16:13:46.037451'
updated_at: '2026-02-05T16:13:58.462290'
status: open
bees_version: '1.1'
---

Context: Lifecycle tests have been moved to test_mcp_server_lifecycle.py and should be removed from the original file.

What to Remove:
- Identify all test functions related to server startup, shutdown, and tool registration
- Remove these test functions and their helpers
- Remove any imports used only by these tests

Files: tests/test_mcp_server.py

Acceptance: No lifecycle-related tests remain in test_mcp_server.py
