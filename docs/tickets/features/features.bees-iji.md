---
id: features.bees-iji
type: subtask
title: Run unit tests and fix failures
description: 'Execute full test suite to verify all scan/validate tests pass in their
  new location and no tests were broken during cleanup.


  Context: Final verification that the test extraction is complete and working.


  Steps:

  1. Run pytest tests/test_mcp_server.py

  2. Run pytest tests/test_mcp_scan_validate.py

  3. Run full test suite: pytest tests/

  4. Fix any failures found

  5. Ensure 100% pass rate


  Acceptance:

  - All tests in test_mcp_server.py pass

  - All tests in test_mcp_scan_validate.py pass

  - Full test suite passes with no errors

  - No duplicate test execution warnings'
up_dependencies:
- features.bees-oie
- features.bees-2z5
- features.bees-eun
- features.bees-u8x
parent: features.bees-o4v
created_at: '2026-02-05T16:39:46.548673'
updated_at: '2026-02-05T16:43:50.266858'
status: closed
bees_version: '1.1'
---

Execute full test suite to verify all scan/validate tests pass in their new location and no tests were broken during cleanup.

Context: Final verification that the test extraction is complete and working.

Steps:
1. Run pytest tests/test_mcp_server.py
2. Run pytest tests/test_mcp_scan_validate.py
3. Run full test suite: pytest tests/
4. Fix any failures found
5. Ensure 100% pass rate

Acceptance:
- All tests in test_mcp_server.py pass
- All tests in test_mcp_scan_validate.py pass
- Full test suite passes with no errors
- No duplicate test execution warnings
