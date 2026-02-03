---
id: features.bees-72w
type: subtask
title: Update mcp_server.py imports and tool registration
description: 'Context: After extracting _help() to mcp_help.py, update mcp_server.py
  to import and use the extracted function.


  Requirements:

  - Add import statement: `from mcp_help import _help`

  - Verify tool registration still works: `help = mcp.tool(name="help")(_help)`

  - Ensure no broken references to _help in mcp_server.py


  Files: src/mcp_server.py


  Acceptance Criteria:

  - Import statement added at top of file

  - Tool registration references imported _help function

  - No import errors when module loads

  - Help command still accessible via MCP


  Parent Task: features.bees-jlu'
parent: features.bees-jlu
up_dependencies:
- features.bees-u51
status: open
created_at: '2026-02-03T17:03:22.337078'
updated_at: '2026-02-03T17:03:22.337082'
bees_version: '1.1'
---

Context: After extracting _help() to mcp_help.py, update mcp_server.py to import and use the extracted function.

Requirements:
- Add import statement: `from mcp_help import _help`
- Verify tool registration still works: `help = mcp.tool(name="help")(_help)`
- Ensure no broken references to _help in mcp_server.py

Files: src/mcp_server.py

Acceptance Criteria:
- Import statement added at top of file
- Tool registration references imported _help function
- No import errors when module loads
- Help command still accessible via MCP

Parent Task: features.bees-jlu
