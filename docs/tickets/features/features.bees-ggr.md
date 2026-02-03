---
id: features.bees-ggr
type: subtask
title: Update src/mcp_server.py imports and remove extracted functions
description: "Context: After extracting hive lifecycle operations to mcp_hive_ops.py,\
  \ need to update mcp_server.py to import from the new module.\n\nWhat to Do:\n-\
  \ Add import statement for mcp_hive_ops functions at top of src/mcp_server.py\n\
  - Remove the 6 extracted function definitions from mcp_server.py:\n  - colonize_hive_core()\
  \ (lines 429-687)\n  - _colonize_hive() (lines 2175-2260)\n  - _list_hives() (lines\
  \ 2262-2349)\n  - _abandon_hive() (lines 2351-2436)\n  - _rename_hive() (lines 2438-2840)\n\
  \  - _sanitize_hive() (lines 2842-2990)\n- Ensure MCP tool registrations still reference\
  \ the correct function names\n- Verify no other parts of mcp_server.py depend on\
  \ these functions\n\nFiles: src/mcp_server.py\n\nAcceptance Criteria:\n- mcp_server.py\
  \ imports from mcp_hive_ops\n- All 6 functions removed from mcp_server.py\n- MCP\
  \ server still registers hive operation tools correctly\n- No broken references\
  \ or missing imports"
down_dependencies:
- features.bees-dkz
parent: features.bees-2hp
created_at: '2026-02-03T17:03:10.573295'
updated_at: '2026-02-03T17:03:35.217749'
status: open
bees_version: '1.1'
---

Context: After extracting hive lifecycle operations to mcp_hive_ops.py, need to update mcp_server.py to import from the new module.

What to Do:
- Add import statement for mcp_hive_ops functions at top of src/mcp_server.py
- Remove the 6 extracted function definitions from mcp_server.py:
  - colonize_hive_core() (lines 429-687)
  - _colonize_hive() (lines 2175-2260)
  - _list_hives() (lines 2262-2349)
  - _abandon_hive() (lines 2351-2436)
  - _rename_hive() (lines 2438-2840)
  - _sanitize_hive() (lines 2842-2990)
- Ensure MCP tool registrations still reference the correct function names
- Verify no other parts of mcp_server.py depend on these functions

Files: src/mcp_server.py

Acceptance Criteria:
- mcp_server.py imports from mcp_hive_ops
- All 6 functions removed from mcp_server.py
- MCP server still registers hive operation tools correctly
- No broken references or missing imports
