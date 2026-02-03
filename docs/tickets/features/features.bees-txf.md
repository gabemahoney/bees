---
id: features.bees-txf
type: subtask
title: Move _update_ticket() function to mcp_ticket_ops.py
description: 'Context: Extract ticket update operation from mcp_server.py to new dedicated
  module.


  Requirements:

  - Copy _update_ticket() function from src/mcp_server.py (lines 1398-1637) to src/mcp_ticket_ops.py

  - Preserve all validation logic

  - Preserve all bidirectional sync handling

  - Ensure all imports needed by this function are present

  - Verify function signature and return type unchanged


  Files: src/mcp_ticket_ops.py, src/mcp_server.py


  Acceptance: _update_ticket() function exists in mcp_ticket_ops.py with identical
  functionality to original.'
parent: features.bees-jzd
status: open
created_at: '2026-02-03T17:03:12.280569'
updated_at: '2026-02-03T17:03:12.280573'
bees_version: '1.1'
---

Context: Extract ticket update operation from mcp_server.py to new dedicated module.

Requirements:
- Copy _update_ticket() function from src/mcp_server.py (lines 1398-1637) to src/mcp_ticket_ops.py
- Preserve all validation logic
- Preserve all bidirectional sync handling
- Ensure all imports needed by this function are present
- Verify function signature and return type unchanged

Files: src/mcp_ticket_ops.py, src/mcp_server.py

Acceptance: _update_ticket() function exists in mcp_ticket_ops.py with identical functionality to original.
