---
id: features.bees-oe3
type: subtask
title: Update src/mcp_server.py to use mcp_relationships module
description: 'Context: After extracting relationship sync functions to mcp_relationships.py,
  update mcp_server.py to import and use the new module.


  What to Change:

  - Remove the 9 relationship sync functions from src/mcp_server.py (lines 689-816
  and helpers)

  - Add import statement: `from mcp_relationships import _update_bidirectional_relationships`

  - Ensure all calls to `_update_bidirectional_relationships()` still work

  - Verify no other code depends on the removed helper functions


  Files: src/mcp_server.py


  Acceptance Criteria:

  - All 9 functions removed from mcp_server.py

  - Import added for _update_bidirectional_relationships

  - No broken references to moved functions

  - mcp_server.py is ~400 lines shorter'
parent: features.bees-t9t
status: open
created_at: '2026-02-03T17:03:07.038432'
updated_at: '2026-02-03T17:03:07.038436'
bees_version: '1.1'
---

Context: After extracting relationship sync functions to mcp_relationships.py, update mcp_server.py to import and use the new module.

What to Change:
- Remove the 9 relationship sync functions from src/mcp_server.py (lines 689-816 and helpers)
- Add import statement: `from mcp_relationships import _update_bidirectional_relationships`
- Ensure all calls to `_update_bidirectional_relationships()` still work
- Verify no other code depends on the removed helper functions

Files: src/mcp_server.py

Acceptance Criteria:
- All 9 functions removed from mcp_server.py
- Import added for _update_bidirectional_relationships
- No broken references to moved functions
- mcp_server.py is ~400 lines shorter
