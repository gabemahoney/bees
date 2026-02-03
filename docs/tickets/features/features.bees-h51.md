---
id: features.bees-h51
type: subtask
title: Move _show_ticket() function to mcp_ticket_ops.py
description: 'Context: Extract ticket retrieval operation from mcp_server.py to new
  dedicated module.


  Requirements:

  - Copy _show_ticket() function from src/mcp_server.py (lines 2001-2117) to src/mcp_ticket_ops.py

  - Preserve all data formatting logic

  - Preserve all error handling

  - Ensure all imports needed by this function are present

  - Verify function signature and return type unchanged


  Files: src/mcp_ticket_ops.py, src/mcp_server.py


  Acceptance: _show_ticket() function exists in mcp_ticket_ops.py with identical functionality
  to original.'
parent: features.bees-jzd
status: open
created_at: '2026-02-03T17:03:19.404357'
updated_at: '2026-02-03T17:03:19.404362'
bees_version: '1.1'
---

Context: Extract ticket retrieval operation from mcp_server.py to new dedicated module.

Requirements:
- Copy _show_ticket() function from src/mcp_server.py (lines 2001-2117) to src/mcp_ticket_ops.py
- Preserve all data formatting logic
- Preserve all error handling
- Ensure all imports needed by this function are present
- Verify function signature and return type unchanged

Files: src/mcp_ticket_ops.py, src/mcp_server.py

Acceptance: _show_ticket() function exists in mcp_ticket_ops.py with identical functionality to original.
