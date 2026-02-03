---
id: bugs.bees-ciy
type: task
title: Update FastMCP server name in mcp_server.py
description: 'Context: Server is named "Bees Ticket Management Server" with spaces,
  violating MCP standards and creating `mcp______` tool prefix pattern.


  What Needs to Change:

  - Change line 46 in src/mcp_server.py from `FastMCP("Bees Ticket Management Server")`
  to `FastMCP("bees")`

  - Verify no other code references the old server name string


  Why: MCP naming conventions require lowercase, no-space names. This will change
  tool prefix from `mcp______` to `mcp_bees_`.


  Success Criteria:

  - Server initializes with name "bees"

  - Tools exposed as `mcp_bees_create_ticket`, etc.


  Files: src/mcp_server.py


  Epic: bugs.bees-itw'
parent: bugs.bees-itw
children:
- bugs.bees-ako
- bugs.bees-y9t
- bugs.bees-lx6
- bugs.bees-8g2
- bugs.bees-fws
created_at: '2026-02-03T07:21:17.614342'
updated_at: '2026-02-03T07:22:11.602954'
priority: 0
status: open
bees_version: '1.1'
---

Context: Server is named "Bees Ticket Management Server" with spaces, violating MCP standards and creating `mcp______` tool prefix pattern.

What Needs to Change:
- Change line 46 in src/mcp_server.py from `FastMCP("Bees Ticket Management Server")` to `FastMCP("bees")`
- Verify no other code references the old server name string

Why: MCP naming conventions require lowercase, no-space names. This will change tool prefix from `mcp______` to `mcp_bees_`.

Success Criteria:
- Server initializes with name "bees"
- Tools exposed as `mcp_bees_create_ticket`, etc.

Files: src/mcp_server.py

Epic: bugs.bees-itw
