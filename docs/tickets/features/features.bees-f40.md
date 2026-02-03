---
id: features.bees-f40
type: subtask
title: Update docstrings for execute_query, execute_freeform_query tools
description: 'Update the docstrings for query execution MCP tools that use repo_root
  fallback mechanism.


  Context: These tools use ctx: Context | None = None and call get_repo_root(ctx).
  Users need to understand when and how to provide repo_root explicitly for MCP clients
  that don''t support the roots protocol.


  Requirements:

  - Update _execute_query() docstring (line ~1818)

  - Update _execute_freeform_query() docstring (line ~1904)


  For each function, add to Args section:

  - ctx: FastMCP Context (auto-injected, gets client''s repo root). For MCP clients
  that don''t support roots protocol, this will be None.

  - repo_root: Optional explicit repository root path. Provide this for MCP clients
  that don''t support the roots protocol.


  Add example usage showing both scenarios:

  ```python

  # With roots protocol support (ctx provided automatically)

  await execute_query(query_name="my_query")


  # Without roots protocol (provide repo_root explicitly)

  await execute_query(query_name="my_query", repo_root="/path/to/repo")

  ```


  Files: src/mcp_server.py


  Acceptance: Both docstrings updated with repo_root parameter documentation and usage
  examples.'
parent: features.bees-61r
status: open
created_at: '2026-02-03T06:57:47.475010'
updated_at: '2026-02-03T06:57:47.475013'
bees_version: '1.1'
---

Update the docstrings for query execution MCP tools that use repo_root fallback mechanism.

Context: These tools use ctx: Context | None = None and call get_repo_root(ctx). Users need to understand when and how to provide repo_root explicitly for MCP clients that don't support the roots protocol.

Requirements:
- Update _execute_query() docstring (line ~1818)
- Update _execute_freeform_query() docstring (line ~1904)

For each function, add to Args section:
- ctx: FastMCP Context (auto-injected, gets client's repo root). For MCP clients that don't support roots protocol, this will be None.
- repo_root: Optional explicit repository root path. Provide this for MCP clients that don't support the roots protocol.

Add example usage showing both scenarios:
```python
# With roots protocol support (ctx provided automatically)
await execute_query(query_name="my_query")

# Without roots protocol (provide repo_root explicitly)
await execute_query(query_name="my_query", repo_root="/path/to/repo")
```

Files: src/mcp_server.py

Acceptance: Both docstrings updated with repo_root parameter documentation and usage examples.
