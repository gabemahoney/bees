---
id: features.bees-zyt
type: subtask
title: Update docstrings for abandon_hive, rename_hive, sanitize_hive tools
description: 'Update the docstrings for remaining hive management MCP tools that use
  repo_root fallback mechanism.


  Context: These tools use ctx: Context | None = None and call get_repo_root(ctx).
  Users need to understand when and how to provide repo_root explicitly for MCP clients
  that don''t support the roots protocol.


  Requirements:

  - Update _abandon_hive() docstring (line ~2351)

  - Update _rename_hive() docstring (line ~2438)

  - Update _sanitize_hive() docstring (line ~2842)


  For each function, add to Args section:

  - ctx: FastMCP Context (auto-injected, gets client''s repo root). For MCP clients
  that don''t support roots protocol, this will be None.

  - repo_root: Optional explicit repository root path. Provide this for MCP clients
  that don''t support the roots protocol.


  Add example usage showing both scenarios:

  ```python

  # With roots protocol support (ctx provided automatically)

  await abandon_hive("backend")


  # Without roots protocol (provide repo_root explicitly)

  await abandon_hive("backend", repo_root="/path/to/repo")

  ```


  Files: src/mcp_server.py


  Acceptance: All three docstrings updated with repo_root parameter documentation
  and usage examples.'
parent: features.bees-61r
status: open
created_at: '2026-02-03T06:57:57.527372'
updated_at: '2026-02-03T06:57:57.527377'
bees_version: '1.1'
---

Update the docstrings for remaining hive management MCP tools that use repo_root fallback mechanism.

Context: These tools use ctx: Context | None = None and call get_repo_root(ctx). Users need to understand when and how to provide repo_root explicitly for MCP clients that don't support the roots protocol.

Requirements:
- Update _abandon_hive() docstring (line ~2351)
- Update _rename_hive() docstring (line ~2438)
- Update _sanitize_hive() docstring (line ~2842)

For each function, add to Args section:
- ctx: FastMCP Context (auto-injected, gets client's repo root). For MCP clients that don't support roots protocol, this will be None.
- repo_root: Optional explicit repository root path. Provide this for MCP clients that don't support the roots protocol.

Add example usage showing both scenarios:
```python
# With roots protocol support (ctx provided automatically)
await abandon_hive("backend")

# Without roots protocol (provide repo_root explicitly)
await abandon_hive("backend", repo_root="/path/to/repo")
```

Files: src/mcp_server.py

Acceptance: All three docstrings updated with repo_root parameter documentation and usage examples.
