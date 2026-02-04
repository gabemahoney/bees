---
id: features.bees-wo5
type: subtask
title: Update mcp_server.py to import from mcp_index_ops
description: 'Context: Replace local _generate_index implementation with import from
  new mcp_index_ops module.


  What to Change in src/mcp_server.py:

  - Add import: from mcp_index_ops import _generate_index

  - Remove _generate_index function definition (lines 2119-2168)

  - Keep tool registration: generate_index_tool = mcp.tool(name="generate_index")(_generate_index)


  Implementation:

  - Add import at top of file with other local imports

  - Delete function implementation completely

  - Verify tool registration still works


  Files: src/mcp_server.py


  Acceptance:

  - _generate_index imported from mcp_index_ops

  - Function definition removed from mcp_server.py

  - Tool registration unchanged and functional

  - No duplicate definitions'
parent: features.bees-zy7
status: completed
created_at: '2026-02-03T17:03:17.930973'
updated_at: '2026-02-03T17:03:17.930976'
bees_version: '1.1'
---

Context: Replace local _generate_index implementation with import from new mcp_index_ops module.

What to Change in src/mcp_server.py:
- Add import: from mcp_index_ops import _generate_index
- Remove _generate_index function definition (lines 2119-2168)
- Keep tool registration: generate_index_tool = mcp.tool(name="generate_index")(_generate_index)

Implementation:
- Add import at top of file with other local imports
- Delete function implementation completely
- Verify tool registration still works

Files: src/mcp_server.py

Acceptance:
- _generate_index imported from mcp_index_ops
- Function definition removed from mcp_server.py
- Tool registration unchanged and functional
- No duplicate definitions
