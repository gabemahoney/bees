---
id: features.bees-ay0
type: subtask
title: Move _delete_ticket() function to mcp_ticket_ops.py
description: 'Context: Extract ticket deletion operation from mcp_server.py to new
  dedicated module.


  Requirements:

  - Copy _delete_ticket() function from src/mcp_server.py (lines 1639-1758) to src/mcp_ticket_ops.py

  - Preserve all cascade deletion logic

  - Preserve all relationship cleanup logic

  - Ensure all imports needed by this function are present

  - Verify function signature and return type unchanged


  Files: src/mcp_ticket_ops.py, src/mcp_server.py


  Acceptance: _delete_ticket() function exists in mcp_ticket_ops.py with identical
  functionality to original.'
parent: features.bees-jzd
status: completed
created_at: '2026-02-03T17:03:15.854677'
updated_at: '2026-02-03T17:03:15.854680'
bees_version: '1.1'
---

Context: Extract ticket deletion operation from mcp_server.py to new dedicated module.

Requirements:
- Copy _delete_ticket() function from src/mcp_server.py (lines 1639-1758) to src/mcp_ticket_ops.py
- Preserve all cascade deletion logic
- Preserve all relationship cleanup logic
- Ensure all imports needed by this function are present
- Verify function signature and return type unchanged

Files: src/mcp_ticket_ops.py, src/mcp_server.py

Acceptance: _delete_ticket() function exists in mcp_ticket_ops.py with identical functionality to original.
