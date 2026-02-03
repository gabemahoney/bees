---
id: bugs.bees-lx6
type: subtask
title: Update master_plan.md with MCP server naming implementation
description: 'Context: Server name changed from "Bees Ticket Management Server" to
  "bees" to comply with MCP naming conventions.


  Requirements:

  - Document the MCP server naming convention requirement (lowercase, no spaces)

  - Explain why "bees" was chosen as the server name

  - Document the resulting tool prefix pattern change from `mcp______` to `mcp_bees_`

  - Update any architectural diagrams or references to the MCP server name

  - Document the impact on client integrations (tool names changed)


  Files: docs/plans/master_plan.md


  Parent Task: bugs.bees-ciy


  Acceptance Criteria:

  - MCP naming convention requirement is documented

  - Server name rationale is explained

  - Tool prefix pattern change is documented

  - Client integration impact is noted'
parent: bugs.bees-ciy
up_dependencies:
- bugs.bees-ako
status: open
created_at: '2026-02-03T07:21:57.478034'
updated_at: '2026-02-03T07:21:57.478046'
bees_version: '1.1'
---

Context: Server name changed from "Bees Ticket Management Server" to "bees" to comply with MCP naming conventions.

Requirements:
- Document the MCP server naming convention requirement (lowercase, no spaces)
- Explain why "bees" was chosen as the server name
- Document the resulting tool prefix pattern change from `mcp______` to `mcp_bees_`
- Update any architectural diagrams or references to the MCP server name
- Document the impact on client integrations (tool names changed)

Files: docs/plans/master_plan.md

Parent Task: bugs.bees-ciy

Acceptance Criteria:
- MCP naming convention requirement is documented
- Server name rationale is explained
- Tool prefix pattern change is documented
- Client integration impact is noted
