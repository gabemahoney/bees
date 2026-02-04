---
id: features.bees-60z
type: subtask
title: Update src/mcp_server.py to import from mcp_id_utils
description: 'Context: After extracting ID parsing utilities, update mcp_server.py
  to use the new module instead of local definitions.


  Requirements:

  - Remove parse_ticket_id() function definition (lines 52-91)

  - Remove parse_hive_from_ticket_id() function definition (lines 93-122)

  - Add import statement: `from mcp_id_utils import parse_ticket_id, parse_hive_from_ticket_id`

  - Verify all existing calls to these functions still work

  - Ensure no other code depends on these functions being in mcp_server.py


  Files: src/mcp_server.py


  Acceptance Criteria:

  - Both function definitions removed from mcp_server.py

  - Import statement added at top of file

  - mcp_server.py still functions correctly

  - File is ~100-150 lines shorter'
parent: features.bees-pt9
created_at: '2026-02-03T17:03:03.388127'
updated_at: '2026-02-03T18:58:16.998213'
status: completed
bees_version: '1.1'
---

Context: After extracting ID parsing utilities, update mcp_server.py to use the new module instead of local definitions.

Requirements:
- Remove parse_ticket_id() function definition (lines 52-91)
- Remove parse_hive_from_ticket_id() function definition (lines 93-122)
- Add import statement: `from mcp_id_utils import parse_ticket_id, parse_hive_from_ticket_id`
- Verify all existing calls to these functions still work
- Ensure no other code depends on these functions being in mcp_server.py

Files: src/mcp_server.py

Acceptance Criteria:
- Both function definitions removed from mcp_server.py
- Import statement added at top of file
- mcp_server.py still functions correctly
- File is ~100-150 lines shorter
