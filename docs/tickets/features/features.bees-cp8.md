---
id: features.bees-cp8
type: subtask
title: Update docstrings for show_ticket, colonize_hive, list_hives tools
description: 'Update the docstrings for ticket viewing and hive management MCP tools
  that use repo_root fallback mechanism.


  Context: These tools use ctx: Context | None = None and call get_repo_root(ctx).
  Users need to understand when and how to provide repo_root explicitly for MCP clients
  that don''t support the roots protocol.


  Requirements:

  - Update _show_ticket() docstring (line ~2001)

  - Update _colonize_hive() docstring (line ~2175)

  - Update _list_hives() docstring (line ~2262)


  For each function, add to Args section:

  - ctx: FastMCP Context (auto-injected, gets client''s repo root). For MCP clients
  that don''t support roots protocol, this will be None.

  - repo_root: Optional explicit repository root path. Provide this for MCP clients
  that don''t support the roots protocol.


  Add example usage showing both scenarios:

  ```python

  # With roots protocol support (ctx provided automatically)

  await show_ticket("features.bees-abc")


  # Without roots protocol (provide repo_root explicitly)

  await show_ticket("features.bees-abc", repo_root="/path/to/repo")

  ```


  Files: src/mcp_server.py


  Acceptance: All three docstrings updated with repo_root parameter documentation
  and usage examples.'
parent: features.bees-61r
status: open
created_at: '2026-02-03T06:57:52.648028'
updated_at: '2026-02-03T06:57:52.648036'
bees_version: '1.1'
---

Update the docstrings for ticket viewing and hive management MCP tools that use repo_root fallback mechanism.

Context: These tools use ctx: Context | None = None and call get_repo_root(ctx). Users need to understand when and how to provide repo_root explicitly for MCP clients that don't support the roots protocol.

Requirements:
- Update _show_ticket() docstring (line ~2001)
- Update _colonize_hive() docstring (line ~2175)
- Update _list_hives() docstring (line ~2262)

For each function, add to Args section:
- ctx: FastMCP Context (auto-injected, gets client's repo root). For MCP clients that don't support roots protocol, this will be None.
- repo_root: Optional explicit repository root path. Provide this for MCP clients that don't support the roots protocol.

Add example usage showing both scenarios:
```python
# With roots protocol support (ctx provided automatically)
await show_ticket("features.bees-abc")

# Without roots protocol (provide repo_root explicitly)
await show_ticket("features.bees-abc", repo_root="/path/to/repo")
```

Files: src/mcp_server.py

Acceptance: All three docstrings updated with repo_root parameter documentation and usage examples.
