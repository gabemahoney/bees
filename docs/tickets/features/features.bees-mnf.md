---
id: features.bees-mnf
type: subtask
title: Replace _parse_ticket_id_for_path() with parse_ticket_id() from mcp_id_utils
description: "**Context**: paths.py contains duplicate implementation of ticket ID\
  \ parsing logic that exists in mcp_id_utils.parse_ticket_id(). The duplicate function\
  \ _parse_ticket_id_for_path() was created to avoid circular imports but duplicates\
  \ validation logic.\n\n**What to do**:\n1. Import parse_ticket_id from mcp_id_utils\
  \ at top of paths.py\n2. Replace all calls to _parse_ticket_id_for_path() with parse_ticket_id()\n\
  3. Delete the _parse_ticket_id_for_path() function (lines 10-41)\n4. Note: _parse_ticket_id_for_path()\
  \ requires hive prefix (raises ValueError without dot), while parse_ticket_id()\
  \ accepts legacy format. Verify existing calls expect the stricter validation.\n\
  \n**Files**: \n- src/paths.py (lines 10-41, 70, 133)\n- src/mcp_id_utils.py (reference\
  \ implementation)\n\n**Acceptance**: \n- _parse_ticket_id_for_path() function removed\n\
  - All calls replaced with parse_ticket_id()\n- No circular import errors\n- Existing\
  \ functionality preserved (paths.py functions work correctly)"
down_dependencies:
- features.bees-71g
- features.bees-2k3
- features.bees-hyk
parent: features.bees-tho
created_at: '2026-02-03T19:07:40.141149'
updated_at: '2026-02-03T19:09:31.575040'
status: completed
bees_version: '1.1'
---

**Context**: paths.py contains duplicate implementation of ticket ID parsing logic that exists in mcp_id_utils.parse_ticket_id(). The duplicate function _parse_ticket_id_for_path() was created to avoid circular imports but duplicates validation logic.

**What to do**:
1. Import parse_ticket_id from mcp_id_utils at top of paths.py
2. Replace all calls to _parse_ticket_id_for_path() with parse_ticket_id()
3. Delete the _parse_ticket_id_for_path() function (lines 10-41)
4. Note: _parse_ticket_id_for_path() requires hive prefix (raises ValueError without dot), while parse_ticket_id() accepts legacy format. Verify existing calls expect the stricter validation.

**Files**: 
- src/paths.py (lines 10-41, 70, 133)
- src/mcp_id_utils.py (reference implementation)

**Acceptance**: 
- _parse_ticket_id_for_path() function removed
- All calls replaced with parse_ticket_id()
- No circular import errors
- Existing functionality preserved (paths.py functions work correctly)
