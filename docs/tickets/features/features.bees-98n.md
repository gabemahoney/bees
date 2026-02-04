---
id: features.bees-98n
type: subtask
title: Add unit tests for mcp_hive_utils.py functions
description: "Context: Ensure extracted hive utilities work correctly with comprehensive\
  \ test coverage.\n\nWhat to Do:\n1. Create tests/test_mcp_hive_utils.py\n2. Test\
  \ validate_hive_path():\n   - Valid absolute paths within repo\n   - Invalid relative\
  \ paths\n   - Paths outside repo\n   - Nonexistent paths\n   - Edge cases (symlinks,\
  \ special characters)\n3. Test scan_for_hive():\n   - Finding .hive marker in directory\n\
  \   - Recursive search upward from subdirectories\n   - Handling missing markers\n\
  \   - Config validation\n4. Use fixtures from conftest.py for temp directories\n\
  \nFiles: tests/test_mcp_hive_utils.py (new)\n\nAcceptance Criteria:\n- All validate_hive_path()\
  \ scenarios tested\n- All scan_for_hive() scenarios tested\n- Edge cases and error\
  \ conditions covered\n- Tests use appropriate fixtures"
up_dependencies:
- features.bees-hnv
down_dependencies:
- features.bees-axt
parent: features.bees-wvm
created_at: '2026-02-03T17:03:37.920115'
updated_at: '2026-02-03T19:47:25.636556'
status: completed
bees_version: '1.1'
---

Context: Ensure extracted hive utilities work correctly with comprehensive test coverage.

What to Do:
1. Create tests/test_mcp_hive_utils.py
2. Test validate_hive_path():
   - Valid absolute paths within repo
   - Invalid relative paths
   - Paths outside repo
   - Nonexistent paths
   - Edge cases (symlinks, special characters)
3. Test scan_for_hive():
   - Finding .hive marker in directory
   - Recursive search upward from subdirectories
   - Handling missing markers
   - Config validation
4. Use fixtures from conftest.py for temp directories

Files: tests/test_mcp_hive_utils.py (new)

Acceptance Criteria:
- All validate_hive_path() scenarios tested
- All scan_for_hive() scenarios tested
- Edge cases and error conditions covered
- Tests use appropriate fixtures
