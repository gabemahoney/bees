---
id: bugs.bees-itw
type: epic
title: Fix MCP server name to follow naming conventions
description: "## Problem\n\nServer is currently named \"Bees Ticket Management Server\"\
  \ (with spaces) in src/mcp_server.py:46, which violates MCP naming standards.\n\n\
  This causes Claude Code to expose tools with awkward 6-underscore prefix:\n- `mcp______create_ticket`\n\
  - `mcp______execute_query`\n- etc.\n\n## Standard Convention\n\nMCP servers should\
  \ use simple lowercase names (kebab-case for packages, simple names for server instances):\n\
  - Server name: `\"bees\"` (not \"Bees Ticket Management Server\")\n- Tools appear\
  \ as: `mcp_bees_create_ticket`, `mcp_bees_execute_query`\n- Permission pattern:\
  \ `mcp_bees_*()`\n\n## What Needs to Change\n\n1. Update FastMCP initialization\
  \ in src/mcp_server.py:46:\n   ```python\n   # FROM:\n   mcp = FastMCP(\"Bees Ticket\
  \ Management Server\")\n   \n   # TO:\n   mcp = FastMCP(\"bees\")\n   ```\n\n2.\
  \ Test that tools are now exposed with proper naming pattern\n\n3. Update any documentation\
  \ referencing the old server name\n\n4. Update permission examples to use `mcp_bees_*()`\
  \ pattern\n\n## References\n\n- MCP naming conventions require lowercase, no spaces\n\
  - Server name affects tool prefix: spaces/hyphens → underscores\n- Simple names\
  \ improve discoverability and compatibility"
children:
- bugs.bees-ciy
- bugs.bees-ulw
- bugs.bees-hl0
created_at: '2026-02-03T07:20:27.875411'
updated_at: '2026-02-03T07:23:37.200838'
priority: 0
status: open
bees_version: '1.1'
---

## Problem

Server is currently named "Bees Ticket Management Server" (with spaces) in src/mcp_server.py:46, which violates MCP naming standards.

This causes Claude Code to expose tools with awkward 6-underscore prefix:
- `mcp______create_ticket`
- `mcp______execute_query`
- etc.

## Standard Convention

MCP servers should use simple lowercase names (kebab-case for packages, simple names for server instances):
- Server name: `"bees"` (not "Bees Ticket Management Server")
- Tools appear as: `mcp_bees_create_ticket`, `mcp_bees_execute_query`
- Permission pattern: `mcp_bees_*()`

## What Needs to Change

1. Update FastMCP initialization in src/mcp_server.py:46:
   ```python
   # FROM:
   mcp = FastMCP("Bees Ticket Management Server")
   
   # TO:
   mcp = FastMCP("bees")
   ```

2. Test that tools are now exposed with proper naming pattern

3. Update any documentation referencing the old server name

4. Update permission examples to use `mcp_bees_*()` pattern

## References

- MCP naming conventions require lowercase, no spaces
- Server name affects tool prefix: spaces/hyphens → underscores
- Simple names improve discoverability and compatibility
