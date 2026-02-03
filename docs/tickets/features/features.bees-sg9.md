---
id: features.bees-sg9
type: subtask
title: Update docstring for colonize_hive_core function
description: 'Update the docstring for the core colonize_hive_core() function that
  uses repo_root fallback mechanism.


  Context: This is the core implementation function (not an MCP tool wrapper) that
  uses ctx: Context | None = None and calls get_repo_root(ctx). Users need to understand
  when and how to provide repo_root explicitly for MCP clients that don''t support
  the roots protocol.


  Requirements:

  - Update colonize_hive_core() docstring (line ~429)


  Add to Args section:

  - ctx: FastMCP Context (auto-injected, gets client''s repo root). For MCP clients
  that don''t support roots protocol, this will be None.

  - repo_root: Optional explicit repository root path. Provide this for MCP clients
  that don''t support the roots protocol.


  Add example usage showing both scenarios:

  ```python

  # With roots protocol support (ctx provided automatically)

  await colonize_hive_core("backend", "/path/to/hive")


  # Without roots protocol (provide repo_root explicitly)

  await colonize_hive_core("backend", "/path/to/hive", repo_root="/path/to/repo")

  ```


  Files: src/mcp_server.py


  Acceptance: colonize_hive_core docstring updated with repo_root parameter documentation
  and usage examples.'
parent: features.bees-61r
status: open
created_at: '2026-02-03T06:58:03.204971'
updated_at: '2026-02-03T06:58:03.204976'
bees_version: '1.1'
---

Update the docstring for the core colonize_hive_core() function that uses repo_root fallback mechanism.

Context: This is the core implementation function (not an MCP tool wrapper) that uses ctx: Context | None = None and calls get_repo_root(ctx). Users need to understand when and how to provide repo_root explicitly for MCP clients that don't support the roots protocol.

Requirements:
- Update colonize_hive_core() docstring (line ~429)

Add to Args section:
- ctx: FastMCP Context (auto-injected, gets client's repo root). For MCP clients that don't support roots protocol, this will be None.
- repo_root: Optional explicit repository root path. Provide this for MCP clients that don't support the roots protocol.

Add example usage showing both scenarios:
```python
# With roots protocol support (ctx provided automatically)
await colonize_hive_core("backend", "/path/to/hive")

# Without roots protocol (provide repo_root explicitly)
await colonize_hive_core("backend", "/path/to/hive", repo_root="/path/to/repo")
```

Files: src/mcp_server.py

Acceptance: colonize_hive_core docstring updated with repo_root parameter documentation and usage examples.
