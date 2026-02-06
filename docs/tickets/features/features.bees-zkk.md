---
id: features.bees-zkk
type: subtask
title: Remove scan/validate tests from test_mcp_server.py
description: 'Context: Scan and validation tests have been moved to test_mcp_scan_validate.py
  and should be removed from the original file.


  What to Remove:

  - Identify all test functions related to scanning and validation

  - Remove these test functions and their helpers

  - Remove any imports used only by these tests


  Files: tests/test_mcp_server.py


  Acceptance: No scan/validate-related tests remain in test_mcp_server.py'
down_dependencies:
- features.bees-xz7
parent: features.bees-xab
created_at: '2026-02-05T16:13:48.149622'
updated_at: '2026-02-05T16:45:18.298774'
status: completed
bees_version: '1.1'
---

Context: Scan and validation tests have been moved to test_mcp_scan_validate.py and should be removed from the original file.

What to Remove:
- Identify all test functions related to scanning and validation
- Remove these test functions and their helpers
- Remove any imports used only by these tests

Files: tests/test_mcp_server.py

Acceptance: No scan/validate-related tests remain in test_mcp_server.py
