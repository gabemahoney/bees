---
id: features.bees-oie
type: subtask
title: Remove duplicate scan/validate test classes from test_mcp_server.py
description: 'Remove TestGetRepoRoot, TestValidateHivePath, and TestScanForHive* classes
  that were copied to test_mcp_scan_validate.py but not removed from test_mcp_server.py.


  Context: These classes were duplicated during the test file split (Task features.bees-82b)


  Files to modify:

  - tests/test_mcp_server.py


  Steps:

  1. Identify all scan/validate test classes in test_mcp_server.py

  2. Verify they exist in test_mcp_scan_validate.py

  3. Remove duplicate classes from test_mcp_server.py

  4. Ensure imports are cleaned up


  Acceptance:

  - No TestGetRepoRoot, TestValidateHivePath, TestScanForHive* classes in test_mcp_server.py

  - File length reduced by ~300 lines'
down_dependencies:
- features.bees-iji
parent: features.bees-o4v
created_at: '2026-02-05T16:39:29.060125'
updated_at: '2026-02-05T16:42:27.430489'
status: closed
bees_version: '1.1'
---

Remove TestGetRepoRoot, TestValidateHivePath, and TestScanForHive* classes that were copied to test_mcp_scan_validate.py but not removed from test_mcp_server.py.

Context: These classes were duplicated during the test file split (Task features.bees-82b)

Files to modify:
- tests/test_mcp_server.py

Steps:
1. Identify all scan/validate test classes in test_mcp_server.py
2. Verify they exist in test_mcp_scan_validate.py
3. Remove duplicate classes from test_mcp_server.py
4. Ensure imports are cleaned up

Acceptance:
- No TestGetRepoRoot, TestValidateHivePath, TestScanForHive* classes in test_mcp_server.py
- File length reduced by ~300 lines
