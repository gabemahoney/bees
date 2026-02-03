---
id: features.bees-5ob
type: subtask
title: Remove all extracted function implementations from mcp_server.py
description: 'Context: All utility and operation functions have been extracted to
  separate modules. The implementations need to be removed from mcp_server.py to avoid
  duplication.


  What to Remove:

  - All ID parsing functions (now in mcp_id_utils)

  - All repo root functions (now in mcp_repo_utils)

  - All hive validation functions (now in mcp_hive_utils)

  - All relationship sync functions (now in mcp_relationships)

  - All ticket CRUD functions (now in mcp_ticket_ops)

  - All hive lifecycle functions (now in mcp_hive_ops)

  - All query functions (now in mcp_query_ops)

  - All index generation functions (now in mcp_index_ops)

  - All help functions (now in mcp_help)


  What to Keep:

  - FastMCP initialization

  - Logging setup

  - Server state variables

  - start_server(), stop_server(), _health_check()

  - All @mcp.tool() decorators


  Files: src/mcp_server.py


  Acceptance: File contains only server initialization, lifecycle functions, and tool
  decorators. No function implementations that exist in extracted modules.'
parent: features.bees-4u5
status: open
created_at: '2026-02-03T17:03:17.111947'
updated_at: '2026-02-03T17:03:17.111950'
bees_version: '1.1'
---

Context: All utility and operation functions have been extracted to separate modules. The implementations need to be removed from mcp_server.py to avoid duplication.

What to Remove:
- All ID parsing functions (now in mcp_id_utils)
- All repo root functions (now in mcp_repo_utils)
- All hive validation functions (now in mcp_hive_utils)
- All relationship sync functions (now in mcp_relationships)
- All ticket CRUD functions (now in mcp_ticket_ops)
- All hive lifecycle functions (now in mcp_hive_ops)
- All query functions (now in mcp_query_ops)
- All index generation functions (now in mcp_index_ops)
- All help functions (now in mcp_help)

What to Keep:
- FastMCP initialization
- Logging setup
- Server state variables
- start_server(), stop_server(), _health_check()
- All @mcp.tool() decorators

Files: src/mcp_server.py

Acceptance: File contains only server initialization, lifecycle functions, and tool decorators. No function implementations that exist in extracted modules.
