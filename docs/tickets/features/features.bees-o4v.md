---
id: features.bees-o4v
type: task
title: Complete extraction of scan/validate tests from test_mcp_server.py
description: 'Code review found that scan/validate tests were copied to test_mcp_scan_validate.py
  instead of moved - duplicates remain in test_mcp_server.py. Also missing 2 test
  classes.


  What Needs to Change:

  - Remove duplicate test classes from test_mcp_server.py (TestGetRepoRoot, TestValidateHivePath,
  TestScanForHive*)

  - Add missing TestScanForHiveErrorPropagation and TestScanForHiveConfigHandling
  to test_mcp_scan_validate.py

  - Verify no duplicate tests exist

  - Verify all tests pass


  Success Criteria:

  - Scan/validate test classes removed from test_mcp_server.py

  - All scan/validate test classes in test_mcp_scan_validate.py

  - All tests pass

  - No duplicate test execution'
labels:
- bug
up_dependencies:
- features.bees-82b
parent: features.bees-5y8
children:
- features.bees-oie
- features.bees-2z5
- features.bees-eun
- features.bees-u8x
- features.bees-iji
created_at: '2026-02-05T16:39:04.913112'
updated_at: '2026-02-05T16:43:50.897948'
priority: 1
status: closed
bees_version: '1.1'
---

Code review found that scan/validate tests were copied to test_mcp_scan_validate.py instead of moved - duplicates remain in test_mcp_server.py. Also missing 2 test classes.

What Needs to Change:
- Remove duplicate test classes from test_mcp_server.py (TestGetRepoRoot, TestValidateHivePath, TestScanForHive*)
- Add missing TestScanForHiveErrorPropagation and TestScanForHiveConfigHandling to test_mcp_scan_validate.py
- Verify no duplicate tests exist
- Verify all tests pass

Success Criteria:
- Scan/validate test classes removed from test_mcp_server.py
- All scan/validate test classes in test_mcp_scan_validate.py
- All tests pass
- No duplicate test execution
