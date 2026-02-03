---
id: bugs.bees-ako
type: subtask
title: Change FastMCP server name from "Bees Ticket Management Server" to "bees"
description: 'Context: Line 46 in src/mcp_server.py initializes FastMCP with a name
  containing spaces and capitals, violating MCP naming conventions and causing tool
  prefix `mcp______` instead of `mcp_bees_`.


  Requirements:

  - Update line 46: `mcp = FastMCP("Bees Ticket Management Server")` to `mcp = FastMCP("bees")`

  - Search entire codebase for other references to "Bees Ticket Management Server"
  string and update if found

  - Verify no hardcoded references to the old server name in tests or documentation


  Files: src/mcp_server.py


  Acceptance Criteria:

  - Server initializes with name "bees"

  - No references to old server name remain in codebase

  - Tools will be exposed with `mcp_bees_` prefix instead of `mcp______`'
down_dependencies:
- bugs.bees-y9t
- bugs.bees-lx6
- bugs.bees-8g2
parent: bugs.bees-ciy
created_at: '2026-02-03T07:21:45.155471'
updated_at: '2026-02-03T07:22:03.740811'
status: open
bees_version: '1.1'
---

Context: Line 46 in src/mcp_server.py initializes FastMCP with a name containing spaces and capitals, violating MCP naming conventions and causing tool prefix `mcp______` instead of `mcp_bees_`.

Requirements:
- Update line 46: `mcp = FastMCP("Bees Ticket Management Server")` to `mcp = FastMCP("bees")`
- Search entire codebase for other references to "Bees Ticket Management Server" string and update if found
- Verify no hardcoded references to the old server name in tests or documentation

Files: src/mcp_server.py

Acceptance Criteria:
- Server initializes with name "bees"
- No references to old server name remain in codebase
- Tools will be exposed with `mcp_bees_` prefix instead of `mcp______`
