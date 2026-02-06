---
id: features.bees-82b
type: task
title: Create test_mcp_scan_validate.py with scan and validation tests
description: 'Context: Scan and validation tests verify ticket discovery and integrity
  checks - distinct from CRUD operations.


  What Needs to Change:

  - Create tests/test_mcp_scan_validate.py

  - Extract identified scan/validate tests from test_mcp_server.py

  - Ensure imports reference conftest.py fixtures

  - Target ~300 lines


  Why: Isolates validation logic from tool operation tests.


  Success Criteria:

  - File exists with scan/validate tests only

  - `pytest tests/test_mcp_scan_validate.py` passes all tests

  - File size approximately 300 lines


  Files: tests/test_mcp_scan_validate.py, tests/test_mcp_server.py. Epic: features.bees-5y8'
up_dependencies:
- features.bees-4i1
down_dependencies:
- features.bees-xab
- features.bees-o4v
parent: features.bees-5y8
children:
- features.bees-le1
- features.bees-2sx
- features.bees-ffm
- features.bees-2i5
- features.bees-qi5
- features.bees-61l
created_at: '2026-02-05T16:12:51.341868'
updated_at: '2026-02-05T16:39:04.926659'
priority: 0
status: completed
bees_version: '1.1'
---

Context: Scan and validation tests verify ticket discovery and integrity checks - distinct from CRUD operations.

What Needs to Change:
- Create tests/test_mcp_scan_validate.py
- Extract identified scan/validate tests from test_mcp_server.py
- Ensure imports reference conftest.py fixtures
- Target ~300 lines

Why: Isolates validation logic from tool operation tests.

Success Criteria:
- File exists with scan/validate tests only
- `pytest tests/test_mcp_scan_validate.py` passes all tests
- File size approximately 300 lines

Files: tests/test_mcp_scan_validate.py, tests/test_mcp_server.py. Epic: features.bees-5y8
