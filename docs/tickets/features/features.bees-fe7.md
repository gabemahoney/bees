---
id: features.bees-fe7
type: subtask
title: Add unit tests for mcp_index_ops module
description: 'Context: Ensure extracted mcp_index_ops module is properly tested.


  What to Test:

  - Test _generate_index() with no filters (all tickets)

  - Test with status filter (status=''open'', status=''completed'')

  - Test with type filter (type=''epic'', type=''task'', type=''subtask'')

  - Test with combined filters (status + type)

  - Test with hive_name filter (single hive)

  - Test error handling when index generation fails


  Implementation:

  - Add test file tests/test_mcp_index_ops.py OR add to existing test_mcp_server.py

  - Mock generate_index from index_generator module

  - Verify function calls generate_index with correct parameters

  - Test return structure (status, markdown fields)

  - Verify logging on success and error


  Files: tests/test_mcp_index_ops.py (new) or tests/test_mcp_server.py


  Acceptance:

  - All _generate_index scenarios tested

  - Mock verify correct parameters passed

  - Success and error cases covered

  - Tests pass with 100% coverage of new module'
up_dependencies:
- features.bees-mhy
down_dependencies:
- features.bees-4ib
parent: features.bees-zy7
created_at: '2026-02-03T17:03:36.075015'
updated_at: '2026-02-03T17:03:45.449315'
status: open
bees_version: '1.1'
---

Context: Ensure extracted mcp_index_ops module is properly tested.

What to Test:
- Test _generate_index() with no filters (all tickets)
- Test with status filter (status='open', status='completed')
- Test with type filter (type='epic', type='task', type='subtask')
- Test with combined filters (status + type)
- Test with hive_name filter (single hive)
- Test error handling when index generation fails

Implementation:
- Add test file tests/test_mcp_index_ops.py OR add to existing test_mcp_server.py
- Mock generate_index from index_generator module
- Verify function calls generate_index with correct parameters
- Test return structure (status, markdown fields)
- Verify logging on success and error

Files: tests/test_mcp_index_ops.py (new) or tests/test_mcp_server.py

Acceptance:
- All _generate_index scenarios tested
- Mock verify correct parameters passed
- Success and error cases covered
- Tests pass with 100% coverage of new module
