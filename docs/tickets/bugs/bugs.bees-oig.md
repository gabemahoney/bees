---
id: bugs.bees-oig
type: subtask
title: Add unit tests for MCP tool naming verification
description: "Context: Integration test needs comprehensive unit test coverage.\n\n\
  What to Test:\n- File: tests/test_mcp_tool_naming.py\n- Test cases to add:\n  1.\
  \ test_all_tools_have_mcp_bees_prefix() - verify every tool starts with mcp_bees_\n\
  \  2. test_no_tools_have_incorrect_underscore_pattern() - assert no mcp______* tools\n\
  \  3. test_tool_list_not_empty() - verify MCP server exposes tools\n  4. test_specific_tools_exist()\
  \ - check key tools like mcp_bees_create_ticket\n  5. Edge case: test_server_name_affects_prefix()\
  \ (if feasible to test server name change)\n\nTesting Strategy:\n- Use parametrized\
  \ tests for multiple tool checks\n- Mock/patch if needed to test different server\
  \ names\n- Verify error messages when incorrect pattern detected\n\nSuccess Criteria:\n\
  - Comprehensive test coverage for tool naming\n- Tests cover positive and negative\
  \ cases\n- Edge cases and error conditions tested\n- All tests pass with current\
  \ implementation\n\nReferences:\n- Parent Task: bugs.bees-hl0\n- Implementation\
  \ Subtask: bugs.bees-763"
up_dependencies:
- bugs.bees-763
down_dependencies:
- bugs.bees-8bp
parent: bugs.bees-hl0
created_at: '2026-02-03T07:22:25.614943'
updated_at: '2026-02-03T07:22:33.819688'
status: open
bees_version: '1.1'
---

Context: Integration test needs comprehensive unit test coverage.

What to Test:
- File: tests/test_mcp_tool_naming.py
- Test cases to add:
  1. test_all_tools_have_mcp_bees_prefix() - verify every tool starts with mcp_bees_
  2. test_no_tools_have_incorrect_underscore_pattern() - assert no mcp______* tools
  3. test_tool_list_not_empty() - verify MCP server exposes tools
  4. test_specific_tools_exist() - check key tools like mcp_bees_create_ticket
  5. Edge case: test_server_name_affects_prefix() (if feasible to test server name change)

Testing Strategy:
- Use parametrized tests for multiple tool checks
- Mock/patch if needed to test different server names
- Verify error messages when incorrect pattern detected

Success Criteria:
- Comprehensive test coverage for tool naming
- Tests cover positive and negative cases
- Edge cases and error conditions tested
- All tests pass with current implementation

References:
- Parent Task: bugs.bees-hl0
- Implementation Subtask: bugs.bees-763
