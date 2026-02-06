---
id: features.bees-2sx
type: subtask
title: Create test_mcp_scan_validate.py with extracted tests
description: 'Context: Extract identified scan and validation tests from test_mcp_server.py
  into new focused test file.


  What to Do:

  - Create tests/test_mcp_scan_validate.py

  - Copy scan/validation tests identified in previous subtask

  - Copy required shared fixtures and helpers

  - Update imports to reference conftest.py fixtures

  - Remove extracted tests from test_mcp_server.py

  - Ensure file is ~300 lines


  Why: Separates validation logic tests from CRUD operation tests.


  Files: tests/test_mcp_scan_validate.py, tests/test_mcp_server.py


  Success Criteria:

  - New file exists with scan/validate tests only

  - Imports correctly reference conftest.py

  - No duplicate tests between files

  - File approximately 300 lines'
up_dependencies:
- features.bees-le1
down_dependencies:
- features.bees-qi5
parent: features.bees-82b
created_at: '2026-02-05T16:13:49.200001'
updated_at: '2026-02-05T16:35:49.966876'
status: completed
bees_version: '1.1'
---

Context: Extract identified scan and validation tests from test_mcp_server.py into new focused test file.

What to Do:
- Create tests/test_mcp_scan_validate.py
- Copy scan/validation tests identified in previous subtask
- Copy required shared fixtures and helpers
- Update imports to reference conftest.py fixtures
- Remove extracted tests from test_mcp_server.py
- Ensure file is ~300 lines

Why: Separates validation logic tests from CRUD operation tests.

Files: tests/test_mcp_scan_validate.py, tests/test_mcp_server.py

Success Criteria:
- New file exists with scan/validate tests only
- Imports correctly reference conftest.py
- No duplicate tests between files
- File approximately 300 lines
