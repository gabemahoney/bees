---
id: features.bees-3aa
type: subtask
title: Update docstring for generate_index tool
description: 'Update the docstring for the _generate_index() MCP tool that uses repo_root
  fallback mechanism.


  Context: This tool uses ctx: Context | None = None and may call get_repo_root(ctx).
  Users need to understand when and how to provide repo_root explicitly for MCP clients
  that don''t support the roots protocol.


  Requirements:

  - Update _generate_index() docstring (around line ~2172, check actual location)

  - Verify this function actually uses get_repo_root(ctx) before documenting


  Add to Args section:

  - ctx: FastMCP Context (auto-injected, gets client''s repo root). For MCP clients
  that don''t support roots protocol, this will be None.

  - repo_root: Optional explicit repository root path. Provide this for MCP clients
  that don''t support the roots protocol.


  Add example usage showing both scenarios:

  ```python

  # With roots protocol support (ctx provided automatically)

  await generate_index()


  # Without roots protocol (provide repo_root explicitly)

  await generate_index(repo_root="/path/to/repo")

  ```


  Files: src/mcp_server.py


  Acceptance: _generate_index docstring updated with repo_root parameter documentation
  and usage examples (or skipped if function doesn''t actually need repo_root).'
parent: features.bees-61r
created_at: '2026-02-03T06:58:08.925198'
updated_at: '2026-02-03T13:07:51.730044'
status: completed
bees_version: '1.1'
---

Update the docstring for the _generate_index() MCP tool that uses repo_root fallback mechanism.

Context: This tool uses ctx: Context | None = None and may call get_repo_root(ctx). Users need to understand when and how to provide repo_root explicitly for MCP clients that don't support the roots protocol.

Requirements:
- Update _generate_index() docstring (around line ~2172, check actual location)
- Verify this function actually uses get_repo_root(ctx) before documenting

Add to Args section:
- ctx: FastMCP Context (auto-injected, gets client's repo root). For MCP clients that don't support roots protocol, this will be None.
- repo_root: Optional explicit repository root path. Provide this for MCP clients that don't support the roots protocol.

Add example usage showing both scenarios:
```python
# With roots protocol support (ctx provided automatically)
await generate_index()

# Without roots protocol (provide repo_root explicitly)
await generate_index(repo_root="/path/to/repo")
```

Files: src/mcp_server.py

Acceptance: _generate_index docstring updated with repo_root parameter documentation and usage examples (or skipped if function doesn't actually need repo_root).
