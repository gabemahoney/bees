---
id: features.bees-2z5
type: subtask
title: Add missing TestScanForHiveErrorPropagation to test_mcp_scan_validate.py
description: 'Add TestScanForHiveErrorPropagation class to test_mcp_scan_validate.py
  that was identified as missing during code review.


  Context: This test class should have been moved during the test file split but was
  skipped.


  Files to modify:

  - tests/test_mcp_scan_validate.py


  Steps:

  1. Find TestScanForHiveErrorPropagation in test_mcp_server.py

  2. Move class to test_mcp_scan_validate.py in appropriate location

  3. Ensure imports are correct

  4. Verify test runs successfully


  Acceptance:

  - TestScanForHiveErrorPropagation class exists in test_mcp_scan_validate.py

  - All tests in the class pass'
down_dependencies:
- features.bees-iji
parent: features.bees-o4v
created_at: '2026-02-05T16:39:32.953727'
updated_at: '2026-02-05T16:42:28.136416'
status: closed
bees_version: '1.1'
---

Add TestScanForHiveErrorPropagation class to test_mcp_scan_validate.py that was identified as missing during code review.

Context: This test class should have been moved during the test file split but was skipped.

Files to modify:
- tests/test_mcp_scan_validate.py

Steps:
1. Find TestScanForHiveErrorPropagation in test_mcp_server.py
2. Move class to test_mcp_scan_validate.py in appropriate location
3. Ensure imports are correct
4. Verify test runs successfully

Acceptance:
- TestScanForHiveErrorPropagation class exists in test_mcp_scan_validate.py
- All tests in the class pass
