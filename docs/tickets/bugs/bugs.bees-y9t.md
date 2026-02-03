---
id: bugs.bees-y9t
type: subtask
title: Update README.md with server name change documentation
description: 'Context: After changing the FastMCP server name from "Bees Ticket Management
  Server" to "bees", documentation needs to reflect the new MCP tool prefix pattern.


  Requirements:

  - Update any references to MCP tool names from `mcp______` prefix to `mcp_bees_`
  prefix

  - Document that tools are now exposed as `mcp_bees_create_ticket`, `mcp_bees_update_ticket`,
  etc.

  - Update any examples or usage instructions that reference the old tool naming pattern


  Files: README.md


  Parent Task: bugs.bees-ciy


  Acceptance Criteria:

  - All tool name examples use correct `mcp_bees_` prefix

  - No references to `mcp______` prefix remain

  - Documentation accurately reflects server name "bees"'
parent: bugs.bees-ciy
up_dependencies:
- bugs.bees-ako
status: open
created_at: '2026-02-03T07:21:51.214708'
updated_at: '2026-02-03T07:21:51.214713'
bees_version: '1.1'
---

Context: After changing the FastMCP server name from "Bees Ticket Management Server" to "bees", documentation needs to reflect the new MCP tool prefix pattern.

Requirements:
- Update any references to MCP tool names from `mcp______` prefix to `mcp_bees_` prefix
- Document that tools are now exposed as `mcp_bees_create_ticket`, `mcp_bees_update_ticket`, etc.
- Update any examples or usage instructions that reference the old tool naming pattern

Files: README.md

Parent Task: bugs.bees-ciy

Acceptance Criteria:
- All tool name examples use correct `mcp_bees_` prefix
- No references to `mcp______` prefix remain
- Documentation accurately reflects server name "bees"
