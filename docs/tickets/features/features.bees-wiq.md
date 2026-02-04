---
id: features.bees-wiq
type: subtask
title: Add unit tests for mcp_query_ops.py module
description: "Context: Ensure the extracted query operations module works correctly\
  \ in isolation and when imported by mcp_server.py.\n\nImplementation Steps:\n1.\
  \ Create tests/test_mcp_query_ops.py or add to existing query operation tests\n\
  2. Test module imports correctly:\n   - Can import _add_named_query, _execute_query,\
  \ _execute_freeform_query\n   - No circular dependency issues\n3. Test function\
  \ behavior (leverage existing test fixtures):\n   - Named query registration works\n\
  \   - Query execution with hive filtering works\n   - Freeform queries work\n  \
  \ - Error handling preserved\n4. Verify integration with mcp_server.py:\n   - Tool\
  \ decorators call module functions correctly\n   - MCP tools still work end-to-end\n\
  \nFiles Affected:\n- tests/test_mcp_query_ops.py (new or existing test file)\n\n\
  Acceptance Criteria:\n- Unit tests cover module imports\n- Function behavior tests\
  \ pass\n- Integration with mcp_server.py verified\n- All edge cases and error conditions\
  \ tested\n\nParent Task: features.bees-txe"
parent: features.bees-txe
up_dependencies:
- features.bees-af3
status: closed
created_at: '2026-02-03T17:03:35.763534'
updated_at: '2026-02-03T17:03:35.763538'
bees_version: '1.1'
---

Context: Ensure the extracted query operations module works correctly in isolation and when imported by mcp_server.py.

Implementation Steps:
1. Create tests/test_mcp_query_ops.py or add to existing query operation tests
2. Test module imports correctly:
   - Can import _add_named_query, _execute_query, _execute_freeform_query
   - No circular dependency issues
3. Test function behavior (leverage existing test fixtures):
   - Named query registration works
   - Query execution with hive filtering works
   - Freeform queries work
   - Error handling preserved
4. Verify integration with mcp_server.py:
   - Tool decorators call module functions correctly
   - MCP tools still work end-to-end

Files Affected:
- tests/test_mcp_query_ops.py (new or existing test file)

Acceptance Criteria:
- Unit tests cover module imports
- Function behavior tests pass
- Integration with mcp_server.py verified
- All edge cases and error conditions tested

Parent Task: features.bees-txe
