---
id: features.bees-lmo
type: task
title: Add optional repo_root parameter to all MCP tool functions
description: 'Currently 11 MCP tools (_create_ticket, _update_ticket, _delete_ticket,
  _execute_query, _execute_freeform_query, _show_ticket, _colonize_hive, _list_hives,
  _abandon_hive, _rename_hive, _sanitize_hive) call get_repo_root(ctx) which returns
  None if the client doesn''t support roots protocol. We need to provide a fallback
  path parameter.


  What Needs to Change:

  - Add optional repo_root: str | None = None parameter to all 11 MCP tool functions
  in src/mcp_server.py

  - Update each function to use provided repo_root if present, otherwise fall back
  to get_repo_root(ctx)

  - If both repo_root param is None AND get_repo_root returns None, raise ValueError
  with helpful message

  - Update get_repo_root() docstring to explain the fallback pattern


  Files: src/mcp_server.py


  Epic: features.bees-h0a'
down_dependencies:
- features.bees-o0l
- features.bees-4ju
- features.bees-cyh
parent: features.bees-h0a
children:
- features.bees-jsp
- features.bees-t1r
- features.bees-w67
- features.bees-xwd
- features.bees-5mw
- features.bees-h1s
- features.bees-cmd
- features.bees-0i0
created_at: '2026-02-03T06:40:56.157691'
updated_at: '2026-02-03T12:35:29.016342'
priority: 0
status: completed
bees_version: '1.1'
---

Currently 11 MCP tools (_create_ticket, _update_ticket, _delete_ticket, _execute_query, _execute_freeform_query, _show_ticket, _colonize_hive, _list_hives, _abandon_hive, _rename_hive, _sanitize_hive) call get_repo_root(ctx) which returns None if the client doesn't support roots protocol. We need to provide a fallback path parameter.

What Needs to Change:
- Add optional repo_root: str | None = None parameter to all 11 MCP tool functions in src/mcp_server.py
- Update each function to use provided repo_root if present, otherwise fall back to get_repo_root(ctx)
- If both repo_root param is None AND get_repo_root returns None, raise ValueError with helpful message
- Update get_repo_root() docstring to explain the fallback pattern

Files: src/mcp_server.py

Epic: features.bees-h0a
