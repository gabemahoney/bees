---
id: features.bees-z0t
type: subtask
title: Remove extracted MCP content from master_plan.md
description: 'Clean up master_plan.md by removing MCP server sections that have been
  moved to mcp_server.md.


  Context: After extracting MCP documentation to dedicated file, remove duplicate
  content from master_plan.md to avoid maintenance overhead.


  Requirements:

  - Remove "MCP Server Architecture" section from master_plan.md

  - Remove detailed MCP tool listings

  - Remove HTTP transport architecture details

  - Remove repo_root resolution details

  - Keep brief cross-reference: "See docs/architecture/mcp_server.md for MCP server
  architecture"

  - Ensure remaining content flows naturally


  Success Criteria:

  - No duplicate MCP content in master_plan.md

  - Clear cross-reference to mcp_server.md added

  - Document structure remains coherent

  - No broken references


  Files: docs/plans/master_plan.md

  Parent Task: features.bees-dsa

  Blocked By: features.bees-dwp (must extract content first)'
up_dependencies:
- features.bees-dwp
parent: features.bees-dsa
created_at: '2026-02-03T16:53:12.464807'
updated_at: '2026-02-03T17:36:11.766429'
status: completed
bees_version: '1.1'
---

Clean up master_plan.md by removing MCP server sections that have been moved to mcp_server.md.

Context: After extracting MCP documentation to dedicated file, remove duplicate content from master_plan.md to avoid maintenance overhead.

Requirements:
- Remove "MCP Server Architecture" section from master_plan.md
- Remove detailed MCP tool listings
- Remove HTTP transport architecture details
- Remove repo_root resolution details
- Keep brief cross-reference: "See docs/architecture/mcp_server.md for MCP server architecture"
- Ensure remaining content flows naturally

Success Criteria:
- No duplicate MCP content in master_plan.md
- Clear cross-reference to mcp_server.md added
- Document structure remains coherent
- No broken references

Files: docs/plans/master_plan.md
Parent Task: features.bees-dsa
Blocked By: features.bees-dwp (must extract content first)
