---
id: features.bees-7lh
type: subtask
title: Update mcp_server.py imports and remove moved functions
description: 'Context: After moving ticket CRUD functions to mcp_ticket_ops.py, need
  to update mcp_server.py to use the new module.


  Requirements:

  - Add import statement: `from mcp_ticket_ops import _create_ticket, _update_ticket,
  _delete_ticket, _show_ticket`

  - Remove the original function definitions from mcp_server.py (lines 1087-1396,
  1398-1637, 1639-1758, 2001-2117)

  - Ensure no other code references are broken

  - Verify all MCP tool registrations still work correctly

  - Update any internal module references if needed


  Files: src/mcp_server.py


  Acceptance: mcp_server.py imports and uses ticket operations from mcp_ticket_ops.py
  without errors. Module is significantly shorter (~700-800 lines removed).'
parent: features.bees-jzd
status: completed
created_at: '2026-02-03T17:03:25.765213'
updated_at: '2026-02-03T17:03:25.765216'
bees_version: '1.1'
---

Context: After moving ticket CRUD functions to mcp_ticket_ops.py, need to update mcp_server.py to use the new module.

Requirements:
- Add import statement: `from mcp_ticket_ops import _create_ticket, _update_ticket, _delete_ticket, _show_ticket`
- Remove the original function definitions from mcp_server.py (lines 1087-1396, 1398-1637, 1639-1758, 2001-2117)
- Ensure no other code references are broken
- Verify all MCP tool registrations still work correctly
- Update any internal module references if needed

Files: src/mcp_server.py

Acceptance: mcp_server.py imports and uses ticket operations from mcp_ticket_ops.py without errors. Module is significantly shorter (~700-800 lines removed).
