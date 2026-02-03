---
id: bugs.bees-763
type: subtask
title: Create test_mcp_tool_naming.py integration test file
description: "Context: Need integration test to verify MCP server exposes tools with\
  \ correct naming pattern after server name change.\n\nWhat to Create:\n- Create\
  \ new file: tests/test_mcp_tool_naming.py\n- Test class: TestMCPToolNaming\n- Test\
  \ method: test_tool_names_follow_mcp_bees_pattern()\n- Test should:\n  1. Import\
  \ mcp instance from src.mcp_server\n  2. Retrieve list of registered tool names\
  \ (mcp may have .list_tools() or similar)\n  3. Assert all tool names start with\
  \ \"mcp_bees_\" prefix\n  4. Assert NO tool names have \"mcp______\" prefix (6 underscores)\n\
  \  5. Log tool names for debugging\n\nImplementation Details:\n- Use pytest framework\
  \ (consistent with existing tests)\n- May need to inspect mcp._tools or mcp.tools\
  \ attribute\n- Check FastMCP documentation for tool introspection methods\n\nSuccess\
  \ Criteria:\n- Test file created in tests/ directory\n- Test passes when server\
  \ name is \"bees\"\n- Test fails when server name has spaces (would produce mcp______*)\n\
  \nReferences:\n- Parent Task: bugs.bees-hl0\n- Related Epic: bugs.bees-itw (Fix\
  \ MCP server name)\n- Existing test: tests/test_mcp_server.py (for pattern reference)"
down_dependencies:
- bugs.bees-jru
- bugs.bees-eo6
- bugs.bees-oig
parent: bugs.bees-hl0
created_at: '2026-02-03T07:22:03.720159'
updated_at: '2026-02-03T07:22:25.620179'
status: open
bees_version: '1.1'
---

Context: Need integration test to verify MCP server exposes tools with correct naming pattern after server name change.

What to Create:
- Create new file: tests/test_mcp_tool_naming.py
- Test class: TestMCPToolNaming
- Test method: test_tool_names_follow_mcp_bees_pattern()
- Test should:
  1. Import mcp instance from src.mcp_server
  2. Retrieve list of registered tool names (mcp may have .list_tools() or similar)
  3. Assert all tool names start with "mcp_bees_" prefix
  4. Assert NO tool names have "mcp______" prefix (6 underscores)
  5. Log tool names for debugging

Implementation Details:
- Use pytest framework (consistent with existing tests)
- May need to inspect mcp._tools or mcp.tools attribute
- Check FastMCP documentation for tool introspection methods

Success Criteria:
- Test file created in tests/ directory
- Test passes when server name is "bees"
- Test fails when server name has spaces (would produce mcp______*)

References:
- Parent Task: bugs.bees-hl0
- Related Epic: bugs.bees-itw (Fix MCP server name)
- Existing test: tests/test_mcp_server.py (for pattern reference)
