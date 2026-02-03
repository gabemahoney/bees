---
id: features.bees-00q
type: subtask
title: Update src/mcp_server.py to import from mcp_repo_utils
description: 'Context: After extracting functions to mcp_repo_utils.py, update mcp_server.py
  to import them.


  What to Modify:

  - File: src/mcp_server.py

  - Remove lines 124-253 (the three extracted functions)

  - Add import statement: `from .mcp_repo_utils import get_repo_root_from_path, get_client_repo_root,
  get_repo_root`

  - Verify all usages of these functions still work


  Requirements:

  - Import all three functions

  - Remove duplicate function definitions

  - Ensure no broken references

  - Keep all MCP tool functions working


  Success Criteria:

  - Import statement added to mcp_server.py

  - Original function definitions removed

  - No syntax errors

  - All MCP tools can still call these functions'
parent: features.bees-alr
status: open
created_at: '2026-02-03T17:03:05.319443'
updated_at: '2026-02-03T17:03:05.319446'
bees_version: '1.1'
---

Context: After extracting functions to mcp_repo_utils.py, update mcp_server.py to import them.

What to Modify:
- File: src/mcp_server.py
- Remove lines 124-253 (the three extracted functions)
- Add import statement: `from .mcp_repo_utils import get_repo_root_from_path, get_client_repo_root, get_repo_root`
- Verify all usages of these functions still work

Requirements:
- Import all three functions
- Remove duplicate function definitions
- Ensure no broken references
- Keep all MCP tool functions working

Success Criteria:
- Import statement added to mcp_server.py
- Original function definitions removed
- No syntax errors
- All MCP tools can still call these functions
