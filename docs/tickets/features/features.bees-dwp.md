---
id: features.bees-dwp
type: subtask
title: Create docs/architecture/mcp_server.md with MCP overview
description: 'Extract and condense MCP server architecture from master_plan.md into
  a new focused document.


  Context: Part of splitting master_plan.md into modular docs. MCP server is the primary
  LLM interface.


  Requirements:

  - Create docs/architecture/mcp_server.md

  - Extract MCP Server Architecture section from master_plan.md

  - List all MCP tools (colonize_hive, list_hives, rename_hive, abandon_hive, sanitize_hive,
  create_ticket, update_ticket, delete_ticket, show_ticket, execute_query, execute_freeform_query,
  add_named_query, generate_index)

  - Include brief purpose for each tool

  - Document HTTP/SSE transport architecture and rationale

  - Explain repo_root resolution strategy (roots protocol with fallback)

  - Cover startup and CLI integration patterns

  - Condense "Recent Changes" to major architectural changes only

  - Remove verbose change logs and task histories


  Success Criteria:

  - Document is under 2k tokens

  - All MCP tools listed with brief descriptions

  - HTTP transport choice explained

  - repo_root resolution covered

  - No verbose API docs (overview only)

  - Clear, focused, maintainable


  Files: docs/architecture/mcp_server.md (create), docs/plans/master_plan.md (source)

  Parent Task: features.bees-dsa'
down_dependencies:
- features.bees-z0t
parent: features.bees-dsa
created_at: '2026-02-03T16:53:05.475954'
updated_at: '2026-02-03T16:53:12.470397'
status: open
bees_version: '1.1'
---

Extract and condense MCP server architecture from master_plan.md into a new focused document.

Context: Part of splitting master_plan.md into modular docs. MCP server is the primary LLM interface.

Requirements:
- Create docs/architecture/mcp_server.md
- Extract MCP Server Architecture section from master_plan.md
- List all MCP tools (colonize_hive, list_hives, rename_hive, abandon_hive, sanitize_hive, create_ticket, update_ticket, delete_ticket, show_ticket, execute_query, execute_freeform_query, add_named_query, generate_index)
- Include brief purpose for each tool
- Document HTTP/SSE transport architecture and rationale
- Explain repo_root resolution strategy (roots protocol with fallback)
- Cover startup and CLI integration patterns
- Condense "Recent Changes" to major architectural changes only
- Remove verbose change logs and task histories

Success Criteria:
- Document is under 2k tokens
- All MCP tools listed with brief descriptions
- HTTP transport choice explained
- repo_root resolution covered
- No verbose API docs (overview only)
- Clear, focused, maintainable

Files: docs/architecture/mcp_server.md (create), docs/plans/master_plan.md (source)
Parent Task: features.bees-dsa
