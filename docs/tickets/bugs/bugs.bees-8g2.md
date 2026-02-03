---
id: bugs.bees-8g2
type: subtask
title: Add unit tests for MCP server name validation
description: 'Context: FastMCP server name changed to "bees" to comply with MCP naming
  conventions. Need tests to ensure server name remains valid.


  Requirements:

  - Add test verifying server initializes with name "bees"

  - Add test verifying server name follows MCP conventions (lowercase, no spaces)

  - Add test checking tool prefix pattern is `mcp_bees_` not `mcp______`

  - Test that server.name property returns "bees"

  - Consider adding negative tests for invalid server names if applicable


  Test Location: tests/test_mcp_server.py or appropriate test file


  Parent Task: bugs.bees-ciy


  Acceptance Criteria:

  - All tests pass

  - Server name "bees" is validated

  - Tool prefix pattern is verified

  - Edge cases covered (if any)'
up_dependencies:
- bugs.bees-ako
down_dependencies:
- bugs.bees-fws
parent: bugs.bees-ciy
created_at: '2026-02-03T07:22:03.734948'
updated_at: '2026-02-03T07:22:11.606109'
status: open
bees_version: '1.1'
---

Context: FastMCP server name changed to "bees" to comply with MCP naming conventions. Need tests to ensure server name remains valid.

Requirements:
- Add test verifying server initializes with name "bees"
- Add test verifying server name follows MCP conventions (lowercase, no spaces)
- Add test checking tool prefix pattern is `mcp_bees_` not `mcp______`
- Test that server.name property returns "bees"
- Consider adding negative tests for invalid server names if applicable

Test Location: tests/test_mcp_server.py or appropriate test file

Parent Task: bugs.bees-ciy

Acceptance Criteria:
- All tests pass
- Server name "bees" is validated
- Tool prefix pattern is verified
- Edge cases covered (if any)
