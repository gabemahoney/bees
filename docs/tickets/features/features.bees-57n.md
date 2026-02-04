---
id: features.bees-57n
type: subtask
title: Update test files importing parse_ticket_id or parse_hive_from_ticket_id
description: 'Context: Test files may directly import the moved functions from mcp_server.
  Update imports to use the new mcp_id_utils module.


  Requirements:

  - Search for test files importing parse_ticket_id or parse_hive_from_ticket_id from
  mcp_server

  - Update imports to: `from mcp_id_utils import parse_ticket_id, parse_hive_from_ticket_id`

  - Verify no other modules import these functions from mcp_server

  - Check for any mocks or patches referencing the old location


  Files: tests/*.py (any files importing these functions)


  Acceptance Criteria:

  - All test imports updated to use mcp_id_utils

  - No remaining imports of these functions from mcp_server

  - Tests can still import and use both functions correctly'
down_dependencies:
- features.bees-0k5
parent: features.bees-pt9
created_at: '2026-02-03T17:03:07.739567'
updated_at: '2026-02-03T18:58:32.609214'
status: completed
bees_version: '1.1'
---

Context: Test files may directly import the moved functions from mcp_server. Update imports to use the new mcp_id_utils module.

Requirements:
- Search for test files importing parse_ticket_id or parse_hive_from_ticket_id from mcp_server
- Update imports to: `from mcp_id_utils import parse_ticket_id, parse_hive_from_ticket_id`
- Verify no other modules import these functions from mcp_server
- Check for any mocks or patches referencing the old location

Files: tests/*.py (any files importing these functions)

Acceptance Criteria:
- All test imports updated to use mcp_id_utils
- No remaining imports of these functions from mcp_server
- Tests can still import and use both functions correctly
