---
id: features.bees-6sr
type: subtask
title: Update docstrings for create_ticket, update_ticket, delete_ticket tools
description: "Update the docstrings for the first three MCP tools that use repo_root\
  \ fallback mechanism.\n\nContext: These tools use ctx: Context | None = None and\
  \ call get_repo_root(ctx). Users need to understand when and how to provide repo_root\
  \ explicitly for MCP clients that don't support the roots protocol.\n\nRequirements:\n\
  - Update _create_ticket() docstring (line ~1087)\n- Update _update_ticket() docstring\
  \ (line ~1398)  \n- Update _delete_ticket() docstring (line ~1639)\n\nFor each function,\
  \ add to Args section:\n- ctx: FastMCP Context (auto-injected, gets client's repo\
  \ root). For MCP clients that don't support roots protocol, this will be None.\n\
  - repo_root: Optional explicit repository root path. Provide this for MCP clients\
  \ that don't support the roots protocol.\n\nAdd example usage showing both scenarios:\n\
  ```python\n# With roots protocol support (ctx provided automatically)\nawait create_ticket(...)\n\
  \n# Without roots protocol (provide repo_root explicitly)  \nawait create_ticket(...,\
  \ repo_root=\"/path/to/repo\")\n```\n\nFiles: src/mcp_server.py\n\nAcceptance: All\
  \ three docstrings updated with repo_root parameter documentation and usage examples."
down_dependencies:
- features.bees-9nv
- features.bees-17q
- features.bees-uj5
parent: features.bees-61r
created_at: '2026-02-03T06:57:42.014733'
updated_at: '2026-02-03T13:05:15.110370'
status: completed
bees_version: '1.1'
---

Update the docstrings for the first three MCP tools that use repo_root fallback mechanism.

Context: These tools use ctx: Context | None = None and call get_repo_root(ctx). Users need to understand when and how to provide repo_root explicitly for MCP clients that don't support the roots protocol.

Requirements:
- Update _create_ticket() docstring (line ~1087)
- Update _update_ticket() docstring (line ~1398)  
- Update _delete_ticket() docstring (line ~1639)

For each function, add to Args section:
- ctx: FastMCP Context (auto-injected, gets client's repo root). For MCP clients that don't support roots protocol, this will be None.
- repo_root: Optional explicit repository root path. Provide this for MCP clients that don't support the roots protocol.

Add example usage showing both scenarios:
```python
# With roots protocol support (ctx provided automatically)
await create_ticket(...)

# Without roots protocol (provide repo_root explicitly)  
await create_ticket(..., repo_root="/path/to/repo")
```

Files: src/mcp_server.py

Acceptance: All three docstrings updated with repo_root parameter documentation and usage examples.
