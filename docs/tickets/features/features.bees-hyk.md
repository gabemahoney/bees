---
id: features.bees-hyk
type: subtask
title: Add unit tests for paths.py refactored implementation
description: "**Context**: Task features.bees-tho removes _parse_ticket_id_for_path()\
  \ and uses mcp_id_utils.parse_ticket_id() instead. Need to verify paths.py functions\
  \ still work correctly with the new implementation.\n\n**What to do**:\n1. Add tests\
  \ to verify get_ticket_path() correctly parses hive-prefixed IDs\n2. Add tests to\
  \ verify infer_ticket_type_from_id() correctly parses hive-prefixed IDs\n3. Test\
  \ edge cases: empty string, None, missing dot separator, malformed IDs\n4. Test\
  \ that ValueError is raised for unprefixed IDs (if paths.py requires hive prefix)\n\
  5. Verify existing test suite coverage for paths.py functions\n\n**Files**: \n-\
  \ tests/test_paths.py (or create if missing)\n- src/paths.py (functions under test)\n\
  \n**Acceptance**: \n- Unit tests cover get_ticket_path() and infer_ticket_type_from_id()\
  \ with parse_ticket_id()\n- Edge cases tested (error handling, malformed inputs)\n\
  - All new tests pass"
up_dependencies:
- features.bees-mnf
down_dependencies:
- features.bees-aqc
parent: features.bees-tho
created_at: '2026-02-03T19:08:00.553646'
updated_at: '2026-02-03T19:10:52.639878'
status: completed
bees_version: '1.1'
---

**Context**: Task features.bees-tho removes _parse_ticket_id_for_path() and uses mcp_id_utils.parse_ticket_id() instead. Need to verify paths.py functions still work correctly with the new implementation.

**What to do**:
1. Add tests to verify get_ticket_path() correctly parses hive-prefixed IDs
2. Add tests to verify infer_ticket_type_from_id() correctly parses hive-prefixed IDs
3. Test edge cases: empty string, None, missing dot separator, malformed IDs
4. Test that ValueError is raised for unprefixed IDs (if paths.py requires hive prefix)
5. Verify existing test suite coverage for paths.py functions

**Files**: 
- tests/test_paths.py (or create if missing)
- src/paths.py (functions under test)

**Acceptance**: 
- Unit tests cover get_ticket_path() and infer_ticket_type_from_id() with parse_ticket_id()
- Edge cases tested (error handling, malformed inputs)
- All new tests pass
