---
id: features.bees-2g6
type: subtask
title: Move _create_ticket() function to mcp_ticket_ops.py
description: 'Context: Extract ticket creation operation from mcp_server.py to new
  dedicated module.


  Requirements:

  - Copy _create_ticket() function from src/mcp_server.py (lines 1087-1396) to src/mcp_ticket_ops.py

  - Preserve all validation logic

  - Preserve all error handling

  - Ensure all imports needed by this function are present

  - Verify function signature and return type unchanged


  Files: src/mcp_ticket_ops.py, src/mcp_server.py


  Acceptance: _create_ticket() function exists in mcp_ticket_ops.py with identical
  functionality to original.'
parent: features.bees-jzd
status: open
created_at: '2026-02-03T17:03:08.764602'
updated_at: '2026-02-03T17:03:08.764607'
bees_version: '1.1'
---

Context: Extract ticket creation operation from mcp_server.py to new dedicated module.

Requirements:
- Copy _create_ticket() function from src/mcp_server.py (lines 1087-1396) to src/mcp_ticket_ops.py
- Preserve all validation logic
- Preserve all error handling
- Ensure all imports needed by this function are present
- Verify function signature and return type unchanged

Files: src/mcp_ticket_ops.py, src/mcp_server.py

Acceptance: _create_ticket() function exists in mcp_ticket_ops.py with identical functionality to original.
